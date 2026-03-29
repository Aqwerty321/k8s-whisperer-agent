PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
UVICORN := .venv/bin/uvicorn

.PHONY: venv install test run lint demo-setup demo-deploy tunnel poll-once docker-build deploy-backend

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

docker-build:
	docker build -t k8s-whisperer:dev .

deploy-backend:
	bash scripts/deploy_backend.sh

tunnel:
	bash scripts/tunnel.sh

poll-once:
	.venv/bin/python - <<'PY'
import json
import urllib.request

request = urllib.request.Request(
    "http://localhost:8000/api/poller/run-once",
    method="POST",
)
with urllib.request.urlopen(request) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
