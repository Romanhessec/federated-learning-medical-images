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
import pickle
import os
from google.protobuf import empty_pb2

import weights_transmitting_pb2
import weights_transmitting_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WeightsAggregatorService(weights_transmitting_pb2_grpc.SendWeightsServicer):
    def __init__(self, num_clients=5, min_clients=2):
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
        self.weights_output_dir = '/dataset'  # Shared PVC mount
        logger.info(f"Aggregator initialized: expecting {num_clients} clients, min {min_clients}")
    
    def TransmitWeights(self, request, context):
        """Receive weights from a client and trigger aggregation if ready"""
        client_id = request.client_id
        
        with self.lock:
            self.received_weights[client_id] = request
            num_received = len(self.received_weights)
            logger.info(f"Received weights from client '{client_id}' ({num_received}/{self.num_clients})")
            
            # Trigger aggregation if we have enough clients
            if num_received >= self.min_clients:
                logger.info(f"Threshold reached ({num_received} >= {self.min_clients}). Performing FedAvg...")
                self.federated_averaging()
                self.received_weights.clear()  # Reset for next round
                self.round_number += 1
        
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
                array = np.array(tensor.data, dtype=np.float32).reshape(tensor.shape)
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
        
        # Log weight statistics for verification
        for i, w in enumerate(aggregated_weights):
            logger.info(f"  Layer {i}: shape={w.shape}, mean={w.mean():.6f}, std={w.std():.6f}")
        
        # Save weights to disk for evaluation
        self.save_global_weights()
    
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
        
        # Log weight statistics for verification
        for i, w in enumerate(aggregated_weights):
            logger.info(f"  Layer {i}: shape={w.shape}, mean={w.mean():.6f}, std={w.std():.6f}")
    
    def get_global_weights(self):
        """Return the current global model weights (for future use)"""
        with self.lock:
            return self.global_weights
    
    def GetGlobalWeights(self, request, context):
        """Send global weights to a requesting client"""
        with self.lock:
            if self.global_weights is None:
                logger.warning("No global weights available yet")
                return weights_transmitting_pb2.ModelWeights()  # Empty message
            
            # Convert numpy arrays back to protobuf
            msg = weights_transmitting_pb2.ModelWeights()
            msg.client_id = "global"
            for w in self.global_weights:
                tensor = weights_transmitting_pb2.WeightTensor()
                tensor.data.extend(w.flatten().tolist())
                tensor.shape.extend(w.shape)
                msg.tensors.append(tensor)
            
            logger.info(f"✓ Sending global weights (round {self.round_number}) to client")
            return msg
    
    def save_global_weights(self):
        """Save global weights to disk for evaluation"""
        if self.global_weights is None:
            logger.warning("No global weights to save")
            return
        
        try:
            output_path = os.path.join(self.weights_output_dir, 'global_model_weights.pkl')
            with open(output_path, 'wb') as f:
                pickle.dump(self.global_weights, f)
            logger.info(f"✓ Saved global weights to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save weights: {e}")

def serve():
    """Start the gRPC server"""
    # For minimal testing with 2 pods, set min_clients=2
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    weights_transmitting_pb2_grpc.add_SendWeightsServicer_to_server(
        WeightsAggregatorService(num_clients=5, min_clients=2), server
    )
    
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting mock aggregator server on {listen_addr}")
    server.start()
    
    try:
        while True:
            time.sleep(3600)  # Keep server running
    except KeyboardInterrupt:
        logger.info("Shutting down aggregator server...")
        server.stop(0)

if __name__ == '__main__':
    serve()
