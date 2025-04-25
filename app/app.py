# app/app.py
from flask import Flask, request
import time
import random
import logging
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.metrics import get_meter_provider, set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
import prometheus_client
from prometheus_client import Counter, Histogram

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# Get OpenTelemetry collector endpoint from environment or use default
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:14317")

# Set up OpenTelemetry trace provider
resource = Resource(attributes={SERVICE_NAME: "flask-app"})
trace_provider = TracerProvider(resource=resource)
otlp_trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
trace_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# Set up OpenTelemetry metrics
metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=1000)
meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
set_meter_provider(meter_provider)
meter = get_meter_provider().get_meter(__name__)

# Set up direct Prometheus metrics
REQUEST_COUNT = Counter(
    'flask_app_requests_total', 
    'Total number of requests',
    ['endpoint', 'status']
)
REQUEST_DURATION = Histogram(
    'flask_app_request_duration_seconds', 
    'Duration of requests in seconds',
    ['endpoint']
)

# Create Flask application
app = Flask(__name__)

# Instrument Flask with OpenTelemetry
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# Expose metrics endpoint for Prometheus
@app.route('/metrics')
def metrics():
    return prometheus_client.generate_latest(), 200, {'Content-Type': 'text/plain'}

@app.route('/')
def home():
    logger.info("Home endpoint called")
    with tracer.start_as_current_span("home-operation"):
        # Add some random processing time
        time.sleep(random.uniform(0.01, 0.1))
        REQUEST_COUNT.labels(endpoint="home", status="success").inc()
        return "Welcome to the Flask App!"

@app.route('/api/data')
def get_data():
    # Start timing the request
    start_time = time.time()
    
    logger.info("Data endpoint called")
    with tracer.start_as_current_span("data-operation") as span:
        # Add some random processing time
        processing_time = random.uniform(0.05, 0.5)
        time.sleep(processing_time)
        
        # Add custom attributes to the span
        span.set_attribute("processing_time", processing_time)
        
        # Simulate a database call with another span
        with tracer.start_as_current_span("database-query"):
            time.sleep(random.uniform(0.1, 0.3))
            logger.info("Database query executed")
        
        # Sometimes generate an error
        if random.random() < 0.1:  # 10% chance
            logger.error("Random error occurred")
            REQUEST_COUNT.labels(endpoint="data", status="error").inc()
            return "Error processing request", 500
        
        # Calculate request duration and record it
        duration = time.time() - start_time
        REQUEST_DURATION.labels(endpoint="data").observe(duration)
        REQUEST_COUNT.labels(endpoint="data", status="success").inc()
        
        return {"data": "Some important data", "processing_time": processing_time}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
