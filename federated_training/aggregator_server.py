#!/usr/bin/env python3
"""
Federated Learning Aggregator Server - Mock Implementation
"""

import grpc
from concurrent import futures
import time
import logging
from google.protobuf import empty_pb2

import weights_transmitting_pb2
import weights_transmitting_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WeightsAggregatorService(weights_transmitting_pb2_grpc.SendWeightsServicer):
    def __init__(self):
        logger.info("Mock Aggregator service initialized")
    
    def TransmitWeights(self, request, context):
        """Mock implementation - just log and return empty"""
        logger.info("Received weights from client (mock)")
        return empty_pb2.Empty()

def serve():
    """Start the gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    weights_transmitting_pb2_grpc.add_SendWeightsServicer_to_server(
        WeightsAggregatorService(), server
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
