#!/bin/bash
# Build aggregator image

set -e

IMAGE_NAME="federated-aggregator"
IMAGE_TAG="latest"
DOCKERFILE_PATH="k8s/deployments/aggregator.Dockerfile"

echo "🚀 Building aggregator Docker image..."
docker build -t $IMAGE_NAME:$IMAGE_TAG -f $DOCKERFILE_PATH .

echo "📝 Verifying Docker image..."
if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "$IMAGE_NAME:$IMAGE_TAG"; then
    echo "❌ Image build failed!"
    exit 1
fi

echo "✅ Build successful: $IMAGE_NAME:$IMAGE_TAG"
