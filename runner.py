"""Main app entrypoint. Starts Uvicorn-based REST API service."""

import logging
import os
import tempfile
import threading
from pathlib import Path

import certifi
import uvicorn
from cryptography import x509

import ols.app.models.config as config_model
from ols.utils.auth_dependency import K8sClientSingleton
from ols.utils.logging import configure_logging


def configure_hugging_face_envs(ols_config: config_model.OLSConfig) -> None:
    """Configure HuggingFace library environment variables."""
    if (
        ols_config
        and hasattr(ols_config, "reference_content")
        and hasattr(ols_config.reference_content, "embeddings_model_path")
        and ols_config.reference_content.embeddings_model_path
    ):
        os.environ["TRANSFORMERS_CACHE"] = str(
            ols_config.reference_content.embeddings_model_path
        )
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def configure_gradio_ui_envs() -> None:
    """Configure GradioUI framework environment variables."""
    # disable Gradio analytics, which calls home to https://api.gradio.app
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "false"

    # Setup config directory for Matplotlib. It will be used to store info
    # about fonts (usually one JSON file) and it really is just temporary
    # storage that can be deleted at any time and recreated later.
    # Fixes: https://issues.redhat.com/browse/OLS-301
    tempdir = os.path.join(tempfile.gettempdir(), "matplotlib")
    os.environ["MPLCONFIGDIR"] = tempdir


def load_index():
    """Load the index."""
    # accessing the config's rag_index property will trigger the loading
    # of the index
    config.rag_index


# NOTE: Be aware this is irreversible step, as it modifies the certifi
# store. To restore original certs, the certifi lib needs to be
# reinstalled (or extra cert manually removed from the file).
def add_ca_to_certifi(
    logger: logging.Logger, cert_path: Path, certifi_cert_location=certifi.where()
) -> None:
    """Add a certificate to the certifi store."""
    logger.info("Cerfify store location: %s", certifi_cert_location)
    logger.info("Adding certificate '%s' to certify store", cert_path)
    with open(cert_path, "rb") as certificate_file:
        new_certificate_data = certificate_file.read()
    new_cert = x509.load_pem_x509_certificate(new_certificate_data)

    # load certifi certs
    with open(certifi_cert_location, "rb") as certifi_store:
        certifi_certs_data = certifi_store.read()
    certifi_certs = x509.load_pem_x509_certificates(certifi_certs_data)

    # append the certificate to the certifi store
    if new_cert in certifi_certs:
        logger.warning("Certificate '%s' is already in certifi store", cert_path)
    else:
        with open(certifi_cert_location, "ab") as certifi_store:
            certifi_store.write(new_certificate_data)


def generate_certificates_file(
    logger: logging.Logger, ols_config: config_model.OLSConfig
) -> None:
    """Generate certificates by merging certificates from certify with defined certificates."""
    logger.info("Generating certificates file")
    for certificate_path in ols_config.extra_ca:
        add_ca_to_certifi(logger, certificate_path)


def start_uvicorn():
    """Start Uvicorn-based REST API service."""
    # use workers=1 so config loaded can be accessed from other modules
    host = (
        "localhost"
        if config.dev_config.run_on_localhost
        else "0.0.0.0"  # noqa: S104 # nosec: B104
    )
    log_level = config.ols_config.logging_config.uvicorn_log_level

    if config.dev_config.disable_tls:
        # TLS is disabled, run without SSL configuration
        uvicorn.run(
            "ols.app.main:app",
            host=host,
            port=8080,
            log_level=log_level,
            workers=1,
            access_log=log_level < logging.INFO,
        )
    else:
        uvicorn.run(
            "ols.app.main:app",
            host=host,
            port=8443,
            workers=1,
            log_level=log_level,
            ssl_keyfile=config.ols_config.tls_config.tls_key_path,
            ssl_certfile=config.ols_config.tls_config.tls_certificate_path,
            ssl_keyfile_password=config.ols_config.tls_config.tls_key_password,
            access_log=log_level < logging.INFO,
        )


if __name__ == "__main__":

    # First of all, configure environment variables for Gradio before
    # import config and initializing config module.
    configure_gradio_ui_envs()

    # NOTE: We import config here to avoid triggering import of anything
    # else via our code before other envs are set (mainly the gradio).
    from ols import config

    cfg_file = os.environ.get("OLS_CONFIG_FILE", "olsconfig.yaml")
    config.reload_from_yaml_file(cfg_file)

    logger = logging.getLogger("ols")
    configure_logging(config.ols_config.logging_config)

    logger.info(f"Config loaded from {Path(cfg_file).resolve()}")
    configure_hugging_face_envs(config.ols_config)

    # generate certificates file from all certificates from certifi package
    # merged with explicitly specified certificates
    generate_certificates_file(logger, config.ols_config)

    # Initialize the K8sClientSingleton with cluster id during module load.
    # We want the application to fail early if the cluster ID is not available.
    cluster_id = K8sClientSingleton.get_cluster_id()
    logger.info(f"running on cluster with ID '{cluster_id}'")

    # init loading of query redactor
    config.query_redactor

    if config.dev_config.pyroscope_url:
        try:
            import requests

            response = requests.get(config.dev_config.pyroscope_url, timeout=60)
            if requests.codes.ok:
                logger.info(
                    f"Pyroscope server is reachable at {config.dev_config.pyroscope_url}"
                )
                import pyroscope

                pyroscope.configure(
                    application_name="lightspeed-service",
                    server_address=config.dev_config.pyroscope_url,
                    oncpu=True,
                    gil_only=True,
                    enable_logging=True,
                )
                with pyroscope.tag_wrapper({"main": "main_method"}):
                    # create and start the rag_index_thread - allows loading index in
                    # parallel with starting the Uvicorn server
                    rag_index_thread = threading.Thread(target=load_index)
                    rag_index_thread.start()

                    # start the Uvicorn server
                    start_uvicorn()
            else:
                logger.info(
                    f"Failed to reach Pyroscope server. Status code: {response.status_code}"
                )
        except requests.exceptions.RequestException as e:
            logger.info(f"Error connecting to Pyroscope server: {e}")
    else:
        logger.info(
            "Pyroscope url is not specified. To enable profiling please set `pyroscope_url` "
            "in the `dev_config` section of the configuration file."
        )
        # create and start the rag_index_thread - allows loading index in
        # parallel with starting the Uvicorn server
        rag_index_thread = threading.Thread(target=load_index)
        rag_index_thread.start()

        # start the Uvicorn server
        start_uvicorn()
