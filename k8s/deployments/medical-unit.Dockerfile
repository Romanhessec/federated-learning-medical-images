FROM python:3.9

WORKDIR /app

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

# copy training 
COPY federated_training/train_medical_unit.py /app/train.py
COPY federated_training/pod_recognisition.py /app/pod_recognisition.py
# set defaults
# ENV CLIENT_DATA_DIR=/data/client
# ENV EPOCHS=3

# run the trainer on container start
CMD ["sleep", "infinity"]