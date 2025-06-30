"""Collect insights and upload it to the Ingress service.

It waits `INITIAL_WAIT` min after startup before collects the data. Then
it collects data after specified interval.

When `cp_offline_token` is provided via config (either for prod or stage),
it is used for ingress authentication instead of cluster pull-secret.
"""

import base64
import io
import json
import logging
import os
import pathlib
import sys
import tarfile
import time
from typing import Any

import kubernetes
import requests

# we need to add the root directory to the path to import from ols
sys.path.append(pathlib.Path(__file__).parent.parent.parent.as_posix())

# initialize config
from ols import config  # pylint: disable=C0413
from ols.app.models.config import UserDataCollectorConfig  # pylint: disable=C0413
from ols.constants import (  # pylint: disable=C0413
    CONFIGURATION_FILE_NAME_ENV_VARIABLE,
    DEFAULT_CONFIGURATION_FILE,
)
from ols.customize import filenames  # pylint: disable=C0413

# pylint: disable-next=C0413
from ols.src.auth.k8s import K8sClientSingleton

data_collection_magic_file_name = filenames.DATA_COLLECTION_MAGIC_FILE_NAME

logger = logging.getLogger(__name__)


class ClusterPullSecretNotFoundError(Exception):
    """Cluster pull-secret is not found."""


class ClusterIDNotFoundError(Exception):
    """Cluster id is not found."""


def access_token_from_offline_token(
    offline_token: str, ingress_url: str, access_token_generation_timeout: int
) -> str:
    """Generate "access token" from the "offline token".

    Offline token can be generated at:
        prod - https://access.redhat.com/management/api
        stage - https://access.stage.redhat.com/management/api

    Args:
        offline_token: Offline token from the Customer Portal.
        ingress_url: url of the chosen ingress environment
        access_token_generation_timeout: timeout for access token, in seconds
    Returns:
        Refresh token.
    """
    endpoint = "auth/realms/redhat-external/protocol/openid-connect/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": "rhsm-api",
        "refresh_token": offline_token,
    }

    response = requests.post(
        ingress_url + endpoint, data=data, timeout=access_token_generation_timeout
    )
    try:
        if response.status_code == requests.codes.ok:
            return response.json()["access_token"]
        raise Exception(f"Failed to generate access token. Response: {response.json()}")
    except json.JSONDecodeError:
        raise Exception(
            "Failed to generate access token. Response is not JSON."
            f"Response: {response.status_code}: {response.text}"
        )


def get_cloud_openshift_pull_secret() -> str:
    """Get the pull secret token from the cluster."""
    kubernetes.config.load_incluster_config()
    v1 = kubernetes.client.CoreV1Api()
    dockerconfig: Any = None

    try:
        secret = v1.read_namespaced_secret("pull-secret", "openshift-config")
        dockerconfigjson = secret.data[".dockerconfigjson"]
        dockerconfig = json.loads(base64.b64decode(dockerconfigjson).decode("utf-8"))
        return dockerconfig["auths"]["cloud.openshift.com"]["auth"]
    except KeyError:
        logger.error("failed to get token from cluster pull-secret, missing keys")
    except TypeError:
        logger.error(
            "failed to get token from cluster pull-secret, unexpected object type: %s",
            str(type(dockerconfig)),
        )
    except kubernetes.client.exceptions.ApiException as e:
        logger.error("failed to get pull-secret object, body: %s", str(e.body))
    raise ClusterPullSecretNotFoundError


def collect_ols_data_from(location: str) -> list[pathlib.Path]:
    """Collect files from a given location.

    Args:
        location: Path to the directory to be searched for files.

    Returns:
        List of paths to the collected files.

    Only JSON files from the 'feedback' and 'transcripts' directories are collected.
    """
    files = []

    files += list(pathlib.Path(location).glob("feedback/*.json"))
    files += list(pathlib.Path(location).glob("transcripts/*/*/*.json"))

    return files


