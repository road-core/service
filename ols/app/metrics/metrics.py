"""Prometheus metrics that are exposed by REST API."""

import logging

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    generate_latest,
    REGISTRY
)

from ols import config
from ols.src.auth.auth import get_auth_dependency
from ols.utils.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])
auth_dependency = get_auth_dependency(
    config.ols_config, virtual_path="/ols-metrics-access"
)

disable_created_metrics()  # type: ignore [no-untyped-call]


_DEFAULT_METRICS_LIST = [
    "rest_api_calls_total",
    "response_duration_seconds",
    "llm_calls_total",
    "llm_calls_failures_total",
    "llm_calls_validation_errors_total",
    "llm_token_sent_total",
    "llm_token_received_total",
    "provider_model_configuration"
]

# Helper object to keep API compatibility with disabled metrics
class NoopMetric():
    def inc(self, *args, **kwargs):
        pass

    def labels(self, *args, **kwargs):
        return self

    def set(self, *args, **kwargs):
        pass

    def time(self, *args, **kwargs):
        class NoopTimer():
            def __enter__(self):
                pass
            def __exit__(self, typ, value, traceback):
                pass
        return NoopTimer()

rest_api_calls_total = Counter(
    "ols_rest_api_calls_total", "REST API calls counter", ["path", "status_code"]
)

response_duration_seconds = Histogram(
    "ols_response_duration_seconds", "Response durations", ["path"]
)

llm_calls_total = Counter(
    "ols_llm_calls_total", "LLM calls counter", ["provider", "model"]
)
llm_calls_failures_total = Counter("ols_llm_calls_failures_total", "LLM calls failures")
llm_calls_validation_errors_total = Counter(
    "ols_llm_validation_errors_total", "LLM validation errors"
)

llm_token_sent_total = Counter(
    "ols_llm_token_sent_total", "LLM tokens sent", ["provider", "model"]
)
llm_token_received_total = Counter(
    "ols_llm_token_received_total", "LLM tokens received", ["provider", "model"]
)
# metric that indicates what provider + model customers are using so we can
# understand what is popular/important
provider_model_configuration = Gauge(
    "ols_provider_model_configuration",
    "LLM provider/models combinations defined in configuration",
    ["provider", "model"],
)


def setup_metrics(config):
    # TODO better comments
    # Disable metrics not configured in config file.
    # Metrics initialization does not work in a class/function.
    global rest_api_calls_total
    global response_duration_seconds
    global llm_calls_total
    global llm_calls_failures_total
    global llm_calls_validation_errors_total
    global llm_token_sent_total
    global llm_token_received_total
    global provider_model_configuration

    if not config.ols_config.metrics:
        # No metrics configured - keep all enabled.
        return
    # Metrics to disable
    disabled_metrics = set(_DEFAULT_METRICS_LIST) - set(config.ols_config.metrics)

    for m in disabled_metrics:
        match m:
            case "rest_api_calls_total":
                REGISTRY.unregister(rest_api_calls_total)
                rest_api_calls_total = NoopMetric()
            case "response_duration_seconds":
                REGISTRY.unregister(response_duration_seconds)
                response_duration_seconds = NoopMetric()
            case "llm_calls_total":
                REGISTRY.unregister(llm_calls_total)
                llm_calls_total = NoopMetric()
            case "llm_calls_failures_total":
                REGISTRY.unregister(llm_calls_failures_total)
                llm_calls_failures_total = NoopMetric()
            case "llm_calls_validation_errors_total":
                REGISTRY.unregister(llm_calls_validation_errors_total)
                llm_calls_validation_errors_total = NoopMetric()
            case "llm_token_sent_total":
                REGISTRY.unregister(llm_token_sent_total)
                llm_token_sent_total = NoopMetric()
            case "llm_token_received_total":
                REGISTRY.unregister(llm_token_received_total)
                llm_token_received_total = NoopMetric()
            case "provider_model_configuration":
                REGISTRY.unregister(provider_model_configuration)
                provider_model_configuration = NoopMetric()
            case _:
                logger.warning(f"Metric `{m}` does not exit. Check the `ols_config`"
                                "section of the configuration file.")


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics(auth: Annotated[Any, Depends(auth_dependency)]) -> PlainTextResponse:
    """Metrics Endpoint.

    Args:
        auth: The Authentication handler (FastAPI Depends) that will handle authentication Logic.

    Returns:
        Response containing the latest metrics.
    """
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_model_metrics(config: AppConfig) -> None:
    """Perform setup of all metrics related to LLM model and provider."""
    # Set to track which provider/model combinations are set to 1, to
    # avoid setting provider/model to 0 in case it is already in metric
    # with value 1 - case when there are more "same" providers/models
    # combinations, but with the different names and other parameters.
    model_metrics_set = set()

    for provider in config.llm_config.providers.values():
        for model_name in provider.models:
            label_key = (provider.type, model_name)
            if (
                provider.name == config.ols_config.default_provider
                and model_name == config.ols_config.default_model
            ):
                provider_model_configuration.labels(*label_key).set(1)
                model_metrics_set.add(label_key)
            elif label_key not in model_metrics_set:
                provider_model_configuration.labels(*label_key).set(0)
