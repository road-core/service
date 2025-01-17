"""FastAPI endpoint for the OLS streaming query.

This module defines the endpoint and supporting functions for handling
streaming queries.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ols import config
from ols.app.endpoints.ols import (
    retrieve_user_id,
    retrieve_previous_input
)
from ols.app.models.models import (
    ErrorResponse,
    ForbiddenResponse,
    UnauthorizedResponse,
)
from ols.src.auth.auth import get_auth_dependency

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])
auth_dependency = get_auth_dependency(config.ols_config, virtual_path="/ols-access")



@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user_id: str | None = None,
    auth: Any = Depends(auth_dependency)
) -> list[BaseMessage]:
    """Get conversation history for a given conversation ID.

    Args:
        auth: The Authentication handler (FastAPI Depends) that will handle authentication Logic.
        conversation_id: The conversation ID to retrieve.
        user_id: (Optional)The user ID to retrieve the conversation for.

    Returns:
        List of conversation messages.
    
    Raises:
        HTTPException: 404 if conversation not found
    """
    # Initialize variables
    previous_input = []
    chat_history: list[BaseMessage] = []

    effective_user_id = user_id or retrieve_user_id(auth)
    logger.info("User ID %s", effective_user_id)

    # Log incoming request (after redaction)
    logger.info("Getting chat history for user: %s with conversation_id: %s", user_id, conversation_id)

    previous_input = retrieve_previous_input(effective_user_id, conversation_id)
    if previous_input.__len__() == 0:
        logger.info("No chat history found for user: %s with conversation_id: %s", user_id, conversation_id)
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        ) 
    for entry in previous_input:
        chat_history.append(entry.query)
        chat_history.append(entry.response)

    return chat_history


@router.delete("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user_id: str | None = None,
    auth: Any = Depends(auth_dependency)
) -> JSONResponse:
    """Delete conversation history for a given conversation ID.

    Args:
        auth: The Authentication handler (FastAPI Depends) that will handle authentication Logic.
        conversation_id: The conversation ID to delete.
        user_id: (Optional)The user ID to delete the conversation for.
    
    Raises:
        HTTPException: 404 if conversation not found

    """

    effective_user_id = user_id or retrieve_user_id(auth)
    logger.info("User ID %s", effective_user_id)

    # Log incoming request (after redaction)
    logger.info("Deleting chat history for user: %s with conversation_id: %s", user_id, conversation_id)

    if config.conversation_cache.delete(effective_user_id, conversation_id):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Conversation {conversation_id} successfully deleted"}
        )
    else:
        logger.info("No chat history found for user: %s with conversation_id: %s", user_id, conversation_id)
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )


@router.get("/conversations")
def get_conversation(
    user_id: str | None = None,
    auth: Any = Depends(auth_dependency)
) -> list[str]:
    """List all conversations for a given user.

    Args:
        auth: The Authentication handler (FastAPI Depends) that will handle authentication Logic.
        user_id: (Optional)The user ID to get all conversations for.

    """

    effective_user_id = user_id or retrieve_user_id(auth)
    logger.info("User ID %s", effective_user_id)

    # Log incoming request (after redaction)
    logger.info("Listing all conversations for user: %s ", user_id)

    return config.conversation_cache.list(effective_user_id)

