import os
import re
import yaml
import time
import json
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from kubernetes import client, config, utils
import boto3

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

# Initialize Athena Client (for production analytics)
ENV = os.environ.get("ENV", "local").lower()
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ATHENA_DATABASE = "dijkfood_analytics"

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


def run_athena_query(query_str: str) -> list[dict]:
    """Runs a query on Amazon Athena and returns the parsed rows."""
    if ENV == "local":
        return []

    try:
        athena_client = boto3.client("athena", region_name=AWS_REGION)
        # We need a configured S3 bucket to output Athena query results
        # We use the datalake bucket name from the environment variable if available
        datalake_bucket = os.environ.get("DATALAKE_BUCKET")
        if datalake_bucket:
            s3_output = f"s3://{datalake_bucket}/athena-results/"
        else:
            s3_output = f"s3://dijkfood-datalake-results/"

        response = athena_client.start_query_execution(
            QueryString=query_str,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            ResultConfiguration={"OutputLocation": s3_output}
        )
        query_execution_id = response["QueryExecutionId"]
        
        # Wait for query execution to complete
        for _ in range(30):
            status_resp = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if state == "SUCCEEDED":
                    results = athena_client.get_query_results(QueryExecutionId=query_execution_id)
                    rows = results["ResultSet"]["Rows"]
                    if not rows:
                        return []
                    headers = [col.get("VarCharValue", "") for col in rows[0]["Data"]]
                    data = []
                    for row in rows[1:]:
                        row_data = {}
                        for i, col in enumerate(row["Data"]):
                            header = headers[i] if i < len(headers) else f"col_{i}"
                            row_data[header] = col.get("VarCharValue", "")
                        data.append(row_data)
                    return data
                else:
                    print(f"Athena query execution ended with state: {state}")
                    return []
            time.sleep(0.5)
    except Exception as e:
        print(f"Failed to query Athena: {e}")
    return []


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}


# Server dashboard GUI
@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(current_dir, "dashboard.html")
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<h3>Erro ao carregar dashboard: {str(e)}</h3>"


def get_namespace_status(namespace_name: str) -> dict:
    try:
        try:
            v1 = client.CoreV1Api()
        except Exception:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()

        # Read namespace status
        try:
            ns = v1.read_namespace(name=namespace_name)
            if ns.status.phase != "Active":
                return {"status": "inactive", "detail": f"Inativo ({ns.status.phase})"}
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return {"status": "not_created", "detail": "Não criado no K8s"}
            raise

        # List pods in the namespace
        pods = v1.list_namespaced_pod(namespace=namespace_name)
        if not pods.items:
            return {"status": "empty", "detail": "Aguardando agendamento dos pods..."}

        total_pods = len(pods.items)
        ready_pods = 0
        matching_status = "pending"

        pod_details = []
        for pod in pods.items:
            pod_name = pod.metadata.name
            pod_app = pod.metadata.labels.get("app", pod_name)
            phase = pod.status.phase
            
            # Check container readiness
            is_ready = False
            if pod.status.container_statuses:
                is_ready = all(c.ready for c in pod.status.container_statuses)
            
            if is_ready:
                ready_pods += 1
                
            if pod_app == "matching":
                if is_ready:
                    matching_status = "ready"
                else:
                    restarts = sum(c.restart_count for c in pod.status.container_statuses) if pod.status.container_statuses else 0
                    if restarts > 0:
                        matching_status = "error"
                    else:
                        matching_status = "downloading_map"
            
            pod_details.append({
                "name": pod_app,
                "status": "Running (Ready)" if is_ready else phase,
                "ready": is_ready
            })
            
        # Overall status heuristic
        if ready_pods >= 6:
            status_str = "ready"
            detail_str = "Pronto para uso (todos os pods saudáveis)"
        elif matching_status == "downloading_map":
            status_str = "downloading_map"
            detail_str = f"Roteador baixando mapa de Campinas ({ready_pods}/{total_pods} prontos)"
        elif matching_status == "error":
            status_str = "error"
            detail_str = f"Falha na inicialização do roteador ({ready_pods}/{total_pods} prontos)"
        else:
            status_str = "provisioning"
            detail_str = f"Criando recursos ({ready_pods}/{total_pods} prontos)"
            
        return {
            "status": status_str,
            "detail": detail_str,
            "pods": pod_details
        }
    except Exception as e:
        return {"status": "error", "detail": f"Erro k8s: {str(e)}", "pods": []}


