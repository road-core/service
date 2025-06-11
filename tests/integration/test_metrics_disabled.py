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
    "ols_llm_calls_total",
    "ols_provider_model_configuration",
)


@pytest.fixture(scope="function", autouse=True)
def _setup():
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
        # Setup metrics based on config with disabled metrics.
        from ols.app.metrics import setup_metrics
        setup_metrics(config)
        # app.main need to be imported after the configuration is read
        from ols.app.main import app  # pylint: disable=C0415

        pytest.client = TestClient(app)


def retrieve_metrics(client):
    """Retrieve all service metrics."""
    response = pytest.client.get("/metrics")

    # check that the /metrics endpoint is correct and we got
    # some response
    assert response.status_code == requests.codes.ok
    assert response.text is not None

    # return response text (it is not JSON!)
    return response.text


def test_metrics_missing():
    """Check if service provides metrics endpoint with some expected counters."""
    response_text = retrieve_metrics(pytest.client)

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
