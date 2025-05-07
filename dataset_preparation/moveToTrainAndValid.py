import os
import shutil

# Define source and target directories
sources = {
    "../chexpertchestxrays-u20210408/CheXpert-v1.0 batch 1 (validate & csv)/valid": "CheXpert-v1.0/valid",
    "../chexpertchestxrays-u20210408/CheXpert-v1.0 batch 2 (train 1)": "CheXpert-v1.0/train",
    "../chexpertchestxrays-u20210408/CheXpert-v1.0 batch 3 (train 2)": "CheXpert-v1.0/train",
    "../chexpertchestxrays-u20210408/CheXpert-v1.0 batch 4 (train 3)": "CheXpert-v1.0/train",
}

# Create target folders if they don't exist
for dest in set(sources.values()):
    os.makedirs(dest, exist_ok=True)

# Move patient folders
for src_dir, dest_dir in sources.items():
    for patient_folder in os.listdir(src_dir):
        src_path = os.path.join(src_dir, patient_folder)
        dest_path = os.path.join(dest_dir, patient_folder)

        # Only move folders that start with "patient"
        if os.path.isdir(src_path) and patient_folder.startswith("patient"):
            print(f"Moving {src_path} → {dest_path}")
            shutil.move(src_path, dest_path)
