import argparse
import importlib
import os
import sys
import json
import uuid

def run_stage(generator_type, stage_name, module_name, input_filepath, original_filename):
    """
    Helper to run a single stage of a multi-stage generator (like transformer).
    It passes file paths and expects a file path in return.
    """
    if not module_name:
        return input_filepath

    print(f"INFO: Running stage '{stage_name}' with module '{module_name}'...")
    try:
        module_path = f"app.generators.{generator_type}.{stage_name}.{module_name}"
        processing_module = importlib.import_module(module_path)
        
        output_filepath = processing_module.encode(input_filepath, original_filename)
        
        if input_filepath != args.input_file:
            os.remove(input_filepath)
            
        return output_filepath
    except Exception as e:
        print(f"ERROR: Failed during stage '{stage_name}'. Reason: {e}", file=sys.stderr)
        raise

def run_simple_module(generator_type, module_name, input_filepath, original_filename):
    """
    Helper for simple, single-module generators (like compiler).
    """
    print(f"INFO: Running simple generator '{module_name}'...")
    try:
        module_path = f"app.generators.{generator_type}.{module_name}"
        processing_module = importlib.import_module(module_path)
        
        final_artifact_name = processing_module.encode(input_filepath, original_filename)
        
        return final_artifact_name
    except Exception as e:
        print(f"ERROR: Failed during simple generator '{module_name}'. Reason: {e}", file=sys.stderr)
        raise

def main():
    parser = argparse.ArgumentParser(description="A smart worker for hierarchical file processing.")
    parser.add_argument('--input-file', required=True)
    parser.add_argument('--original-filename', required=True)
    parser.add_argument('--generator-type', required=True)
    parser.add_argument('--options', required=True, help='A JSON string of selected options.')
    
    global args
    args = parser.parse_args()
    job_name = os.environ.get("JOB_NAME")
    options = json.loads(args.options)

    try:
        print(f"INFO: Starting job {job_name} for generator '{args.generator_type}' with options: {options}")
        
        current_filepath = args.input_file
        final_filename = ""

        if 'module' in options:
            final_filename = run_simple_module(args.generator_type, options['module'], current_filepath, args.original_filename)
        else:
            current_filepath = run_stage(args.generator_type, 'encoding', options.get('encoding'), current_filepath, args.original_filename)
            current_filepath = run_stage(args.generator_type, 'compression', options.get('compression'), current_filepath, args.original_filename)
            final_filename = os.path.basename(current_filepath)

        result_filepath = os.path.join('/tmp/uploads', f"{job_name}.result")
        with open(result_filepath, 'w') as f_result:
            f_result.write(final_filename)

        print(f"SUCCESS: Job complete. Final artifact: {final_filename}")

    except Exception as e:
        print(f"ERROR: Job failed. Reason: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
