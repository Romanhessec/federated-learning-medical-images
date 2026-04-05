#!/bin/bash
# Deploy aggregator to k3s (requires build_aggregator.sh to be run first)

set -e

IMAGE_NAME="federated-aggregator"
IMAGE_TAG="latest"
TAR_FILE="aggregator.tar"
NAMESPACE="federated-learning"

MAX_WAIT=300
ELAPSED=0

echo "🔄 Saving Docker image as tar file..."
docker save -o $TAR_FILE $IMAGE_NAME:$IMAGE_TAG

echo "📦 Importing image into k3s..."
sudo k3s ctr images import $TAR_FILE

echo "🔍 Verifying image is present in k3s containerd..."
if ! sudo k3s ctr images ls | grep -q "docker.io/library/${IMAGE_NAME}:${IMAGE_TAG}"; then
    echo "❌ Image import verification failed for ${IMAGE_NAME}:${IMAGE_TAG}"
    exit 1
fi

echo "🗑️ Deleting old aggregator deployment..."
k3s kubectl delete deployment federated-aggregator -n $NAMESPACE --ignore-not-found=true

echo "⏳ Waiting for old pods to terminate..."
sleep 10

echo "🚀 Deploying aggregator..."
k3s kubectl apply -f k8s/deployments/aggregator-deployment.yaml -n $NAMESPACE
k3s kubectl apply -f k8s/services/aggregator-service.yaml -n $NAMESPACE

echo "⏳ Waiting for aggregator to be READY..."
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    READY=$(k3s kubectl get deployment federated-aggregator -n $NAMESPACE -o jsonpath="{.status.conditions[?(@.type=='Available')].status}" 2>/dev/null || echo "False")
    
    if [[ "$READY" == "True" ]]; then
        echo "✅ Aggregator is READY!"
        break
    fi
    
    ELAPSED=$((ELAPSED + 5))
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo "❌ Timeout waiting for aggregator!"
        exit 1
    fi
    
    echo "⏳ Waiting... ($ELAPSED/$MAX_WAIT)"
    sleep 5
done

echo "🔍 Status:"
k3s kubectl get deployment,pods -n $NAMESPACE | grep aggregator

echo "🗑️ Cleaning up tar file..."
rm -f $TAR_FILE

echo "✅ Aggregator deployment complete!"
