import os
import uuid
import glob
import time
import logging
from flask import send_from_directory
from ..k8s_client import batch_v1, core_v1, NAMESPACE
from kubernetes.client import (
    ApiException, V1Container, V1VolumeMount, V1EnvVar, V1PodTemplateSpec,
    V1ObjectMeta, V1PodSpec, V1Volume, V1PersistentVolumeClaimVolumeSource,
    V1Job, V1JobSpec
)

# --- Configuration ---
SHARED_VOLUME_PATH = '/tmp/uploads'

# This mapping is the key to using specialized worker images.
# It links a 'generator_type' directory to a specific Docker image.
GENERATOR_IMAGE_MAP = {
    "transformer": "redbuild-backend",
    "compiler": "win-c-compiler-worker",
    # As you add new types, you add their image names here.
}

# --- Service Functions (The Core Logic) ---
def discover_generators():
    """
    Dynamically discovers all generator types and their available options.
    """
    generators = {}
    
    app_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_path = os.path.join(app_root_path, 'generators')
    
    if not os.path.isdir(base_path):
        logging.warning(f"Generator directory not found at: {base_path}")
        return {}

    for gen_type in os.listdir(base_path):
        type_path = os.path.join(base_path, gen_type)
        if os.path.isdir(type_path) and not gen_type.startswith('__'):
            options = []
            for f_path in glob.glob(os.path.join(type_path, '*.py')):
                if '__init__' in f_path:
                    continue
                module_name = os.path.basename(f_path).replace('.py', '')
                display_name = module_name.replace('_', ' ').title()
                options.append({'value': module_name, 'text': display_name})
            if options:
                generators[gen_type] = options
    
    logging.info(f"Discovered generators: {generators}")
    return generators

def start_generator_job(generator_type, generator_name, file_storage, original_filename):
    """
    A generic function to start any type of generator job. It saves the
    uploaded file and creates a Kubernetes Job with the correct image and command.
    """
    input_filename = f"{uuid.uuid4()}"
    file_storage.save(os.path.join(SHARED_VOLUME_PATH, input_filename))

    job_name = f"{generator_type}-{generator_name.replace('_', '-')}-{uuid.uuid4().hex[:6]}"
    job_body = _build_job_object(job_name, generator_type, generator_name, input_filename, original_filename)

    logging.info(f"Creating job '{job_name}' in namespace '{NAMESPACE}'...")
    batch_v1.create_namespaced_job(body=job_body, namespace=NAMESPACE)
    logging.info(f"Successfully created job '{job_name}'.")
    return job_name


def check_job_status(job_name):
    """
    Checks the status of a given job and returns a structured response.
    This logic remains the same regardless of the job type.
    """
    try:
        job = batch_v1.read_namespaced_job_status(name=job_name, namespace=NAMESPACE)
        status = job.status
    except ApiException as e:
        if e.status == 404:
            return {"state": "NOT_FOUND", "error": "Job not found."}
        logging.error(f"API Error checking status for {job_name}: {e.reason}")
        return {"state": "UNKNOWN", "error": f"API Error: {e.reason}"}

    if status.succeeded:
        result_filepath = os.path.join(SHARED_VOLUME_PATH, f"{job_name}.result")
        time.sleep(0.5) # Give a moment for PVC to sync
        if os.path.exists(result_filepath):
            with open(result_filepath, 'r') as f:
                result = f.read().strip()
            os.remove(result_filepath)
            return {"state": "SUCCESS", "result": result}
        else:
            return {"state": "FAILURE", "error": "Result file not found after job completion."}

    if status.failed:
        return {"state": "FAILURE", "error": "Job failed. Check logs."}

    return {"state": "ACTIVE"} if status.active else {"state": "PENDING"}


def download_result_file(filename):
    """Serves a file from the shared volume for download."""
    return send_from_directory(SHARED_VOLUME_PATH, filename, as_attachment=True)


# --- Private Helper Functions ---
def _build_job_object(job_name, generator_type, generator_name, input_filename, original_filename):
    """
    A private helper to construct the full Kubernetes Job object.
    This is where the image is selected and the command is built.
    """
    # 1. Select the correct Docker image for this job type.
    # Defaults to the main backend image if the type is not in our map.
    image_name = GENERATOR_IMAGE_MAP.get(generator_type, "redbuild-backend")
    logging.info(f"Selected image '{image_name}' for generator type '{generator_type}'.")

    # 2. Build the command with the correct arguments for job_runner.py
    job_command = [
        "python", "-m", "app.job_runner",
        "--generator-type", generator_type,
        "--generator-name", generator_name,
        "--input-file", f"{SHARED_VOLUME_PATH}/{input_filename}",
        "--original-filename", original_filename
    ]

    # 3. Define the container using the selected image and command.
    container = V1Container(
        name="worker",
        image=image_name,
        image_pull_policy="IfNotPresent",
        command=job_command,
        volume_mounts=[V1VolumeMount(name="uploads-storage", mount_path=SHARED_VOLUME_PATH)],
        env=[V1EnvVar(name="JOB_NAME", value=job_name)]
    )

    # 4. Assemble the rest of the Job specification.
    pod_template = V1PodTemplateSpec(
        metadata=V1ObjectMeta(labels={"app": "transformer-job", "job-type": generator_type}),
        spec=V1PodSpec(
            restart_policy="Never",
            containers=[container],
            volumes=[V1Volume(
                name="uploads-storage",
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name="shared-uploads-pvc")
            )]
        )
    )

    return V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=V1ObjectMeta(name=job_name),
        spec=V1JobSpec(template=pod_template, backoff_limit=0, ttl_seconds_after_finished=20)
    )

