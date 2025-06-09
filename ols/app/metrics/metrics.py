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
    """Update list of metrics exposed in /metrics end point."""
    # Metrics are global module-level variables.
    # `global` ensures module-level variables are updated.
    global rest_api_calls_total, response_duration_seconds, llm_calls_total, \
           llm_calls_failures_total, llm_calls_validation_errors_total, \
           llm_token_sent_total, llm_token_received_total, provider_model_configuration

    # Helper object to keep API compatibility for disabled metrics
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

    default_metrics = {
        "rest_api_calls_total": rest_api_calls_total,
        "response_duration_seconds": response_duration_seconds,
        "llm_calls_total": llm_calls_total,
        "llm_calls_failures_total": llm_calls_failures_total,
        "llm_calls_validation_errors_total": llm_calls_validation_errors_total,
        "llm_token_sent_total": llm_token_sent_total,
        "llm_token_received_total": llm_token_received_total,
        "provider_model_configuration": provider_model_configuration
    }

    if config.ols_config.metrics:
        # Disable metrics not configured in config file.
        configured_metrics = set(config.ols_config.metrics)
        for m_name, m_obj in default_metrics.items():
            if m_name in default_metrics:
                if m_name not in configured_metrics:
                    REGISTRY.unregister(m_obj)
                    default_metrics[m_name] = NoopMetric()
            else:
                logger.warning(f"Metric `{m_name}` does not exit. Check the `ols_config`"
                                "section of the configuration file.")
    else:
        logger.info("No metrics configuration provided; all metrics are enabled.")


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
