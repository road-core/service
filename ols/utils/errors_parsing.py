"""Module for parsing errors from different LLMs."""

import json

from fastapi import status
from genai.exceptions import ApiResponseException
from ibm_watsonx_ai.wml_client_error import ApiRequestFailure
from openai import BadRequestError

# Constants for default messages and status codes
DEFAULT_ERROR_MESSAGE = "Oops, something went wrong during LLM invocation"
DEFAULT_STATUS_CODE = status.HTTP_500_INTERNAL_SERVER_ERROR


def parse_openai_error(e: BadRequestError) -> tuple[int, str, str]:
    """Parse OpenAI or Azure error."""
    if e.body is not None and isinstance(e.body, dict) and "message" in e.body:
        response_text = e.body["message"]
    else:
        response_text = e.message
    return e.status_code, response_text, e.message


def parse_bam_error(e: ApiResponseException) -> tuple[int, str, str]:
    """Parse BAM error."""
    if e.response.extensions.state is not None and "message" in e.response.extensions.state:
        response_text = e.response.extensions.state["message"]
    else:
        response_text = e.message
    return e.response.status_code, response_text, e.message


def parse_watsonx_error(e: ApiRequestFailure) -> tuple[int, str, str]:
    """Parse Watsonx error."""
    try:
        errors = json.loads(e.response.text)["errors"]
        if len(errors) != 1 or errors[0].get("message") is None:
            raise ValueError
        response_text = errors[0]["message"]
    except (json.JSONDecodeError, KeyError, ValueError):
        # fallback to response reason if message is not found
        response_text = e.response.reason
    return e.response.status_code, response_text, e.error_msg


def parse_generic_llm_error(e: Exception) -> tuple[int, str, str]:
    """Try to parse generic LLM error."""
    match e:
        case BadRequestError():
            return parse_openai_error(e)
        case ApiResponseException():
            return parse_bam_error(e)
        case ApiRequestFailure():
            return parse_watsonx_error(e)
        case _:
            return DEFAULT_STATUS_CODE, DEFAULT_ERROR_MESSAGE, str(e)
