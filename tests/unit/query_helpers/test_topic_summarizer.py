"""Unit tests for TopicSummarizer class."""

from unittest.mock import patch

import pytest

from ols import config
from ols.constants import GenericLLMParameters

# Configure test environment
config.ols_config.authentication_config.module = "k8s"

from ols.src.query_helpers.topic_summarizer import (  # noqa: E402
    QueryHelper,
    TopicSummarizer,
)
from tests.mock_classes.mock_llm_chain import mock_llm_chain  # noqa: E402
from tests.mock_classes.mock_llm_loader import mock_llm_loader  # noqa: E402


@pytest.fixture
def topic_summarizer():
    """Fixture containing constructed and initialized TopicSummarizer."""
    return TopicSummarizer(llm_loader=mock_llm_loader(None))


def test_is_query_helper_subclass():
    """Test that TopicSummarizer is a subclass of QueryHelper."""
    assert issubclass(TopicSummarizer, QueryHelper)


def test_initialization():
    """Test that TopicSummarizer initializes correctly with default parameters."""
    config.reload_from_yaml_file("tests/config/valid_config.yaml")

    summarizer = TopicSummarizer()
    assert summarizer.max_tokens_for_response == 4
    assert hasattr(summarizer, "provider_config")
    assert hasattr(summarizer, "model_config")
    assert hasattr(summarizer, "bare_llm")
    assert GenericLLMParameters.MAX_TOKENS_FOR_RESPONSE in summarizer.generic_llm_params


def test_prepare_llm():
    """Test that _prepare_llm method sets up all required attributes."""
    config.reload_from_yaml_file("tests/config/valid_config.yaml")

    summarizer = TopicSummarizer(llm_loader=mock_llm_loader(None))
    summarizer._prepare_llm()

    assert summarizer.provider_config is not None
    assert summarizer.model_config is not None
    assert summarizer.generic_llm_params is not None
    assert summarizer.bare_llm is not None


@patch("ols.src.query_helpers.topic_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_topic():
    """Test the summarize_topic method with mocked LLM chain."""
    config.reload_from_yaml_file("tests/config/valid_config.yaml")

    # Mock response from LLM
    expected_response = "Technology"
    mock_chain = mock_llm_chain({"text": expected_response})

    with patch("ols.src.query_helpers.topic_summarizer.LLMChain", new=mock_chain):
        summarizer = TopicSummarizer(llm_loader=mock_llm_loader(None))
        response = summarizer.summarize_topic(
            "123e4567-e89b-12d3-a456-426614174000",
            "What are the latest developments in artificial intelligence?",
        )

        assert response == expected_response


@patch("ols.customize.prompts.TOPIC_SUMMARY_PROMPT_TEMPLATE", "")
def test_skip_summarize_topic():
    """Test topic summarizer is skipped when TOPIC_SUMMARY_PROMPT_TEMPLATE is not set."""
    config.reload_from_yaml_file("tests/config/valid_config.yaml")

    summarizer = TopicSummarizer(llm_loader=mock_llm_loader(None))
    response = summarizer.summarize_topic(
        "123e4567-e89b-12d3-a456-426614174000",
        "What are the latest developments in artificial intelligence?",
    )

    assert response == ""
