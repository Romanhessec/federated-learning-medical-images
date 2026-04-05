#!/usr/bin/env python3
"""
Evaluation script for federated learning model on CheXpert validation set.
Loads global model weights and evaluates binary classification for Pleural Effusion.
"""

import os
import sys
import numpy as np
import pandas as pd
import tensorflow as tf
from pathlib import Path
import pickle
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_model():
    """Create the same model architecture as train_local.py"""
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=(128, 128, 1)),
        tf.keras.layers.Conv2D(32, 3, activation="relu"),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(1, activation="sigmoid")
    ])

def load_image(img_path, size=(128, 128)):
    """Load and preprocess a CheXpert image"""
    try:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=1)
        img = tf.image.resize(img, size)
        img = img / 255.0  # Normalize
        return img.numpy()
    except Exception as e:
        logger.warning(f"Failed to load {img_path}: {e}")
        return None

def make_validation_dataset(csv_path, img_root, batch_size=32):
    """
    Load validation dataset from CheXpert CSV.
    Returns (images, labels) for Pleural Effusion classification.
    """
    df = pd.read_csv(csv_path)
    
    # Filter for Pleural Effusion label (column index 14)
    pleural_effusion_idx = 14  # "Pleural Effusion" column
    
    images = []
    labels = []
    skipped = 0
    
    for idx, row in df.iterrows():
        img_path = os.path.join(img_root, row['Path'])
        label = row.iloc[pleural_effusion_idx]
        
        # Skip if label is -1.0 (uncertain) or NaN
        if pd.isna(label) or label == -1.0:
            skipped += 1
            continue
        
        img = load_image(img_path)
        if img is not None:
            images.append(img)
            labels.append(int(label))
    
    logger.info(f"Loaded {len(images)} validation images (skipped {skipped} with uncertain labels)")
    
    if len(images) == 0:
        logger.error("No valid images loaded!")
        return None, None
    
    images = np.array(images)
    labels = np.array(labels, dtype=np.float32)
    
    # Create TF dataset
    ds = tf.data.Dataset.from_tensor_slices((images, labels))
    ds = ds.batch(batch_size)
    
    return ds, labels

def load_global_weights(weights_file):
    """Load global weights from pickle file"""
    try:
        with open(weights_file, 'rb') as f:
            weights = pickle.load(f)
        logger.info(f"Loaded global weights from {weights_file}")
        return weights
    except FileNotFoundError:
        logger.error(f"Weights file not found: {weights_file}")
        return None

def evaluate_model(model, validation_ds, true_labels):
    """Evaluate model on validation set"""
    predictions = model.predict(validation_ds)
    predictions = predictions.flatten()
    
    # Binary classification metrics
    pred_binary = (predictions >= 0.5).astype(int)
    accuracy = np.mean(pred_binary == true_labels)
    
    # AUC
    from sklearn.metrics import roc_auc_score, confusion_matrix, precision_recall_fscore_support
    auc = roc_auc_score(true_labels, predictions)
    
    # Confusion matrix
    tn, fp, fn, tp = confusion_matrix(true_labels, pred_binary).ravel()
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
    
    # Random baseline
    random_pred = np.random.randint(0, 2, size=len(true_labels))
    random_accuracy = np.mean(random_pred == true_labels)
    
    return {
        'accuracy': accuracy,
        'auc': auc,
        'sensitivity': sensitivity,
        'specificity': specificity,
        'random_baseline': random_accuracy,
        'tp': tp,
        'tn': tn,
        'fp': fp,
        'fn': fn
    }

def main():
    # Paths
    chexpert_root = '/data/federated-learning-medical-images'  # Parent directory
    valid_csv = os.path.join(chexpert_root, 'CheXpert-v1.0/valid.csv')
    weights_file = os.path.join(chexpert_root, 'CheXpert-v1.0/global_model_weights.pkl')
    
    # Check if weights file exists
    if not os.path.exists(weights_file):
        logger.warning(f"Weights file not found: {weights_file}")
        logger.info("Make sure aggregator has saved final weights to this location.")
        sys.exit(1)
    
    # Load validation data
    logger.info("Loading validation dataset...")
    validation_ds, true_labels = make_validation_dataset(valid_csv, chexpert_root)
    if validation_ds is None:
        logger.error("Failed to load validation data")
        sys.exit(1)
    
    # Create and load model
    logger.info("Creating model...")
    model = create_model()
    
    weights = load_global_weights(weights_file)
    if weights is None:
        sys.exit(1)
    
    model.set_weights(weights)
    logger.info("✓ Model weights loaded")
    
    # Evaluate
    logger.info("Evaluating model...")
    metrics = evaluate_model(model, validation_ds, true_labels)
    
    # Print results
    logger.info("\n" + "="*60)
    logger.info("FEDERATED LEARNING MODEL EVALUATION RESULTS")
    logger.info("="*60)
    logger.info(f"Accuracy:           {metrics['accuracy']:.4f}")
    logger.info(f"AUC (ROC):          {metrics['auc']:.4f}")
    logger.info(f"Sensitivity (TPR):  {metrics['sensitivity']:.4f}")
    logger.info(f"Specificity (TNR):  {metrics['specificity']:.4f}")
    logger.info(f"Random Baseline:    {metrics['random_baseline']:.4f}")
    logger.info("="*60)
    logger.info(f"Confusion Matrix:")
    logger.info(f"  True Positives:  {metrics['tp']}")
    logger.info(f"  True Negatives:  {metrics['tn']}")
    logger.info(f"  False Positives: {metrics['fp']}")
    logger.info(f"  False Negatives: {metrics['fn']}")
    logger.info("="*60)
    
    # Check if federated model beats random
    if metrics['accuracy'] > metrics['random_baseline']:
        logger.info(f"✓ Federated model beats random baseline by {(metrics['accuracy'] - metrics['random_baseline']):.4f}")
    else:
        logger.warning(f"⚠ Federated model underperforms random baseline")

if __name__ == '__main__':
    main()