def package_files_into_tarball(
    file_paths: list[pathlib.Path], path_to_strip: str
) -> io.BytesIO:
    """Package specified directory into a tarball.

    Args:
        file_paths: List of paths to the files to be packaged.
        path_to_strip: Path to be stripped from the file paths (not
            included in the archive).

    Returns:
        BytesIO object representing the tarball.
    """
    tarball_io = io.BytesIO()
    with tarfile.open(fileobj=tarball_io, mode="w:gz") as tar:
        # arcname parameter is set to a stripped path to avoid including
        # the full path of the root dir
        for file_path in file_paths:
            # skip symlinks as those are a potential security risk
            if not file_path.is_symlink():
                tar.add(
                    file_path, arcname=file_path.as_posix().replace(path_to_strip, "")
                )

        # add magic file for identification of our archive on the CCX side
        empty_file = tarfile.TarInfo(data_collection_magic_file_name)
        empty_file.size = 0
        tar.addfile(empty_file)

    tarball_io.seek(0)

    return tarball_io


def upload_data_to_ingress(
    tarball: io.BytesIO, udc_config: UserDataCollectorConfig
) -> requests.Response:
    """Attempt to upload the tarball to a Ingress.

    If upload fails, for any reason, another attempt is made, with delay
    and number of repetitions set in the `udc_config`.

    Args:
        tarball: BytesIO object representing the tarball to be uploaded.
        udc_config: Configuration for the data collector
    Returns:
        Response object from the Ingress.
    """
    logger.info("sending collected data")
    payload = {
        "file": (
            "rcs.tgz",
            tarball.read(),
            "application/vnd.redhat.openshift.periodic+tar",
        ),
    }

    headers: dict[str, str | bytes]

    retries = 0
    while retries < udc_config.ingress_max_retries:
        try:
            if udc_config.cp_offline_token:
                logger.debug("using CP offline token to generate refresh token")
                token = access_token_from_offline_token(
                    udc_config.cp_offline_token,
                    str(udc_config.ingress_url),
                    udc_config.access_token_generation_timeout,
                )
                # when authenticating with token, user-agent is not accepted
                # causing "UHC services authentication failed"
                headers = {"Authorization": f"Bearer {token}"}
            else:
                logger.debug("using cluster pull secret to authenticate")
                cluster_id = K8sClientSingleton.get_cluster_id()
                token = get_cloud_openshift_pull_secret()
                headers = {
                    "User-Agent": udc_config.user_agent.format(cluster_id=cluster_id),
                    "Authorization": f"Bearer {token}",
                }

            with requests.Session() as s:
                s.headers = headers
                logger.debug("posting payload to %s", udc_config.ingress_url)
                response = s.post(
                    url=str(udc_config.ingress_url),
                    files=payload,
                    timeout=udc_config.ingress_timeout,
                )

            if response.status_code != requests.codes.accepted:
                logger.error(
                    "posting payload failed, response: %d: %s",
                    response.status_code,
                    response.text,
                )
                raise requests.exceptions.HTTPError(
                    f"data upload failed with response code: {response.status_code}"
                )

            request_id = response.json()["request_id"]
            logger.info("data uploaded with request_id: '%s'", request_id)

        except Exception as e:
            logger.error("attempt %d failed with error: %s", retries + 1, str(e))
            retries += 1
            delay = udc_config.ingress_base_delay * 2**retries
            logger.info("retrying in %d seconds...", delay)
            time.sleep(delay)

    logger.error("max retries reached, operation failed.")

    return response


def delete_data(file_paths: list[pathlib.Path]) -> None:
    """Delete files from the provided paths.

    Args:
        file_paths: List of paths to the files to be deleted.
    """
    for file_path in file_paths:
        logger.debug("removing '%s'", file_path)
        file_path.unlink()
        if file_path.exists():
            logger.error("failed to remove '%s'", file_path)


def chunk_data(
    data: list[pathlib.Path], chunk_max_size: int
) -> list[list[pathlib.Path]]:
    """Chunk the data into smaller parts.

    Args:
        data: List of paths to the files to be chunked.
        chunk_max_size: Maximum size of a chunk.

    Returns:
        List of lists of paths to the chunked files.
    """
    # if file is bigger than OLS_USER_DATA_MAX_SIZE, it will be in a
    # chunk by itself
    chunk_size = 0
    chunks: list = []
    chunk: list = []
    for file in data:
        file_size = file.stat().st_size
        if chunk_max_size < chunk_size + file_size or file_size > chunk_max_size:
            if chunk:
                chunks.append(chunk)
            chunk = []
            chunk_size = 0
        chunk.append(file)
        chunk_size += file_size
    if chunk:
        chunks.append(chunk)
    return chunks


