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
    Starts a processing job based on a selected generator type and its options,
    which are passed as a JSON string.
    """
    form_data = request.form
    if 'file' not in request.files or 'generator_type' not in form_data or 'options' not in form_data:
        return jsonify({"error": "Missing file, generator type, or options."}), 400

    try:
        job_name = services.start_generator_job(
            file_storage=request.files['file'],
            original_filename=form_data.get('original_filename', 'unknown_file'),
            generator_type=form_data['generator_type'],
            options_json=form_data['options']
        )
        return jsonify({"task_id": job_name}), 202
    except Exception as e:
        current_app.logger.error(f"Error starting generator job: {e}", exc_info=True)
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

