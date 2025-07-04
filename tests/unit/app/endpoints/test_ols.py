"""Unit tests for OLS endpoint."""

import json
import re
import time
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from ols import config, constants

# needs to be setup there before is_user_authorized is imported
config.ols_config.authentication_config.module = "k8s"

from ols.app.endpoints import ols  # noqa:E402
from ols.app.models.config import UserDataCollection  # noqa:E402
from ols.app.models.models import (  # noqa:E402
    Attachment,
    CacheEntry,
    LLMRequest,
    RagChunk,
    SummarizerResponse,
    TokenCounter,
)
from ols.customize import prompts  # noqa:E402
from ols.src.llms.llm_loader import LLMConfigurationError  # noqa:E402
from ols.utils import suid  # noqa:E402
from ols.utils.errors_parsing import DEFAULT_ERROR_MESSAGE  # noqa:E402
from ols.utils.redactor import Redactor, RegexFilter  # noqa:E402
from ols.utils.token_handler import PromptTooLongError  # noqa:E402


@pytest.fixture(scope="function")
def _load_config():
    """Load config before unit tests."""
    config.reload_from_yaml_file("tests/config/test_app_endpoints.yaml")


@pytest.fixture
def auth():
    """Tuple containing user ID and user name, mocking auth. output."""
    # we can use any UUID, so let's use randomly generated one
    return ("2a3dfd17-1f42-4831-aaa6-e28e7cb8e26b", "name", False, "fake-token")


@pytest.mark.usefixtures("_load_config")
def test_retrieve_conversation_new_id():
    """Check the function to retrieve conversation ID."""
    llm_request = LLMRequest(query="Tell me about Kubernetes", conversation_id=None)
    new_id = ols.retrieve_conversation_id(llm_request)
    assert suid.check_suid(new_id), "Improper conversation ID generated"


@pytest.mark.usefixtures("_load_config")
def test_retrieve_conversation_id_existing_id():
    """Check the function to retrieve conversation ID when one already exists."""
    old_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes", conversation_id=old_id)
    new_id = ols.retrieve_conversation_id(llm_request)
    assert new_id == old_id, "Old (existing) ID should be retrieved."


@pytest.mark.usefixtures("_load_config")
def test_retrieve_previous_input_no_previous_history():
    """Check how function to retrieve previous input handle empty history."""
    llm_request = LLMRequest(query="Tell me about Kubernetes", conversation_id="")
    assert llm_request.conversation_id is not None
    llm_input = ols.retrieve_previous_input(
        constants.DEFAULT_USER_UID, llm_request.conversation_id
    )
    assert llm_input == []


@pytest.mark.usefixtures("_load_config")
def test_retrieve_previous_input_empty_user_id():
    """Check how function to retrieve previous input handle empty user ID."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes", conversation_id=conversation_id
    )
    assert llm_request.conversation_id is not None
    # cache must check if user ID is correct
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.retrieve_previous_input("", llm_request.conversation_id)
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.retrieve_previous_input(None, llm_request.conversation_id)


@pytest.mark.usefixtures("_load_config")
def test_retrieve_previous_input_improper_user_id():
    """Check how function to retrieve previous input handle improper user ID."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes", conversation_id=conversation_id
    )
    assert llm_request.conversation_id is not None
    # cache must check if user ID is correct
    with pytest.raises(HTTPException, match="Invalid user ID improper_user_id"):
        ols.retrieve_previous_input("improper_user_id", llm_request.conversation_id)


@pytest.mark.usefixtures("_load_config")
def test_retrieve_previous_input_for_previous_history():
    """Check how function to retrieve previous input handle existing history."""
    conversation_id = suid.get_suid()
    with patch("ols.config.conversation_cache.get") as get:
        get.return_value = "input"
        llm_request = LLMRequest(
            query="Tell me about Kubernetes", conversation_id=conversation_id
        )
        assert llm_request.conversation_id is not None
        previous_input = ols.retrieve_previous_input(
            constants.DEFAULT_USER_UID, llm_request.conversation_id
        )
        assert previous_input == "input"


@pytest.mark.usefixtures("_load_config")
def test_retrieve_attachments_on_no_input():
    """Check the function to retrieve attachments from payload when attachments are not send."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes", conversation_id=conversation_id
    )
    attachments = ols.retrieve_attachments(llm_request)
    # empty list should be returned
    assert attachments is not None
    assert len(attachments) == 0


@pytest.mark.usefixtures("_load_config")
def test_retrieve_attachments_on_empty_list():
    """Check the function to retrieve attachments from payload when list of attachments is empty."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes",
        conversation_id=conversation_id,
        attachments=[],
    )
    attachments = ols.retrieve_attachments(llm_request)
    # empty list should be returned
    assert attachments is not None
    assert len(attachments) == 0


