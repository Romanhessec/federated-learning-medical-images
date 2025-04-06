import pandas as pd
import sys
import os
import cv2
import shutil
import numpy as np

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, udf, concat, lit, split, explode
import matplotlib.pyplot as plt

# add project root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.preprocessing_testing_utils import (
    test_normalization,
    test_augmentation,
    test_partitioning,
    verify_unique_split
)

def normalize_images_spark(spark_df, output_folder):
    """
    Normalize images using Spark DataFrame.
    Args:
        spark_df: Spark DataFrame containing image paths.
        output_folder: Folder to save normalized images.
    Returns:
        Normalized images DataFrame
    """
    os.makedirs(output_folder, exist_ok=True)

    def normalize_image_simple(path):
        try:
            if not os.path.exists(path):
                print(f"File does not exist: {path}")
                return None
            
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"Failed to read image: {path}")
                return None
            
            img = cv2.equalizeHist(img)
            
            # extract relevant path for image naming
            # e.g. 'test/patient65177/study1/view1_frontal.jpg' becomes 'patient65177/study1/view1_frontal.jpg'
            new_filename = path.replace("/", "_")
            new_path = os.path.join(output_folder, new_filename)
            
            cv2.imwrite(new_path, img)
            return new_path
        except Exception as e:
            print(f"Error processing {path}: {e}")
            return None

    normalize_udf = udf(lambda path: normalize_image_simple(path))
    
    normalized_df = spark_df.withColumn("Normalized_path", normalize_udf(col("Path")))
    # force materialization
    normalized_df.select("Normalized_path").collect()

    return normalized_df

def augment_image(image):
    """
    Augment image with rotation, scaling, translation, noise, contrast adjustment, etc.
    Args:
        image: Input image as a NumPy array.
    Returns:
        List of augmented images.
    """

    augmented_images = []

    # random rotation
    for _ in range(3):
        angle = np.random.uniform(-5, 5)
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h))
        augmented_images.append(rotated)

    # scaling and translation
    for _ in range(3):
        scale = np.random.uniform(0.9, 1.1)
        tx = np.random.randint(-3, 3)
        ty = np.random.randint(-3, 3)
        M = np.array([[scale, 0, tx], [0, scale, ty]], dtype=np.float32)
        transformed = cv2.warpAffine(image, M, (w, h))
        augmented_images.append(transformed)

    # gaussian noise
    for _ in range (3):
        noise = np.random.normal(0, 1, image.shape).astype(np.uint8)
        noisy_image = cv2.add(image, noise)
        augmented_images.append(noisy_image)

    return augmented_images

def augment_images_spark(spark_df, output_folder):
    """
    Apply augmentation to images using Spark DataFrame.
    Args:
        spark_df: Spark DataFrame containing image paths.
        output_folder: Folder to save augmented images.
    """
    os.makedirs(output_folder, exist_ok=True)

    def augment_and_save(path):
        try:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"Failed to read image: {path}")
                return None
            augmented_images = augment_image(img)
            saved_paths = []
            for idx, augmented_img in enumerate(augmented_images):
                new_path = os.path.join(output_folder, f"{path.replace('/', '_')}_{idx}.jpg")
                cv2.imwrite(new_path, augmented_img)
                saved_paths.append(new_path)
            return ",".join(saved_paths)
        except Exception as e:
            print(f"Error processing {path}: {e}")
            return None

    # register UDF
    augment_udf = udf(lambda path: augment_and_save(path))

    augmented_df = spark_df.withColumn("Augmented_Paths", augment_udf(col("Path")))
    augmented_df.select("Augmented_Paths").collect()

    return augmented_df

def prepare_augmented_df_for_partitioning(augmented_df):
    """
    Prepare the augmented DataFrame for partitioning by exploding the 'Augmented_Paths' column.
    Args:
        augmented_df: Spark DataFrame containing the Augmented_Paths column.
    Returns:
        Reformatted Spark DataFrame suitable for partitioning.
    """
    # split the Augmented_Paths column into an array
    augmented_df = augmented_df.withColumn("Augmented_Paths_Array", split(col("Augmented_Paths"), ","))

    # explode the array to create individual rows for each augmented image
    exploded_df = augmented_df.withColumn("Augmented_Path", explode(col("Augmented_Paths_Array")))

    # drop the array column as it's no longer needed
    exploded_df = exploded_df.drop("Augmented_Paths", "Augmented_Paths_Array")
    
    exploded_df.select("Augmented_Path").collect()

    return exploded_df

# this is how it is supposed to be done - for now, we will use the random splitting one
def partition_data_spark(final_df, client_distribution, output_dir):
    """
    Partition data into non-IID subsets using Spark.
    Args:
        final_df: Final Spark DataFrame (augmented and prepared).
        client_distribution: Dictionary specifying label distribution for each client.
        output_dir: Base directory to save partitioned data for each client.
    Returns:
        Dictionary with client IDs and corresponding Spark DataFrames.
    """
    os.makedirs(output_dir, exist_ok=True)

    client_dfs = {}

    # WARNING - this is hardcoded now for "Pneumonia" - should fix later
    for client_id, distribution in client_distribution.items():
        unique_labels = [row[0] for row in final_df.select("Pneumonia").distinct().collect()]
        sample_fractions = {label: distribution.get(label, 0) for label in unique_labels}
        client_df = final_df.sampleBy("Pneumonia", fractions=sample_fractions, seed=42)

        # save client-specific data
        client_output_path = os.path.join(output_dir, f"{client_id}_data.csv")
        client_df.write.csv(client_output_path, header=True)
        client_dfs[client_id] = client_df

    return client_dfs

