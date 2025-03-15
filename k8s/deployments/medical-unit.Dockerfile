FROM python:3.9

WORKDIR /app

RUN pip install --no-cache-dir tensorflow-federated numpy grpcio protobuf pandas

# copy tff training scripts
# COPY train.py /app/train.py

# set default command (change this later)
CMD ["sleep", "infinity"]