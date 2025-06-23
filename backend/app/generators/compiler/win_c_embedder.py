import os
import subprocess

# This C code template will be populated with the bytecode.
C_SOURCE_TEMPLATE = """
#include <stdio.h>
#include <stdlib.h>

// Bytecode from the input file is injected here.
unsigned char bytecode[] = {{{byte_array_str}}};
unsigned int bytecode_len = sizeof(bytecode);

// This is the main function of the final Windows executable.
// It simply writes the embedded bytecode to a file.
int main() {{
    const char* filename = "{output_filename}";
    FILE *fp = fopen(filename, "wb");
    if (fp == NULL) {{
        return 1; // Exit with an error code if file creation fails.
    }}
    fwrite(bytecode, 1, bytecode_len, fp);
    fclose(fp);
    return 0; // Success
}}
"""

def encode(file_content_bytes, original_filename):
    """
    Embeds bytecode into a C source file and cross-compiles it into a
    Windows PE32+ executable.
    The final artifact of this generator is the compiled .exe file itself.
    """
    # 1. Prepare data for the C template
    byte_array_string = ", ".join([f"0x{byte:02x}" for byte in file_content_bytes])
    base_name, _ = os.path.splitext(original_filename)
    final_output_filename = f"{base_name}.embedded"

    c_source_code = C_SOURCE_TEMPLATE.format(
        byte_array_str=byte_array_string,
        output_filename=final_output_filename
    )

    # 2. Write the C source to a temporary file in the pod
    c_source_filename = "temp_builder.c"
    with open(c_source_filename, "w") as f:
        f.write(c_source_code)

    # 3. Cross-compile for Windows using the MinGW-w64 toolchain
    compiled_binary_name = f"{base_name}.exe"
    # This is the command for the 64-bit Windows cross-compiler
    compiler_command = ["x86_64-w64-mingw32-gcc", c_source_filename, "-o", compiled_binary_name]
    
    print(f"Cross-compiling {c_source_filename} for Windows...")
    try:
        subprocess.run(compiler_command, check=True, capture_output=True, text=True)
        print(f"Compilation successful. Output: {compiled_binary_name}")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Cross-compilation failed. Stderr: {e.stderr}")
        raise Exception(f"C cross-compilation failed: {e.stderr}")

    # 4. Return the name of the compiled executable, which is our final artifact.
    return compiled_binary_name

