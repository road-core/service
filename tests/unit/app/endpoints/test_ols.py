"""Unit tests for OLS endpoint."""

import json
import re
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from ols import config, constants
from ols.app.endpoints import ols
from ols.app.models.config import UserDataCollection
from ols.app.models.models import (
    Attachment,
    CacheEntry,
    LLMRequest,
    RagChunk,
    SummarizerResponse,
)
from ols.customize import prompts
from ols.src.llms.llm_loader import LLMConfigurationError
from ols.utils import suid
from ols.utils.errors_parsing import DEFAULT_ERROR_MESSAGE
from ols.utils.redactor import Redactor, RegexFilter
from ols.utils.token_handler import PromptTooLongError


@pytest.fixture(scope="function")
def _load_config():
    """Load config before unit tests."""
    config.reload_from_yaml_file("tests/config/test_app_endpoints.yaml")


@pytest.fixture
def auth():
    """Tuple containing user ID and user name, mocking auth. output."""
    # we can use any UUID, so let's use randomly generated one
    return ("2a3dfd17-1f42-4831-aaa6-e28e7cb8e26b", "name", False)


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
    llm_request = LLMRequest(query="Tell me about Kubernetes", conversation_id=None)
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
    # cache must check if user ID is correct
    with pytest.raises(HTTPException, match="Invalid user ID improper_user_id"):
        ols.retrieve_previous_input("improper_user_id", llm_request.conversation_id)


@pytest.mark.usefixtures("_load_config")
@patch("ols.config.conversation_cache.get")
def test_retrieve_previous_input_for_previous_history(get):
    """Check how function to retrieve previous input handle existing history."""
    conversation_id = suid.get_suid()
    get.return_value = "input"
    llm_request = LLMRequest(
        query="Tell me about Kubernetes", conversation_id=conversation_id
    )
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
            {
                "attachment_type": "log",
                "content_type": "text/plain",
                "content": "this is attachment",
            },
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
            {
                "attachment_type": "not-correct-one",
                "content_type": "text/plain",
                "content": "this is attachment",
            },
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
            {
                "attachment_type": "log",
                "content_type": "not/known",
                "content": "this is attachment",
            },
        ],
    )
    with pytest.raises(
        HTTPException, match="Attachment with improper content type not/known detected"
    ):
        ols.retrieve_attachments(llm_request)


@pytest.mark.usefixtures("_load_config")
@patch("ols.config.conversation_cache.insert_or_append")
def test_store_conversation_history(insert_or_append):
    """Test if operation to store conversation history to cache is called."""
    conversation_id = suid.get_suid()
    skip_user_id_check = False
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query)

    ols.store_conversation_history(
        constants.DEFAULT_USER_UID, conversation_id, llm_request, "", []
    )

    expected_history = CacheEntry(query=HumanMessage(query))
    insert_or_append.assert_called_with(
        constants.DEFAULT_USER_UID,
        conversation_id,
        expected_history,
        skip_user_id_check,
    )


@pytest.mark.usefixtures("_load_config")
@patch("ols.config.conversation_cache.insert_or_append")
def test_store_conversation_history_some_response(insert_or_append):
    """Test if operation to store conversation history to cache is called."""
    user_id = "1234"
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query)
    response = "*response*"
    skip_user_id_check = False

    ols.store_conversation_history(user_id, conversation_id, llm_request, response, [])

    expected_history = CacheEntry(
        query=HumanMessage(query), response=AIMessage(response)
    )
    insert_or_append.assert_called_with(
        user_id, conversation_id, expected_history, skip_user_id_check
    )


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_empty_user_id():
    """Test if basic input verification is done during history store operation."""
    user_id = ""
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(user_id, conversation_id, llm_request, "", [])
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(user_id, conversation_id, llm_request, None, [])


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_improper_user_id():
    """Test if basic input verification is done during history store operation."""
    user_id = "::::"
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid user ID"):
        ols.store_conversation_history(user_id, conversation_id, llm_request, "", [])


@pytest.mark.usefixtures("_load_config")
def test_store_conversation_history_improper_conversation_id():
    """Test if basic input verification is done during history store operation."""
    conversation_id = "::::"
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    with pytest.raises(HTTPException, match="Invalid conversation ID"):
        ols.store_conversation_history(
            constants.DEFAULT_USER_UID, conversation_id, llm_request, "", []
        )


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.KEYWORD,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
def test_validate_question_valid_kw(llm_validate_question_mock):
    """Check the behaviour of validate_question function using valid keyword."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes?"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    resp = ols.validate_question(conversation_id, llm_request)

    assert resp
    assert llm_validate_question_mock.call_count == 0


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch(
    "ols.src.query_helpers.question_validator.QuestionValidator.validate_question",
    side_effect=PromptTooLongError("Prompt length 10000 exceeds LLM"),
)
def test_validate_question_too_long_query(llm_validate_question_mock):
    """Check the behaviour of validate_question function with too long query."""
    # This test case is applicable only for LLM based query validation.
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes?"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    # PromptTooLongError should be caught and HTTPException needs to be raised
    with pytest.raises(HTTPException, match="413: {'response': 'Prompt is too long'"):
        ols.validate_question(conversation_id, llm_request)


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.KEYWORD,
)
def test_validate_question_invalid_kw():
    """Check the behaviour of validate_question function using invalid keyword."""
    conversation_id = suid.get_suid()
    query = "What does 42 signify ?"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    resp = ols.validate_question(conversation_id, llm_request)
    assert not resp


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
def test_validate_question_llm(validate_question_mock):
    """Check the behaviour of validate_question function with LLM."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    ols.validate_question(conversation_id, llm_request)
    validate_question_mock.assert_called_with(conversation_id, query)


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
def test_validate_question_on_configuration_error_llm(validate_question_mock):
    """Check the behaviour of validate_question function when wrong configuration is detected."""
    # This test case is applicable only for LLM based query validation.
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    validate_question_mock.side_effect = LLMConfigurationError

    # HTTP exception should be raises
    with pytest.raises(HTTPException, match="Unable to process this request"):
        ols.validate_question(conversation_id, llm_request)


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
def test_validate_question_on_validation_error(validate_question_mock):
    """Check the behaviour of validate_question function when query is not validated properly."""
    conversation_id = suid.get_suid()
    query = "Tell me about Kubernetes"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)
    validate_question_mock.side_effect = (
        ValueError  # any exception except HTTPException can be used there
    )

    # HTTP exception should be raises
    with pytest.raises(HTTPException, match="Error while validating question"):
        ols.validate_question(conversation_id, llm_request)


