#!/bin/bash

set -e

IMAGE_NAME="medical-unit-image"
IMAGE_TAG="latest"
TAR_FILE="medical-unit.tar"
DOCKERFILE_PATH="k8s/deployments/medical-unit.Dockerfile"

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