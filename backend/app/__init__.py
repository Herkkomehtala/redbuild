import os
import secrets
from flask import Flask, request
import logging
import uuid
from contextvars import ContextVar

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

from opentelemetry.instrumentation.flask import FlaskInstrumentor

from .k8s_client import init_k8s_client

task_id_var = ContextVar('task_id', default='system')

class ContextVarsRecordProcessor(LogRecordProcessor):
    """
    An OpenTelemetry LogRecordProcessor that injects context variables
    (like task_id) into every log record's attributes.
    """
    def on_emit(self, log_record):
        task_id = task_id_var.get()
        if task_id:
            record = getattr(log_record, "log_record", log_record)
            
            attrs = getattr(record, "attributes", None)
            if attrs is not None:
                try:
                    record.attributes["task_id"] = task_id
                except (TypeError, AttributeError):
                    pass
            else:
                try:
                    record.attributes = {"task_id": task_id}
                except (AttributeError, TypeError):
                    pass

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        pass

def init_telemetry():
    base_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not base_url:
        logging.basicConfig(level=logging.INFO)
        return

    resource = Resource.create({"service.name": "redbuild-backend"})

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
    

    logger_provider.add_log_record_processor(ContextVarsRecordProcessor())
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

def create_app():
    """Application Factory Function"""
    app = Flask(__name__)
    
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
    
    init_telemetry()
    
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        FlaskInstrumentor().instrument_app(
            app, 
            meter_provider=metrics.get_meter_provider(),
            tracer_provider=trace.get_tracer_provider(),
            excluded_urls="/api/health,/favicon.ico"
        )

    @app.before_request
    def before_request():
        task_id = str(uuid.uuid4())
        task_id_var.set(task_id)
        request.task_id = task_id

    init_k8s_client()

    from .api import bp as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app
