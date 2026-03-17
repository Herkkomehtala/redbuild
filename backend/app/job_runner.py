import argparse
import importlib
import os
import sys
import json
import uuid
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

def init_telemetry(job_name):
    base_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not base_url:
        logging.basicConfig(level=logging.INFO)
        return trace.get_tracer(__name__)

    resource = Resource.create({
        "service.name": "redbuild-worker",
        "job.name": job_name or "unknown"
    })

    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=f"{base_url}/v1/traces")
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    metric_exporter = OTLPMetricExporter(endpoint=f"{base_url}/v1/metrics")
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint=f"{base_url}/v1/logs")
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    otlp_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    console_handler = logging.StreamHandler()
    logger.addHandler(otlp_handler)
    logger.addHandler(console_handler)

    return trace.get_tracer(__name__)

def run_stage(stage_name, module_name, input_filepath, original_filename, generator_type="transformer"):
    """
    Helper to run a single stage of a multi-stage generator.
    """
    if not module_name:
        return input_filepath

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(f"stage.{stage_name}") as span:
        span.set_attribute("module", module_name)
        logging.info(f"Running stage '{stage_name}' with module '{module_name}'...")
        try:
            module_path = f"app.generators.{generator_type}.{stage_name}.{module_name}"
            processing_module = importlib.import_module(module_path)
            
            output_filepath = processing_module.encode(input_filepath, original_filename)
            
            if input_filepath != args.input_file:
                os.remove(input_filepath)
                
            return output_filepath
        except Exception as e:
            logging.error(f"Failed during stage '{stage_name}'. Reason: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise

def run_simple_generator(generator_type, options, input_filepath, original_filename):
    """
    Helper for simple, manifest-driven generators (like compiler).
    """
    entry_module_name = options.get('entry_module')
    if not entry_module_name:
        raise ValueError("Manifest for simple generator is missing 'entry_module' key.")

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(f"generator.{generator_type}") as span:
        span.set_attribute("entry_module", entry_module_name)
        logging.info(f"Running simple generator '{entry_module_name}'...")
        try:
            module_path = f"app.generators.{generator_type}.{entry_module_name}"
            processing_module = importlib.import_module(module_path)
            
            final_artifact_name = processing_module.encode(input_filepath, original_filename, options)
            
            return final_artifact_name
        except Exception as e:
            logging.error(f"Failed during simple generator '{entry_module_name}'. Reason: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
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

    tracer = init_telemetry(job_name)

    carrier = {}
    if "OTEL_TRACEPARENT" in os.environ:
        carrier["traceparent"] = os.environ["OTEL_TRACEPARENT"]
    ctx = TraceContextTextMapPropagator().extract(carrier)

    with tracer.start_as_current_span("worker_execution", context=ctx) as span:
        span.set_attribute("generator_type", args.generator_type)
        span.set_attribute("job_name", job_name or "unknown")

        try:
            logging.info(f"Starting job {job_name} for generator '{args.generator_type}' with options: {options}")
            
            current_filepath = args.input_file
            final_filename = ""

            is_compiler_job = 'output_format' in options 
            is_transformer_job = not is_compiler_job

            if is_compiler_job:
                final_filename = run_simple_generator(args.generator_type, options, current_filepath, args.original_filename)
            elif is_transformer_job:
                current_filepath = run_stage('compression', options.get('compression'), current_filepath, args.original_filename)
                current_filepath = run_stage('encoding', options.get('encoding'), current_filepath, args.original_filename)
                final_filename = os.path.basename(current_filepath)

            result_filepath = os.path.join('/tmp/uploads', f"{job_name}.result")
            with open(result_filepath, 'w') as f_result:
                f_result.write(final_filename)

            logging.info(f"SUCCESS: Job complete. Final artifact: {final_filename}")
            span.set_attribute("artifact", final_filename)

        except Exception as e:
            logging.error(f"ERROR: Job failed. Reason: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            sys.exit(1)
        finally:
            tracer_provider = trace.get_tracer_provider()
            if hasattr(tracer_provider, "shutdown"):
                tracer_provider.shutdown()
                
            meter_provider = metrics.get_meter_provider()
            if hasattr(meter_provider, "shutdown"):
                meter_provider.shutdown()

if __name__ == '__main__':
    main()
