#!/bin/bash
echo "🚀 Restarting K3s and Kubernetes components..."

# Restart K3s service
echo "🔄 Restarting K3s..."
sudo systemctl restart k3s

sleep 5

# remove stale pods in "Unknown" state
echo "🗑️ Deleting stale pods..."
k3s kubectl delete pod --all --force --grace-period=0 --all-namespaces --ignore-not-found=true

# reapply networking (Calico)
echo "🌐 Reapplying Calico networking..."
k3s kubectl delete -f https://docs.projectcalico.org/manifests/calico.yaml --ignore-not-found=true
k3s kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# wait for Calico to stabilize
echo "⏳ Waiting for Calico pods to start..."
sleep 30
k3s kubectl get pods -n kube-system | grep calico

# restart coredns - sometimes it is needed
echo "🔄 Restarting CoreDNS..."
k3s kubectl delete pod -n kube-system --selector k8s-app=kube-dns --ignore-not-found=true

# ensure namespace exists before any namespaced resources
echo "🆕 Ensuring 'federated-learning' namespace exists..."
k3s kubectl create namespace federated-learning --dry-run=client -o yaml | k3s kubectl apply -f -

# apply PV + PVC 
echo "💾 Applying PV & PVC for master dataset..."
k3s kubectl apply -f k8s/storage/master-data-pv.yaml
k3s kubectl apply -f k8s/storage/master-data-pvc.yaml

# wait for PVC to bind
echo "⏳ Waiting for PV to bind (master-data-pvc)…"
k3s kubectl wait --for=condition=Bound pvc/master-data-pvc -n federated-learning --timeout=120s

# remove old StatefulSet
echo "🗑️ Removing old StatefulSet so we can recreate with the new spec…"
k3s kubectl delete statefulset medical-unit -n federated-learning --ignore-not-found

# reapply deployments and services
echo "🔁 Reapplying deployments and services..."
k3s kubectl apply -f k8s/deployments/ --recursive
k3s kubectl apply -f k8s/services/ --recursive

# ── Monitoring stack ────────────────────────────────────────
echo "🆕 Ensuring 'monitoring' namespace exists..."
k3s kubectl create namespace monitoring --dry-run=client -o yaml | k3s kubectl apply -f -

# Check if kube-prometheus-stack Helm release exists; if not, prompt to install
if command -v helm &> /dev/null; then
    RELEASE_STATUS=$(helm status kube-prometheus-stack -n monitoring --kubeconfig /etc/rancher/k3s/k3s.yaml 2>/dev/null || true)
    if [ -z "$RELEASE_STATUS" ]; then
        echo "⚠️  kube-prometheus-stack Helm release not found."
        echo "   Run ./scripts/deploy_monitoring.sh to install the monitoring stack."
    else
        echo "✅ kube-prometheus-stack Helm release found."
    fi
else
    echo "⚠️  Helm not installed. Run ./scripts/deploy_monitoring.sh to install Helm and the monitoring stack."
fi

# Reapply FL-specific monitoring resources (ServiceMonitors, alerts, dashboards)
echo "📊 Reapplying monitoring resources (ServiceMonitors, alerts, dashboards)..."
k3s kubectl apply -f k8s/monitoring/ --recursive

echo "⏳ Waiting for pods to stabilize..."
sleep 60

echo "✅ Done! Checking pod status..."
k3s kubectl get pods --all-namespaces

# Show monitoring pod status separately for clarity
echo ""
echo "📊 Monitoring pods:"
k3s kubectl get pods -n monitoring -o wide 2>/dev/null || echo "   (monitoring namespace not found — run ./scripts/deploy_monitoring.sh)"
