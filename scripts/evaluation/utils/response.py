"""Response for evaluation."""

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

from ols import config
from ols.constants import GenericLLMParameters
from ols.src.prompts.prompt_generator import GeneratePrompt

from .constants import BASIC_PROMPT, REST_API_TIMEOUT
from .models import MODEL_OLS_PARAM, VANILLA_MODEL
from .rag import retrieve_rag_chunks


def get_model_response(query, provider, model, mode, api_client=None):
    """Get response depending upon the mode."""
    if mode == "ols":
        response = api_client.post(
            "/v1/query",
            json={
                "query": query,
                "provider": provider,
                "model": model,
            },
            timeout=REST_API_TIMEOUT,
        )
        if response.status_code != 200:
            raise Exception(response)
        return response.json()["response"].strip()

    prompt = PromptTemplate.from_template("{query}")
    prompt_input = {"query": query}
    provider_config = config.config.llm_providers.providers[provider]
    model_config = provider_config.models[model]
    llm = VANILLA_MODEL[provider](model, provider_config).load()

    if mode == "ols_param":
        max_resp_tokens = model_config.parameters.max_tokens_for_response
        override_params = {
            GenericLLMParameters.MAX_TOKENS_FOR_RESPONSE: max_resp_tokens
        }
        llm = MODEL_OLS_PARAM[provider](model, provider_config, override_params).load()
    if mode == "ols_prompt":
        prompt, prompt_input = GeneratePrompt(query, [], []).generate_prompt(model)
    if mode == "ols_rag":
        rag_chunks = retrieve_rag_chunks(query, model, model_config)
        prompt, prompt_input = GeneratePrompt(
            query, rag_chunks, [], BASIC_PROMPT
        ).generate_prompt(model)

    llm_chain = LLMChain(llm=llm, prompt=prompt, verbose=True)
    return llm_chain(inputs=prompt_input)["text"].strip()
