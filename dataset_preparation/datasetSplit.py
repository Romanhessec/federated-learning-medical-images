import os
import json
import shutil
import random
import logging
from tqdm import tqdm
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split

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

# Fraction of patients to process (e.g., 0.001 for 0.1%)
PATIENT_FRACTION = 0.003

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
logging.info(f"Client distribution: {distribution}")

# ========== Extract Patient ID ==========
df = df.withColumn("PatientID", split(col("Path"), "/")[2])
df = df.withColumn(label_col, col(label_col).cast("int"))

# ========== Filter patients by label ==========
labeled_patients_df = df.filter(col(label_col) == 1).select("PatientID").distinct()
unlabeled_patients_df = df.filter((col(label_col).isNull()) | (col(label_col) != 1)).select("PatientID").distinct()

labeled_patients = [row["PatientID"] for row in labeled_patients_df.collect()]
unlabeled_patients = [row["PatientID"] for row in unlabeled_patients_df.collect()]

# Limit the number of patients based on the fraction
labeled_patients = labeled_patients[:int(len(labeled_patients) * PATIENT_FRACTION)]
unlabeled_patients = unlabeled_patients[:int(len(unlabeled_patients) * PATIENT_FRACTION)]

logging.info(f"Found {len(labeled_patients)} labeled patients and {len(unlabeled_patients)} unlabeled patients.")

# Shuffle
random.shuffle(labeled_patients)
random.shuffle(unlabeled_patients)

# ========== Assign Patients to Clients ==========
client_patients = {}
total_labeled = len(labeled_patients)
total_unlabeled = len(unlabeled_patients)

# Equal total patients per client
total_patients_per_client = (total_labeled + total_unlabeled) // len(clients)
logging.info(f"Each client will receive approximately {total_patients_per_client} total patients.")

# Calculate labeled and unlabeled patients per client
labeled_per_client = {client: int(distribution[client] * total_labeled) for client in clients}
unlabeled_per_client = {client: total_patients_per_client - labeled_per_client[client] for client in clients}

# Assign labeled patients
start = 0
for client in clients:
    count = labeled_per_client[client]
    client_patients[client] = labeled_patients[start:start + count]
    start += count
    logging.info(f"{client}: assigned {count} labeled patients.")

# Handle any remaining labeled patients
remaining_labeled = labeled_patients[start:]

# Assign unlabeled patients
start = 0
for client in clients:
    count = unlabeled_per_client[client]
    client_patients[client].extend(unlabeled_patients[start:start + count])
    start += count
    logging.info(f"{client}: assigned {count} unlabeled patients.")

# Distribute any remaining patients (labeled or unlabeled) evenly
remaining_patients = remaining_labeled + unlabeled_patients[start:]
random.shuffle(remaining_patients)

for i, patient in enumerate(remaining_patients):
    client = clients[i % len(clients)]
    client_patients[client].append(patient)

logging.info("Patient distribution complete.")

# ========== Write to Output Folders (Move Folders) ==========
df_pd = df.toPandas()
df_pd['PatientID'] = df_pd['Path'].apply(lambda x: x.split('/')[2])

for client in tqdm(clients, desc="Distributing clients"):
    output_dir = os.path.join(CLIENT_ROOT, client)
    train_out_dir = os.path.join(output_dir, "train")
    os.makedirs(train_out_dir, exist_ok=True)

    patients = set(client_patients[client])
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
