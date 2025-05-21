"""Integration tests for /conversations REST API endpoints."""

# we add new attributes into pytest instance, which is not recognized
# properly by linters
# pyright: reportAttributeAccessIssue=false

from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

from ols import config
from ols.utils import suid
from tests.mock_classes.mock_langchain_interface import mock_langchain_interface
from tests.mock_classes.mock_llm_chain import mock_llm_chain
from tests.mock_classes.mock_llm_loader import mock_llm_loader


@pytest.fixture(scope="function")
def _setup():
    """Setups the test client."""
    config.reload_from_yaml_file("tests/config/config_for_integration_tests.yaml")

    # app.main need to be imported after the configuration is read
    from ols.app.main import app  # pylint: disable=C0415

    pytest.client = TestClient(app)


@pytest.mark.parametrize("endpoint", ("/conversations/{conversation_id}",))
def test_get_conversation_with_history(_setup, endpoint):
    """Test getting conversation history after creating some chat history."""
    ml = mock_langchain_interface("test response")
    with (
        patch(
            "ols.src.query_helpers.docs_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
        patch(
            "ols.src.query_helpers.query_helper.load_llm",
            new=mock_llm_loader(ml()),
        ),
        patch(
            "ols.src.query_helpers.topic_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
    ):
        # First create some conversation history
        conversation_id = suid.get_suid()

        # Make first query to create conversation
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conversation_id,
                "query": "First question",
            },
        )
        assert response.status_code == requests.codes.ok

        # Make second query to add to conversation
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conversation_id,
                "query": "Second question",
            },
        )
        assert response.status_code == requests.codes.ok

        # Now test getting the conversation history
        response = pytest.client.get(endpoint.format(conversation_id=conversation_id))
        assert response.status_code == requests.codes.ok

        history = response.json()["chat_history"]
        assert len(history) == 4  # 2 query + 2 response

        # Verify first message
        assert history[0]["content"] == "First question"
        assert history[0]["type"] == "human"
        # Verify first response
        assert history[1]["type"] == "ai"

        # Verify second message
        assert history[2]["content"] == "Second question"
        assert history[2]["type"] == "human"
        # Verify second response
        assert history[3]["type"] == "ai"


@pytest.mark.parametrize("endpoint", ("/conversations/{conversation_id}",))
def test_get_conversation_with_history_length(_setup, endpoint):
    """Test getting conversation history with history_length param."""
    ml = mock_langchain_interface("test response")
    with (
        patch(
            "ols.src.query_helpers.docs_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
        patch(
            "ols.src.query_helpers.query_helper.load_llm",
            new=mock_llm_loader(ml()),
        ),
        patch(
            "ols.src.query_helpers.topic_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
    ):
        # First create some conversation history
        conversation_id = suid.get_suid()

        # Make first query to create conversation
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conversation_id,
                "query": "First question",
            },
        )
        assert response.status_code == requests.codes.ok

        # Make second query to add to conversation
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conversation_id,
                "query": "Second question",
            },
        )
        assert response.status_code == requests.codes.ok

        # Now test getting the conversation history
        response = pytest.client.get(
            f"{endpoint.format(conversation_id=conversation_id)}?history_length=2"
        )
        assert response.status_code == requests.codes.ok

        history = response.json()["chat_history"]
        assert len(history) == 2  # 1 query + 1 response

        # Verify second message
        assert history[0]["content"] == "Second question"
        assert history[0]["type"] == "human"
        # Verify second response
        assert history[1]["type"] == "ai"


@pytest.mark.parametrize("endpoint", ("/conversations",))
def test_list_conversations_with_history(_setup, endpoint):
    """Test listing conversations after creating multiple conversations."""
    ml = mock_langchain_interface("test response")
    with (
        patch(
            "ols.src.query_helpers.docs_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
        patch(
            "ols.src.query_helpers.query_helper.load_llm",
            new=mock_llm_loader(ml()),
        ),
        patch(
            "ols.src.query_helpers.topic_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
    ):
        # Create first conversation
        conv_id_1 = suid.get_suid()
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conv_id_1,
                "query": "Question for conversation 1",
            },
        )
        assert response.status_code == requests.codes.ok

        # Create second conversation
        conv_id_2 = suid.get_suid()
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conv_id_2,
                "query": "Question for conversation 2",
            },
        )
        assert response.status_code == requests.codes.ok

        # Test listing conversations
        response = pytest.client.get(endpoint)
        assert response.status_code == requests.codes.ok

        conversations = response.json()["conversations"]
        assert len(conversations) >= 2  # May have more from other tests
        found_conv_ids = {conv["conversation_id"] for conv in conversations}
        assert conv_id_1 in found_conv_ids
        assert conv_id_2 in found_conv_ids

        for conv in conversations:
            assert (
                "topic_summary" in conv
            ), f"Conversation {conv['conversation_id']} is missing topic_summary"
            assert (
                "last_message_timestamp" in conv
            ), f"Conversation {conv['conversation_id']} is missing last_message_timestamp"


