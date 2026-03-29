PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
UVICORN := .venv/bin/uvicorn

.PHONY: venv install test run lint demo-setup demo-deploy demo-reset demo-ready tunnel poll-once docker-build deploy-backend public-bridge

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

test:
	$(PYTEST)

run:
	$(UVICORN) backend.main:app --reload

demo-setup:
	bash scripts/setup_minikube.sh

demo-deploy:
	bash scripts/deploy_demo.sh

demo-reset:
	bash scripts/demo_reset.sh

demo-ready:
	bash scripts/demo_ready.sh

docker-build:
	docker build -t k8s-whisperer:dev .

deploy-backend:
	bash scripts/deploy_backend.sh

public-bridge:
	bash scripts/run_public_callback_bridge.sh

tunnel:
	bash scripts/tunnel.sh

poll-once:
	$(PYTHON) -c "import json, urllib.request; request = urllib.request.Request('http://localhost:8000/api/poller/run-once', method='POST'); response = urllib.request.urlopen(request); print(json.dumps(json.loads(response.read().decode('utf-8')), indent=2))"
