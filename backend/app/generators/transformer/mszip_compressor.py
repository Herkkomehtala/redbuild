import zlib
import os
import sys
import struct
import binascii

# --- Constants based on the pymszip library and MSZIP format ---

# The format string for the main 24-byte MSZIP header.
HEADER_FORMAT = "<6BBBQQ"

# The format string for the header of each compressed data chunk.
CHUNK_HEADER_FORMAT = "<IH"

# The 2-byte signature 'CK' (as a little-endian short) that follows the chunk header.
CHUNK_SIGNATURE = 0x4B43

# The maximum size of an uncompressed data chunk.
MAX_CHUNK_SIZE = 2**15

# The 6 magic bytes required at the start of the MSZIP header.
MAGIC_BYTES = [10, 81, 229, 192, 24, 0]

# The algorithm identifier for MSZIP.
ALGORITHM_ID = 2


# --- Generator Interface Implementation ---
def encode(file_content_bytes, original_filename):
    """
    This is the standard entry point called by a job runner.
    It compresses the input data using the correct MSZIP format, which is
    natively decompressible on Windows.

    Args:
        file_content_bytes (bytes): The raw data from the uploaded file.
        original_filename (str): The original name of the file.

    Returns:
        str: The name of the final compressed output file.
    """
    print("INFO: Compressing data using the official MSZIP format...")
    
    try:
        decompressed_data = file_content_bytes
        decompressed_length = len(decompressed_data)
        
        # The size of the first chunk is the smaller of the total size or the max chunk size.
        first_chunk_decompressed_length = min(decompressed_length, MAX_CHUNK_SIZE)

        # 1. Prepare the main 24-byte header without the CRC checksum first.
        header_no_crc = struct.pack(
            HEADER_FORMAT,
            *MAGIC_BYTES,
            0,  # Placeholder for CRC
            ALGORITHM_ID,
            decompressed_length,
            first_chunk_decompressed_length,
        )
        
        # 2. Calculate the CRC based on the header content, as specified by the format.
        # This mimics the calculation done by Cabinet.dll.
        actual_crc = (
            binascii.crc32(header_no_crc[7:24], binascii.crc32(header_no_crc[:6])) & 0xFF
        )
        
        # 3. Create the final header with the correct CRC.
        final_header = struct.pack(
            HEADER_FORMAT,
            *MAGIC_BYTES,
            actual_crc,
            ALGORITHM_ID,
            decompressed_length,
            first_chunk_decompressed_length,
        )
        
        compressed_stream = bytearray(final_header)
        
        # This dictionary will be used to maintain compression history across chunks.
        current_zdict = bytearray()
        
        # 4. Process the data in 32KB chunks.
        while decompressed_data:
            chunk = decompressed_data[:MAX_CHUNK_SIZE]
            decompressed_data = decompressed_data[MAX_CHUNK_SIZE:]

            # The zdict parameter is crucial. It uses the previously decompressed
            # data as a "dictionary" to compress the current chunk, which is
            # required for compatibility with the Windows API.
            compressor = zlib.compressobj(
                level=9, # Per pymszip, level 9 is recommended.
                method=zlib.DEFLATED,
                wbits=-zlib.MAX_WBITS,
                zdict=current_zdict,
                memLevel=9,  # This is required for Windows API compatibility.
            )

            chunk_compressed = compressor.compress(chunk) + compressor.flush()
            
            # The chunk size includes the 2 bytes for the 'CK' signature.
            chunk_size_with_signature = len(chunk_compressed) + 2
            
            # Write the per-chunk header and signature.
            compressed_stream.extend(struct.pack(CHUNK_HEADER_FORMAT, chunk_size_with_signature, CHUNK_SIGNATURE))
            
            # Write the compressed data for this chunk.
            compressed_stream.extend(chunk_compressed)

            # Update the dictionary with the uncompressed data from the chunk we just processed.
            current_zdict.extend(chunk)
            
        # 5. Define the output filename and path.
        base_name, _ = os.path.splitext(original_filename)
        output_filename = f"{base_name}.mszip"
        output_filepath = os.path.join('/tmp/uploads', output_filename)
        
        # 6. Write the complete compressed stream to the output file.
        with open(output_filepath, "wb") as f:
            f.write(compressed_stream)

        # 7. Log the results.
        total_file_size = len(compressed_stream)
        ratio = total_file_size / decompressed_length * 100 if decompressed_length > 0 else 0
        
        print(f"INFO: Successfully compressed data.")
        print(f"      Original Size: {decompressed_length} bytes")
        print(f"      Total File Size: {total_file_size} bytes (Ratio: {ratio:.2f}%)")
        
        # 8. Return the filename of the final artifact.
        return output_filename
        
    except Exception as e:
        print(f"ERROR: Compression failed. Reason: {e}", file=sys.stderr)
        raise

