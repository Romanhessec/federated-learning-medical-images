import os
import shutil
import pandas as pd
import logging

# ========== Logging Setup ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ========== Config ==========
BASE_DIR = "CheXpert-v1.0"
TRAIN_DIR = os.path.join(BASE_DIR, "train")
CSV_PATH = os.path.join(BASE_DIR, "train.csv")
CLIENT_ROOT = os.path.join(BASE_DIR, "clients")

def move_patient_folders_back():
    """Moves patient folders from each client back to the main train directory."""
    os.makedirs(TRAIN_DIR, exist_ok=True)
    clients = os.listdir(CLIENT_ROOT)
    
    for client in clients:
        client_train_dir = os.path.join(CLIENT_ROOT, client, "train")
        if not os.path.isdir(client_train_dir):
            logging.warning(f"Client train dir not found for {client}, skipping...")
            continue

        for pid in os.listdir(client_train_dir):
            src = os.path.join(client_train_dir, pid)
            dst = os.path.join(TRAIN_DIR, pid)
            if os.path.exists(dst):
                logging.warning(f"Folder {pid} already exists in train. Skipping.")
                continue
            shutil.move(src, dst)
            logging.info(f"Moved {pid} for {client} back to train/")
        logging.info(f"Moved folders from {client} to train.")

if __name__ == "__main__":
    logging.info("🔁 Starting dataset reset...")
    move_patient_folders_back()
    logging.info("✅ Reset complete.")
