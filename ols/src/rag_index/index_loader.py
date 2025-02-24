# type: ignore  # noqa: PGH003
"""Module for loading index."""

import logging
from typing import Any, Optional

from ols.app.models.config import ReferenceContent
from ols.constants import VectorStoreType

logger = logging.getLogger(__name__)


# NOTE: Loading/importing something from llama_index bumps memory
# consumption up to ~400MiB. To avoid loading llama_index in all cases,
# we load it only when it is required.
# As these dependencies are lazily loaded, we can't use them in type hints.
# So this module is excluded from mypy checks as a whole.
def load_llama_index_deps(vector_store_type=VectorStoreType.FAISS) -> None:
    """Load llama_index dependencies."""
    # pylint: disable=global-statement disable=C0415
    global Settings
    global StorageContext
    global load_index_from_storage
    global EmbedType
    global BaseIndex
    global resolve_llm
    global FaissVectorStore
    from llama_index.core import Settings, StorageContext, load_index_from_storage
    from llama_index.core.embeddings.utils import EmbedType
    from llama_index.core.indices.base import BaseIndex
    from llama_index.core.llms.utils import resolve_llm

    if vector_store_type == VectorStoreType.FAISS:
        global FaissVectorStore
        from llama_index.vector_stores.faiss import FaissVectorStore
    elif vector_store_type == VectorStoreType.POSTGRES:
        global VectorStoreIndex
        global PGVectorStore
        from llama_index.core import VectorStoreIndex
        from llama_index.vector_stores.postgres import PGVectorStore


class IndexLoader:
    """Load index from local file storage."""

    def __init__(self, index_config: Optional[ReferenceContent]) -> None:
        """Initialize loader."""
        self._vector_store_type = (
            VectorStoreType.FAISS
            if index_config is None or index_config.vector_store_type is None
            else index_config.vector_store_type
        )

        load_llama_index_deps(self._vector_store_type)
        self._index = None

        self._index_config = index_config
        logger.debug("Config used for index load: %s", str(self._index_config))

        if self._index_config is None:
            logger.warning("Config for reference content is not set.")
        else:
            self._index_path = self._index_config.product_docs_index_path
            self._index_id = self._index_config.product_docs_index_id

            self._embed_model_path = self._index_config.embeddings_model_path
            self._embed_model = self._get_embed_model()
            self._load_index()

    def _get_embed_model(self) -> Any:
        """Get embed model according to configuration."""
        if self._embed_model_path is not None:
            # pylint: disable=C0415
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            logger.debug(
                "Loading embedding model info from path %s", self._embed_model_path
            )
            return HuggingFaceEmbedding(model_name=self._embed_model_path)

        logger.warning("Embedding model path is not set.")
        logger.warning("Embedding model is set to default")
        return "local:sentence-transformers/all-mpnet-base-v2"

    def _set_context(self) -> None:
        """Set storage/service context required for index load."""
        logger.debug("Using %s as embedding model for index", str(self._embed_model))
        logger.info("Setting up settings for index load...")
        Settings.embed_model = self._embed_model
        Settings.llm = resolve_llm(None)
        logger.info("Setting up storage context for index load...")
        # pylint: disable=W0201
        if self._vector_store_type == VectorStoreType.FAISS:
            self._vector_store = FaissVectorStore.from_persist_dir(self._index_path)
            self._storage_context = StorageContext.from_defaults(
                vector_store=self._vector_store,
                persist_dir=self._index_path,
            )
        elif self._vector_store_type == VectorStoreType.POSTGRES:
            postgres = self._index_config.postgres
            user = postgres.user
            password = postgres.password
            host = postgres.host
            port = postgres.port
            dbname = postgres.dbname
            table_name = self._index_id.replace("-", "_")
            embed_dim = len(Settings.embed_model.get_text_embedding("random text"))

            self._vector_store = PGVectorStore.from_params(
                database=dbname,
                host=host,
                password=password,
                port=port,
                user=user,
                table_name=table_name,
                embed_dim=embed_dim,
            )
        self._storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store,
        )

    def _load_index(self) -> None:
        """Load vector index."""
        if self._vector_store_type == VectorStoreType.FAISS:
            if self._index_path is None:
                logger.warning("Index path is not set.")
            else:
                try:
                    self._set_context()
                    logger.info("Loading vector index...")
                    self._index = load_index_from_storage(
                        storage_context=self._storage_context,
                        index_id=self._index_id,
                    )
                    logger.info("Vector index is loaded.")
                except Exception as err:
                    logger.exception("Error loading vector index:", exc_info=err)
        elif self._vector_store_type == VectorStoreType.POSTGRES:
            self._set_context()
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=self._vector_store,
            )

    @property
    def vector_index(self) -> Optional[ReferenceContent]:
        """Get index."""
        if self._index is None:
            logger.warning(
                "Proceeding without RAG content. "
                "Either there is an error or required parameters are not set."
            )
        return self._index
