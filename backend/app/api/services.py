import os
import uuid
import glob
import time
import logging
import json
from flask import send_from_directory
from ..k8s_client import batch_v1, core_v1, NAMESPACE
from kubernetes.client import (
    ApiException, V1Container, V1VolumeMount, V1EnvVar, V1PodTemplateSpec,
    V1ObjectMeta, V1PodSpec, V1Volume, V1PersistentVolumeClaimVolumeSource,
    V1Job, V1JobSpec
)

# --- Configuration ---
SHARED_VOLUME_PATH = '/tmp/uploads'

# --- Service Functions ---
def discover_generators():
    """
    Discovers all generator types and their internal stages/options.
    Returns a consistent structure for both simple and complex generators.
    """
    generators = {}
    app_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_path = os.path.join(app_root_path, 'generators')

    if not os.path.isdir(base_path):
        logging.warning(f"Base generator directory not found at: {base_path}")
        return {}

    for gen_type in os.listdir(base_path):
        type_path = os.path.join(base_path, gen_type)
        if os.path.isdir(type_path) and not gen_type.startswith('__'):
            generator_info = {'stages': {}}
            has_stages = False

            for stage_name in os.listdir(type_path):
                stage_path = os.path.join(type_path, stage_name)
                if os.path.isdir(stage_path) and not stage_name.startswith('__'):
                    has_stages = True
                    options = []
                    for f_path in glob.glob(os.path.join(stage_path, '*.py')):
                        if '__init__' in f_path: continue
                        module_name = os.path.basename(f_path).replace('.py', '')
                        display_name = module_name.replace('_', ' ').title()
                        options.append({'value': module_name, 'text': display_name})
                    if options:
                        generator_info['stages'][stage_name] = options
            
            if not has_stages:
                options = []
                for f_path in glob.glob(os.path.join(type_path, '*.py')):
                    if '__init__' in f_path: continue
                    module_name = os.path.basename(f_path).replace('.py', '')
                    display_name = module_name.replace('_', ' ').title()
                    options.append({'value': module_name, 'text': display_name})
                if options:
                    generator_info['stages']['module'] = options

            generators[gen_type] = generator_info
            
    logging.info(f"Discovered generators: {generators}")
    return generators


def start_generator_job(file_storage, original_filename, generator_type, options_json):
    """
    Starts a job for a specific generator type, passing a JSON string
    of the selected options for its internal stages.
    """
    input_filename = f"{uuid.uuid4()}"
    file_storage.save(os.path.join(SHARED_VOLUME_PATH, input_filename))

    job_name = f"job-{generator_type}-{uuid.uuid4().hex[:6]}"
    job_body = _build_job_object(job_name, input_filename, original_filename, generator_type, options_json)

    logging.info(f"Creating job '{job_name}' in namespace '{NAMESPACE}'...")
    batch_v1.create_namespaced_job(body=job_body, namespace=NAMESPACE)
    logging.info(f"Successfully created job '{job_name}'.")
    return job_name

def _get_image_tag_from_env():
    """
    Parses the full image string from the MY_POD_IMAGE environment variable
    to extract just the unique tag.
    """
    pod_image_string = os.environ.get("MY_POD_IMAGE")
    if pod_image_string and ':' in pod_image_string:
        return pod_image_string.split(':', 1)[1]
    return "latest" # Fallback for local testing

def _get_image_for_generator(generator_type):
    """
    Constructs the full, correctly-tagged image name for any generator type.
    """
    tag = _get_image_tag_from_env()
    
    if generator_type == "compiler":
        return f"win-c-compiler-worker:{tag}"
    else:
        return f"redbuild-backend:{tag}"

def _build_job_object(job_name, input_filename, original_filename, generator_type, options_json):
    """
    Builds the Kubernetes Job object using a dynamically constructed,
    fully-tagged image name for any worker type.
    """
    image_name = _get_image_for_generator(generator_type)
    
    logging.info(f"Using fully-tagged image '{image_name}' for generator type '{generator_type}'.")
    
    job_command = [
        "python", "-m", "app.job_runner",
        "--input-file", f"{SHARED_VOLUME_PATH}/{input_filename}",
        "--original-filename", original_filename,
        "--generator-type", generator_type,
        "--options", options_json
    ]

    container = V1Container(
        name="worker",
        image=image_name,
        image_pull_policy="IfNotPresent",
        command=job_command,
        volume_mounts=[V1VolumeMount(name="uploads-storage", mount_path=SHARED_VOLUME_PATH)],
        env=[V1EnvVar(name="JOB_NAME", value=job_name)]
    )
    
    pod_template = V1PodTemplateSpec(
        metadata=V1ObjectMeta(labels={"app": "processing-job", "gen-type": generator_type}),
        spec=V1PodSpec(
            restart_policy="Never", containers=[container],
            volumes=[V1Volume(
                name="uploads-storage",
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name="shared-uploads-pvc")
            )]
        )
    )

    return V1Job(
        api_version="batch/v1", kind="Job", metadata=V1ObjectMeta(name=job_name),
        spec=V1JobSpec(template=pod_template, backoff_limit=0, ttl_seconds_after_finished=20)
    )

    return V1Job(
        api_version="batch/v1", kind="Job", metadata=V1ObjectMeta(name=job_name),
        spec=V1JobSpec(template=pod_template, backoff_limit=0, ttl_seconds_after_finished=20)
    )

# ... (check_job_status and download_result_file remain the same) ...
def check_job_status(job_name):
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
        time.sleep(0.5)
        if os.path.exists(result_filepath):
            with open(result_filepath, 'r') as f:
                result = f.read().strip()
            os.remove(result_filepath)
            return {"state": "SUCCESS", "result": result}
        else:
            return {"state": "FAILURE", "error": "Result file not found after job completion."}
    if status.failed:
        try:
            pods = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=f"job-name={job_name}")
            pod_name = pods.items[0].metadata.name
            logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace=NAMESPACE)
            error_reason = "Could not determine error from pod logs."
            for line in logs.splitlines():
                if "ERROR: Job failed. Reason:" in line:
                    error_reason = line.split("Reason:")[-1].strip()
                    break
            return {"state": "FAILURE", "error": error_reason}
        except Exception as log_e:
            logging.error(f"Failed to retrieve logs for failed job {job_name}: {log_e}")
            return {"state": "FAILURE", "error": "Job failed, but could not retrieve logs."}
    return {"state": "ACTIVE"} if status.active else {"state": "PENDING"}

def download_result_file(filename):
    return send_from_directory(SHARED_VOLUME_PATH, filename, as_attachment=True)