def partition_data_even_split(final_df, num_clients, output_dir):
    """
    Partition data into evenly split subsets for clients without overlap.
    Args:
        final_df: Final Spark DataFrame (augmented and prepared).
        num_clients: Number of clients.
        output_dir: Base directory to save partitioned data for each client.
    Returns:
        List of Spark DataFrames, one for each client.
    """
    os.makedirs(output_dir, exist_ok=True)

    # randomly split data into unique subsets for each client
    proportions = [1.0 / num_clients] * num_clients
    client_dfs = final_df.randomSplit(proportions, seed=42)

    # save each client's data
    for idx, client_df in enumerate(client_dfs):
        client_output_path = os.path.join(output_dir, f"Client_{idx + 1}_data.csv")
        client_df.write.csv(client_output_path, header=True, mode='overwrite')
        print(f"Client {idx + 1} data saved to {client_output_path}")

    return client_dfs

def partition_data_with_skew(final_df, client_distribution, output_dir):
    """
    Partition data into subsets for clients with custom label distribution.
    Args:
        final_df: Final Spark DataFrame (augmented and prepared).
        client_distribution: Dictionary specifying label distribution for each client.
        output_dir: Base directory to save partitioned data for each client.
    Returns:
        Dictionary with client IDs and corresponding Spark DataFrames.
    """
    if not client_distribution:
        raise ValueError("client_distribution must be a non-empty dictionary.")

    os.makedirs(output_dir, exist_ok=True)
    client_dfs = {}

    for client_id, distribution in client_distribution.items():
        unique_labels = [row["Pneumonia"] for row in final_df.select("Pneumonia").distinct().collect()]
        fractions = {label: distribution.get(label, 0) for label in unique_labels}

        client_df = final_df.sampleBy("Pneumonia", fractions, seed=42)

        # save the sampled data
        client_output_path = os.path.join(output_dir, f"{client_id}_data.csv")
        client_df.write.csv(client_output_path, header=True, mode='overwrite')

        sampled_count = client_df.count()
        print(f"{client_id} data saved to {client_output_path} with {sampled_count} rows.")

        client_dfs[client_id] = client_df

    return client_dfs


# initialize spark session
spark = SparkSession.builder \
    .appName("NormalizeImages") \
    .master("local[*]") \
    .getOrCreate()

# spark.sparkContext.setLogLevel("DEBUG") # delete later

# clean output folder
if os.path.exists("output"):
    shutil.rmtree("output")

# load datasets labels
# WARNING: we do use test_labels.csv as val labels since test labels are 
# more numerous
val_df = pd.read_csv("chexlocalize/CheXpert/test_labels.csv")
test_df = pd.read_csv("chexlocalize/CheXpert/val_labels.csv")

# convert validation DataFrame to Spark DataFrame
# the labels csv have relative paths - this is why we need base_dir
base_dir = "chexlocalize/CheXpert/"
spark_val_df_relative = spark.createDataFrame(val_df)
spark_val_df = spark_val_df_relative.withColumn(
    "Path",
    concat(lit(base_dir), col("Path"))
)

spark_val_df.show()

# set the number of partitions for Spark
spark_val_df = spark_val_df.repartition(16, col("Path"))

print(f"Number of partitions after repartitioning: {spark_val_df.rdd.getNumPartitions()}")
partition_sizes = spark_val_df.rdd.glom().map(len).collect()
print(f"Rows in each partition: {partition_sizes}")

# check for duplicates in partitions
duplicates = spark_val_df.groupBy("Path").count().filter("count > 1").count()
print(f"Number of duplicate rows: {duplicates}")
if duplicates > 0:
    spark_val_df = spark_val_df.dropDuplicates(["Path"])

# normalize data
normalized_output_dir = "output/normalized_val"
os.makedirs(normalized_output_dir, exist_ok=True)

normalized_val_df = normalize_images_spark(spark_val_df, normalized_output_dir)
normalized_val_df.show()

# check number of processed rows
print(f"Total processed rows: {normalized_val_df.count()}")

# verify output directory
output_files = os.listdir(normalized_output_dir)
print(f"Number of files in output directory: {len(output_files)}")

# cross-check with Spark processed rows
processed_rows = normalized_val_df.count()
if len(output_files) != processed_rows:
    print("Mismatch: Processed rows do not match saved files.")
    print(f"Processed rows: {processed_rows}, Files in output: {len(output_files)}")

# augment data
augmented_normalized_output_dir = "output/augmented_images"
os.makedirs(augmented_normalized_output_dir, exist_ok=True)

augmented_val_df = augment_images_spark(normalized_val_df, augmented_normalized_output_dir)
augmented_val_df.show()

# verify output 
augmented_files = os.listdir(augmented_normalized_output_dir)
print(f"Number of augmented files in output directory: {len(augmented_files)}")

final_val_df = prepare_augmented_df_for_partitioning(augmented_val_df)
final_val_df.show()

# will use this later
client_distribution = {
    'Client_1': {1: 0.7, 0: 0.3},  # 70% Pneumonia cases, 30% Non-Pneumonia cases
    'Client_2': {1: 0.4, 0: 0.6},  # 40% Pneumonia, 60% Non-Pneumonia
    'Client_3': {1: 0.5, 0: 0.5},  # Balanced data
    'Client_4': {1: 0.2, 0: 0.8},  # More Non-Pneumonia cases
}

partitioned_output_dir = "output/clients"
num_clients = 4
client_dfs = partition_data_even_split(final_val_df, num_clients, partitioned_output_dir)
# clients_dfs = partition_data_with_skew(final_val_df, client_distribution, partitioned_output_dir)
verify_unique_split(client_dfs)