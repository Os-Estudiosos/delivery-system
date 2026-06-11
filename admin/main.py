import os
import re
import yaml
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from kubernetes import client, config, utils

from shared.database.connection import get_session
from shared.database.models import Region

app = FastAPI(title="admin-service")

# Initialize Kubernetes configuration
try:
    config.load_incluster_config()
    print("[K8s] Loaded in-cluster configuration.")
except Exception:
    try:
        config.load_kube_config()
        print("[K8s] Loaded local kube-config.")
    except Exception as e:
        print(f"[K8s] Warning: Could not initialize Kubernetes client: {e}")

# Schemas
class CityCreate(BaseModel):
    name: str  # e.g., "São Paulo, Brazil" or "Campinas"

class CityResponse(BaseModel):
    id: int
    name: str
    namespace: str | None = None
    status: str


def slugify(s: str) -> str:
    """Convert a string to a safe Kubernetes namespace name."""
    s = s.lower()
    s = re.sub(r'[^a-z0-9\-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}


@app.get("/city", response_model=list[dict])
def list_cities(session: Session = Depends(get_session)):
    regions = session.query(Region).all()
    return [{"id": r.id, "name": r.name} for r in regions]


@app.post("/city", response_model=CityResponse, status_code=status.HTTP_201_CREATED)
def create_city(city: CityCreate, session: Session = Depends(get_session)):
    # 1. Register Region in the database
    # Check if region already exists
    existing = session.query(Region).filter(Region.name == city.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"City '{city.name}' is already registered."
        )

    db_region = Region(name=city.name)
    session.add(db_region)
    try:
        session.commit()
        session.refresh(db_region)
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    # 2. Dynamic Kubernetes Provisioning
    namespace_name = f"city-{db_region.id}-{slugify(city.name)}"
    
    try:
        v1 = client.CoreV1Api()
        k8s_client = client.ApiClient()

        # Check if namespace already exists
        ns_exists = False
        try:
            v1.read_namespace(name=namespace_name)
            ns_exists = True
        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise

        # Create Namespace if it doesn't exist
        if not ns_exists:
            ns = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace_name))
            v1.create_namespace(body=ns)
            print(f"[K8s] Created namespace: {namespace_name}")

        # Create ConfigMap 'app-config' in the new namespace
        cm_data = {
            "DB_HOST": os.environ.get("DB_HOST", "host.docker.internal"),
            "DB_PORT": os.environ.get("DB_PORT", "5432"),
            "DB_NAME": os.environ.get("DB_NAME", "dijkfood"),
            "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            "AWS_ENDPOINT": os.environ.get("AWS_ENDPOINT", "http://host.docker.internal:4566"),
            "REGION_ID": str(db_region.id),
            "CITY_NAME": city.name,
        }
        
        cm = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(name="app-config", namespace=namespace_name),
            data=cm_data
        )
        try:
            v1.create_namespaced_config_map(namespace=namespace_name, body=cm)
        except client.exceptions.ApiException as e:
            if e.status == 409:  # Conflict / Already exists
                v1.replace_namespaced_config_map(name="app-config", namespace=namespace_name, body=cm)
            else:
                raise

        # Create Secret 'app-secret' in the new namespace
        sec = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(name="app-secret", namespace=namespace_name),
            string_data={
                "DB_USER": os.environ.get("DB_USER", "postgres"),
                "DB_PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            }
        )
        try:
            v1.create_namespaced_secret(namespace=namespace_name, body=sec)
        except client.exceptions.ApiException as e:
            if e.status == 409:
                v1.replace_namespaced_secret(name="app-secret", namespace=namespace_name, body=sec)
            else:
                raise

        # Replicate microservices in the namespace
        env = os.environ.get("ENV", "local").lower()
        service_file = "service-local.yaml" if env == "local" else "service-prod.yaml"
        
        manifest_files = [
            "clients.yaml",
            "couriers.yaml",
            "matching.yaml",
            "orders.yaml",
            "restaurants.yaml",
            "region.yaml",
            service_file
        ]

        for filename in manifest_files:
            filepath = f"/app/infra/k8s/city/{filename}"
            if not os.path.exists(filepath):
                print(f"[K8s] Warning: Manifest file not found: {filepath}")
                continue
                
            with open(filepath, "r") as f:
                content = f.read()
                
            # Replace placeholder namespace with actual dynamic namespace
            content = content.replace("namespace: city-example-namespace", f"namespace: {namespace_name}")
            
            # Apply resources
            dicts = list(yaml.safe_load_all(content))
            for d in dicts:
                if d:
                    try:
                        utils.create_from_dict(k8s_client, d)
                    except utils.FailToActionException as err:
                        # If a resource already exists, log it. In some cases, we can ignore conflict errors.
                        print(f"[K8s] Resource already exists or failed to create: {err}")
                    except Exception as err:
                        print(f"[K8s] Error creating resource from dict: {err}")

        return CityResponse(
            id=db_region.id,
            name=db_region.name,
            namespace=namespace_name,
            status="provisioned"
        )

    except Exception as e:
        print(f"[K8s] Provisioning failed for namespace {namespace_name}: {e}")
        # Return DB record registered, but Kubernetes deployment failed
        return CityResponse(
            id=db_region.id,
            name=db_region.name,
            namespace=namespace_name,
            status=f"provision_error: {str(e)}"
        )
