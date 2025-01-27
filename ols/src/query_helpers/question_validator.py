"""Class responsible for validating questions and providing one-word responses."""

import logging
from typing import Any

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

from ols import config
from ols.app.metrics import TokenMetricUpdater
from ols.constants import SUBJECT_REJECTED, GenericLLMParameters
from ols.customize import prompts
from ols.src.query_helpers.query_helper import QueryHelper
from ols.utils.token_handler import TokenHandler

logger = logging.getLogger(__name__)


class QuestionValidator(QueryHelper):
    """This class is responsible for validating questions and providing one-word responses."""

    # hardcoded value - we always want to use 4 tokens for the response
    # as we only need to check if the question is valid or not - we have
    # a fixed responses for that
    max_tokens_for_response = 4

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the QuestionValidator."""
        generic_llm_params = {
            GenericLLMParameters.MAX_TOKENS_FOR_RESPONSE: self.max_tokens_for_response
        }
        super().__init__(*args, **dict(kwargs, generic_llm_params=generic_llm_params))

    def validate_question(
        self, conversation_id: str, query: str, verbose: bool = False
    ) -> bool:
        """Validate a question and provides a one-word response.

        Args:
          conversation_id: The identifier for the conversation or task context.
          query: The question to be validated.
          verbose: If `LLMChain` should be verbose. Defaults to `False`.

        Returns:
            bool: true/false indicating if the question was deemed valid
        """
        settings_string = (
            f"conversation_id: {conversation_id}, "
            f"query: {query}, "
            f"provider: {self.provider}, "
            f"model: {self.model}, "
            f"verbose: {verbose}"
        )
        logger.info("%s call settings: %s", conversation_id, settings_string)

        prompt_instructions = PromptTemplate.from_template(
            prompts.QUESTION_VALIDATOR_PROMPT_TEMPLATE
        )

        bare_llm = self.llm_loader(
            self.provider, self.model, self.generic_llm_params, self.streaming
        )

        # Tokens-check: We trigger the computation of the token count
        # without care about the return value. This is to ensure that
        # the query is within the token limit.
        provider_config = config.llm_config.providers.get(self.provider)
        model_config = provider_config.models.get(self.model)
        TokenHandler().calculate_and_check_available_tokens(
            query, model_config.context_window_size, self.max_tokens_for_response
        )

        llm_chain = LLMChain(
            llm=bare_llm,
            prompt=prompt_instructions,
            verbose=verbose,
        )

        logger.debug("%s validating user query: %s", conversation_id, query)

        with TokenMetricUpdater(
            llm=bare_llm,
            provider=provider_config.type,
            model=self.model,
        ) as generic_token_counter:
            response = llm_chain.invoke(
                input={"query": query}, config={"callbacks": [generic_token_counter]}
            )
        clean_response = str(response["text"]).strip()

        logger.debug(
            "%s query validation response: %s", conversation_id, clean_response
        )

        # Default to be permissive(allow the question) if we don't get a clean
        # rejection from the LLM.
        return SUBJECT_REJECTED not in clean_response
