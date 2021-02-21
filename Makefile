IMAGE   ?= mineyannik/homematicip-exporter
VERSION = $(shell git rev-parse --verify HEAD | head -c 8)

build: clean-build
	python setup.py sdist

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +

clean-build:
	rm -rf build/ dist/ *.egg-info

docker-build:
	docker build -t $(IMAGE):$(VERSION) .

docker-push: docker-build
	docker push $(IMAGE):$(VERSION)

latest: docker-push
	docker tag $(IMAGE):$(VERSION) $(IMAGE):latest
	docker push $(IMAGE):latest

.PHONY: clean-build docker-build docker-push
