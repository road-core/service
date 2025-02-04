"""Unit tests for utility functions."""
import re
import pytest
from ols.utils.checks import expand_lightspeed_environment_variables

import os

os.environ["TEST_TOKEN"] = "first-token"
os.environ["TEST_TOKEN_TWO"] = "second-token"

def test_expand_lightspeed_env_vars_failure():
    """Tests the expansion of Lightspeed environment variables that are unset."""
    data = [
        {
            'id': 'test-id',
            'url': 'https://localhost:8080',
            'token': '${TEST_TOKEN_THREE}',
            'models': [{"name": "test-model-name"}],
            'type': 'openai'
        },
        {
            'id': 'second-test-id',
            'url': 'https://localhost:6060',
            'token': 'token',
            'models': [{"name": "test-name"}],
            'type': 'openai'
        }
    ]
    with pytest.raises(Exception, match=re.escape("Environment variable referenced but not set. ${TEST_TOKEN_THREE}")):
        expand_lightspeed_environment_variables(data)


def test_expand_lightspeed_env_vars_success():
    """Tests the ability to expand environment variables into Python dictionaries."""
    data = [
        {
            'id': 'test-id',
            'url': 'https://localhost:8080',
            'token': '${TEST_TOKEN}',
            'models': [{"name": "test-model-name"}],
            'type': 'openai'
        },
        {
            'id': 'second-test-id',
            'url': 'https://localhost:6060',
            'token': '${TEST_TOKEN_TWO}',
            'models': [{"name": "expected-model-name"}],
            'type': 'openai'
        }
    ]
    expected_data = [
        {
            'id': 'test-id',
            'url': 'https://localhost:8080',
            'token': 'first-token',
            'models': [{"name": "test-model-name"}],
            'type': 'openai'
        },
        {
            'id': 'second-test-id',
            'url': 'https://localhost:6060',
            'token': 'second-token',
            'models': [{"name": "expected-model-name"}],
            'type': 'openai'
        }
    ]
    expand_lightspeed_environment_variables(data)
    assert data == expected_data
