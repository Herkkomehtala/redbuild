import zlib
import os
import sys
import struct
import binascii
import uuid

# --- Constants for the MSZIP format ---
HEADER_FORMAT = "<6BBBQQ"
CHUNK_HEADER_FORMAT = "<IH"
CHUNK_SIGNATURE = 0x4B43
MAX_CHUNK_SIZE = 2**15
MAGIC_BYTES = [10, 81, 229, 192, 24, 0]
ALGORITHM_ID = 2

def encode(input_filepath, original_filename):
    """
    Compresses the content of a file using the MSZIP format, which is
    natively decompressible on Windows.

    Args:
        input_filepath (str): The absolute path to the input file for this stage.
        original_filename (str): The original name of the user's uploaded file.

    Returns:
        str: The absolute path to the new, temporary output file for the next stage.
    """
    print("INFO: Compressing data using the official MSZIP format")
    
    try:
        with open(input_filepath, "rb") as f_in:
            decompressed_data = f_in.read()
        
        decompressed_length = len(decompressed_data)
        first_chunk_decompressed_length = min(decompressed_length, MAX_CHUNK_SIZE)

        header_no_crc = struct.pack(
            HEADER_FORMAT, *MAGIC_BYTES, 0, ALGORITHM_ID,
            decompressed_length, first_chunk_decompressed_length
        )
        
        actual_crc = (
            binascii.crc32(header_no_crc[7:24], binascii.crc32(header_no_crc[:6])) & 0xFF
        )
        
        final_header = struct.pack(
            HEADER_FORMAT, *MAGIC_BYTES, actual_crc, ALGORITHM_ID,
            decompressed_length, first_chunk_decompressed_length
        )
        
        compressed_stream = bytearray(final_header)
        current_zdict = bytearray()
        
        data_to_process = decompressed_data
        while data_to_process:
            chunk = data_to_process[:MAX_CHUNK_SIZE]
            data_to_process = data_to_process[MAX_CHUNK_SIZE:]

            compressor = zlib.compressobj(
                level=9, method=zlib.DEFLATED, wbits=-zlib.MAX_WBITS,
                zdict=current_zdict, memLevel=9
            )

            chunk_compressed = compressor.compress(chunk) + compressor.flush()
            
            chunk_size_with_signature = len(chunk_compressed) + 2
            
            compressed_stream.extend(struct.pack(CHUNK_HEADER_FORMAT, chunk_size_with_signature, CHUNK_SIGNATURE))
            compressed_stream.extend(chunk_compressed)

            current_zdict.extend(chunk)
            
        output_filename = f"{uuid.uuid4()}.tmp"
        output_filepath = os.path.join('/tmp/uploads', output_filename)
        
        with open(output_filepath, "wb") as f:
            f.write(compressed_stream)

        print(f"INFO: Successfully compressed data to {output_filename}")
        
        return output_filepath
        
    except Exception as e:
        print(f"ERROR: Compression failed. Reason: {e}", file=sys.stderr)
        raise

