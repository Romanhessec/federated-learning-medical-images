#!/usr/bin/env python3
import os
import io
import grpc
import pandas as pd
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.optimizers import SGD
from tensorflow.keras.losses import BinaryCrossentropy
from tensorflow.keras.metrics import BinaryAccuracy

def load_local_data(client_csv_dir, batch_size=32):
    """
    Loads all CSVs in a directory, builds a tf.data.Dataset of (images, labels).
    """
    # read & concat all CSV shards
    csv_files = [
        os.path.join(client_csv_dir, f)
        for f in os.listdir(client_csv_dir)
        if f.endswith('.csv')
    ]
    df = pd.concat((pd.read_csv(f) for f in csv_files), ignore_index=True)
    
    # paths and one-hot labels - might need a lot of changes
    image_paths = df['Augmented_Path'].values
    labels      = df[['Cardiomegaly','Lung Opacity','Edema','Consolidation','Pneumonia']].astype('float32').values

    ds = tf.data.Dataset.from_tensor_slices((image_paths, labels))
    ds = ds.shuffle(buffer_size=len(df))
    ds = ds.map(lambda p, y: (
        tf.image.resize(tf.image.decode_jpeg(tf.io.read_file(p), channels=3), [224,224]),
        y
    ), num_parallel_calls=tf.data.AUTOTUNE)
    return ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)

def load_evaluation_data(eval_csv, batch_size=32):
    """
    Load and preprocess global evaluation set.
    Might or might not be used.
    """
    df = pd.read_csv(eval_csv)
    # TBD if these paths are correct
    df['Path'] = df['Path'].str.replace('CheXpert-v1.0/valid',
                                        'chexlocalize/CheXpert/val',
                                        regex=False)
    image_paths = df['Path'].values
    labels      = df[['Cardiomegaly','Pneumonia','Lung Opacity','Edema','Consolidation']].values.astype('float32')

    ds = tf.data.Dataset.from_tensor_slices((image_paths, labels))
    ds = ds.shuffle(buffer_size=len(df))
    ds = ds.map(lambda p, y: (
        tf.image.resize(tf.image.decode_jpeg(tf.io.read_file(p), channels=3), [224,224]),
        y
    ), num_parallel_calls=tf.data.AUTOTUNE)
    return ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)

def create_model():
    """
    Instantiate a MobileNetV2-based Keras model.
    """
    base = MobileNetV2(weights='imagenet',
                      include_top=False,
                      input_shape=(224,224,3))
    return tf.keras.Sequential([
        base,
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dense(5, activation='sigmoid')
    ])

def send_weights_to_aggregator():
    pass

def main():
    # might want to set these in the deployment spec:
    client_dir = os.environ['CLIENT_DATA_DIR']
    eval_csv   = os.environ.get('EVAL_DATA_CSV') # optional
    client_id  = os.environ.get('CLIENT_ID', 'unit1')
    epochs     = int(os.environ.get('EPOCHS', '3'))

    # load datasets
    train_ds = load_local_data(client_dir)
    if eval_csv:
        eval_ds = load_evaluation_data(eval_csv)
    
    # build & compile model
    model = create_model()
    model.compile(
        optimizer=SGD(learning_rate=0.02, momentum=0.9),
        loss=BinaryCrossentropy(from_logits=False),
        metrics=[BinaryAccuracy()]
    )

    # train locally
    model.fit(train_ds, epochs=epochs)

    # optional: evaluate on local eval data
    if eval_csv:
        loss, acc = model.evaluate(eval_ds)
        print(f"[Eval] Loss: {loss:.4f}, Acc: {acc:.4f}")

    # serialize weights to HDF5 in-memory buffer
    buf = io.BytesIO()
    model.save_weights(buf)
    weights_bytes = buf.getvalue()

    # send update over gRPC
    send_weights_to_aggregator()

if __name__ == "__main__":
    main()
