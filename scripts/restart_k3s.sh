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

# apply PVs + PVCs
echo "💾 Applying PV & PVC for master dataset..."
k3s kubectl apply -f k8s/storage/master-data-pv.yaml
k3s kubectl apply -f k8s/storage/master-data-pvc.yaml
k3s kubectl apply -f k8s/storage/clients-data-medical-unit-pv.yaml
k3s kubectl apply -f k8s/storage/clients-data-medical-unit-pvc.yaml

# wait for PVCs to bind
echo "⏳ Waiting for PVCs to bind (master-data-pvc)…"
k3s kubectl wait --for=condition=Bound pvc/master-data-pvc -n federated-learning --timeout=30s
k3s kubectl wait --for=condition=Bound pvc/pvc-client-data-medical-unit-0 -n federated-learning --timeout=20s
k3s kubectl wait --for=condition=Bound pvc/pvc-client-data-medical-unit-1 -n federated-learning --timeout=20s
k3s kubectl wait --for=condition=Bound pvc/pvc-client-data-medical-unit-2 -n federated-learning --timeout=20s
k3s kubectl wait --for=condition=Bound pvc/pvc-client-data-medical-unit-3 -n federated-learning --timeout=20s
k3s kubectl wait --for=condition=Bound pvc/pvc-client-data-medical-unit-4 -n federated-learning --timeout=20s

# remove old StatefulSet
echo "🗑️ Removing old StatefulSet so we can recreate with the new spec…"
k3s kubectl delete statefulset medical-unit -n federated-learning --ignore-not-found

# reapply deployments and services
echo "🔁 Reapplying deployments and services..."
k3s kubectl apply -f k8s/deployments/ --recursive
k3s kubectl apply -f k8s/services/ --recursive

echo "⏳ Waiting for pods to stabilize..."
sleep 60

echo "✅ Done! Checking pod status..."
k3s kubectl get pods --all-namespaces
