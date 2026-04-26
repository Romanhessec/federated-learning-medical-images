FROM tensorflow/tensorflow:2.16.1-gpu

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends vim protobuf-compiler
    
# install runtime dependencies: Pandas, gRPC, protobuf compiler (TF already included in base image)
# protobuf must stay <6.0.0 to be compatible with tensorflow 2.19.0
RUN pip install --no-cache-dir \
    pandas \
    "grpcio==1.71.0" \
    "protobuf>=3.20.3,<6.0.0" \
    "grpcio-tools==1.71.0"

# copy .proto and pre-generated gRPC stubs
COPY federated_training/weights_transmitting.proto /app/weights_transmitting.proto
COPY federated_training/weights_transmitting_pb2.py /app/weights_transmitting_pb2.py
COPY federated_training/weights_transmitting_pb2_grpc.py /app/weights_transmitting_pb2_grpc.py

# copy scripts
COPY federated_training/pod_recognisition.py /app/pod_recognisition.py
COPY federated_training/train_local.py /app/train_local.py
COPY federated_training/data_loader.py /app/data_loader.py
# set defaults
# ENV CLIENT_DATA_DIR=/data/client
# ENV EPOCHS=3

# run the trainer on container start
CMD ["sleep", "infinity"]