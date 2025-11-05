import os
import uuid
import math
import random
from PIL import Image

def chunk_bytecode_to_pngs(bytecode, temp_files_to_clean, max_dim=48):
    """Split bytecode into multiple PNG files and return their paths."""
    # Calculate number of 4-byte pixels needed (RGBA = 4 bytes per pixel)
    total_bytes = len(bytecode)
    remaining_pixels = (total_bytes + 3) // 4
    
    png_files = []
    offset = 0
    
    while remaining_pixels > 0:
        sqrt_val = math.sqrt(remaining_pixels)
        
        if sqrt_val > max_dim:
            width = height = max_dim
        elif sqrt_val > 4.0:
            dimension = int(math.floor(sqrt_val))
            width = dimension
            height = dimension
        else:
            width = remaining_pixels
            height = 1
        
        chunk_pixels = width * height
        chunk_bytes = chunk_pixels * 4
        
        rgba_data = bytearray(chunk_bytes)
        
        # Fill with bytecode data, padding with random bytes if needed
        for i in range(chunk_pixels):
            pixel_offset = i * 4
            for j in range(4):
                if offset < total_bytes:
                    rgba_data[pixel_offset + j] = bytecode[offset]
                    offset += 1
                else:
                    # Pad with random bytes
                    rgba_data[pixel_offset + j] = random.randint(0, 255)
        
        # Create PNG image
        img = Image.frombytes('RGBA', (width, height), bytes(rgba_data))
        
        # Save to temporary file
        temp_png_filename = f"{uuid.uuid4()}.png"
        temp_png_filepath = os.path.join('/tmp/uploads', temp_png_filename)
        img.save(temp_png_filepath, 'PNG')
        
        png_files.append(temp_png_filename)
        temp_files_to_clean.append(temp_png_filepath)
        
        # Update remaining pixels
        remaining_pixels -= chunk_pixels
    
    return png_files