@app.get("/city", response_model=list[dict])
def list_cities(session: Session = Depends(get_session)):
    regions = session.query(Region).all()
    results = []
    for r in regions:
        namespace_name = f"city-{r.id}-{slugify(r.name)}"
        k8s_status = get_namespace_status(namespace_name)
        results.append({
            "id": r.id,
            "name": r.name,
            "namespace": namespace_name,
            "status": k8s_status["status"],
            "detail": k8s_status["detail"],
            "pods": k8s_status.get("pods", [])
        })
    return results


@app.post("/city", response_model=CityResponse, status_code=status.HTTP_201_CREATED)
def create_city(city: CityCreate, session: Session = Depends(get_session)):
    # 1. Register Region in the database
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
            "AWS_ENDPOINT": os.environ.get("AWS_ENDPOINT", ""),
            "ENV": os.environ.get("ENV", "production"),
            "REGION_ID": str(db_region.id),
            "CITY_NAME": city.name,
            # Limit pool size per replica to avoid saturating RDS db.t3.micro
            # (max ~85 connections). With 3 replicas × 3 services × (5+5) = 90 max.
            "DB_POOL_SIZE": os.environ.get("DB_POOL_SIZE", "4"),
            "DB_MAX_OVERFLOW": os.environ.get("DB_MAX_OVERFLOW", "2"),
            "DB_POOL_TIMEOUT": os.environ.get("DB_POOL_TIMEOUT", "30"),
            # S3 bucket for OSMnx graph cache — without this, matching re-downloads
            # the graph from OpenStreetMap on every pod restart (1-2 min cold start).
            "S3_BUCKET": os.environ.get("S3_BUCKET", ""),
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

        sec_string_data = {
            "DB_USER": os.environ.get("DB_USER", "postgres"),
            "DB_PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        }
        for k in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
            v = os.environ.get(k)
            if v is not None:
                sec_string_data[k] = v

        sec = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(name="app-secret", namespace=namespace_name),
            string_data=sec_string_data
        )
        try:
            v1.create_namespaced_secret(namespace=namespace_name, body=sec)
        except client.exceptions.ApiException as e:
            if e.status == 409:
                v1.replace_namespaced_secret(name="app-secret", namespace=namespace_name, body=sec)
            else:
                raise

        # Replicate microservices in the namespace
        # Dynamically provisioned namespaces always use ClusterIP (service-prod.yaml) to avoid NodePort conflicts
        service_file = "service-prod.yaml"
        
        manifest_files = [
            "clients.yaml",
            "couriers.yaml",
            "matching.yaml",
            "orders.yaml",
            "restaurants.yaml",
            "region.yaml",
            service_file,
            "hpas.yaml"
        ]

        for filename in manifest_files:
            filepath = f"/app/infra/k8s/city/{filename}"
            if not os.path.exists(filepath):
                filepath = f"infra/k8s/city/{filename}" # local testing fallback path
                if not os.path.exists(filepath):
                    print(f"[K8s] Warning: Manifest file not found: {filepath}")
                    continue
                
            with open(filepath, "r") as f:
                content = f.read()
                
            # Replace placeholder namespace with actual dynamic namespace
            content = content.replace("namespace: city-example-namespace", f"namespace: {namespace_name}")
            content = content.replace("city-example-namespace.local", f"{namespace_name}.local")
            
            # Replace local images with ECR URI if ECR_REGISTRY env var is set
            ecr_registry = os.environ.get("ECR_REGISTRY", "")
            if ecr_registry:
                content = content.replace("image: delivery-system/", f"image: {ecr_registry}/delivery-system/")
            
            # Apply resources
            dicts = list(yaml.safe_load_all(content))
            for d in dicts:
                if d:
                    try:
                        utils.create_from_dict(k8s_client, d)
                    except utils.FailToCreateError as err:
                        # If resource exists, skip
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
        return CityResponse(
            id=db_region.id,
            name=db_region.name,
            namespace=namespace_name,
            status=f"provision_error: {str(e)}"
        )


