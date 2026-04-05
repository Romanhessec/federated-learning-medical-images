#!/bin/bash
# Master deployment script - rebuilds and deploys everything from scratch

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=========================================="
echo "🔄 FEDERATED LEARNING FULL DEPLOYMENT"
echo "=========================================="

# Clean up old deployments first
echo ""
echo ">>> STEP 0: Cleaning up old deployments..."
k3s kubectl delete deployment federated-aggregator -n federated-learning --ignore-not-found=true
k3s kubectl delete statefulset medical-unit -n federated-learning --ignore-not-found=true
k3s kubectl delete pods --all -n federated-learning --ignore-not-found=true
echo "⏳ Waiting for pods to terminate..."
sleep 10

# Build and deploy aggregator
echo ""
echo ">>> STEP 1: Building aggregator..."
bash $SCRIPT_DIR/build_aggregator.sh

echo ""
echo ">>> STEP 2: Deploying aggregator..."
bash $SCRIPT_DIR/deploy_aggregator_docker_image.sh

# Build and deploy medical units
echo ""
echo ">>> STEP 3: Building medical units..."
docker build -t medical-unit-image:latest -f k8s/deployments/medical-unit.Dockerfile .
docker save -o medical-unit.tar medical-unit-image:latest
sudo k3s ctr images import medical-unit.tar

echo ""
echo ">>> STEP 4: Deploying medical units..."
k3s kubectl apply -f k8s/deployments/medical-unit-sts.yaml -n federated-learning
k3s kubectl apply -f k8s/services/medical-unit-service.yaml -n federated-learning

# Wait for medical units
TOTAL_PODS=5  # Change to 5 for full deployment
ELAPSED=0
MAX_WAIT=300

echo "⏳ Waiting for $TOTAL_PODS medical units to be READY..."
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    READY=$(k3s kubectl get statefulset medical-unit -n federated-learning -o jsonpath="{.status.readyReplicas}" 2>/dev/null || echo "0")
    
    if [[ "$READY" -eq "$TOTAL_PODS" ]]; then
        echo "✅ All $TOTAL_PODS medical units are READY!"
        break
    fi
    
    echo "⏳ Medical units ready: $READY/$TOTAL_PODS"
    ELAPSED=$((ELAPSED + 5))
    sleep 5
done

echo ""
echo "=========================================="
echo "✅ DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""
echo "Monitor logs with:"
echo "  k3s kubectl logs -f deployment/federated-aggregator -n federated-learning"
echo "  k3s kubectl logs -f pod/medical-unit-0 -n federated-learning"
echo "  k3s kubectl logs -f pod/medical-unit-1 -n federated-learning"
echo ""
echo "=========================================="

rm -f medical-unit.tar
