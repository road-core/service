#!/bin/bash

# Version
RCS_VERSION=v0.2.1

# To build container for local use
if [ -z "$RCS_NO_IMAGE_CACHE" ]; then
  podman build --no-cache --build-arg=VERSION="${RCS_VERSION}" -t "${RCS_API_IMAGE:-quay.io/openshift-lightspeed/lightspeed-service-api:latest}" -f Containerfile
else
  podman build --build-arg=VERSION=${RCS_VERSION} -t "${RCS_API_IMAGE:-quay.io/openshift-lightspeed/lightspeed-service-api:latest}" -f Containerfile
fi

# To test-run for local development
# podman run --rm -ti -p 8080:8080 ${RCS_API_IMAGE:-quay.io/openshift-lightspeed/lightspeed-service-api:latest}
