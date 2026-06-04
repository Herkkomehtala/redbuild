import os
import uuid
import math
import random
import png

def chunk_bytecode_to_pngs(bytecode, temp_files_to_clean, max_dim=256):
    """Split bytecode into multiple PNG files and return their paths."""
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
        
        for i in range(chunk_pixels):
            pixel_offset = i * 4
            for j in range(4):
                if offset < total_bytes:
                    rgba_data[pixel_offset + j] = bytecode[offset]
                    offset += 1
                else:
                    rgba_data[pixel_offset + j] = random.randint(0, 255)
        
        # pypng needs a list of rows. We must
        # convert our flat byte array into a list of rows.
        bytes_per_row = width * 4
        rows = []
        for i in range(height):
            start = i * bytes_per_row
            end = start + bytes_per_row
            rows.append(rgba_data[start:end])
            
        temp_png_filename = f"{uuid.uuid4()}.png"
        temp_png_filepath = os.path.join('/tmp/uploads', temp_png_filename)
        
        try:
            with open(temp_png_filepath, 'wb') as f:
                # Create a pypng writer with our specs
                writer = png.Writer(
                    width=width, 
                    height=height, 
                    greyscale=False,  # We are using color
                    alpha=True,       # We need the alpha channel (RGBA)
                    bitdepth=8,
                )
                
                writer.write(f, rows)
                
            png_files.append(temp_png_filename)
            temp_files_to_clean.append(temp_png_filepath)
            
        except Exception as e:
            print(f"ERROR: Failed to write PNG with pypng: {e}")
            raise
            
        remaining_pixels -= chunk_pixels
    
    return png_files