@pytest.mark.parametrize("endpoint", ("/conversations",))
def test_list_conversations_with_history_length(_setup, endpoint):
    """Test listing conversations with history_length after creating multiple conversations."""
    ml = mock_langchain_interface("test response")
    with (
        patch(
            "ols.src.query_helpers.docs_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
        patch(
            "ols.src.query_helpers.query_helper.load_llm",
            new=mock_llm_loader(ml()),
        ),
        patch(
            "ols.src.query_helpers.topic_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
    ):
        # Create first conversation
        conv_id_1 = suid.get_suid()
        response = pytest.client.post(
            "/v1/query",
            params={"user_id": "testuser"},
            json={
                "conversation_id": conv_id_1,
                "query": "Question for conversation 1",
            },
        )
        assert response.status_code == requests.codes.ok

        # Create second conversation
        conv_id_2 = suid.get_suid()
        response = pytest.client.post(
            "/v1/query",
            params={"user_id": "testuser"},
            json={
                "conversation_id": conv_id_2,
                "query": "Question for conversation 2",
            },
        )
        assert response.status_code == requests.codes.ok

        # Test listing conversations
        response = pytest.client.get(
            endpoint, params={"history_length": 1, "user_id": "testuser"}
        )
        assert response.status_code == requests.codes.ok

        conversations = response.json()["conversations"]
        assert len(conversations) == 1  # Return exact one conversation


@pytest.mark.parametrize("endpoint", ("/conversations/{conversation_id}",))
def test_delete_conversation_with_history(_setup, endpoint):
    """Test deleting a conversation after creating chat history."""
    ml = mock_langchain_interface("test response")
    with (
        patch(
            "ols.src.query_helpers.docs_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
        patch(
            "ols.src.query_helpers.query_helper.load_llm",
            new=mock_llm_loader(ml()),
        ),
        patch(
            "ols.src.query_helpers.topic_summarizer.LLMChain",
            new=mock_llm_chain(None),
        ),
    ):
        # First create a conversation
        conversation_id = suid.get_suid()
        response = pytest.client.post(
            "/v1/query",
            json={
                "conversation_id": conversation_id,
                "query": "Question to create conversation",
            },
        )
        assert response.status_code == requests.codes.ok

        # Verify conversation exists
        response = pytest.client.get(endpoint.format(conversation_id=conversation_id))
        assert response.status_code == requests.codes.ok
        assert len(response.json()["chat_history"]) == 2

        # Delete the conversation
        response = pytest.client.delete(
            endpoint.format(conversation_id=conversation_id)
        )
        assert response.status_code == requests.codes.ok
        assert (
            f"Conversation {conversation_id} successfully deleted"
            in response.json()["response"]
        )

        # Verify conversation is gone
        response = pytest.client.get(endpoint.format(conversation_id=conversation_id))
        assert response.status_code == requests.codes.internal_server_error
        assert (
            "Error retrieving previous chat history"
            in response.json()["detail"]["response"]
        )


def test_get_conversation_not_found(_setup):
    """Test conversation not found scenario."""
    conversation_id = suid.get_suid()

    with patch("ols.app.endpoints.ols.retrieve_previous_input", return_value=[]):
        response = pytest.client.get(f"/conversations/{conversation_id}")

        assert response.status_code == 500
        assert (
            response.json()["detail"]["cause"]
            == f"Conversation {conversation_id} not found"
        )


def test_delete_conversation_not_found(_setup):
    """Test deletion of non-existent conversation."""
    conversation_id = suid.get_suid()

    with patch("ols.config.conversation_cache.delete", return_value=False):
        response = pytest.client.delete(f"/conversations/{conversation_id}")

        assert response.status_code == 500
        assert (
            response.json()["detail"]["cause"]
            == f"Conversation {conversation_id} not found"
        )


def test_invalid_conversation_id(_setup):
    """Test handling of invalid conversation ID format."""
    invalid_id = "not-a-valid-uuid"
    response = pytest.client.get(f"/conversations/{invalid_id}")

    assert response.status_code == 500
    assert "Invalid conversation ID" in response.json()["detail"]["cause"]
