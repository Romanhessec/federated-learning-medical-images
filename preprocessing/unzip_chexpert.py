import os
import zipfile
import shutil

ZIP_DIR = "/data/federated-learning-medical-images/chexpertchestxrays-u20210408"
OUTPUT_DIR = "/data/federated-learning-medical-images/CheXpert-v1.0"

# create output folders
train_dir = os.path.join(OUTPUT_DIR, "train")
valid_dir = os.path.join(OUTPUT_DIR, "valid")
os.makedirs(train_dir, exist_ok=True)
os.makedirs(valid_dir, exist_ok=True)

def unzip(zip_path):
    zip_name = os.path.basename(zip_path).lower()

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        print(f"Unzipping {zip_path}...")
        zip_ref.extractall(OUTPUT_DIR)

def sort():
    batch_folders = [
        "CheXpert-v1.0 batch 2 (train 1)",
        "CheXpert-v1.0 batch 3 (train 2)",
        "CheXpert-v1.0 batch 4 (train 3)",
    ]
    for batch in batch_folders:
        batch_path = os.path.join(OUTPUT_DIR, batch)
        if not os.path.exists(batch_path):
            print(f"Skipping: {batch_path} does not exist.")
            continue

        moved_count = 0
        for item in os.listdir(batch_path):
            src_path = os.path.join(batch_path, item)
            dst_path = os.path.join(train_dir, item)

            if os.path.isdir(src_path) and item.lower().startswith("patient"):
                if not os.path.exists(dst_path):
                    shutil.move(src_path, dst_path)
                    moved_count += 1

        print(f"Moved {moved_count} patient folders from '{batch}'")

    print("All batches moved to train.")

# run it on all 4 zip files
for zip_file in os.listdir(ZIP_DIR):
    if zip_file.endswith(".zip"):
        zip_path = os.path.join(ZIP_DIR, zip_file)
        unzip(zip_path)

sort()

print("All files are extracted and sorted.")
