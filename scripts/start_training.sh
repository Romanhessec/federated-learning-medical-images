#!/bin/bash
# Start federated training across all pods and stream real-time logs.
# Aggregator starts first, then all 5 clients start in parallel.
# Logs from all pods are streamed simultaneously with color-coded prefixes.
# Press Ctrl+C to stop following logs (training continues in pods).

set -e

NS="federated-learning"

# ANSI colors for each pod
C_RESET="\033[0m"
C_AGGREGATOR="\033[1;36m"   # Bold Cyan
C_CLIENT_0="\033[1;32m"     # Bold Green
C_CLIENT_1="\033[1;33m"     # Bold Yellow
C_CLIENT_2="\033[1;34m"     # Bold Blue
C_CLIENT_3="\033[1;35m"     # Bold Magenta
C_CLIENT_4="\033[1;31m"     # Bold Red

echo -e "${C_AGGREGATOR}=========================================="
echo -e "  FEDERATED LEARNING TRAINING START"
echo -e "==========================================${C_RESET}"
echo ""

# --- Check all pods are running ---
echo "Checking pods..."
NOT_READY=$(k3s kubectl get pods -n $NS --no-headers | grep -v "Running" | grep -v "^$" || true)
if [[ -n "$NOT_READY" ]]; then
    echo "ERROR: Some pods are not in Running state:"
    echo "$NOT_READY"
    echo "Run ./scripts/deploy_all.sh first."
    exit 1
fi
echo -e "${C_AGGREGATOR}✅ All pods are Running${C_RESET}"
echo ""

# --- Start aggregator ---
echo -e "${C_AGGREGATOR}>>> Starting aggregator server...${C_RESET}"
AGGREGATOR_POD=$(k3s kubectl get pod -n $NS -l app=federated-aggregator -o jsonpath='{.items[0].metadata.name}')
k3s kubectl exec -n $NS "$AGGREGATOR_POD" -- bash -c "nohup python3 /app/aggregator_server.py > /tmp/aggregator.log 2>&1 &"
echo -e "${C_AGGREGATOR}✅ Aggregator started (pod: $AGGREGATOR_POD)${C_RESET}"
echo ""

# Give aggregator 3 seconds to bind to its port before clients connect
sleep 3

# --- Start all 5 clients in parallel ---
echo -e ">>> Starting 5 medical unit clients...${C_RESET}"
for i in 0 1 2 3 4; do
    k3s kubectl exec -n $NS "medical-unit-$i" -- bash -c "nohup python3 /app/train_local.py > /tmp/train.log 2>&1 &"
    echo -e "  Client $i started"
done
echo ""
echo -e "✅ All clients started. Streaming logs (Ctrl+C to stop following, training continues)..."
echo ""
echo -e "=========================================="
echo ""

# --- Stream logs from all pods in parallel with colored prefixes ---
stream_pod_logs() {
    local pod=$1
    local prefix=$2
    local color=$3
    # --follow with --since=1s to pick up from now
    k3s kubectl exec -n $NS "$pod" -- tail -f /tmp/train.log 2>/dev/null \
        | while IFS= read -r line; do
            echo -e "${color}[${prefix}]${C_RESET} $line"
        done
}

stream_aggregator_logs() {
    k3s kubectl exec -n $NS "$AGGREGATOR_POD" -- tail -f /tmp/aggregator.log 2>/dev/null \
        | while IFS= read -r line; do
            echo -e "${C_AGGREGATOR}[AGGREGATOR]${C_RESET} $line"
        done
}

# Launch all log streams in background
stream_aggregator_logs &
PIDS=($!)

stream_pod_logs "medical-unit-0" "CLIENT-0" "$C_CLIENT_0" & PIDS+=($!)
stream_pod_logs "medical-unit-1" "CLIENT-1" "$C_CLIENT_1" & PIDS+=($!)
stream_pod_logs "medical-unit-2" "CLIENT-2" "$C_CLIENT_2" & PIDS+=($!)
stream_pod_logs "medical-unit-3" "CLIENT-3" "$C_CLIENT_3" & PIDS+=($!)
stream_pod_logs "medical-unit-4" "CLIENT-4" "$C_CLIENT_4" & PIDS+=($!)

# On Ctrl+C, kill all background log streamers (training in pods keeps running)
cleanup() {
    echo ""
    echo -e "${C_AGGREGATOR}Log streaming stopped. Training continues inside pods.${C_RESET}"
    echo ""
    echo "To re-attach to logs later:"
    echo "  Aggregator: k3s kubectl exec -n $NS $AGGREGATOR_POD -- tail -f /tmp/aggregator.log"
    echo "  Client 0:   k3s kubectl exec -n $NS medical-unit-0 -- tail -f /tmp/train.log"
    echo ""
    echo "To evaluate after training:"
    echo "  python3 federated_training/evaluate_model.py"
    kill "${PIDS[@]}" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

wait
