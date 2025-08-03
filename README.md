# federated-learning-medical-images

Master's thesis project.

Lucas Lazaroiu, Gabriel-Marian Roman.

## 1. General Overview

The Kubernetes cluster will host **5 medical-units** that are supposed to locally train their data and send their model updates (gradients/weights) to an **aggregator** that should collect, aggregate and send back the global model. 

This simulates a real-world environment where multiple medical units collaborate with each other in order to create a federated model. This project should test the functionality and fiability of this idea in a controlled, virtualized environment. 

## 2. Set up K3s (lighweight kubernetes)

K3s is a lightweight Kubernetes distribution that includes all essential components.

Run the following commands to install K3s without Flannel (so we can use Calico): `curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=none --disable-network-policy" sh -`

This installs K3s and disables Flannel, allowing us to use Calico as the network plugin.

Configure permissions:
- `sudo chown $(id -u):$(id -g) /etc/rancher/k3s/k3s.yaml`
- `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`

Make it permanent:
- `echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc`
- `source ~/.bashrc`

Check if K3s is running: `k3s kubectl get nodes`

If the node is in `ready` state, K3s is installed successfully.

Allow Calico networking: `k3s kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.25.0/manifests/calico.yaml`

Verify that Calico is running:
- `k3s kubectl get pods -n kube-system | grep calico`

- `Disable swap (permanent) in order for kubernetes to work properly:
- `sudo swapoff -a`
- `sudo sed -i '/ swap / s/^/#/' /etc/fstab`
- `sudo modprobe br_netfilter`
- `echo 'br_netfilter' | sudo tee /etc/modules-load.d/k8s.conf`
- `sudo tee /etc/sysctl.d/k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF`
- `sudo sysctl --system`

After a system reboot, use the restart-k3s.sh script to reapply all deployments and networking: `./scripts/restart-k3s.sh`

This script will:
- restart k3s
- ensure that federated learning namespace exist
- reapply calico networking
- restart CoreDNS
- reapply deployment and services

## 3. CheXpert Dataset

CheXlocalize is a radiologist-annotated segmentation dataset on chest X-rays.he dataset consists of two types of radiologist annotations 
for the localization of 10 pathologies: pixel-level segmentations and most-representative points. Annotations were drawn on images from 
the CheXpert validation and test sets.  The 10 pathologies of interest were Atelectasis, Cardiomegaly, Consolidation, Edema, Enlarged 
Cardiomediastinum, Lung Lesion, Lung Opacity, Pleural Effusion, Pneumothorax, and Support Devices. 

Download it from [here](https://stanfordaimi.azurewebsites.net/datasets/8cbd9ed4-2eb9-4565-affc-111cf4f7ebe2) - requires account in order to
obtain the download link and azcopy for download. Steps:
- `wget https://aka.ms/downloadazcopy-v10-linux -O azcopy.tar.gz`
- `tar -xvf azcopy.tar.gz`
- `sudo mv azcopy_linux_amd64_*/azcopy /usr/local/bin/`
- `azcopy copy "<DOWNLOAD_LINK>" "<DESTINATION_PATH>" --recursive`

The download link will be obtained from the Standford website and the path should be the root directory from git.

One can use the 'preprocessing/unzip_chexpert.py' script to automatically unzip and sort the data.

## 4. Dataset Preparation
1. Prerequisites:
    - Python `3.11.2` (since `pyspark` has some deprecated libraries that won't 
    work after `3.12+`). 
    [Pyenv](https://github.com/pyenv/pyenv?tab=readme-ov-file#installation) can 
    be used for this step
    - `pandas`, `tqdm`, `pyspark`, `bs4` python libraries
    - `openjdk-11-jdk` - can be installed with `sudo apt install openjdk-11-jdk`

While in the root of the repo (and assuming the 400GB+ CheXpert dataset 
folder `chexpertchestxrays-u20210408` is one level higher - but the file
paths can be tweaked in the python scripts if inconvenient):

2. `python dataset_preparation/moveToTrainAndValid.py` - this pulls 
    the patient data into a `CheXpert-v1.0/` folder, under `train/` and 
    `valid/` folders
3. You can also manually move the `valid.csv` and `train.csv` files into
    `CheXpert-v1.0/` since they are small and won't crash your file explorer
4. `python dataset_preparation/datasetSplit.py` - this splits the dataset
    under `train/` into 5 parts. It creates a `clients/` folder and, for each
    client, will generate a `train/` and `train.csv`
5. You may want to tweak `PATIENTS_FRACTION` or customize 
    `dataset_preparation/label_config.json` to control how the sub-datasets
    are skewed

Before each `datasetSplit.py` run, the already split data (if it exists),
is reconsolidated by `rebuildOriginalDataset.py` back into 
`CheXpert-v1.0/train`, but you can also run it manually if needed, 
it won't throw errors on empty folders.

## 5. gRPC
1. It is recommended to go through the official gRPC [tutorial](https://grpc.io/docs/languages/python/quickstart/) first

## 6. Steps/To Do's

1. Kubernetes Cluster General architecture - **done**
    - Aggregator and Medical Units deployments;
    - Aggregator service;
    - **DISCLAIMER**: the deployment .yaml files and services will suffer significant changes thorough the project, this step is just for an initial kubernetes set-up standpoint;
2. Install TFF inside Medical Units - **done**
3. Distribute training data to the Medical Units
    - find proper datasets; --**done**
    - implement an automatic way to distribute data to the Medical Units - **done**
4. Train a local model inside each Medical unit - **done**
5. Implement gRPC communication between Medical Units and Aggregator
    - use gRPC to send updates from Medical Units to Aggregator;
    - use gRPC to send general model updates from Aggregator to Medical Units;
6. Implement federated aggregation logic in Aggregator;
7. Stress/Negative test
    - find ways to network-stress the environment;
    - distribute data unequally and test performance;