def gather_ols_user_data(udc_config: UserDataCollectorConfig) -> None:
    """Gather OLS user data and upload it to the Ingress service."""
    collected_files = collect_ols_data_from(udc_config.data_storage.as_posix())
    data_chunks = chunk_data(collected_files, udc_config.user_data_max_size)
    if any(data_chunks):
        logger.info(
            "collected %d files (splitted to %d chunks) from '%s'",
            len(collected_files),
            len(data_chunks),
            udc_config.data_storage.as_posix(),
        )
        logger.debug("collected files: %s", collected_files)
        for i, data_chunk in enumerate(data_chunks):
            logger.info("uploading data chunk %d/%d", i + 1, len(data_chunks))
            tarball = package_files_into_tarball(
                data_chunk, path_to_strip=udc_config.data_storage.as_posix()
            )
            try:
                upload_data_to_ingress(tarball, udc_config)
                delete_data(data_chunk)
                logger.info("uploaded data removed")
            except (ClusterPullSecretNotFoundError, ClusterIDNotFoundError) as e:
                logger.error(
                    "%s - upload and data removal canceled", e.__class__.__name__
                )

            # close the tarball to release mem
            tarball.close()
    else:
        logger.info(
            "'%s' contains no data, nothing to do...",
            udc_config.data_storage.as_posix(),
        )


def ensure_data_dir_is_not_bigger_than_defined(
    data_dir: str,
    max_size: int,
) -> None:
    """Ensure that the data dir is not bigger than it should be.

    Args:
        data_dir: Path to the directory to be checked.
        max_size: Maximum size of the directory.
    """
    collected_files = collect_ols_data_from(data_dir)
    data_size = sum(file.stat().st_size for file in collected_files)
    if data_size > max_size:
        logger.error(
            "data folder size is bigger than the maximum allowed size: %d > %d",
            data_size,
            max_size,
        )
        logger.info("removing files to fit the data into the limit...")
        extra_size = data_size - max_size
        for file in collected_files:
            extra_size -= file.stat().st_size
            delete_data([file])
            if extra_size < 0:
                break


# NOTE: This condition is here mainly to have a way how to influence
# when the collector is running in the e2e tests. It is not meant to be
# used in the production.
def disabled_by_file(data_storage: pathlib.Path) -> bool:
    """Check if the data collection is disabled by a file.

    Pure existence of the file `disable_collector` in the root of the
    user data dir is enough to disable the data collection.
    """
    if data_storage is None:
        logger.warning(
            "Data storage path is None, cannot check for disable_collector file."
        )
        return False
    return (data_storage / "disable_collector").exists()


if __name__ == "__main__":

    cfg_file = os.environ.get(
        CONFIGURATION_FILE_NAME_ENV_VARIABLE, DEFAULT_CONFIGURATION_FILE
    )
    config.reload_from_yaml_file(
        cfg_file, ignore_llm_secrets=True, ignore_missing_certs=True
    )
    udc_config = config.user_data_collector_config  # shortcut

    logging.basicConfig(
        level=udc_config.log_level,
        stream=sys.stdout,
        format="[%(asctime)s] %(levelname)s: %(message)s",
    )
    # silence libs logging
    # - urllib3 - we don't care about those debug posts
    # - kubernetes - prints resources content when debug, causing secrets leak
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not udc_config.run_without_initial_wait:
        logger.info(
            "collection script started, waiting %d seconds before first collection",
            udc_config.initial_wait,
        )
        time.sleep(udc_config.initial_wait)
    while True:
        if not disabled_by_file(udc_config.data_storage):
            gather_ols_user_data(udc_config.data_storage.as_posix())
            ensure_data_dir_is_not_bigger_than_defined(
                udc_config.data_storage.as_posix(), udc_config.user_data_max_size
            )
        else:
            logger.info("disabled by control file, skipping data collection")
        time.sleep(udc_config.collection_interval)