@pytest.mark.usefixtures("_load_config")
def test_retrieve_attachments_on_proper_input():
    """Check the function to retrieve attachments from payload."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes",
        conversation_id=conversation_id,
        attachments=[
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="this is attachment",
            ),
        ],
    )
    attachments = ols.retrieve_attachments(llm_request)
    # empty list should be returned
    assert attachments is not None
    assert len(attachments) == 1

    expected = Attachment(
        attachment_type="log", content_type="text/plain", content="this is attachment"
    )
    assert attachments[0] == expected


@pytest.mark.usefixtures("_load_config")
def test_retrieve_attachments_on_improper_attachment_type():
    """Check the function to retrieve attachments from payload."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes",
        conversation_id=conversation_id,
        attachments=[
            Attachment(
                attachment_type="not-correct-one",
                content_type="text/plain",
                content="this is attachment",
            ),
        ],
    )
    with pytest.raises(
        HTTPException, match="Attachment with improper type not-correct-one detected"
    ):
        ols.retrieve_attachments(llm_request)


@pytest.mark.usefixtures("_load_config")
def test_retrieve_attachments_on_improper_content_type():
    """Check the function to retrieve attachments from payload."""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(
        query="Tell me about Kubernetes",
        conversation_id=conversation_id,
        attachments=[
            Attachment(
                attachment_type="log",
                content_type="not/known",
                content="this is attachment",
            ),
        ],
    )
    with pytest.raises(
        HTTPException, match="Attachment with improper content type not/known detected"
    ):
        ols.retrieve_attachments(llm_request)


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history():
    """Test if operation to store conversation history to cache is called."""
    conversation_id = suid.get_suid()
    skip_user_id_check = False
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query)
    response = ""
    topic_summary = "test summary"

    with patch("ols.config.conversation_cache.insert_or_append") as insert_or_append:
        ols.store_conversation_history(
            constants.DEFAULT_USER_UID,
            conversation_id,
            llm_request,
            response,
            [],
            [],
            {},
            topic_summary,
        )

        expected_history = CacheEntry(query=HumanMessage(query))
        insert_or_append.assert_called_with(
            constants.DEFAULT_USER_UID,
            conversation_id,
            expected_history,
            topic_summary,
            skip_user_id_check,
        )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_some_response():
    """Test if operation to store conversation history to cache is called."""
    user_id = "1234"
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query)
    response = "*response*"
    topic_summary = "some summary"
    skip_user_id_check = False

    with patch("ols.config.conversation_cache.insert_or_append") as insert_or_append:
        ols.store_conversation_history(
            user_id, conversation_id, llm_request, response, [], [], {}, topic_summary
        )

        expected_history = CacheEntry(
            query=HumanMessage(query), response=AIMessage(response)
        )
        insert_or_append.assert_called_with(
            user_id,
            conversation_id,
            expected_history,
            topic_summary,
            skip_user_id_check,
        )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_store_metadata():
    """Test if operation to store conversation history to cache is called."""
    user_id = "1234"
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    provider = "some-provider"
    model = "some-model"
    llm_request = LLMRequest(query=query, provider=provider, model=model)
    response = "*response*"
    mock_rag_chunk = [
        RagChunk(text="text1", doc_url="url-b", doc_title="title-b"),
        RagChunk(text="text2", doc_url="url-b", doc_title="title-b"),  # duplicate doc
        RagChunk(text="text3", doc_url="url-a", doc_title="title-a"),
    ]
    skip_user_id_check = False
    start_time = time.time()
    response_time = time.time()
    timestamps = {"start": start_time, "generate response": response_time}
    topic_summary = "some summary"

    with patch("ols.config.conversation_cache.insert_or_append") as insert_or_append:
        ols.store_conversation_history(
            user_id,
            conversation_id,
            llm_request,
            response,
            mock_rag_chunk,
            [],
            timestamps,
            topic_summary,
        )

        expected_history = CacheEntry(
            query=HumanMessage(
                content=llm_request.query, response_metadata={"created_at": start_time}
            ),
            response=AIMessage(
                content=response,
                response_metadata={
                    "created_at": response_time,
                    "model": model,
                    "provider": provider,
                },
                additional_kwargs={
                    "referenced_documents": [
                        {"doc_title": "title-b", "doc_url": "url-b"},
                        {"doc_title": "title-a", "doc_url": "url-a"},
                    ]
                },
            ),
        )
        insert_or_append.assert_called_with(
            user_id,
            conversation_id,
            expected_history,
            topic_summary,
            skip_user_id_check,
        )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_empty_user_id():
    """Test if basic input verification is done during history store operation."""
    user_id = ""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(
            user_id, conversation_id, llm_request, "", [], [], {}, ""
        )
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(
            user_id, conversation_id, llm_request, None, [], [], {}, ""
        )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_improper_user_id():
    """Test if basic input verification is done during history store operation."""
    user_id = "::::"
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(
            user_id, conversation_id, llm_request, "", [], [], {}, ""
        )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_improper_conversation_id():
    """Test if basic input verification is done during history store operation."""
    conversation_id = "::::"
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid conversation ID"):
        ols.store_conversation_history(
            constants.DEFAULT_USER_UID, conversation_id, llm_request, "", [], [], {}, ""
        )


