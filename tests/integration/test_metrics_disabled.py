"""Integration tests for metrics exposed by the service."""

# we add new attributes into pytest instance, which is not recognized
# properly by linters
# pyright: reportAttributeAccessIssue=false

import logging
import os
import re
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

from ols import config
from ols.app.models.config import LoggingConfig
from ols.constants import CONFIGURATION_FILE_NAME_ENV_VARIABLE
from ols.utils.logging_configurator import configure_logging

# counters that are expected to be part of metrics
expected_counters = (
    "ols_rest_api_calls_total",
    "ols_response_duration_seconds",
    "ols_llm_calls_failures_total",
    "ols_llm_validation_errors_total",
    "ols_llm_token_sent_total",
    "ols_llm_token_received_total",
)

missing_counters = (
    # This metric is disabled
    "ols_provider_model_configuration",
    "ols_llm_calls_total",
)


@pytest.fixture(scope="function")
def client_for_testing():
    """Setups the test client."""
    config.reload_from_yaml_file(
        "tests/config/config_for_integration_tests_metrics.yaml"
    )

    # we need to patch the config file path to point to the test
    # config file before we import anything from main.py
    with patch.dict(
        os.environ,
        {
            CONFIGURATION_FILE_NAME_ENV_VARIABLE: "tests/config/config_for_integration_tests_metrics.yaml"
        },
    ):
        # Save original values of disabled metric counters.
        import ols.app.metrics as metrics
        saved_metric_1 = metrics.provider_model_configuration
        saved_metric_2 = metrics.llm_calls_total

        # app.main need to be imported after the configuration is read
        from ols.app.main import app  # pylint: disable=C0415

        yield TestClient(app)

        # Restore original metric counters to avoid
        # failures of other metrics integration tests
        from prometheus_client import REGISTRY
        # 1. register metrics again
        REGISTRY.register(saved_metric_1)
        REGISTRY.register(saved_metric_2)
        # 2. restore global variables in the module
        metrics.provider_model_configuration = saved_metric_1
        metrics.llm_calls_total = saved_metric_2
        # 3. setup again the provider_model_configuration metric
        metrics.setup_model_metrics(config)


def retrieve_metrics(client):
    """Retrieve all service metrics."""
    response = client.get("/metrics")

    # check that the /metrics endpoint is correct and we got
    # some response
    assert response.status_code == requests.codes.ok
    assert response.text is not None

    # return response text (it is not JSON!)
    return response.text


def test_metrics_missing(client_for_testing: TestClient):
    """Check if service provides metrics endpoint with some expected counters."""
    response_text = retrieve_metrics(client_for_testing)

    # check if expected counters are present
    for expected_counter in expected_counters:
        assert (
            f"{expected_counter} " in response_text
        ), f"Counter {expected_counter} not found in {response_text}"
    # check if missing counters are NOT present
    for missing_counter in missing_counters:
        assert (
            f"{missing_counter} " not in response_text
        ), f"Counter {missing_counter} FOUND in {response_text}"
