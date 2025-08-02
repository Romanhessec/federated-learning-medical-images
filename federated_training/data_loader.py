import os
import tensorflow as tf
import pandas as pd

# adjust
IMAGE_SIZE = (128, 128)
AUTOTUNE = tf.data.AUTOTUNE
TARGET_LABEL = 'Pleural Effusion'

def load_and_preprocess_image(path):
    """
    Reads an image file from `path`, decodes it (JPEG), converts to grayscale,
    resizes to IMAGE_SIZE, and normalizes pixel values to [0,1].
    """
    image = tf.io.read_file(path)  # path is a Tensor
    image = tf.image.decode_jpeg(image, channels=1)
    # ensure the tensor has rank 3
    image.set_shape([None, None, 1])
    image = tf.image.resize(image, IMAGE_SIZE)
    image = tf.image.convert_image_dtype(image, tf.float32)
    return image

def make_dataset(client_path, batch_size=32, shuffle_buffer=100):
    """
    Builds a tf.data.Dataset from a client directory.

    Expects:
        client_path/
            train.csv         # CSV with columns: patient_id, image_filename, label
            train/            # directory containing patient subfolders
                patient_01/
                    img1.png
                    img2.png
                patient_02/
                    ...

    Returns:
        A tf.data.Dataset yielding (image, label) batches.
    """
    csv_path = os.path.join(client_path, 'train.csv')
    df = pd.read_csv(csv_path)

    # remove 'CheXpert-1v.0' prefix due to Kubernetes pods file structure
    df['AdjustedPath'] = df['Path'].str.replace(r'^CheXpert-v1\.0/', '', regex=True)
    image_paths = df['AdjustedPath'].apply(lambda p: os.path.join(client_path, p)).tolist()
    # label_cols = [
    #     'No Finding', 'Enlarged Cardiomediastinum', 'Cardiomegaly',
    #     'Lung Opacity', 'Lung Lesion', 'Edema', 'Consolidation',
    #     'Pneumonia', 'Atelectasis', 'Pneumothorax', 'Pleural Effusion',
    #     'Pleural Other', 'Fracture', 'Support Devices'
    # ]

    # filter out rows without labels
    # TBD how this will be done cleaner in the future
    df = df[df[TARGET_LABEL].notna()]
    df = df[df[TARGET_LABEL].isin([0.0, 1.0])] # DISCLAIMER: we don't know what to do with -1 (uncertain diagnostic) values yet
    labels = df[TARGET_LABEL].astype('float32').values
    # labels = df[label_cols].astype('float32').values.tolist()

    # create TF Dataset from tensors
    path_ds = tf.data.Dataset.from_tensor_slices(image_paths)
    label_ds = tf.data.Dataset.from_tensor_slices(labels)
    ds = tf.data.Dataset.zip((path_ds, label_ds))

    # load images and preprocess
    ds = ds.map(
        lambda path, label: (load_and_preprocess_image(path), label),
        num_parallel_calls=AUTOTUNE
    )

    # shuffle, batch, and prefetch
    ds = ds.shuffle(shuffle_buffer)
    ds = ds.batch(batch_size)
    ds = ds.prefetch(AUTOTUNE)

    return ds

if __name__ == '__main__':
    # usage example - should be called in train_medical_unit.py
    client_root = os.environ.get('CLIENT_DATA_ROOT', '/data/clients/client_0')
    dataset = make_dataset(client_root, batch_size=16)
    for images, labels in dataset.take(1):
        print('Batch of images shape:', images.shape)
        print('Batch of labels shape:', labels.shape)
