#!/bin/bash

set -e

TAR_FILE="medical-unit.tar"
NAMESPACE="federated-learning"

MAX_WAIT_TIME=300
INTERVAL=5
ELAPSED_TIME=0

# echo "🗑️ Removing old Kubernetes deployment (if exists)..."
# kubectl delete deployment medical-unit -n federated-learning --ignore-not-found=true

# # wait 60 seconds for medical-unit deployment to terminate
# sleep 60
# echo "✅ Verifying no old pods remain..."
# kubectl get pods -n $NAMESPACE

echo "🚀 Deploying Medical Units to Kubernetes..."
k3s kubectl apply -f k8s/deployments/ --recursive
k3s kubectl apply -f k8s/services/ --recursive

echo "⏳ Waiting for all medical unit pods to be READY..."
while [[ $ELAPSED_TIME -lt $MAX_WAIT_TIME ]]; do
    # count ready medical unit pods
    READY_PODS=$(kubectl get pods -n $NAMESPACE -l app=medical-unit \
        --field-selector=status.phase=Running \
        -o=jsonpath="{.items[*].status.conditions[?(@.type=='Ready')].status}" \
        | grep -o "True" | wc -l)

    TOTAL_PODS=$(kubectl get statefulset medical-unit -n $NAMESPACE -o jsonpath="{.spec.replicas}")

    echo "🔍 Ready Pods: $READY_PODS / $TOTAL_PODS"

    if [[ "$READY_PODS" -ge "$TOTAL_PODS" ]]; then
        echo "✅ All Medical Unit pods are READY!"
        break
    fi

    # timeout handling
    ELAPSED_TIME=$((ELAPSED_TIME + INTERVAL))
    if [[ $ELAPSED_TIME -ge $MAX_WAIT_TIME ]]; then
        echo "❌ Timeout: Pods did not reach Ready state within 5 minutes!"
        kubectl get pods -n $NAMESPACE -o wide
        exit 1
    fi

    echo "⏳ Checking again in $INTERVAL seconds..."
    sleep $INTERVAL
done

echo "🔍 Checking pod status..."
kubectl get pods -n $NAMESPACE -o wide

echo "🗑️ Cleaning up the temporary image tar file..."
sudo chown $USER:$USER medical-unit.tar
sudo rm -f $TAR_FILE

echo "✅ Deployment complete!"