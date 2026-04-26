import os
import tensorflow as tf
import grpc
import numpy as np
import logging
import weights_transmitting_pb2
import weights_transmitting_pb2_grpc

from data_loader import make_dataset
from pod_recognisition import get_client_id

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    for weight in weights:
        tensor = weights_transmitting_pb2.WeightTensor()
        tensor.data.extend(weight.flatten().tolist())
        tensor.shape.extend(weight.shape)
        model_weights_msg.tensors.append(tensor)
    return model_weights_msg

def proto_to_weights(msg):
    """Convert protobuf ModelWeights back to numpy arrays."""
    weights = []
    for tensor in msg.tensors:
        array = np.array(tensor.data, dtype=np.float32).reshape(tensor.shape)
        weights.append(array)
    return weights

# Configuration
# Updated for real-scale test: 12 rounds x 4 epochs = 48 total epochs per client
NUM_ROUNDS = 12
EPOCHS_PER_ROUND = 4
LOCAL_BATCH_SIZE = int(os.environ.get('LOCAL_BATCH_SIZE', '8'))
SHUFFLE_BUFFER = int(os.environ.get('SHUFFLE_BUFFER', '32'))
AGGREGATOR_ADDRESS = 'aggregator-service:50051'

# Setup
root = os.environ['CLIENT_DATA_ROOT']
pod_name = os.environ['POD_NAME']
client_id = pod_name.split('-')[-1]
ds = make_dataset(
    f"{root}/clients/client_{client_id}",
    batch_size=LOCAL_BATCH_SIZE,
    shuffle_buffer=SHUFFLE_BUFFER,
)

logger.info(f"Client {client_id} starting federated training for {NUM_ROUNDS} rounds")
logger.info(f"Training config: batch_size={LOCAL_BATCH_SIZE}, shuffle_buffer={SHUFFLE_BUFFER}")

# Initialize model
model = create_model()
optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
loss_fn = tf.keras.losses.BinaryCrossentropy()

# Connect to aggregator
channel = grpc.insecure_channel(AGGREGATOR_ADDRESS)
stub = weights_transmitting_pb2_grpc.SendWeightsStub(channel)

# Federated learning rounds
for round_num in range(NUM_ROUNDS):
    logger.info(f"=== Round {round_num + 1}/{NUM_ROUNDS} ===")
    
    # 1. Pull global weights if not first round
    if round_num > 0:
        try:
            logger.info("Pulling global weights from aggregator...")
            global_weights_msg = stub.GetGlobalWeights(
                weights_transmitting_pb2.GetWeightsRequest(round_number=round_num)
            )
            if global_weights_msg.tensors:
                global_weights = proto_to_weights(global_weights_msg)
                model.set_weights(global_weights)
                logger.info(f"✓ Loaded global weights from round {round_num - 1}")
            else:
                logger.warning("Received empty global weights")
        except Exception as e:
            logger.error(f"Failed to get global weights: {e}")
    
    # 2. Train locally for EPOCHS_PER_ROUND
    for epoch in range(EPOCHS_PER_ROUND):
        total_loss = 0.0
        num_batches = 0
        for x, y in ds:
            with tf.GradientTape() as tape:
                logits = model(x, training=True)
                loss = loss_fn(y, logits)
            grads = tape.gradient(loss, model.trainable_variables)
            optimizer.apply_gradients(zip(grads, model.trainable_variables))
            total_loss += loss.numpy()
            num_batches += 1
        avg_loss = total_loss / max(1, num_batches)
        logger.info(f"Round {round_num + 1}, Epoch {epoch + 1}/{EPOCHS_PER_ROUND}: Loss = {avg_loss:.6f}")
    
    # 3. Send updated weights to aggregator
    try:
        weights = model.get_weights()
        model_weights_msg = convert_weights_to_proto(weights, client_id)
        stub.TransmitWeights(model_weights_msg)
        logger.info(f"✓ Sent weights to aggregator at end of round {round_num + 1}")
    except Exception as e:
        logger.error(f"Failed to send weights: {e}")

logger.info("Federated training complete")

