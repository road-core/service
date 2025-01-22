#!/bin/bash

# Build an ansible-chatbot-service image locally

AAP_VERSION=v2.5
LIGHTSPEED_RAG_CONTENT_IMAGE=quay.io/ansible/aap-rag-content:latest
LIGHTSPEED_RAG_EMBEDDINGS_IMAGE=quay.io/ansible/aap-rag-embeddings-image:latest
RAG_CONTENTS_SUB_FOLDER=vector_db/aap_product_docs

CACHE_OPTS=""
if [ -z "$OLS_NO_IMAGE_CACHE" ]; then
  CACHE_OPTS="--no-cache"
fi

# To build container for local use
podman build \
  ${CACHE_OPTS} \
  --build-arg=VERSION="${AAP_VERSION}" \
  --build-arg=LIGHTSPEED_RAG_CONTENT_IMAGE="${LIGHTSPEED_RAG_CONTENT_IMAGE}" \
  --build-arg=LIGHTSPEED_RAG_EMBEDDINGS_IMAGE="${LIGHTSPEED_RAG_EMBEDDINGS_IMAGE}" \
  --build-arg=RAG_CONTENTS_SUB_FOLDER="${RAG_CONTENTS_SUB_FOLDER}" \
  -t "${AAP_API_IMAGE:-quay.io/ansible/ansible-chatbot-service:latest}" \
  -f Containerfile

# To test-run for local development
#
#  podman run --rm \
#    --name chatbot-8080 \
#    -p 8080:8080 \
#    -v ${PWD}/rcsconfig.yaml:/app-root/rcsconfig.yaml:Z \
#    -e OPENAI_API_KEY=IGNORED  \
#    quay.io/ansible/ansible-chatbot-service:latest
