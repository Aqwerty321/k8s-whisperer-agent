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


def test_crashloop_demo_uses_replacement_state_marker() -> None:
    manifest = Path("k8s/demo/crashloop.yaml").read_text(encoding="utf-8")

    assert "kind: Deployment" in manifest
    assert "type: Recreate" in manifest
    assert "/tmp/k8s-whisperer-demo-crashloop" in manifest
    assert "recovered after pod replacement" in manifest


def test_deploy_demo_resets_crashloop_state() -> None:
    script = Path("scripts/deploy_demo.sh").read_text(encoding="utf-8")

    assert "minikube ssh -- \"sudo rm -rf /tmp/k8s-whisperer-demo-crashloop && sudo mkdir -p /tmp/k8s-whisperer-demo-crashloop\"" in script
    assert "kubectl delete deployment demo-crashloop -n default --ignore-not-found" in script
    assert "kubectl delete pod demo-oomkill -n default --ignore-not-found" in script
    assert "kubectl rollout status deployment/demo-oomkill -n default" in script


def test_backend_manifest_uses_persistent_runtime_volume_and_tuned_probes() -> None:
    manifest = Path("k8s/backend.yaml").read_text(encoding="utf-8")

    assert "kind: PersistentVolumeClaim" in manifest
    assert "name: k8s-whisperer-runtime" in manifest
    assert "persistentVolumeClaim:" in manifest
    assert "timeoutSeconds: 3" in manifest
    assert "failureThreshold: 6" in manifest


def test_makefile_includes_demo_reset_and_ready_targets() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "demo-reset:" in makefile
    assert "demo-ready:" in makefile
    assert "demo-snapshot:" in makefile
    assert "demo-reset-oomkill:" in makefile


def test_demo_reset_script_clears_runtime_files() -> None:
    script = Path("scripts/demo_reset.sh").read_text(encoding="utf-8")

    assert "langgraph-checkpoints.pkl" in script
    assert "audit.jsonl" in script
    assert script.count("kubectl rollout restart deployment/k8s-whisperer -n default") >= 2


def test_backup_approval_script_signs_local_callback() -> None:
    script = Path("scripts/approve_incident.sh").read_text(encoding="utf-8")

    assert "X-Slack-Request-Timestamp" in script
    assert "X-Slack-Signature" in script
    assert "/api/slack/actions" in script
    assert "awaiting_human" in script


def test_demo_snapshot_script_reports_health_incidents_and_audit() -> None:
    script = Path("scripts/demo_snapshot.sh").read_text(encoding="utf-8")

    assert "/health" in script
    assert "/api/incidents" in script
    assert "/api/audit" in script
    assert "tracked_incidents" in script
    assert "INCIDENT_LIMIT" in script
    assert "AUDIT_LIMIT" in script


def test_demo_incident_oomkill_uses_live_pod_name() -> None:
    script = Path("scripts/demo_incident.sh").read_text(encoding="utf-8")

    assert "kubectl get pods -n default -l app=demo-oomkill" in script
    assert "jq -n" in script
    assert "ownerReferences" in script


def test_oomkill_demo_uses_deployment_workload() -> None:
    manifest = Path("k8s/demo/oomkill.yaml").read_text(encoding="utf-8")

    assert "kind: Deployment" in manifest
    assert "72 * 1024 * 1024" in manifest


def test_rbac_includes_deployment_patch_permissions() -> None:
    manifest = Path("k8s/rbac.yaml").read_text(encoding="utf-8")

    assert 'apiGroups: ["apps"]' in manifest
    assert 'resources: ["deployments"]' in manifest
    assert 'verbs: ["get", "list", "watch", "patch"]' in manifest


def test_rubric_mapping_doc_mentions_safety_and_demoability() -> None:
    rubric = Path("docs/rubric-mapping.md").read_text(encoding="utf-8")

    assert "Safety And Reliability" in rubric
    assert "Demoability" in rubric
    assert "fallback local approval path" in rubric


def test_demo_reset_oomkill_script_restores_failing_memory_limit() -> None:
    script = Path("scripts/demo_reset_oomkill.sh").read_text(encoding="utf-8")

    assert 'kubectl patch deployment demo-oomkill' in script
    assert '"64Mi"' in script
    assert '"32Mi"' in script


def test_export_incident_report_script_uses_report_endpoint() -> None:
    script = Path("scripts/export_incident_report.sh").read_text(encoding="utf-8")

    assert "/api/incidents/${INCIDENT_ID}/report" in script
    assert "limit=1" in script
