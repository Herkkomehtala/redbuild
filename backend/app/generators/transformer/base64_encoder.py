import base64
import os
import uuid
import re

def encode(file_content_bytes: bytes, original_filename: str) -> str:
    """
    Performs Base64 encoding on byte content and saves it to a unique file.
    """
    output_dir = '/tmp/uploads'
    os.makedirs(output_dir, exist_ok=True)
    encoded_content = base64.b64encode(file_content_bytes)
    base_name, _ = os.path.splitext(original_filename)
    safe_base_name = re.sub(r'[^a-zA-Z0-9._-]', '', base_name)

    output_filename = f"{safe_base_name}_{uuid.uuid4()}.b64"
    output_filepath = os.path.join(output_dir, output_filename)

    with open(output_filepath, 'wb') as f_out:
        f_out.write(encoded_content)
        
    return output_filename
