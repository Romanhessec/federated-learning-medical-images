FROM python:3.9

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends vim
    
# install runtime dependencies: TF, Pandas, gRPC, protobuf compiler
RUN pip install --no-cache-dir \
    tensorflow \
    pandas \
    grpcio \
    protobuf \
    grpcio-tools

# copy .proto and generate Python gRPC stubs
# TO DO
# COPY aggregator.proto /app/
# RUN python -m grpc_tools.protoc \
#     -I. \
#     --python_out=. \
#     --grpc_python_out=. \
#     aggregator.proto

# copy scripts
COPY federated_training/pod_recognisition.py /app/pod_recognisition.py
COPY federated_training/train_local.py /app/train_local.py
COPY federated_training/data_loader.py /app/data_loader.py
# set defaults
# ENV CLIENT_DATA_DIR=/data/client
# ENV EPOCHS=3

# run the trainer on container start
CMD ["sleep", "infinity"]