# -------------------- Analytics Endpoints (OLAP) --------------------

@app.get("/analytics/volume-over-time")
def get_volume_over_time():
    query = """
        SELECT date_trunc('hour', from_iso8601_timestamp(timestamp)) AS order_hour, count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events
        WHERE status = 'CONFIRMED'
        GROUP BY 1 ORDER BY 1 ASC;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }
    
    return {
        "labels": [r.get("order_hour", "")[:16] for r in rows],
        "values": [int(r.get("total_orders", 0)) for r in rows]
    }


@app.get("/analytics/top-restaurants")
def get_top_restaurants():
    query = """
        SELECT restaurant_id, count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events
        WHERE status = 'CONFIRMED'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }

    return {
        "labels": [f"Restaurante {r.get('restaurant_id', '')}" for r in rows],
        "values": [int(r.get("total_orders", 0)) for r in rows]
    }


@app.get("/analytics/transition-times")
def get_transition_times():
    query = """
        WITH event_intervals AS (
          SELECT order_id, status, from_iso8601_timestamp(timestamp) AS current_time,
            lead(from_iso8601_timestamp(timestamp)) OVER(PARTITION BY order_id ORDER BY timestamp) AS next_time,
            lead(status) OVER(PARTITION BY order_id ORDER BY timestamp) AS next_status
          FROM dijkfood_analytics.events
        )
        SELECT status, next_status, avg(date_diff('second', current_time, next_time)) AS avg_duration_seconds
        FROM event_intervals WHERE next_status IS NOT NULL GROUP BY 1, 2;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }

    labels = [f"{r.get('status', '')} → {r.get('next_status', '')}" for r in rows]
    values = [float(r.get("avg_duration_seconds", 0)) for r in rows]
    return {"labels": labels, "values": values}


@app.get("/analytics/delivery-histogram")
def get_delivery_histogram():
    query = """
        WITH delivery_times AS (
          SELECT order_id, min(from_iso8601_timestamp(timestamp)) AS confirmed_at, max(from_iso8601_timestamp(timestamp)) AS delivered_at,
            date_diff('minute', min(from_iso8601_timestamp(timestamp)), max(from_iso8601_timestamp(timestamp))) AS delivery_duration_minutes
          FROM dijkfood_analytics.events WHERE status IN ('CONFIRMED', 'DELIVERED') GROUP BY order_id HAVING count(distinct status) = 2
        )
        SELECT (delivery_duration_minutes / 5) * 5 AS duration_bucket_start_mins, count(*) AS total_orders
        FROM delivery_times GROUP BY 1 ORDER BY 1 ASC;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }

    labels = [f"{r.get('duration_bucket_start_mins', '')} - {int(r.get('duration_bucket_start_mins', 0)) + 5} min" for r in rows]
    values = [int(r.get("total_orders", 0)) for r in rows]
    return {"labels": labels, "values": values}


@app.get("/analytics/regions")
def get_regions():
    query = """
        SELECT region_id, count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events
        WHERE status = 'CONFIRMED'
        GROUP BY 1 ORDER BY 2 DESC;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }

    return {
        "labels": [f"Região {r.get('region_id', '')}" for r in rows],
        "values": [int(r.get("total_orders", 0)) for r in rows]
    }


@app.get("/analytics/heatmap")
def get_heatmap():
    query = """
        SELECT day_of_week(from_iso8601_timestamp(timestamp)) AS day_of_week_num, hour(from_iso8601_timestamp(timestamp)) AS hour_of_day, count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events WHERE status = 'CONFIRMED' GROUP BY 1, 2 ORDER BY 1, 2;
    """
    rows = run_athena_query(query)
    if not rows:
        return {"values": []}

    return {
        "values": [
            {
                "x": int(r.get("day_of_week_num", 1)),
                "y": int(r.get("hour_of_day", 0)),
                "r": int(r.get("total_orders", 0)) // 2 + 3 # scale radius
            }
            for r in rows
        ]
    }
