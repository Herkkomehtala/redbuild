import importlib
from celery import Celery

celery = Celery(__name__)
celery.config_from_object('celery_config')

@celery.task(name='tasks.run_transform_task')
def run_transform_task(file_content_bytes, transformer_name, original_filename):
    """
    A generic Celery task that dynamically calls a specified transformer.

    Args:
        file_content_bytes: The raw bytes of the file.
        transformer_name: The name of the transformer module to use.
        original_filename: The original name of the uploaded file.
    """
    try:
        module_path = f"generators.transformer.{transformer_name}"
        transformer_module = importlib.import_module(module_path)

        output_filename = transformer_module.encode(file_content_bytes, original_filename)
        return output_filename
    except ModuleNotFoundError:
        raise ValueError(f"Unknown transformer: {transformer_name}")
    except Exception as e:
        raise e
