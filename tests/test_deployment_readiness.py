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
