import os

pod = os.environ["POD_NAME"]                    # e.g. "medical-unit-3"
ORD = pod.rsplit("-", 1)[-1]                    # "3"
root = os.environ.get("CLIENT_DATA_ROOT", "/data/clients")
client_dir = os.path.join(root, f"client_{ORD}")

print(f"➡️ Loading data from {client_dir}")
# then point your TF data loader at `client_dir`