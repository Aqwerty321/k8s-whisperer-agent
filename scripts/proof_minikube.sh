#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-default}"

printf '== Minikube Profile ==\n'
minikube profile list

printf '\n== Cluster Info ==\n'
kubectl cluster-info

printf '\n== Current Context ==\n'
kubectl config current-context

printf '\n== Minikube Status ==\n'
minikube status

printf '\n== Nodes ==\n'
kubectl get nodes -o wide

printf '\n== Backend Deployment ==\n'
kubectl get deployment k8s-whisperer -n "${NAMESPACE}" -o wide

printf '\n== Backend Service ==\n'
kubectl get svc k8s-whisperer -n "${NAMESPACE}" -o wide

printf '\n== Backend Pods ==\n'
kubectl get pods -n "${NAMESPACE}" -l app=k8s-whisperer -o wide

printf '\n== Demo Workloads ==\n'
kubectl get deployment demo-crashloop demo-oomkill -n "${NAMESPACE}" -o wide
kubectl get pod demo-pending -n "${NAMESPACE}" -o wide

printf '\n== Namespace Inventory ==\n'
kubectl get all -n "${NAMESPACE}"

printf '\n== OOM Limit Proof ==\n'
kubectl get deployment demo-oomkill -n "${NAMESPACE}" -o jsonpath='{"memory_limit="}{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'

printf '\n== Local Backend Health ==\n'
curl -fsS http://127.0.0.1:8010/health | jq
