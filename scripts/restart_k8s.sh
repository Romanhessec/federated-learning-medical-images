#!/bin/bash
echo "Restarting Kubernetes components..."

sudo systemctl restart kubelet
sudo systemctl restart docker

# remove stale pods in "Unknown" state
echo "Deleting stale pods..."
kubectl delete pod --all --force --grace-period=0 --all-namespaces

# reapply networking (Calico)
echo "Reapplying Calico networking..."
kubectl delete -f https://docs.projectcalico.org/manifests/calico.yaml
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# reapply DNS (CoreDNS) if needed
echo "Restarting CoreDNS..."
kubectl delete pod -n kube-system --selector k8s-app=kube-dns

# reapply deployments to ensure pods restart
echo "Reapplying deployments..."
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/

# wait 1 minute for pods to restart
sleep 60
echo "Done! Checking pod status..."
kubectl get pods --all-namespaces
