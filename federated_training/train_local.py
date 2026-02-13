import os
import time
import logging
import tensorflow as tf
import grpc
import numpy as np
from prometheus_client import (
    Counter, Gauge, Histogram, start_http_server
)

import weights_transmitting_pb2, weights_transmitting_pb2_grpc

from data_loader import make_dataset
from pod_recognisition import get_client_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== Prometheus Metrics ==========

# Training progress
FL_TRAINING_LOSS = Gauge(
    'fl_training_loss',
    'Current training loss value'
)
FL_TRAINING_EPOCH = Gauge(
    'fl_training_epoch_current',
    'Current training epoch'
)
FL_TRAINING_STEP = Gauge(
    'fl_training_step_current',
    'Current training step within the epoch'
)
FL_TRAINING_STEPS_TOTAL = Counter(
    'fl_training_steps_total',
    'Total number of training steps completed'
)

# Training duration
FL_TRAINING_DURATION = Histogram(
    'fl_training_duration_seconds',
    'Total local training time across all epochs',
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600]
)
FL_EPOCH_DURATION = Histogram(
    'fl_training_epoch_duration_seconds',
    'Duration of a single training epoch',
    buckets=[5, 10, 30, 60, 120, 300, 600, 1200]
)

# Weight upload
FL_UPLOAD_DURATION = Histogram(
    'fl_weight_upload_duration_seconds',
    'Time to transmit weights to the aggregator via gRPC',
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)
FL_UPLOAD_STATUS = Counter(
    'fl_weight_upload_total',
    'Weight upload attempts',
    ['status']
)

# Dataset info
FL_DATASET_BATCHES = Gauge(
    'fl_dataset_batches_per_epoch',
    'Number of batches in the training dataset per epoch'
)

# Weight payload info
FL_WEIGHT_PAYLOAD_BYTES = Gauge(
    'fl_weight_payload_bytes',
    'Approximate size of the weight payload in bytes'
)

# ========== Start Prometheus metrics server ==========
metrics_port = 8000
start_http_server(metrics_port)
logger.info(f"Prometheus metrics server started on :{metrics_port}/metrics")

# ========== Model Definition ==========

def create_model():
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=(128,128,1)),
        tf.keras.layers.Conv2D(32,3,activation="relu"),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(1, activation="sigmoid")
    ])

def convert_weights_to_proto(weights, client_id="unknown"):
    """Convert model weights to a protobuf message."""
    model_weights_msg = weights_transmitting_pb2.ModelWeights()
    model_weights_msg.client_id = client_id
    total_bytes = 0
    for weight in weights:
        tensor = weights_transmitting_pb2.WeightTensor()
        flat = weight.flatten().tolist()
        tensor.data.extend(flat)
        tensor.shape.extend(weight.shape)
        model_weights_msg.tensors.append(tensor)
        total_bytes += len(flat) * 4  # float32 = 4 bytes
    FL_WEIGHT_PAYLOAD_BYTES.set(total_bytes)
    logger.info(f"Weight payload: ~{total_bytes / 1024:.1f} KB ({len(weights)} tensors)")
    return model_weights_msg

# ========== Load Data ==========
root = os.environ['CLIENT_DATA_ROOT']
client_id = os.environ['POD_NAME'].split('-')[-1]
logger.info(f"Client {client_id}: loading dataset...")
ds = make_dataset(f"{root}/clients/client_{client_id}")

# ========== Train Locally ==========
NUM_EPOCHS = 3

model = create_model()
optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
loss_fn = tf.keras.losses.BinaryCrossentropy()

logger.info(f"Client {client_id}: starting local training for {NUM_EPOCHS} epochs")
training_start = time.time()

for epoch in range(NUM_EPOCHS):
    FL_TRAINING_EPOCH.set(epoch)
    epoch_start = time.time()
    step = 0
    epoch_loss = 0.0

    for x, y in ds:
        with tf.GradientTape() as tape:
            logits = model(x, training=True)
            loss = loss_fn(y, logits)
        grads = tape.gradient(loss, model.trainable_variables)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))

        loss_val = float(loss.numpy())
        epoch_loss += loss_val
        step += 1

        FL_TRAINING_LOSS.set(loss_val)
        FL_TRAINING_STEP.set(step)
        FL_TRAINING_STEPS_TOTAL.inc()

    epoch_duration = time.time() - epoch_start
    FL_EPOCH_DURATION.observe(epoch_duration)
    FL_DATASET_BATCHES.set(step)

    avg_loss = epoch_loss / max(step, 1)
    logger.info(
        f"Client {client_id}: epoch {epoch}/{NUM_EPOCHS} — "
        f"avg_loss={avg_loss:.4f}, steps={step}, duration={epoch_duration:.1f}s"
    )

training_duration = time.time() - training_start
FL_TRAINING_DURATION.observe(training_duration)
logger.info(f"Client {client_id}: training complete in {training_duration:.1f}s")

# ========== Send Weights to Aggregator ==========
weights = model.get_weights()
client_id = get_client_id()
model_weights_msg = convert_weights_to_proto(weights, client_id)

channel = grpc.insecure_channel('server:50051')
stub = weights_transmitting_pb2_grpc.SendWeights(channel)

logger.info(f"Client {client_id}: uploading weights to aggregator...")
upload_start = time.time()

try:
    stub.TransmitWeights(model_weights_msg)
    upload_duration = time.time() - upload_start
    FL_UPLOAD_DURATION.observe(upload_duration)
    FL_UPLOAD_STATUS.labels(status='ok').inc()
    logger.info(f"Client {client_id}: weights uploaded successfully in {upload_duration:.2f}s")
except grpc.RpcError as e:
    upload_duration = time.time() - upload_start
    FL_UPLOAD_DURATION.observe(upload_duration)
    FL_UPLOAD_STATUS.labels(status='error').inc()
    logger.error(f"Client {client_id}: weight upload failed after {upload_duration:.2f}s — {e}")
    raise
