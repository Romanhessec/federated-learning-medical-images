#!/usr/bin/env python3
"""
Federated Learning Aggregator Server - FedAvg Implementation
"""

import grpc
from concurrent import futures
import time
import logging
import numpy as np
import threading
from google.protobuf import empty_pb2
import weights_transmitting_pb2
import weights_transmitting_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== Prometheus Metrics (optional) ==========
# If prometheus_client is not installed, all metric objects become no-ops
# so the server runs identically — just without /metrics export.

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    logger.warning("prometheus_client not installed — metrics disabled")

    # No-op fallbacks that mirror the prometheus_client API
    class _NoOpMetric:
        """Drop-in silent replacement for any Prometheus metric."""
        def inc(self, *a, **kw): pass
        def set(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def labels(self, **kw): return self
        def time(self):
            """Context-manager that does nothing."""
            import contextlib
            return contextlib.nullcontext()

    def _noop_factory(*args, **kwargs):
        return _NoOpMetric()

    Counter = Gauge = Histogram = _noop_factory
    def start_http_server(*a, **kw): pass

# FL round tracking
FL_ROUNDS_COMPLETED = Counter(
    'fl_rounds_completed_total',
    'Total number of federated learning rounds completed'
)
FL_ROUND_CURRENT = Gauge(
    'fl_round_current',
    'Current federated learning round number'
)

# Client participation
FL_CLIENTS_REPORTED = Gauge(
    'fl_clients_reported',
    'Number of clients that have reported weights in the current round'
)
FL_CLIENTS_IN_LAST_ROUND = Gauge(
    'fl_clients_in_last_round',
    'Number of clients that participated in the last completed round'
)
FL_WEIGHTS_RECEIVED = Counter(
    'fl_weights_received_total',
    'Total number of weight submissions received',
    ['client_id']
)

# Aggregation performance
FL_AGGREGATION_DURATION = Histogram(
    'fl_aggregation_duration_seconds',
    'Time spent performing federated averaging',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

# gRPC request performance
FL_GRPC_DURATION = Histogram(
    'fl_grpc_request_duration_seconds',
    'Duration of gRPC TransmitWeights calls',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
)
FL_GRPC_REQUESTS = Counter(
    'fl_grpc_requests_total',
    'Total gRPC requests received',
    ['status']
)

# Global model weight statistics (per layer)
FL_GLOBAL_WEIGHT_MEAN = Gauge(
    'fl_global_weight_mean',
    'Mean of global model weights after aggregation',
    ['layer']
)
FL_GLOBAL_WEIGHT_STD = Gauge(
    'fl_global_weight_std',
    'Standard deviation of global model weights after aggregation',
    ['layer']
)
FL_GLOBAL_MODEL_LAYERS = Gauge(
    'fl_global_model_layers',
    'Number of layers in the global model'
)

# Weight payload size
FL_WEIGHT_PAYLOAD_TENSORS = Histogram(
    'fl_weight_payload_tensors',
    'Number of tensors in a received weight payload',
    buckets=[1, 2, 4, 8, 16, 32, 64]
)

class WeightsAggregatorService(weights_transmitting_pb2_grpc.SendWeightsServicer):
    def __init__(self, num_clients=5, min_clients=3):
        """
        Initialize the aggregator service.
        
        Args:
            num_clients: Total expected number of clients
            min_clients: Minimum clients needed before aggregation
        """
        self.num_clients = num_clients
        self.min_clients = min_clients
        self.received_weights = {}  # {client_id: ModelWeights}
        self.global_weights = None
        self.round_number = 0
        self.lock = threading.Lock()
        logger.info(f"Aggregator initialized: expecting {num_clients} clients, min {min_clients}")
    
    def TransmitWeights(self, request, context):
        """Receive weights from a client and trigger aggregation if ready"""
        start_time = time.time()
        client_id = request.client_id
        
        try:
            with self.lock:
                self.received_weights[client_id] = request
                num_received = len(self.received_weights)
                logger.info(f"Received weights from client '{client_id}' ({num_received}/{self.num_clients})")
                
                # Record metrics for this submission
                FL_WEIGHTS_RECEIVED.labels(client_id=client_id).inc()
                FL_CLIENTS_REPORTED.set(num_received)
                FL_WEIGHT_PAYLOAD_TENSORS.observe(len(request.weights))
                
                # Trigger aggregation if we have enough clients
                if num_received >= self.min_clients:
                    logger.info(f"Threshold reached ({num_received} >= {self.min_clients}). Performing FedAvg...")
                    FL_CLIENTS_IN_LAST_ROUND.set(num_received)
                    
                    with FL_AGGREGATION_DURATION.time():
                        self.federated_averaging()
                    
                    FL_ROUNDS_COMPLETED.inc()
                    self.received_weights.clear()  # Reset for next round
                    self.round_number += 1
                    FL_ROUND_CURRENT.set(self.round_number)
                    FL_CLIENTS_REPORTED.set(0)
            
            FL_GRPC_REQUESTS.labels(status='ok').inc()
        except Exception as e:
            FL_GRPC_REQUESTS.labels(status='error').inc()
            logger.error(f"Error processing weights from '{client_id}': {e}")
            raise
        finally:
            FL_GRPC_DURATION.observe(time.time() - start_time)
        
        return empty_pb2.Empty()
    
    def federated_averaging(self):
        """Perform federated averaging on collected weights"""
        if not self.received_weights:
            logger.warning("No weights to aggregate")
            return
        
        num_clients = len(self.received_weights)
        logger.info(f"Aggregating weights from {num_clients} clients")
        
        # Convert protobuf weights to numpy arrays
        all_client_weights = []
        for client_id, model_weights in self.received_weights.items():
            client_weights_list = []
            for tensor in model_weights.tensors:
                # Reconstruct numpy array from flattened data and shape
                array = np.array(tensor.data).reshape(tensor.shape)
                client_weights_list.append(array)
            all_client_weights.append(client_weights_list)
            logger.info(f"  - Client '{client_id}': {len(client_weights_list)} weight tensors")
        
        # Perform averaging: average each layer across all clients
        aggregated_weights = []
        num_layers = len(all_client_weights[0])
        
        for layer_idx in range(num_layers):
            # Stack weights from all clients for this layer
            layer_weights = [client_weights[layer_idx] for client_weights in all_client_weights]
            # Average them
            avg_weight = np.mean(layer_weights, axis=0)
            aggregated_weights.append(avg_weight)
        
        # Store global weights
        self.global_weights = aggregated_weights
        logger.info(f"✓ Round {self.round_number} complete: Global model updated with {num_layers} layers")
        
        # Log weight statistics for verification and export to Prometheus
        FL_GLOBAL_MODEL_LAYERS.set(num_layers)
        for i, w in enumerate(aggregated_weights):
            w_mean = float(w.mean())
            w_std = float(w.std())
            FL_GLOBAL_WEIGHT_MEAN.labels(layer=str(i)).set(w_mean)
            FL_GLOBAL_WEIGHT_STD.labels(layer=str(i)).set(w_std)
            logger.info(f"  Layer {i}: shape={w.shape}, mean={w_mean:.6f}, std={w_std:.6f}")
    
    # Not used yet, but could be extended to support weighted averaging based on dataset sizes
    def weighted_federated_averaging(self, dataset_sizes):
        """
        Perform weighted federated averaging on collected weights.
        
        Weights are averaged proportionally to each client's dataset size.
        Formula: global_weight = sum(n_i * w_i) / sum(n_i)
        
        Args:
            dataset_sizes: Dict mapping client_id to number of samples
                          e.g., {'client_0': 1000, 'client_1': 1500, ...}
        
        This is more realistic for medical settings where hospitals have
        different numbers of patients.
        """
        if not self.received_weights:
            logger.warning("No weights to aggregate")
            return
        
        num_clients = len(self.received_weights)
        logger.info(f"Aggregating weights from {num_clients} clients (weighted by dataset size)")
        
        # Convert protobuf weights to numpy arrays
        all_client_weights = []
        client_ids = []
        weights_per_client = []
        
        total_samples = 0
        for client_id, model_weights in self.received_weights.items():
            client_weights_list = []
            for tensor in model_weights.tensors:
                # Reconstruct numpy array from flattened data and shape
                array = np.array(tensor.data).reshape(tensor.shape)
                client_weights_list.append(array)
            
            all_client_weights.append(client_weights_list)
            client_ids.append(client_id)
            
            # Get dataset size for this client (default to 1 if not provided)
            num_samples = dataset_sizes.get(client_id, 1)
            weights_per_client.append(num_samples)
            total_samples += num_samples
            
            logger.info(f"  - Client '{client_id}': {len(client_weights_list)} tensors, {num_samples} samples")
        
        # Normalize weights to sum to 1
        normalized_weights = [w / total_samples for w in weights_per_client]
        logger.info(f"  Total samples: {total_samples}")
        logger.info(f"  Normalized weights: {[f'{w:.4f}' for w in normalized_weights]}")
        
        # Perform weighted averaging: weighted sum for each layer
        aggregated_weights = []
        num_layers = len(all_client_weights[0])
        
        for layer_idx in range(num_layers):
            # Weighted sum of this layer across all clients
            weighted_layer = None
            for client_idx, client_weights in enumerate(all_client_weights):
                layer_weight = client_weights[layer_idx] * normalized_weights[client_idx]
                if weighted_layer is None:
                    weighted_layer = layer_weight
                else:
                    weighted_layer += layer_weight
            
            aggregated_weights.append(weighted_layer)
        
        # Store global weights
        self.global_weights = aggregated_weights
        logger.info(f"✓ Round {self.round_number} complete: Global model updated with {num_layers} layers (weighted)")
        
        # Log weight statistics for verification and export to Prometheus
        FL_GLOBAL_MODEL_LAYERS.set(num_layers)
        for i, w in enumerate(aggregated_weights):
            w_mean = float(w.mean())
            w_std = float(w.std())
            FL_GLOBAL_WEIGHT_MEAN.labels(layer=str(i)).set(w_mean)
            FL_GLOBAL_WEIGHT_STD.labels(layer=str(i)).set(w_std)
            logger.info(f"  Layer {i}: shape={w.shape}, mean={w_mean:.6f}, std={w_std:.6f}")
    
    def get_global_weights(self):
        """Return the current global model weights (for future use)"""
        with self.lock:
            return self.global_weights

def serve():
    """Start the gRPC server and Prometheus metrics endpoint"""
    # Start Prometheus metrics HTTP server on port 8000 (no-op if lib missing)
    metrics_port = 8000
    start_http_server(metrics_port)
    if METRICS_ENABLED:
        logger.info(f"Prometheus metrics server started on :{metrics_port}/metrics")
    else:
        logger.info("Running without Prometheus metrics (prometheus_client not installed)")
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    weights_transmitting_pb2_grpc.add_SendWeightsServicer_to_server(
        WeightsAggregatorService(), server
    )
    
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting aggregator server on {listen_addr}")
    server.start()
    
    try:
        while True:
            time.sleep(3600)  # Keep server running
    except KeyboardInterrupt:
        logger.info("Shutting down aggregator server...")
        server.stop(0)

if __name__ == '__main__':
    serve()
