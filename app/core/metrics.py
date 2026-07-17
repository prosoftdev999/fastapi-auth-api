from fastapi import FastAPI
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

from app.db.session import engine

db_pool_size = Gauge(
    "db_pool_size", "Configured SQLAlchemy connection pool size"
)
db_pool_checked_out = Gauge(
    "db_pool_checked_out_connections",
    "Connections currently checked out of the SQLAlchemy pool",
)
health_check_status = Gauge(
    "health_check_status",
    "Result of the most recent GET /health call (1=ok, 0=degraded)",
)


def setup_metrics(app: FastAPI) -> None:
    """Wires up Prometheus instrumentation and exposes GET /metrics.

    Request-level metrics (count, latency, in-progress) come from
    prometheus-fastapi-instrumentator, the standard library for this.
    Database pool metrics are point-in-time gauges evaluated at scrape
    time (Gauge.set_function), since they aren't tied to any one request.
    """
    instrumentator = Instrumentator(
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)

    db_pool_size.set_function(lambda: engine.pool.size())
    db_pool_checked_out.set_function(lambda: engine.pool.checkedout())
