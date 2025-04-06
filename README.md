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

## 4. Steps/To Do's

1. Kubernetes Cluster General architecture - **done**
    - Aggregator and Medical Units deployments;
    - Aggregator service;
    - **DISCLAIMER**: the deployment .yaml files and services will suffer significant changes thorough the project, this step is just for an initial kubernetes set-up standpoint;
2. Install TFF inside Medical Units - **done**
3. Distribute training data to the Medical Units
    - find proper datasets;
    - implement an automatic way to distribute data to the Medical Units - big data project;
4. Train a local model inside each Medical unit
5. Implement gRPC communication between Medical Units and Aggregator
    - use gRPC to send updates from Medical Units to Aggregator;
    - use gRPC to send general model updates from Aggregator to Medical Units;
6. Implement federated aggregation logic in Aggregator;
7. Stress/Negative test
    - find ways to network-stress the environment;
    - distribute data unequally and test performance;
