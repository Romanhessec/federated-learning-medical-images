#!/bin/bash
# ============================================================
#  Deploy the monitoring stack (Prometheus + Grafana + Alertmanager)
#  on K3s using the kube-prometheus-stack Helm chart.
# ============================================================

set -e

KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
export KUBECONFIG

NAMESPACE="monitoring"
RELEASE_NAME="kube-prometheus-stack"
CHART="prometheus-community/kube-prometheus-stack"
GRAFANA_NODEPORT=30080
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"

# ── 1. Install Helm if not present ──────────────────────────
if ! command -v helm &> /dev/null; then
    echo "📦 Helm not found. Installing Helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
else
    echo "✅ Helm is already installed: $(helm version --short)"
fi

# ── 2. Add the Prometheus community Helm repo ──────────────
echo "📦 Adding prometheus-community Helm repo..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update

# ── 3. Create the monitoring namespace ──────────────────────
echo "🆕 Ensuring '${NAMESPACE}' namespace exists..."
k3s kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | k3s kubectl apply -f -

# ── 4. Install / upgrade the kube-prometheus-stack ──────────
echo "🚀 Installing kube-prometheus-stack..."
helm upgrade --install "${RELEASE_NAME}" "${CHART}" \
    --namespace "${NAMESPACE}" \
    --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
    --set prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues=false \
    --set grafana.adminPassword="${GRAFANA_PASSWORD}" \
    --set grafana.service.type=NodePort \
    --set grafana.service.nodePort="${GRAFANA_NODEPORT}" \
    --set grafana.sidecar.dashboards.enabled=true \
    --set grafana.sidecar.dashboards.searchNamespace=ALL \
    --set alertmanager.enabled=true \
    --set nodeExporter.enabled=true \
    --set kubeStateMetrics.enabled=true \
    --wait --timeout 10m

echo ""
echo "✅ Monitoring stack deployed!"
echo ""

# ── 5. Apply FL-specific monitoring resources ───────────────
echo "📊 Applying ServiceMonitors and alert rules..."
k3s kubectl apply -f k8s/monitoring/ --recursive

echo ""
echo "✅ ServiceMonitors and PrometheusRules applied."
echo ""

# ── 6. Show access info ────────────────────────────────────
NODE_IP=$(k3s kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

echo "============================================="
echo "  Monitoring Stack Access"
echo "============================================="
echo ""
echo "  Grafana:      http://${NODE_IP}:${GRAFANA_NODEPORT}"
echo "  Credentials:  admin / ${GRAFANA_PASSWORD}"
echo ""
echo "  Prometheus:    kubectl port-forward -n ${NAMESPACE} svc/${RELEASE_NAME}-prometheus 9090:9090"
echo "                 then open http://localhost:9090"
echo ""
echo "  Alertmanager:  kubectl port-forward -n ${NAMESPACE} svc/${RELEASE_NAME}-alertmanager 9093:9093"
echo "                 then open http://localhost:9093"
echo ""
echo "============================================="

# ── 7. Verify pods are running ──────────────────────────────
echo ""
echo "📋 Monitoring pods status:"
k3s kubectl get pods -n "${NAMESPACE}" -o wide
