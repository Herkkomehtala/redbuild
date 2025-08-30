import logging
import json
from flask import request, jsonify, current_app
from . import bp
from . import services

@bp.route('/options', methods=['GET'])
def get_options():
    """
    Discovers and returns all available hierarchical generator options.
    This now calls the correct service function.
    """
    try:
        options = services.discover_generators()
        return jsonify(options)
    except Exception as e:
        current_app.logger.error(f"Error in discover_generators: {e}", exc_info=True)
        return jsonify({"error": "Could not discover processing options."}), 500

@bp.route('/process', methods=['POST'])
def process_file():
    """
    Starts a processing job.
    """
    if 'generator_type' not in request.form or 'options' not in request.form:
        return jsonify({"error": "Missing generator type or options."}), 400

    try:
        generator_type = request.form['generator_type']
        options = json.loads(request.form['options'])
        file_storage = request.files.get('file')
        original_filename = request.form.get('original_filename', 'untitled')

        data_source = options.get('data_source', 'embedded')
        is_file_required = (generator_type == 'transformer') or \
                           (generator_type == 'compiler' and data_source == 'embedded')

        if is_file_required and not file_storage:
            return jsonify({"error": "A file is required for the selected options."}), 400

        task_id = services.start_generator_job(
            file_storage, original_filename, generator_type, json.dumps(options)
        )
        return jsonify({"task_id": task_id}), 202
        
    except Exception as e:
        current_app.logger.error(f"Error starting job: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- Status and Download endpoints remain the same ---
@bp.route('/status/<job_name>', methods=['GET'])
def get_status(job_name):
    status_data = services.check_job_status(job_name)
    status_code = 404 if status_data.get('state') == 'NOT_FOUND' else 200
    return jsonify(status_data), status_code

@bp.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return services.download_result_file(filename)

