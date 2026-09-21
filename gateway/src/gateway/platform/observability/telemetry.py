from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
    HTTPXClientInstrumentor,
)
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

from gateway.platform.observability.settings import TelemetrySettings


class Telemetry:
    """Owns the tracer provider for the lifetime of the application.

    Every method is a no-op while telemetry is disabled.
    """

    def __init__(self, settings: TelemetrySettings) -> None:
        self._settings = settings
        self._provider: TracerProvider | None = None

    def install(self, app: FastAPI) -> None:
        if not self._settings.enabled:
            return
        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: self._settings.service_name}),
            sampler=ParentBased(TraceIdRatioBased(self._settings.sample_ratio)),
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=self._settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/v1/health,/v1/readiness",
            # A span per ASGI message is a span per streamed WebSocket frame.
            exclude_spans=["receive", "send"],
        )
        # httpx2 is a separate package: the Deepgram SDK uses httpx, everything
        # else in the gateway uses httpx2.
        HTTPXClientInstrumentor().instrument()
        HTTPX2ClientInstrumentor().instrument()
        self._provider = provider

    def instrument_engine(self, engine: AsyncEngine) -> None:
        """Patching `create_async_engine` globally would miss this engine, because
        the database provider imports that factory before the SDK is configured."""
        if self._provider is None:
            return
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    def shutdown(self) -> None:
        if self._provider is None:
            return
        self._provider.shutdown()
        self._provider = None