@pytest.mark.usefixtures("_load_config")
def test_validate_question_valid_kw():
    """Check the behaviour of validate_question function using valid keyword."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes?"
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.KEYWORD,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as llm_validate_question_mock,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        resp = ols.validate_question(conversation_id, llm_request)

        assert resp
        assert llm_validate_question_mock.call_count == 0


@pytest.mark.usefixtures("_load_config")
def test_validate_question_too_long_query():
    """Check the behaviour of validate_question function with too long query."""
    # This test case is applicable only for LLM based query validation.
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes?"
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question",
            side_effect=PromptTooLongError("Prompt length 10000 exceeds LLM"),
        ),
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        # PromptTooLongError should be caught and HTTPException needs to be raised
        with pytest.raises(
            HTTPException, match="413: {'response': 'Prompt is too long'"
        ):
            ols.validate_question(conversation_id, llm_request)


@pytest.mark.usefixtures("_load_config")
def test_validate_question_invalid_kw():
    """Check the behaviour of validate_question function using invalid keyword."""
    conversation_id = suid.get_suid()
    query = "What does 42 signify ?"
    with patch(
        "ols.app.endpoints.ols.config.ols_config.query_validation_method",
        constants.QueryValidationMethod.KEYWORD,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        resp = ols.validate_question(conversation_id, llm_request)
        assert not resp


@pytest.mark.usefixtures("_load_config")
def test_validate_question_llm():
    """Check the behaviour of validate_question function with LLM."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as validate_question_mock,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        ols.validate_question(conversation_id, llm_request)
        validate_question_mock.assert_called_with(conversation_id, query)


@pytest.mark.usefixtures("_load_config")
def test_validate_question_on_configuration_error_llm():
    """Check the behaviour of validate_question function when wrong configuration is detected."""
    # This test case is applicable only for LLM based query validation.
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as validate_question_mock,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        validate_question_mock.side_effect = LLMConfigurationError

        # HTTP exception should be raises
        with pytest.raises(HTTPException, match="Unable to process this request"):
            ols.validate_question(conversation_id, llm_request)


@pytest.mark.usefixtures("_load_config")
def test_validate_question_on_validation_error():
    """Check the behaviour of validate_question function when query is not validated properly."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as validate_question_mock,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        validate_question_mock.side_effect = (
            ValueError  # any exception except HTTPException can be used there
        )

        # HTTP exception should be raises
        with pytest.raises(HTTPException, match="Error while validating question"):
            ols.validate_question(conversation_id, llm_request)


def test_validate_question_disabled():
    """Check the behaviour of validate_question function when it is disabled."""
    # This is the default behavior; no query validation.
    conversation_id = suid.get_suid()
    query = "What does 42 signify ?"
    with (
        patch(
            "ols.app.endpoints.ols._validate_question_keyword"
        ) as validate_question_kw_mock,
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as validate_question_llm_mock,
    ):
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)
        resp = ols.validate_question(conversation_id, llm_request)

        assert validate_question_llm_mock.call_count == 0
        assert validate_question_kw_mock.call_count == 0
        assert resp


@pytest.mark.usefixtures("_load_config")
def test_query_filter_no_redact_filters():
    """Test the function to redact query when no filters are setup."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    result = ols.redact_query(conversation_id, llm_request)
    assert result is not None
    assert result.query == query


@pytest.mark.usefixtures("_load_config")
def test_query_filter_with_one_redact_filter():
    """Test the function to redact query when filter is setup."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)

    # use one custom filter
    assert config.ols_config.query_filters is not None
    q = Redactor(config.ols_config.query_filters)
    q.regex_filters = [
        RegexFilter(
            pattern=re.compile(r"Kubernetes"),
            name="kubernetes-filter",
            replace_with="FooBar",
        )
    ]
    config._query_filters = q

    result = ols.redact_query(conversation_id, llm_request)
    assert result is not None
    assert result.query == "Tell me about FooBar"


@pytest.mark.usefixtures("_load_config")
def test_query_filter_with_two_redact_filters():
    """Test the function to redact query when multiple filters are setup."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)

    # use two custom filters
    assert config.ols_config.query_filters is not None
    q = Redactor(config.ols_config.query_filters)
    q.regex_filters = [
        RegexFilter(
            pattern=re.compile(r"Kubernetes"),
            name="kubernetes-filter",
            replace_with="FooBar",
        ),
        RegexFilter(
            pattern=re.compile(r"FooBar"),
            name="FooBar-filter",
            replace_with="Baz",
        ),
    ]
    config._query_filters = q

    result = ols.redact_query(conversation_id, llm_request)
    assert result is not None
    assert result.query == "Tell me about Baz"


