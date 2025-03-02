# federated-learning-medical-images

## 1. Set up Kubernetes Cluster

TBD if this part is needed in the README or not

- `sudo kubeadm init --pod-network-cidr=10.244.0.0/16`
- `mkdir -p $HOME/.kube`
- `sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config`
- `sudo chown $(id -u):$(id -g) $HOME/.kube/config`
- `kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml`