@patch("ols.app.endpoints.ols._validate_question_keyword")
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
def test_validate_question_disabled(
    validate_question_llm_mock, validate_question_kw_mock
):
    """Check the behaviour of validate_question function when it is disabled."""
    # This is the default behavior; no query validation.
    conversation_id = suid.get_suid()
    query = "What does 42 signify ?"
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
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
@patch("ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response")
@patch("ols.config.conversation_cache.get")
def test_conversation_request(
    mock_conversation_cache_get,
    mock_summarize,
    mock_validate_question,
    auth,
):
    """Test conversation request API endpoint."""
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
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
@patch("ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response")
@patch("ols.config.conversation_cache.get")
def test_conversation_request_dedup_ref_docs(
    mock_conversation_cache_get,
    mock_summarize,
    mock_validate_question,
    auth,
):
    """Test deduplication of referenced docs."""
    mock_rag_chunk = [
        RagChunk("text1", "url-b", "title-b"),
        RagChunk("text2", "url-b", "title-b"),  # duplicate doc
        RagChunk("text3", "url-a", "title-a"),
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
    assert response.referenced_documents[0].docs_url == "url-b"
    assert response.referenced_documents[0].title == "title-b"
    assert response.referenced_documents[1].docs_url == "url-a"
    assert response.referenced_documents[1].title == "title-a"


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.config.ols_config.query_validation_method",
    constants.QueryValidationMethod.LLM,
)
@patch("ols.src.query_helpers.question_validator.QuestionValidator.validate_question")
@patch("ols.config.conversation_cache.get")
def test_conversation_request_on_wrong_configuration(
    mock_conversation_cache_get,
    mock_validate_question,
    auth,
):
    """Test conversation request API endpoint."""
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
@patch("ols.app.endpoints.ols.retrieve_previous_input", new=Mock(return_value=None))
@patch(
    "ols.app.endpoints.ols.validate_question",
    new=Mock(return_value=False),
)
def test_question_validation_in_conversation_start(auth):
    """Test if question validation is skipped in follow-up conversation."""
    # note the `validate_question` is patched to always return as `SUBJECT_REJECTED`
    # this should resolve in rejection in summarization
    conversation_id = suid.get_suid()
    query = "some elaborate question"
    llm_request = LLMRequest(query=query, conversation_id=conversation_id)

    response = ols.conversation_request(llm_request, auth)

    assert response.response.startswith(prompts.INVALID_QUERY_RESP)


@pytest.mark.usefixtures("_load_config")
@patch(
    "ols.app.endpoints.ols.retrieve_previous_input",
    new=Mock(return_value=[CacheEntry(query=HumanMessage("some question"))]),
)
@patch(
    "ols.app.endpoints.ols.validate_question",
    new=Mock(return_value=constants.SUBJECT_REJECTED),
)
@patch("ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response")
def test_no_question_validation_in_follow_up_conversation(mock_summarize, auth):
    """Test if question validation is skipped in follow-up conversation."""
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
@patch("ols.app.endpoints.ols.validate_question")
def test_conversation_request_invalid_subject(mock_validate, auth):
    """Test how generate_response function checks validation results."""
    # prepare arguments for DocsSummarizer
    llm_request = LLMRequest(query="Tell me about Kubernetes")

    mock_validate.return_value = False
    response = ols.conversation_request(llm_request, auth)
    assert response.response == prompts.INVALID_QUERY_RESP
    assert len(response.referenced_documents) == 0
    assert not response.truncated


@pytest.mark.usefixtures("_load_config")
@patch("ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response")
def test_generate_response_valid_subject(mock_summarize):
    """Test how generate_response function checks validation results."""
    # mock the DocsSummarizer
    mock_response = (
        "Kubernetes is an open-source container-orchestration system..."  # summary
    )
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
@patch("ols.src.query_helpers.docs_summarizer.DocsSummarizer.create_response")
def test_generate_response_on_summarizer_error(mock_summarize):
    """Test how generate_response function checks validation results."""
    # mock the DocsSummarizer
    mock_summarize.side_effect = Exception  # any exception might occur

    # prepare arguments for DocsSummarizer
    conversation_id = suid.get_suid()
    llm_request = LLMRequest(query="Tell me about Kubernetes")
    previous_input = None

    # try to get response
    with pytest.raises(HTTPException, match=DEFAULT_ERROR_MESSAGE):
        ols.generate_response(conversation_id, llm_request, previous_input)


@patch(
    "ols.src.query_helpers.question_validator.QuestionValidator.validate_question",
    side_effect=Exception("mocked exception"),
)
def test_generate_response_unknown_validation_result(exc):
    """Test how generate_response function checks validation results."""
    # prepare arguments for DocsSummarizer
    conversation_id = suid.get_suid()
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
        RagChunk("text1", "url1", "title1"),
        RagChunk("text2", "url2", "title2"),
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
