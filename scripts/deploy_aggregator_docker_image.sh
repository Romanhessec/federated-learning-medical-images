#!/bin/bash
# Build script for the Federated Learning Aggregator

set -e

IMAGE_NAME="federated-aggregator"
IMAGE_TAG="latest"
TAR_FILE="federated-aggregator.tar"
DOCKERFILE_PATH="k8s/deployments/aggregator.Dockerfile"
NAMESPACE="federated-learning"

echo "🚀 Building the Docker image..."
docker build -t $IMAGE_NAME:$IMAGE_TAG -f $DOCKERFILE_PATH .

echo "📝 Verifying Docker image exists..."
if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "$IMAGE_NAME:$IMAGE_TAG"; then
    echo "❌ Image build failed!"
    exit 1
fi
echo "🔄 Saving Docker image as a tar file..."
docker save -o $TAR_FILE $IMAGE_NAME:$IMAGE_TAG

echo "✅ Building complete!"
