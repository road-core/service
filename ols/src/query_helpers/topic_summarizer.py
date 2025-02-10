"""Class responsible for validating questions and providing one-word responses."""

import logging
from typing import Any

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

from ols import config
from ols.app.metrics import TokenMetricUpdater
from ols.constants import GenericLLMParameters
from ols.customize import prompts
from ols.src.query_helpers.query_helper import QueryHelper
from ols.utils.token_handler import TokenHandler

logger = logging.getLogger(__name__)


class TopicSummarizer(QueryHelper):
    """This class is responsible for summarizing the user initial purpose and return a topic in responses."""

    max_tokens_for_response = 4

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the QuestionValidator."""
        super().__init__(*args, **kwargs)
        self._prepare_llm()
        self.verbose = config.ols_config.logging_config.app_log_level == logging.DEBUG

    def _prepare_llm(self) -> None:
        """Prepare the LLM configuration."""
        self.provider_config = config.llm_config.providers.get(self.provider)
        self.model_config = self.provider_config.models.get(self.model)
        self.generic_llm_params = {
            GenericLLMParameters.MAX_TOKENS_FOR_RESPONSE: self.model_config.parameters.max_tokens_for_response  # noqa: E501
        }
        self.bare_llm = self.llm_loader(
            self.provider, self.model, self.generic_llm_params, self.streaming
        )

    def summarize_topic(self, conversation_id: str, query: str) -> str:
        """Summarize the user initial purpose and return a topic in responses.

        Args:
          conversation_id: The identifier for the conversation or task context.
          query: The question to be summarized.

        Returns:
            str: summarized conversation topic
        """
        settings_string = (
            f"conversation_id: {conversation_id}, "
            f"query: {query}, "
            f"provider: {self.provider}, "
            f"model: {self.model}, "
            f"verbose: {self.verbose}"
        )
        logger.info("%s call settings: %s", conversation_id, settings_string)

        prompt_instructions = PromptTemplate.from_template(
            prompts.TOPIC_SUMMARY_PROMPT_TEMPLATE
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
            verbose=self.verbose,
        )

        logger.debug("%s summarizing user query: %s", conversation_id, query)

        with TokenMetricUpdater(
            llm=bare_llm,
            provider=provider_config.type,
            model=self.model,
        ) as generic_token_counter:
            response = llm_chain.invoke(
                input={"query": query}, config={"callbacks": [generic_token_counter]}
            )
        clean_response = str(response["text"]).strip()

        logger.debug("%s summarizer response: %s", conversation_id, clean_response)

        return clean_response
