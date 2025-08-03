import os
import tensorflow as tf
import grpc
import numpy as np
import weights_transmitting_pb2, weights_transmitting_pb2_grpc

from data_loader import make_dataset
from pod_recognisition import get_client_id

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

root = os.environ['CLIENT_DATA_ROOT']
client_id = os.environ['POD_NAME'].split('-')[-1]
ds = make_dataset(f"{root}/clients/client_{client_id}")

# train locally
model = create_model()
optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
loss_fn = tf.keras.losses.BinaryCrossentropy()

# TBD
for epoch in range(3):
    for x, y in ds:
        with tf.GradientTape() as tape:
            logits = model(x, training=True)
            loss = loss_fn(y, logits)
        grads = tape.gradient(loss, model.trainable_variables)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))

# grab the updated weights (or the last‐step grads)
weights = model.get_weights()
client_id = get_client_id() 
model_weights_msg = convert_weights_to_proto(weights, client_id)

# connect to the server
channel = grpc.insecure_channel('server:50051')
stub = weights_transmitting_pb2_grpc.SendWeights(channel)

stub.TransmitWeights(model_weights_msg)
