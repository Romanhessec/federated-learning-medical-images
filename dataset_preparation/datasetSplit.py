import os
import json
import shutil
import random
import logging
from tqdm import tqdm
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split
from pprint import pprint
import subprocess

# Set a fixed random seed for determinism
random.seed(42)

# Run rebuildOriginalDataset.py at the start
subprocess.run(['python', 'dataset_preparation/rebuildOriginalDataset.py'], check=True)

# ========== Setup Logging ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ========== Config ==========
BASE_DIR = "CheXpert-v1.0"
TRAIN_DIR = os.path.join(BASE_DIR, "train")
CSV_PATH = os.path.join(BASE_DIR, "train.csv")
CLIENT_ROOT = os.path.join(BASE_DIR, "clients")
CONFIG_PATH = "dataset_preparation/label_config.json"

# Fraction of patients to process (e.g., 0.001 for 0.1%, do 1 for the whole dataset)
PATIENTS_FRACTION = 0.003

# ========== Init Spark ==========
logging.info("Starting Spark session...")
spark = SparkSession.builder.appName("CheXpertSplit").getOrCreate()
df = spark.read.option("header", True).csv(CSV_PATH)

# ========== Load Config ==========
logging.info(f"Loading config from {CONFIG_PATH}...")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)
label_col = config["label"]
distribution = config["distribution"]
clients = list(distribution.keys())
logging.info(f"Label of interest: '{label_col}'")

# Pretty print the client distribution
logging.info("Client distribution:")
pprint(distribution)

# ========== Extract Patient ID ==========
df = df.withColumn("PatientID", split(col("Path"), "/")[2])
df = df.withColumn(label_col, col(label_col).cast("int"))

# ========== Filter images by label ==========
labeled_images_df = df.filter(col(label_col) == 1).select("PatientID").distinct()
unlabeled_images_df = df.filter((col(label_col).isNull()) | (col(label_col) != 1)).select("PatientID").distinct()

# Ensure labeled_images_df and unlabeled_images_df are distinct
unlabeled_images_df = unlabeled_images_df.subtract(labeled_images_df)
labeled_images_df = labeled_images_df.subtract(unlabeled_images_df)

labeled_images = [row["PatientID"] for row in labeled_images_df.collect()]
unlabeled_images = [row["PatientID"] for row in unlabeled_images_df.collect()]

# Limit the number of images based on the fraction
labeled_images = labeled_images[:int(len(labeled_images) * PATIENTS_FRACTION)]
unlabeled_images = unlabeled_images[:int(len(unlabeled_images) * PATIENTS_FRACTION)]

logging.info(f"Found {len(labeled_images)} labeled images and {len(unlabeled_images)} unlabeled images.")

# Shuffle
random.shuffle(labeled_images)
random.shuffle(unlabeled_images)

# ========== Assign Patients to Clients ==========
client_images = {}
total_labeled = len(labeled_images)
total_unlabeled = len(unlabeled_images)

# Equal total patients per client
total_patients_per_client = (total_labeled + total_unlabeled) // len(clients)
logging.info(f"Each client will receive approximately {total_patients_per_client} total patients.")

# Calculate labeled and unlabeled images per client
labeled_per_client = {client: int(distribution[client] * total_labeled) for client in clients}
unlabeled_per_client = {client: max(0, total_patients_per_client - labeled_per_client[client]) for client in clients}

# Unified loop to assign labeled and unlabeled images
start_labeled = 0
start_unlabeled = 0
for client in clients:
    labeled_count = labeled_per_client[client]
    unlabeled_count = unlabeled_per_client[client]

    # Assign labeled images
    client_images[client] = labeled_images[start_labeled:start_labeled + labeled_count]
    start_labeled += labeled_count

    # Assign unlabeled images
    client_images[client].extend(unlabeled_images[start_unlabeled:start_unlabeled + unlabeled_count])
    start_unlabeled += unlabeled_count

    logging.info(f"{client}: assigned {labeled_count} labeled images and {unlabeled_count} unlabeled images.")

# Handle any remaining images (labeled or unlabeled)
remaining_images = labeled_images[start_labeled:] + unlabeled_images[start_unlabeled:]
random.shuffle(remaining_images)

# Distribute any remaining images (labeled or unlabeled) evenly
for i, image in enumerate(remaining_images):
    client = clients[i % len(clients)]
    client_images[client].append(image)

logging.info("Image distribution complete.")

# ========== Write to Output Folders (Move Folders) ==========
df_pd = df.toPandas()
df_pd['PatientID'] = df_pd['Path'].apply(lambda x: x.split('/')[2])

for client in tqdm(clients, desc="Distributing clients"):
    output_dir = os.path.join(CLIENT_ROOT, client)
    train_out_dir = os.path.join(output_dir, "train")
    os.makedirs(train_out_dir, exist_ok=True)

    patients = set(client_images[client])
    client_df = df_pd[df_pd["PatientID"].isin(patients)]

    # Save train.csv
    csv_path = os.path.join(output_dir, "train.csv")
    client_df.drop(columns=["PatientID"]).to_csv(csv_path, index=False)
    logging.info(f"{client}: train.csv saved with {len(client_df)} rows")

    # Move patient folders
    for pid in patients:
        src = os.path.join(TRAIN_DIR, pid)
        dst = os.path.join(train_out_dir, pid)
        if os.path.exists(src):
            shutil.move(src, dst)
        else:
            logging.warning(f"Patient folder {pid} not found in train dir.")

logging.info("✅ Done distributing data to clients.")