@pytest.mark.usefixtures("_load_config")
def test_query_filter_on_redact_error():
    """Test the function to redact query when redactor raises an error."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    with pytest.raises(HTTPException, match="Error while redacting query"):
        with patch("ols.utils.redactor.Redactor.redact", side_effect=Exception):
            ols.redact_query(conversation_id, llm_request)


@pytest.mark.usefixtures("_load_config")
def test_attachments_redact_on_no_filters_defined():
    """Test the function to redact attachments when no filters are setup."""
    conversation_id = suid.get_suid()
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by Kubernetes",
        ),
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by OpenShift",
        ),
    ]
    # try to redact all attachments
    redacted = ols.redact_attachments(conversation_id, attachments)
    assert redacted is not None

    # no filters are set up, so the redacted attachments must
    # be the same as original ones
    assert redacted == attachments


@pytest.mark.usefixtures("_load_config")
def test_attachments_redact_with_one_filter_defined():
    """Test the function to redact attachments when one filter is setup."""
    conversation_id = suid.get_suid()
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by Kubernetes",
        ),
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by OpenShift",
        ),
    ]

    # use two custom filters
    assert config.ols_config.query_filters is not None
    q = Redactor(config.ols_config.query_filters)
    q.regex_filters = [
        RegexFilter(
            pattern=re.compile(r"Kubernetes"),
            name="kubernetes-filter",
            replace_with="FooBar",
        ),
    ]
    config._query_filters = q

    # try to redact all attachments
    redacted = ols.redact_attachments(conversation_id, attachments)
    assert redacted is not None

    # one filter must be applied
    assert redacted[0] == Attachment(
        attachment_type="log",
        content_type="text/plain",
        content="Log created by FooBar",
    )
    # no filters should be applied
    assert redacted[1] == Attachment(
        attachment_type="log",
        content_type="text/plain",
        content="Log created by OpenShift",
    )


@pytest.mark.usefixtures("_load_config")
def test_attachments_redact_with_two_filters_defined():
    """Test the function to redact attachments when two filters are setup."""
    conversation_id = suid.get_suid()
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by Kubernetes",
        ),
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by OpenShift",
        ),
    ]

    # use two custom filters
    assert config.ols_config.query_filters is not None
    q = Redactor(config.ols_config.query_filters)
    q.regex_filters = [
        RegexFilter(
            pattern=re.compile(r"Kubernetes"),
            name="kubernetes-filter",
            replace_with="FooBar",
        ),
        RegexFilter(
            pattern=re.compile(r"FooBar"),
            name="FooBar-filter",
            replace_with="Baz",
        ),
    ]
    config._query_filters = q

    # try to redact all attachments
    redacted = ols.redact_attachments(conversation_id, attachments)
    assert redacted is not None

    # both filters must be applied
    assert redacted[0] == Attachment(
        attachment_type="log",
        content_type="text/plain",
        content="Log created by Baz",
    )
    # no filters should be applied
    assert redacted[1] == Attachment(
        attachment_type="log",
        content_type="text/plain",
        content="Log created by OpenShift",
    )


@pytest.mark.usefixtures("_load_config")
def test_attachments_redact_on_redact_error():
    """Test the function to redact attachments when redactor raises an error."""
    conversation_id = suid.get_suid()
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by Kubernetes",
        ),
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="Log created by OpenShift",
        ),
    ]

    # try to redact all attachments
    with pytest.raises(HTTPException, match="Error while redacting attachment"):
        with patch("ols.utils.redactor.Redactor.redact", side_effect=Exception):
            ols.redact_attachments(conversation_id, attachments)


@pytest.mark.usefixtures("_load_config")
def test_conversation_request(auth):
    """Test conversation request API endpoint."""
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as mock_validate_question,
        patch(
            "ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response"
        ) as mock_summarize,
        patch("ols.config.conversation_cache.get"),
        patch("ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"),
    ):
        # valid question
        mock_validate_question.return_value = True
        mock_response = (
            "Kubernetes is an open-source container-orchestration system..."  # summary
        )
        mock_summarize.return_value = SummarizerResponse(
            response=mock_response,
            rag_chunks=[],
            history_truncated=False,
            token_counter=None,
        )
        llm_request = LLMRequest(query="Tell me about Kubernetes")
        response = ols.conversation_request(llm_request, auth)
        assert (
            response.response
            == "Kubernetes is an open-source container-orchestration system..."
        )
        assert suid.check_suid(
            response.conversation_id
        ), "Improper conversation ID returned"

        # invalid question
        mock_validate_question.return_value = False
        llm_request = LLMRequest(query="Generate a yaml")
        response = ols.conversation_request(llm_request, auth)
        assert response.response == prompts.INVALID_QUERY_RESP
        assert suid.check_suid(
            response.conversation_id
        ), "Improper conversation ID returned"

        # validation failure
        mock_validate_question.side_effect = HTTPException
        with pytest.raises(HTTPException) as excinfo:
            llm_request = LLMRequest(query="Generate a yaml")
            response = ols.conversation_request(llm_request, auth)
            assert excinfo.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
            assert len(response.conversation_id) == 0


@pytest.mark.usefixtures("_load_config")
def test_conversation_request_dedup_ref_docs(auth):
    """Test deduplication of referenced docs."""
    with (
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as mock_validate_question,
        patch(
            "ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response"
        ) as mock_summarize,
        patch("ols.config.conversation_cache.get"),
        patch("ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"),
    ):
        mock_rag_chunk = [
            RagChunk(text="text1", doc_url="url-b", doc_title="title-b"),
            RagChunk(
                text="text2", doc_url="url-b", doc_title="title-b"
            ),  # duplicate doc
            RagChunk(text="text3", doc_url="url-a", doc_title="title-a"),
        ]
        mock_validate_question.return_value = True
        mock_summarize.return_value = SummarizerResponse(
            response="some response",
            rag_chunks=mock_rag_chunk,
            history_truncated=False,
            token_counter=None,
        )
        llm_request = LLMRequest(query="some query")
        response = ols.conversation_request(llm_request, auth)

        assert len(response.referenced_documents) == 2
        assert response.referenced_documents[0].doc_url == "url-b"
        assert response.referenced_documents[0].doc_title == "title-b"
        assert response.referenced_documents[1].doc_url == "url-a"
        assert response.referenced_documents[1].doc_title == "title-a"


@pytest.mark.usefixtures("_load_config")
def test_conversation_request_on_wrong_configuration(auth):
    """Test conversation request API endpoint."""
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.query_validation_method",
            constants.QueryValidationMethod.LLM,
        ),
        patch(
            "ols.src.query_helpers.question_validator.QuestionValidator.validate_question"
        ) as mock_validate_question,
        patch("ols.config.conversation_cache.get"),
    ):
        # mock invalid configuration
        message = "wrong model is configured"
        mock_validate_question.side_effect = Mock(
            side_effect=LLMConfigurationError(message)
        )
        llm_request = LLMRequest(query="Tell me about Kubernetes")

        # call must fail because we mocked invalid configuration state
        with pytest.raises(HTTPException, match="Unable to process this request"):
            ols.conversation_request(llm_request, auth)


@pytest.mark.usefixtures("_load_config")
def test_question_validation_in_conversation_start(auth):
    """Test if question validation is skipped in follow-up conversation."""
    with (
        patch(
            "ols.app.endpoints.ols.retrieve_previous_input", new=Mock(return_value=[])
        ),
        patch(
            "ols.app.endpoints.ols.validate_question",
            new=Mock(return_value=False),
        ),
        patch("ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"),
    ):
        # note the `validate_question` is patched to always return as `SUBJECT_REJECTED`
        # this should resolve in rejection in summarization
        conversation_id = suid.get_suid()
        query = "some elaborate question"
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)

        response = ols.conversation_request(llm_request, auth)

        assert response.response.startswith(prompts.INVALID_QUERY_RESP)


@pytest.mark.usefixtures("_load_config")
def test_no_question_validation_in_follow_up_conversation(auth):
    """Test if question validation is skipped in follow-up conversation."""
    with (
        patch(
            "ols.app.endpoints.ols.retrieve_previous_input",
            new=Mock(return_value=[CacheEntry(query=HumanMessage("some question"))]),
        ),
        patch(
            "ols.app.endpoints.ols.validate_question",
            new=Mock(return_value=constants.SUBJECT_REJECTED),
        ),
        patch(
            "ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response"
        ) as mock_summarize,
        patch("ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"),
    ):
        # note the `validate_question` is patched to always return as `SUBJECT_REJECTED`
        # but as it is not the first question, it should proceed to summarization
        mock_summarize.return_value = SummarizerResponse(
            "some elaborate answer",
            [],
            False,
            token_counter=None,
        )
        conversation_id = suid.get_suid()
        query = "some elaborate question"
        llm_request = LLMRequest(query=query, conversation_id=conversation_id)

        response = ols.conversation_request(llm_request, auth)

        assert response.response == "some elaborate answer"


@pytest.mark.usefixtures("_load_config")
def test_conversation_request_invalid_subject(auth):
    """Test how generate_response function checks validation results."""
    with (
        patch("ols.app.endpoints.ols.validate_question") as mock_validate,
        patch("ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"),
    ):
        # prepare arguments for DocsSummarizer
        llm_request = LLMRequest(query="Tell me about Kubernetes")

        mock_validate.return_value = False
        response = ols.conversation_request(llm_request, auth)
        assert response.response == prompts.INVALID_QUERY_RESP
        assert len(response.referenced_documents) == 0
        assert not response.truncated


@pytest.mark.usefixtures("_load_config")
def test_generate_response_valid_subject():
    """Test how generate_response function checks validation results."""
    # mock the DocsSummarizer
    mock_response = (
        "Kubernetes is an open-source container-orchestration system..."  # summary
    )
    with patch(
        "ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response"
    ) as mock_summarize:
        mock_summarize.return_value = SummarizerResponse(
            mock_response,
            [],
            False,
            token_counter=None,
        )

        # prepare arguments for DocsSummarizer
        conversation_id = suid.get_suid()
        llm_request = LLMRequest(query="Tell me about Kubernetes")
        previous_input = []

        # try to get response
        summarizer_response = ols.generate_response(
            conversation_id, llm_request, previous_input
        )

        # check the response
        assert "Kubernetes" in summarizer_response.response
        assert summarizer_response.rag_chunks == []
        assert summarizer_response.history_truncated is False


@pytest.mark.usefixtures("_load_config")
def test_generate_response_on_summarizer_error():
    """Test how generate_response function checks validation results."""
    with patch(
        "ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response"
    ) as mock_summarize:
        # mock the DocsSummarizer
        mock_summarize.side_effect = Exception  # any exception might occur

        # prepare arguments for DocsSummarizer
        conversation_id = suid.get_suid()

        llm_request = LLMRequest(query="Tell me about Kubernetes")
        previous_input = None

        # try to get response
        with pytest.raises(HTTPException, match=DEFAULT_ERROR_MESSAGE):
            ols.generate_response(conversation_id, llm_request, previous_input)


def test_generate_response_unknown_validation_result():
    """Test how generate_response function checks validation results."""
    # prepare arguments for DocsSummarizer
    conversation_id = suid.get_suid()

    with patch(
        "ols.src.query_helpers.question_validator.QuestionValidator.validate_question",
        side_effect=Exception("mocked exception"),
    ):
        llm_request = LLMRequest(query="Tell me about Kubernetes")
        previous_input = None

        # try to get response
        with pytest.raises(HTTPException, match=DEFAULT_ERROR_MESSAGE):
            ols.generate_response(conversation_id, llm_request, previous_input)


@pytest.fixture
def transcripts_location(tmpdir):
    """Fixture sets feedback location to tmpdir and return the path."""
    config.ols_config.user_data_collection = UserDataCollection(
        transcripts_disabled=False, transcripts_storage=tmpdir.strpath
    )
    return tmpdir.strpath


def test_transcripts_are_not_stored_when_disabled(transcripts_location, auth):
    """Test nothing is stored when the transcript collection is disabled."""
    with (
        patch(
            "ols.app.endpoints.ols.config.ols_config.user_data_collection.transcripts_disabled",
            True,
        ),
        patch(
            "ols.app.endpoints.ols.validate_question",
            return_value=True,
        ),
        patch(
            "ols.app.endpoints.ols.generate_response",
            return_value=SummarizerResponse("something", [], False, None),
        ),
        patch(
            "ols.app.endpoints.ols.store_conversation_history",
            return_value=None,
        ),
        patch(
            "ols.app.endpoints.ols.get_topic_summary",
            return_value="some summary",
        ),
    ):
        llm_request = LLMRequest(query="Tell me about Kubernetes")
        response = ols.conversation_request(llm_request, auth)
        assert response
        assert response.response == "something"

        transcript_dir = Path(transcripts_location)
        assert list(transcript_dir.glob("*/*/*.json")) == []


def test_construct_transcripts_path(transcripts_location):
    """Test for the helper function construct_transcripts_path."""
    user_id = "00000000-0000-0000-0000-000000000000"
    conversation_id = "11111111-1111-1111-1111-111111111111"
    path = ols.construct_transcripts_path(user_id, conversation_id)

    assert str(path.resolve()).endswith(f"{user_id}/{conversation_id}")


def test_store_transcript(transcripts_location):
    """Test transcript is successfully stored."""
    user_id = suid.get_suid()
    conversation_id = suid.get_suid()
    query_is_valid = True
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    response = "Kubernetes is ..."
    rag_chunks = [
        RagChunk(text="text1", doc_url="url1", doc_title="title1"),
        RagChunk(text="text2", doc_url="url2", doc_title="title2"),
    ]
    truncated = True
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="this is attachment",
        )
    ]

    ols.store_transcript(
        user_id,
        conversation_id,
        query_is_valid,
        query,
        llm_request,
        response,
        rag_chunks,
        truncated,
        attachments,
    )

    transcript_dir = Path(transcripts_location) / user_id / conversation_id

    # check file exists in the expected path
    assert transcript_dir.exists()
    transcripts = list(transcript_dir.glob("*.json"))
    assert len(transcripts) == 1

    # check the transcript json content
    with open(transcripts[0]) as f:
        transcript = json.loads(f.read())
    # we don't really care about the timestamp, so let's just set it to
    # a fixed value
    transcript["metadata"]["timestamp"] = "fake-timestamp"
    assert transcript == {
        "metadata": {
            "provider": None,
            "model": None,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "timestamp": "fake-timestamp",
        },
        "redacted_query": query,
        "query_is_valid": query_is_valid,
        "llm_response": response,
        "rag_chunks": [
            {"text": "text1", "doc_url": "url1", "doc_title": "title1"},
            {"text": "text2", "doc_url": "url2", "doc_title": "title2"},
        ],
        "truncated": truncated,
        "attachments": [
            {
                "attachment_type": "log",
                "content_type": "text/plain",
                "content": "this is attachment",
            }
        ],
    }


@pytest.mark.usefixtures("_load_config")
def test_get_topic_summary_valid_subject():
    """Test how generate_response function checks validation results."""
    with patch(
        "ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"
    ) as mock_summarize_topic:
        # mock the TopicSummarizer
        mock_response = "OpenShift vs Kubernetes Comparison"
        mock_summarize_topic.return_value = mock_response

        # prepare arguments for TopicSummarizer
        conversation_id = suid.get_suid()
        llm_request = LLMRequest(
            query="Tell me about differences between Kubernetes and Openshift"
        )

        # try to get response
        summarizer_response = ols.get_topic_summary(conversation_id, llm_request)

        # check the response
        assert summarizer_response == mock_response


@pytest.mark.usefixtures("_load_config")
def test_get_topic_summary_on_summarizer_error():
    """Test how generate_response function checks validation results."""
    with patch(
        "ols.src.query_helpers.topic_summarizer.TopicSummarizer.summarize_topic"
    ) as mock_summarize_topic:
        # mock the TopicSummarizer
        mock_summarize_topic.side_effect = Exception  # any exception might occur

        # prepare arguments for TopicSummarizer
        conversation_id = suid.get_suid()

        llm_request = LLMRequest(query="Tell me about Kubernetes")
        previous_input = None

        # try to get response
        with pytest.raises(HTTPException, match=DEFAULT_ERROR_MESSAGE):
            ols.generate_response(conversation_id, llm_request, previous_input)


def test_calc_input_tokens_no_token_counter():
    """Test the helper function calc_input_tokens."""
    token_counter = None
    tokens = ols.calc_input_tokens(token_counter)
    assert tokens == 0


def test_calc_input_tokens_for_token_counter():
    """Test the helper function calc_input_tokens."""
    token_counter = TokenCounter(input_tokens=100)
    tokens = ols.calc_input_tokens(token_counter)
    assert tokens == 100


def test_calc_output_tokens_no_token_counter():
    """Test the helper function calc_output_tokens."""
    token_counter = None
    tokens = ols.calc_output_tokens(token_counter)
    assert tokens == 0


def test_calc_output_tokens_for_token_counter():
    """Test the helper function calc_output_tokens."""
    token_counter = TokenCounter(output_tokens=100)
    tokens = ols.calc_output_tokens(token_counter)
    assert tokens == 100


def test_consume_tokens_no_quota_limiters():
    """Test the function consume_tokens if no quota limiters are configured."""
    quota_limiters = None
    ols.consume_tokens(quota_limiters, None, "user_id", 1, 1, "", "")


def test_consume_tokens_empty_quota_limiters():
    """Test the function consume_tokens if empty list of quota limiters are configured."""
    quota_limiters = []
    ols.consume_tokens(quota_limiters, None, "user_id", 1, 1, "", "")


def test_consume_tokens_with_existing_quota_limiter():
    """Test the function consume_tokens for configured quota limiter."""

    class MockQuotaLimiter:
        def consume_tokens(self, input_tokens=0, output_tokens=0, subject_id=""):
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens
            self._subject_id = subject_id

    mock_quota_limiter = MockQuotaLimiter()

    quota_limiters = [mock_quota_limiter]
    token_usage_history = None
    input_tokens = 1
    output_tokens = 2
    user_id = "user_id"
    provider = "provider"
    model = "model"
    ols.consume_tokens(
        quota_limiters,
        token_usage_history,
        user_id,
        input_tokens,
        output_tokens,
        provider,
        model,
    )
    assert mock_quota_limiter._input_tokens == input_tokens
    assert mock_quota_limiter._output_tokens == output_tokens
    assert mock_quota_limiter._subject_id == user_id


def test_consume_tokens_multiple_quota_limiters():
    """Test the function consume_tokens for more configured quota limiter."""

    class MockQuotaLimiter:
        def consume_tokens(self, input_tokens=0, output_tokens=0, subject_id=""):
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens
            self._subject_id = subject_id

    mock_quota_limiter1 = MockQuotaLimiter()
    mock_quota_limiter2 = MockQuotaLimiter()

    quota_limiters = [mock_quota_limiter1, mock_quota_limiter2]
    token_usage_history = None
    input_tokens = 1
    output_tokens = 2
    user_id = "user_id"
    provider = "provider"
    model = "model"
    ols.consume_tokens(
        quota_limiters,
        token_usage_history,
        user_id,
        input_tokens,
        output_tokens,
        provider,
        model,
    )

    for mock_quota_limiter in [mock_quota_limiter1, mock_quota_limiter2]:
        assert mock_quota_limiter._input_tokens == input_tokens
        assert mock_quota_limiter._output_tokens == output_tokens
        assert mock_quota_limiter._subject_id == user_id


def test_consume_tokens_token_usage_history():
    """Test the function consume_tokens when token_usage_history is setup."""

    class MockTokenUsageHistory:
        def consume_tokens(
            self, user_id="", provider="", model="", input_tokens=0, output_tokens=0
        ):
            self._user_id = user_id
            self._provider = provider
            self._model = model
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens

    quota_limiters = []
    token_usage_history = MockTokenUsageHistory()
    input_tokens = 1
    output_tokens = 2
    user_id = "user_id"
    provider = "provider"
    model = "model"
    ols.consume_tokens(
        quota_limiters,
        token_usage_history,
        user_id,
        input_tokens,
        output_tokens,
        provider,
        model,
    )

    assert token_usage_history._user_id == user_id
    assert token_usage_history._provider == provider
    assert token_usage_history._model == model
    assert token_usage_history._input_tokens == input_tokens
    assert token_usage_history._output_tokens == output_tokens


def test_consume_tokens_token_limiters_and_token_usage_history():
    """Test the function consume_tokens when token_usage_history is setup."""

    class MockQuotaLimiter:
        def consume_tokens(self, input_tokens=0, output_tokens=0, subject_id=""):
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens
            self._subject_id = subject_id

    class MockTokenUsageHistory:
        def consume_tokens(
            self, user_id="", provider="", model="", input_tokens=0, output_tokens=0
        ):
            self._user_id = user_id
            self._provider = provider
            self._model = model
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens

    mock_quota_limiter1 = MockQuotaLimiter()
    mock_quota_limiter2 = MockQuotaLimiter()

    quota_limiters = [mock_quota_limiter1, mock_quota_limiter2]
    token_usage_history = MockTokenUsageHistory()
    input_tokens = 1
    output_tokens = 2
    user_id = "user_id"
    provider = "provider"
    model = "model"
    ols.consume_tokens(
        quota_limiters,
        token_usage_history,
        user_id,
        input_tokens,
        output_tokens,
        provider,
        model,
    )

    assert token_usage_history._user_id == user_id
    assert token_usage_history._provider == provider
    assert token_usage_history._model == model
    assert token_usage_history._input_tokens == input_tokens
    assert token_usage_history._output_tokens == output_tokens

    for mock_quota_limiter in [mock_quota_limiter1, mock_quota_limiter2]:
        assert mock_quota_limiter._input_tokens == input_tokens
        assert mock_quota_limiter._output_tokens == output_tokens
        assert mock_quota_limiter._subject_id == user_id


def test_check_token_available_no_quota_limiters():
    """Test the function check_tokens_available if no quota limiters are configured."""
    quota_limiters = None
    ols.check_tokens_available(quota_limiters, "user_id")


def test_check_token_available_empty_limiters():
    """Test the function check_tokens_available if emply list of quota limiters are configured."""
    quota_limiters = []
    ols.check_tokens_available(quota_limiters, "user_id")


def test_check_token_available_configured_quota_limiter():
    """Test the function check_tokens_available if one quota limiter is configured."""

    class MockQuotaLimiter:
        def ensure_available_quota(self, subject_id=""):
            self._subject_id = subject_id

    mock_quota_limiter = MockQuotaLimiter()
    quota_limiters = [mock_quota_limiter]
    user_id = "user_id"

    ols.check_tokens_available(quota_limiters, user_id)
    assert mock_quota_limiter._subject_id == user_id


def test_check_token_available_on_exceed_error():
    """Test the function check_tokens_available if quota exceed error is thrown."""

    class MockQuotaLimiter:
        def ensure_available_quota(self, subject_id=""):
            raise Exception("Raised exception")

    mock_quota_limiter = MockQuotaLimiter()
    quota_limiters = [mock_quota_limiter]
    user_id = "user_id"

    expected = (
        "500: {'response': 'The quota has been exceeded', 'cause': 'Raised exception'}"
    )
    with pytest.raises(HTTPException, match=expected):
        ols.check_tokens_available(quota_limiters, user_id)


def test_get_available_quotas_no_quota_limiters():
    """Test the function get_available_quotas when no quota limiters are setup."""
    quotas = ols.get_available_quotas(None, "user_id")
    assert quotas == {}


def test_get_available_quotas_one_quota_limiter():
    """Test the function get_available_quotas when one quota limiter is setup."""

    class MockQuotaLimiter:
        def __init__(self, available_quota=0):
            self._available_quota = available_quota

        def available_quota(self, subject_id=""):
            return self._available_quota

    mock_quota_limiter = MockQuotaLimiter(10)
    quotas = ols.get_available_quotas([mock_quota_limiter], "user_id")
    assert quotas == {
        "MockQuotaLimiter": 10,
    }


def test_get_available_quotas_two_quota_limiters():
    """Test the function get_available_quotas when two quota limiters are setup."""

    class MockQuotaLimiter1:
        def __init__(self, available_quota=0):
            self._available_quota = available_quota

        def available_quota(self, subject_id=""):
            return self._available_quota

    class MockQuotaLimiter2:
        def __init__(self, available_quota=0):
            self._available_quota = available_quota

        def available_quota(self, subject_id=""):
            return self._available_quota

    mock_quota_limiter_1 = MockQuotaLimiter1(10)
    mock_quota_limiter_2 = MockQuotaLimiter2(20)
    quotas = ols.get_available_quotas(
        [mock_quota_limiter_1, mock_quota_limiter_2], "user_id"
    )
    assert quotas == {
        "MockQuotaLimiter1": 10,
        "MockQuotaLimiter2": 20,
    }


def test_build_referenced_docs():
    """Test build_referenced_docs."""
    rag_chunks = [
        RagChunk("bla", "url_1", "title_1"),
        RagChunk("bla", "url_2", "title_2"),
        RagChunk("bla", "url_1", "title_1"),  # duplicate
    ]

    assert ols.build_referenced_docs(rag_chunks) == [
        {"doc_title": "title_1", "doc_url": "url_1"},
        {"doc_title": "title_2", "doc_url": "url_2"},
    ]
