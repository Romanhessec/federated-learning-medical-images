# Aggregator Dockerfile for Federated Learning
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    numpy \
    grpcio \
    grpcio-tools \
    protobuf

# Copy gRPC proto files and generated Python files
COPY federated_training/weights_transmitting.proto /app/
COPY federated_training/weights_transmitting_pb2.py /app/
COPY federated_training/weights_transmitting_pb2_grpc.py /app/

# Copy aggregator server
COPY federated_training/aggregator_server.py /app/

# Generate gRPC files (in case they're not present)
RUN python -m grpc_tools.protoc \
    --python_out=. \
    --grpc_python_out=. \
    weights_transmitting.proto

# Expose gRPC port
EXPOSE 50051

# run the trainer on container start
CMD ["sleep", "infinity"]
