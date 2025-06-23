import argparse
import importlib
import os
import sys

def main():
    """
    This is a generic entrypoint for our Kubernetes Job pods.
    It dynamically loads and runs a specific generator based on command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Run a generator module.")
    parser.add_argument('--generator-type', required=True, help="The type of generator (e.g., 'transformer', 'compiler').")
    parser.add_argument('--generator-name', required=True, help="The specific generator module to run (e.g., 'base64_encoder').")
    parser.add_argument('--input-file', required=True, help="Path to the input file on the shared volume.")
    parser.add_argument('--original-filename', required=True, help="The original name of the uploaded file.")

    args = parser.parse_args()

    # The JOB_NAME is passed as an environment variable from the services.py
    job_name = os.environ.get("JOB_NAME")
    if not job_name:
        print("ERROR: Job failed. Reason: JOB_NAME environment variable not set.")
        sys.exit(1)

    print(f"INFO: Starting job {job_name} for generator '{args.generator_type}/{args.generator_name}'")

    try:
        # Dynamically construct the module path from the arguments.
        # e.g., "generators.compiler.win_c_embedder"
        module_path = f"app.generators.{args.generator_type}.{args.generator_name}"

        print(f"INFO: Importing module: {module_path}")
        generator_module = importlib.import_module(module_path)

        # Read the content of the input file provided by the API server.
        print(f"INFO: Reading input file: {args.input_file}")
        with open(args.input_file, 'rb') as f_in:
            file_content_bytes = f_in.read()

        # Call the 'encode' function within the loaded generator module.
        output_artifact_name = generator_module.encode(file_content_bytes, args.original_filename)

        # The 'result' file's content is the name of the final downloadable artifact.
        # The API server reads this file to know what to serve on the /download endpoint.
        result_filepath = os.path.join('/tmp/uploads', f"{job_name}.result")
        with open(result_filepath, 'w') as f_result:
            f_result.write(output_artifact_name)

        print(f"SUCCESS: Transformation complete. Final artifact: {output_artifact_name}")

    except Exception as e:
        # If any step fails, print the error and exit with a non-zero code.
        # The API server will see the Job has failed and retrieve this error from the pod logs.
        print(f"ERROR: Job failed. Reason: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
