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
SHARED_PVC_NAME = os.getenv("SHARED_PVC_NAME", "shared-uploads-pvc")
SHARED_VOLUME_PATH = '/tmp/uploads'
GENERATOR_IMAGE_MAP = {
    "transformer": os.getenv("REDBUILD_BACKEND_IMAGE", "redbuild-backend"),
    "compiler": os.getenv("WIN_C_COMPILER_WORKER_IMAGE", "win-c-compiler-worker"),
    "g2js": os.getenv("G2JS_WORKER_IMAGE", "gadget-to-jscript-worker")
}

logging.info(f"Using transformer image: {GENERATOR_IMAGE_MAP['transformer']}")
logging.info(f"Using compiler image: {GENERATOR_IMAGE_MAP['compiler']}")
logging.info(f"Using g2js image: {GENERATOR_IMAGE_MAP['g2js']}")
logging.info(f"Using shared PVC: {SHARED_PVC_NAME}")

# --- Service Functions ---
def discover_generators():
    """
    Discovers all generators and their options by looking for a 'manifest.json' file.
    """
    generators = {}
    app_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_path = os.path.join(app_root_path, 'generators')

    if not os.path.isdir(base_path):
        logging.warning(f"Base generator directory not found at: {base_path}")
        return {}

    for gen_type in os.listdir(base_path):
        type_path = os.path.join(base_path, gen_type)
        manifest_path = os.path.join(type_path, 'manifest.json')
        
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, 'r') as f:
                    manifest_data = json.load(f)
                    generators[gen_type] = manifest_data
            except json.JSONDecodeError:
                logging.error(f"Could not parse manifest.json for generator: {gen_type}")

    logging.info(f"Discovered generators via manifests: {generators}")
    return generators

def start_generator_job(file_storage, original_filename, generator_type, options_json):
    """
    Starts generator jobs, orchestrating a multi-job pipeline if necessary.
    """
    user_options = json.loads(options_json)
    
    transformation_options = {
        'encoding': user_options.get('bytecode_encoding'),
        'compression': user_options.get('bytecode_compression')
    }
    selected_transformations = {k: v for k, v in transformation_options.items() if v}

    input_filename = f"{uuid.uuid4()}"
    
    data_source = user_options.get('data_source')
    is_preprocessing_needed = (
        (generator_type == 'compiler' and data_source == 'embedded' and selected_transformations) or
        (generator_type == 'g2js' and selected_transformations)
    )

    if is_preprocessing_needed:
        if not file_storage:
             raise ValueError("A file must be provided for pre-processing.")
        
        input_filepath = os.path.join(SHARED_VOLUME_PATH, input_filename)
        file_storage.save(input_filepath)
        
        logging.info("Transformation step required. Starting transformer job first...")
        transformer_job_name = f"job-transformer-preproc-{uuid.uuid4().hex[:6]}"
        transformer_job_body = _build_job_object(
            transformer_job_name, input_filename, original_filename, "transformer", json.dumps(selected_transformations)
        )
        batch_v1.create_namespaced_job(body=transformer_job_body, namespace=NAMESPACE)
        
        final_artifact_name = _wait_for_job_completion(transformer_job_name)
        if not final_artifact_name:
            raise Exception("Pre-processing transformer job failed.")
            
        logging.info(f"Transformer job complete. Intermediate artifact: {final_artifact_name}")
        final_input_for_compiler = final_artifact_name
    else:
        if file_storage:
            input_filepath = os.path.join(SHARED_VOLUME_PATH, input_filename)
            file_storage.save(input_filepath)
        final_input_for_compiler = input_filename


    app_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(app_root_path, 'generators', generator_type, 'manifest.json')
    final_options = user_options.copy()
    
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            if manifest.get('entry_module'):
                final_options['entry_module'] = manifest['entry_module']
                logging.info(f"Enriched options with entry_module: {manifest.get('entry_module')}")

    logging.info(f"Starting main '{generator_type}' job...")
    main_job_name = f"job-{generator_type}-{uuid.uuid4().hex[:6]}"
    main_job_body = _build_job_object(
        main_job_name, final_input_for_compiler, original_filename, generator_type, json.dumps(final_options)
    )
    batch_v1.create_namespaced_job(body=main_job_body, namespace=NAMESPACE)
    
    return main_job_name

def _wait_for_job_completion(job_name, timeout=120):
    """A blocking function to poll for job completion."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            status_data = check_job_status(job_name)
            if status_data['state'] == 'SUCCESS':
                return status_data['result']
            if status_data['state'] == 'FAILURE':
                logging.error(f"Job '{job_name}' failed with error: {status_data.get('error')}")
                return None
        except Exception as e:
            logging.error(f"Error polling for job {job_name}: {e}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job '{job_name}' to complete.")

def _build_job_object(job_name, input_filename, original_filename, generator_type, options_json):
    """
    Builds the Kubernetes Job object.
    """
    image_name = GENERATOR_IMAGE_MAP.get(generator_type, "redbuild-backend")
    
    job_command = [
        "python", "-m", "app.job_runner",
        "--input-file", f"{SHARED_VOLUME_PATH}/{input_filename}",
        "--original-filename", original_filename,
        "--generator-type", generator_type,
        "--options", options_json
    ]

    container = V1Container(
        name="worker", image=image_name, image_pull_policy="IfNotPresent",
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
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name=SHARED_PVC_NAME)
            )]
        )
    )

    return V1Job(
        api_version="batch/v1", kind="Job", metadata=V1ObjectMeta(name=job_name),
        spec=V1JobSpec(template=pod_template, backoff_limit=0, ttl_seconds_after_finished=20)
    )

def check_job_status(job_name):
    try:
        job = batch_v1.read_namespaced_job_status(name=job_name, namespace=NAMESPACE)
        status = job.status
    except ApiException as e:
        if e.status == 404: return {"state": "NOT_FOUND", "error": "Job not found."}
        logging.error(f"API Error checking status for {job_name}: {e.reason}")
        return {"state": "UNKNOWN", "error": f"API Error: {e.reason}"}
    if status.succeeded:
        result_filepath = os.path.join(SHARED_VOLUME_PATH, f"{job_name}.result")
        time.sleep(0.5)
        if os.path.exists(result_filepath):
            with open(result_filepath, 'r') as f: result = f.read().strip()
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
