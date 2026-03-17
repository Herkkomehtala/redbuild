import logging
import json
from flask import request, jsonify, current_app
from . import bp
from . import services
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# --- METRICS DEFINITIONS ---
JOBS_STARTED_TOTAL = meter.create_counter(
    "redbuild.jobs.started_total",
    description="Total number of processing jobs started"
)

JOB_STATUS_CHECKS_TOTAL = meter.create_counter(
    "redbuild.job.status_checks_total",
    description="Total number of job status checks"
)

FILE_DOWNLOADS_TOTAL = meter.create_counter(
    "redbuild.file.downloads_total",
    description="Total number of files downloaded"
)


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

        job_name = services.start_generator_job(
            file_storage, original_filename, generator_type, json.dumps(options), task_id=request.task_id
        )
        JOBS_STARTED_TOTAL.add(1, {"generator_type": generator_type})
        return jsonify({"task_id": job_name}), 202
        
    except Exception as e:
        current_app.logger.error(f"Error starting job: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@bp.route('/status/<job_name>', methods=['GET'])
def get_status(job_name):
    JOB_STATUS_CHECKS_TOTAL.add(1)
    status_data = services.check_job_status(job_name)
    status_code = 404 if status_data.get('state') == 'NOT_FOUND' else 200
    return jsonify(status_data), status_code

@bp.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    FILE_DOWNLOADS_TOTAL.add(1)
    return services.download_result_file(filename)

