#!/bin/bash

set -e

IMAGE_NAME="medical-unit-image"
IMAGE_TAG="latest"
TAR_FILE="medical-unit.tar"
DOCKERFILE_PATH="k8s/deployments/medical-unit.Dockerfile"
NAMESPACE="federated-learning"

MAX_WAIT_TIME=300
INTERVAL=5
ELAPSED_TIME=0

echo "🚀 Building the Docker image..."
docker build -t $IMAGE_NAME:$IMAGE_TAG -f $DOCKERFILE_PATH .

echo "📝 Verifying Docker image exists..."
if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "$IMAGE_NAME:$IMAGE_TAG"; then
    echo "❌ Image build failed!"
    exit 1
fi

echo "🔄 Saving Docker image as a tar file..."
docker save -o $TAR_FILE $IMAGE_NAME:$IMAGE_TAG

echo "📦 Checking if tar file exists before import..."
if [[ -f "$TAR_FILE" ]]; then
    echo "✅ Tar file found, proceeding with import..."
else
    echo "❌ Tar file not found! Aborting import."
    exit 1
fi

echo "📦 Importing image into k3s containerd..."
sudo k3s ctr images import medical-unit.tar

echo "🗑️ Removing old Kubernetes deployment (if exists)..."
kubectl delete deployment medical-unit -n federated-learning --ignore-not-found=true

# wait 60 seconds for medical-unit deployment to terminate
sleep 60
echo "✅ Verifying no old pods remain..."
kubectl get pods -n $NAMESPACE

echo "🚀 Deploying Medical Units to Kubernetes..."
kubectl apply -f k8s/deployments/medical-unit-deployment.yaml

echo "⏳ Waiting for all medical unit pods to be READY..."
while [[ $ELAPSED_TIME -lt $MAX_WAIT_TIME ]]; do
    # count ready medical unit pods
    READY_PODS=$(kubectl get pods -n $NAMESPACE -l app=medical-unit \
        --field-selector=status.phase=Running \
        -o=jsonpath="{.items[*].status.conditions[?(@.type=='Ready')].status}" \
        | grep -o "True" | wc -l)

    TOTAL_PODS=$(kubectl get deployment medical-unit -n $NAMESPACE -o jsonpath="{.spec.replicas}")

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
rm -f $TAR_FILE

echo "✅ Deployment complete!"