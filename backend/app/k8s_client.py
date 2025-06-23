import logging
from kubernetes import client, config

batch_v1 = None
core_v1 = None
NAMESPACE = 'default'

def init_k8s_client():
    global batch_v1, core_v1, NAMESPACE
    
    try:
        config.load_incluster_config()
        api_client = client.ApiClient()
        with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', 'r') as f:
            NAMESPACE = f.read().strip()
        logging.info(f"Successfully loaded in-cluster config for namespace: {NAMESPACE}")
    except (config.ConfigException, FileNotFoundError):
        logging.warning("Not in a cluster. Falling back to local kube config and 'default' namespace.")
        api_client = config.new_client_from_config()
        NAMESPACE = 'default'

    batch_v1 = client.BatchV1Api(api_client)
    core_v1 = client.CoreV1Api(api_client)
