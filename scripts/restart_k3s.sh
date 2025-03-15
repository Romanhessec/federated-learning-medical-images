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

# reapply deployments and services
echo "🆕 Ensuring 'federated-learning' namespace exists..."
k3s kubectl create namespace federated-learning --dry-run=client -o yaml | k3s kubectl apply -f -

echo "🔁 Reapplying deployments and services..."
k3s kubectl apply -f k8s/deployments/ --recursive
k3s kubectl apply -f k8s/services/ --recursive


echo "⏳ Waiting for pods to stabilize..."
sleep 60


echo "✅ Done! Checking pod status..."
k3s kubectl get pods --all-namespaces
