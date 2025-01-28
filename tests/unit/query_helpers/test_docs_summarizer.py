"""Unit tests for DocsSummarizer class."""

import logging
from unittest.mock import ANY, call, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from ols import config

# needs to be setup there before is_user_authorized is imported
config.ols_config.authentication_config.module = "k8s"


from ols.app.models.config import LoggingConfig  # noqa:E402
from ols.src.query_helpers.docs_summarizer import (  # noqa:E402
    DocsSummarizer,
    QueryHelper,
)
from ols.utils import suid  # noqa:E402
from ols.utils.logging_configurator import configure_logging  # noqa:E402
from tests import constants  # noqa:E402
from tests.mock_classes.mock_langchain_interface import (  # noqa:E402
    mock_langchain_interface,
)
from tests.mock_classes.mock_llama_index import MockLlamaIndex  # noqa:E402
from tests.mock_classes.mock_llm_chain import mock_llm_chain  # noqa:E402
from tests.mock_classes.mock_llm_loader import mock_llm_loader  # noqa:E402

conversation_id = suid.get_suid()


def test_is_query_helper_subclass():
    """Test that DocsSummarizer is a subclass of QueryHelper."""
    assert issubclass(DocsSummarizer, QueryHelper)


def check_summary_result(summary, question):
    """Check result produced by DocsSummarizer.summary method."""
    assert question in summary.response
    assert isinstance(summary.rag_chunks, list)
    assert len(summary.rag_chunks) == 1
    assert (
        f"{constants.OCP_DOCS_ROOT_URL}/{constants.OCP_DOCS_VERSION}/docs/test.html"
        in summary.rag_chunks[0].doc_url
    )
    assert summary.history_truncated is False


@pytest.fixture(scope="function", autouse=True)
def _setup():
    """Set up config for tests."""
    config.reload_from_yaml_file("tests/config/valid_config.yaml")


def test_if_system_prompt_was_updated():
    """Test if system prompt was overided from the configuration."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    # expected prompt was loaded during configuration phase
    expected_prompt = config.ols_config.system_prompt
    assert summarizer._system_prompt == expected_prompt


def test_docs_summarizer_streaming_parameter():
    """Test if optional streaming parameter is stored."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    assert summarizer.streaming is False

    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None), streaming=False)
    assert summarizer.streaming is False

    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None), streaming=True)
    assert summarizer.streaming is True


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.utils.token_handler.MINIMUM_CONTEXT_TOKEN_LIMIT", 1)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_empty_history():
    """Basic test for DocsSummarizer using mocked index and query engine."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    rag_index = MockLlamaIndex()
    history = []  # empty history
    summary = summarizer.create_response(question, rag_index, history)
    check_summary_result(summary, question)


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.utils.token_handler.MINIMUM_CONTEXT_TOKEN_LIMIT", 3)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_no_history():
    """Basic test for DocsSummarizer using mocked index and query engine, no history is provided."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    rag_index = MockLlamaIndex()
    # no history is passed into summarize() method
    summary = summarizer.create_response(question, rag_index)
    check_summary_result(summary, question)


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.utils.token_handler.MINIMUM_CONTEXT_TOKEN_LIMIT", 3)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_history_provided():
    """Basic test for DocsSummarizer using mocked index and query engine, history is provided."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    history = ["human: What is Kubernetes?"]
    rag_index = MockLlamaIndex()

    # first call with history provided
    with patch(
        "ols.src.query_helpers.docs_summarizer.TokenHandler.limit_conversation_history",
        return_value=([], False),
    ) as token_handler:
        summary1 = summarizer.create_response(question, rag_index, history)
        token_handler.assert_called_once_with(history, ANY, ANY)
        check_summary_result(summary1, question)

    # second call without history provided
    with patch(
        "ols.src.query_helpers.docs_summarizer.TokenHandler.limit_conversation_history",
        return_value=([], False),
    ) as token_handler:
        summary2 = summarizer.create_response(question, rag_index)
        token_handler.assert_called_once_with([], ANY, ANY)
        check_summary_result(summary2, question)


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_truncation():
    """Basic test for DocsSummarizer to check if truncation is done."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    rag_index = MockLlamaIndex()

    # too long history
    history = [HumanMessage("What is Kubernetes?")] * 10000
    summary = summarizer.create_response(question, rag_index, history)

    # truncation should be done
    assert summary.history_truncated


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_prepare_prompt_context():
    """Basic test for DocsSummarizer to check re-structuring of context for the 'temp' prompt."""
    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    history = [HumanMessage("What is Kubernetes?")]
    rag_index = MockLlamaIndex()

    with patch(
        "ols.src.query_helpers.docs_summarizer.restructure_rag_context",
        return_value="patched_history",
    ) as restructure_rag_context:
        summarizer.create_response(question, rag_index, history)
        restructure_rag_context.assert_has_calls([call("sample", ANY)])

    with patch(
        "ols.src.query_helpers.docs_summarizer.restructure_history",
        return_value="patched_history",
    ) as restructure_history:
        summarizer.create_response(question, rag_index, history)
        restructure_history.assert_has_calls([call(AIMessage("sample"), ANY)])


@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_no_reference_content():
    """Basic test for DocsSummarizer using mocked index and query engine."""
    summarizer = DocsSummarizer(
        llm_loader=mock_llm_loader(mock_langchain_interface("test response")())
    )
    question = "What's the ultimate question with answer 42?"
    summary = summarizer.create_response(question)
    assert question in summary.response
    assert summary.rag_chunks == []
    assert not summary.history_truncated


@patch("ols.utils.token_handler.RAG_SIMILARITY_CUTOFF", 0.4)
@patch("ols.utils.token_handler.MINIMUM_CONTEXT_TOKEN_LIMIT", 3)
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
def test_summarize_reranker(caplog):
    """Basic test to make sure the reranker is called as expected."""
    logging_config = LoggingConfig(app_log_level="debug")

    configure_logging(logging_config)
    logger = logging.getLogger("ols")
    logger.handlers = [caplog.handler]  # add caplog handler to logger

    summarizer = DocsSummarizer(llm_loader=mock_llm_loader(None))
    question = "What's the ultimate question with answer 42?"
    rag_index = MockLlamaIndex()
    # no history is passed into create_response() method
    summary = summarizer.create_response(question, rag_index)
    check_summary_result(summary, question)

    # Check captured log text to see if reranker was called.
    assert "reranker.rerank() is called with 1 result(s)." in caplog.text


@pytest.mark.asyncio
@patch("ols.src.query_helpers.docs_summarizer.LLMChain", new=mock_llm_chain(None))
async def test_response_generator():
    """Test response generator method."""
    summarizer = DocsSummarizer(
        llm_loader=mock_llm_loader(mock_langchain_interface("test response")())
    )
    question = "What's the ultimate question with answer 42?"
    summary_gen = summarizer.generate_response(question)
    generated_content = ""

    async for item in summary_gen:
        if isinstance(item, str):
            generated_content += item

    assert generated_content == question
