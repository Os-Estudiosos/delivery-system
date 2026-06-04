kubectl delete -f infra/k8s/admin/admin.yaml
kubectl delete -f infra/k8s/city/clients.yaml
kubectl delete -f infra/k8s/city/couriers.yaml
kubectl delete -f infra/k8s/city/matching.yaml
kubectl delete -f infra/k8s/city/orders.yaml
kubectl delete -f infra/k8s/city/restaurants.yaml
kubectl delete -f infra/k8s/admin/service-local.yaml
kubectl delete -f infra/k8s/city/service-local.yaml

kubectl delete -f infra/k8s/config/local/admin-configmap.yaml
kubectl delete -f infra/k8s/config/local/admin-secret.yaml
kubectl delete -f infra/k8s/config/local/city-configmap.yaml
kubectl delete -f infra/k8s/config/local/city-secret.yaml

kubectl delete -f infra/k8s/admin/namespace.yaml
kubectl delete -f infra/k8s/city/namespace-template.yaml

kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
docker compose down -v

Write-Host "Ambiente local destruído com sucesso!"