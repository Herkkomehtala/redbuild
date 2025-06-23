from flask import request, jsonify
from . import bp  # Import the blueprint
from . import services

@bp.route('/generators', methods=['GET'])
def get_generators():
    """
    Dynamic endpoint that discovers and returns all available
    generator types and their options (e.g., {"compiler": [...], "transformer": [...]} ).
    The frontend will use this to build its UI dynamically.
    """
    try:
        available_generators = services.discover_generators()
        return jsonify(available_generators)
    except Exception as e:
        # Log the exception here if needed
        return jsonify({"error": "Could not discover generators."}), 500


@bp.route('/generate', methods=['POST'])
def generate_file():
    """
    Generic endpoint to start any kind of job. It expects the frontend
    to send the generator_type and generator_name along with the file.
    """
    form_data = request.form
    if 'file' not in request.files or 'generator_type' not in form_data or 'generator_name' not in form_data:
        return jsonify({"error": "Missing file or generator selection."}), 400

    try:
        # Delegate the entire job creation process to the service layer.
        job_name = services.start_generator_job(
            generator_type=form_data['generator_type'],
            generator_name=form_data['generator_name'],
            file_storage=request.files['file'],
            original_filename=form_data.get('original_filename', 'unknown_file')
        )
        # The frontend receives a task_id to poll for status.
        return jsonify({"task_id": job_name}), 202
    except Exception as e:
        # The service layer might raise an exception if something goes wrong.
        return jsonify({"error": str(e)}), 500

@bp.route('/status/<job_name>', methods=['GET'])
def get_status(job_name):
    """
    This just passes the job_name to the service layer and returns the result.
    """
    status_data = services.check_job_status(job_name)
    status_code = 404 if status_data.get('state') == 'NOT_FOUND' else 200
    return jsonify(status_data), status_code


@bp.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """
    Serves the file that the service layer and worker pods have placed on the shared volume. pls dont check for lfi :D
    """
    return services.download_result_file(filename)
