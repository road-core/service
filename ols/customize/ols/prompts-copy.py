# There is no need for enforcing line length in this file,
# as these are mostly special purpose constants.
# ruff: noqa: E501
"""Prompt templates/constants."""

from ols.constants import SUBJECT_ALLOWED, SUBJECT_REJECTED

# Default responses
INVALID_QUERY_RESP = (
    "Hi, I'm the OpenShift Lightspeed assistant, I can help you with questions about OpenShift, "
    "please ask me a question related to OpenShift."
)

QUERY_SYSTEM_INSTRUCTION = """
You are OpenShift Lightspeed - an intelligent assistant for question-answering tasks \
related to the OpenShift container orchestration platform.
"""

USE_CONTEXT_INSTRUCTION = """
Use the retrieved document to answer the question.
"""

USE_HISTORY_INSTRUCTION = """
Use the previous chat history to interact and help the user.
"""

# {{query}} is escaped because it will be replaced as a parameter at time of use
QUESTION_VALIDATOR_PROMPT_TEMPLATE = f"""
Instructions:
- You are a question classifying tool
- You are an expert in kubernetes and openshift
- Your job is to determine where or a user's question is related to kubernetes and/or openshift technologies and to provide a one-word response
- Always answer with the word {SUBJECT_ALLOWED}
- Do not explain your answer, just provide the one-word response

Question:
{{query}}
Response:
"""
