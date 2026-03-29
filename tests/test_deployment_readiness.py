from pathlib import Path


def test_cloudflared_template_only_exposes_health_and_slack_actions() -> None:
    template = Path("deploy/cloudflared/config.template.yml").read_text(encoding="utf-8")

    assert "path: ^/health$" in template
    assert "path: ^/api/slack/actions$" in template
    assert "/api/status" not in template
    assert "/api/poller/run-once" not in template


def test_backend_manifest_uses_service_account_and_health_probes() -> None:
    manifest = Path("k8s/backend.yaml").read_text(encoding="utf-8")

    assert "serviceAccountName: k8s-whisperer-sa" in manifest
    assert "readinessProbe:" in manifest
    assert "livenessProbe:" in manifest
    assert "name: k8s-whisperer-secrets" in manifest


def test_bridge_script_targets_service_port_forward_and_tunnel_config() -> None:
    script = Path("scripts/run_public_callback_bridge.sh").read_text(encoding="utf-8")

    assert "kubectl port-forward \"svc/${SERVICE_NAME}\" \"${LOCAL_PORT}:${REMOTE_PORT}\" -n \"${NAMESPACE}\"" in script
    assert "cloudflared tunnel --config \"${CONFIG_PATH}\" run \"${TUNNEL_NAME}\"" in script
    assert "/health" in script


def test_secret_template_contains_expected_keys() -> None:
    template = Path("k8s/backend-secret.template.yaml").read_text(encoding="utf-8")

    assert "name: k8s-whisperer-secrets" in template
    assert "slack_bot_token:" in template
    assert "slack_signing_secret:" in template
    assert "gemini_api_key:" in template


def test_deploy_backend_script_forces_rollout_restart() -> None:
    script = Path("scripts/deploy_backend.sh").read_text(encoding="utf-8")

    assert "kubectl rollout restart deployment/k8s-whisperer -n default" in script
