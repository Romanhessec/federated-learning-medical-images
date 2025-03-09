# federated-learning-medical-images

Master's thesis project.

Lucas Lazaroiu, Gabriel-Marian Roman.

## 1. General Overview

The Kubernetes cluster will host **5 medical-units** that are supposed to locally train their data and send their model updates (gradients/weights) to an **aggregator** that should collect, aggregate and send back the global model. 

This simulates a real-world environment where multiple medical units collaborate with each other in order to create a federated model. This project should test the functionality and fiability of this idea in a controlled, virtualized environment. 

## 2. Set up Kubernetes Cluster

TBD if this part is needed in the README or not

- `sudo kubeadm init --pod-network-cidr=10.244.0.0/16`
- `mkdir -p $HOME/.kube`
- `sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config`
- `sudo chown $(id -u):$(id -g) $HOME/.kube/config`
- `kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml`

Should use `scripts/restart_k8s.sh` script to deploy the kubernetes cluster and pods after host's system start-up. 

## 3. Steps/To Do's

1. Kubernetes Cluster General architecture - **done**
    - Aggregator and Medical Units deployments;
    - Aggregator service;
    - **DISCLAIMER**: the deployment .yaml files and services will suffer significant changes thorough the project, this step is just for an initial kubernetes set-up standpoint;
2. Install TFF inside Medical Units
3. Distribute training data to the Medical Units
    - find proper datasets;
    - implement an automatic way to distribute data to the Medical Units - big data project;
4. Train a local model inside each Medical unit
5. Implement gRPC communication between Medical Units and Aggregator
    - use gRPC to send updates from Medical Units to Aggregator;
    - use gRPC to send general model updates from Aggregator to Medical Units;
6. Implement federated aggregation logic in Aggregator;

