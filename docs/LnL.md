---
layout: default
nav_order: 3
---
# Lunch and Learn

# Road core service

## Installation

### Linux
1. `git clone https://github.com/road-core/service`
1. `pip install --user pdm`
1. `pdm --version`
1. `pdm install`

### MacOS
#### Prerequisites
- brew
- git
#### Installation
1. `brew install pdm`
1. `pdm --version` -- should return no error
1. Clone the repo to the current dir:
`git clone https://github.com/road-core/service`
1. `cd service`
1. `pdm info` -- should return no error
1. change `torch==2.6.0+cpu` to `torch==2.6.0` in `pyproject.toml` (section `[project]/dependencies`)
1. `pdm install` -- if it fails (for example because you ran `pdm install` before changing `pyproject.toml`) run:
```sh
pdm update
pdm install
```

## Configuration
1. Retrieve OpenAI key
1. Store into file `openai_api_key.txt`
1. Minimal configuration file `rcsconfig.yaml`:

```yaml
# Minimal service configuration
---
llm_providers:
  - name: my_openai
    type: openai
    url: "https://api.openai.com/v1"
    credentials_path: openai_api_key.txt
    models:
      - name: gpt-3.5-turbo
ols_config:
  conversation_cache:
    type: memory
    memory:
      max_entries: 1000
  default_provider: my_openai
  default_model: gpt-3.5-turbo
  authentication_config:
    module: "noop"

dev_config:
  # config options specific to dev environment - launching OLS in local
  enable_dev_ui: true
  disable_auth: true
  disable_tls: true

```

## Running

`pdm run start`

1. [localhost:8080/ui](localhost:8080/ui)
1. [localhost:8080/docs](localhost:8080/docs)

Hit Ctrl-C to stop.

## RAG

* Retrieval-augmented generation

Stop the service before making these changes.

`make get-rag`

Configuration in `rcsconfig.yaml` with RAG:

```yaml
llm_providers:
  - name: my_openai
    type: openai
    url: "https://api.openai.com/v1"
    credentials_path: openai_api_key.txt
    models:
      - name: gpt-3.5-turbo
ols_config:
  conversation_cache:
    type: memory
    memory:
      max_entries: 1000
  default_provider: my_openai
  default_model: gpt-3.5-turbo
  authentication_config:
    module: "noop"
  reference_content:
    product_docs_index_path: "./vector_db/ocp_product_docs/4.15"
    product_docs_index_id: ocp-product-docs-4_15
    embeddings_model_path: "./embeddings_model"

dev_config:
  enable_dev_ui: true
  disable_auth: true
  disable_tls: true
```

