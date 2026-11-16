# Build, test and version the images in images/ (README). IMAGE is a
# directory name in images/.

# .venv when there is one: python3 -m venv .venv, then
# .venv/bin/pip install -r requirements.txt.
PYTHON := $(if $(wildcard .venv/bin),.venv/bin/python3,python3)

# The cluster's nodes are amd64.
PLATFORM ?= linux/amd64

# renovate: datasource=docker depName=hadolint/hadolint
HADOLINT_VERSION := v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d
# renovate: datasource=docker depName=koalaman/shellcheck
SHELLCHECK_VERSION := v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
# renovate: datasource=docker depName=rhysd/actionlint
ACTIONLINT_VERSION := 1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667

IMAGES := $(shell $(PYTHON) scripts/images.py list)

.PHONY: help build test bump check lint require-image

help:
	@echo "make build IMAGE=<name>   build images/<name> as local/<name>"
	@echo "make test IMAGE=<name>    build, then run images/<name>/test.sh"
	@echo "make bump [IMAGE=<name>]  set version as CI would"
	@echo "make check                check every version"
	@echo "make lint                 hadolint, shellcheck and actionlint"
	@echo "Images: $(IMAGES)"

require-image:
	@test -n "$(IMAGE)" || { echo "Set IMAGE to one of: $(IMAGES)"; exit 1; }
	@test -f images/$(IMAGE)/Dockerfile || { echo "images/$(IMAGE)/Dockerfile does not exist. Set IMAGE to one of: $(IMAGES)"; exit 1; }

build: require-image
	docker build --platform $(PLATFORM) \
		--label org.opencontainers.image.source=https://github.com/gathering/sys-k8s-images \
		--label org.opencontainers.image.version=$$(cat images/$(IMAGE)/version) \
		--label org.opencontainers.image.revision=$$(git rev-parse HEAD) \
		-t local/$(IMAGE) images/$(IMAGE)

test: build
	DOCKER_DEFAULT_PLATFORM=$(PLATFORM) images/$(IMAGE)/test.sh local/$(IMAGE)

bump:
	$(PYTHON) scripts/images.py bump $(IMAGE)

check:
	$(PYTHON) scripts/images.py check
	@for i in $(IMAGES); do \
		test -x images/$$i/test.sh || { echo "images/$$i/test.sh is missing or not executable. Add it, or chmod +x it"; exit 1; }; \
	done

lint:
	@for i in $(IMAGES); do \
		echo "hadolint images/$$i/Dockerfile"; \
		docker run --rm -i -v "$(CURDIR)/images/$$i:/image:ro" -w /image hadolint/hadolint:$(HADOLINT_VERSION) \
			hadolint Dockerfile || exit 1; \
	done
	docker run --rm -v "$(CURDIR):/mnt:ro" koalaman/shellcheck:$(SHELLCHECK_VERSION) images/*/test.sh
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo rhysd/actionlint:$(ACTIONLINT_VERSION) -color=false
