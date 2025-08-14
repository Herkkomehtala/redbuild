import base64
import os
import uuid

def encode(input_filepath, original_filename):
    """
    Encodes the content of a file into Base85 and writes it to a new file.

    Args:
        input_filepath (str): The absolute path to the input file for this stage.
        original_filename (str): The original name of the user's uploaded file.

    Returns:
        str: The absolute path to the new, temporary output file for the next stage.
    """
    print("INFO: Running Base85 encoding...")
    
    with open(input_filepath, "rb") as f_in:
        file_content_bytes = f_in.read()
    
    encoded_data = base64.b85encode(file_content_bytes)
    
    output_filename = f"{uuid.uuid4()}.tmp"
    output_filepath = os.path.join('/tmp/uploads', output_filename)
    
    with open(output_filepath, "wb") as f_out:
        f_out.write(encoded_data)
        
    return output_filepath

