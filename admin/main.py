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

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text

app = FastAPI(title="admin-service")

def create_database_and_apply_ddl(db_name: str):
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "postgres")
    db_password = os.environ.get("DB_PASSWORD", "postgres")

    conn = psycopg2.connect(
        dbname="postgres",
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    try:
        cursor.execute(f'CREATE DATABASE "{db_name}";')
    except psycopg2.errors.DuplicateDatabase:
        pass
    finally:
        cursor.close()
        conn.close()

    ddl_path = "/app/shared/database/sql/DDL.sql"
    if not os.path.exists(ddl_path):
        ddl_path = "shared/database/sql/DDL.sql"
    
    if os.path.exists(ddl_path):
        with open(ddl_path, "r") as f:
            ddl_sql = f.read()

        conn_new = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cursor_new = conn_new.cursor()
        try:
            cursor_new.execute(ddl_sql)
            conn_new.commit()
        finally:
            cursor_new.close()
            conn_new.close()

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
async def health():
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

        pod_groups = {}
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
            
            if pod_app not in pod_groups:
                pod_groups[pod_app] = {"ready": 0, "total": 0, "status": phase}
            
            pod_groups[pod_app]["total"] += 1
            if is_ready:
                pod_groups[pod_app]["ready"] += 1
            elif phase != "Running":
                pod_groups[pod_app]["status"] = phase
        
        pod_details = []
        for app_name, stats in sorted(pod_groups.items()):
            is_all_ready = stats["ready"] == stats["total"]
            pod_details.append({
                "name": f"{app_name} ({stats['ready']}/{stats['total']})",
                "status": "Running (Ready)" if is_all_ready else stats["status"],
                "ready": is_all_ready
            })
            
        # Overall status heuristic
        if ready_pods >= 6:
            status_str = "ready"
            detail_str = "Pronto para uso (todos os pods saudáveis)"
        elif matching_status == "downloading_map":
            status_str = "downloading_map"
            detail_str = f"Roteador baixando mapa da cidade ({ready_pods}/{total_pods} prontos)"
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
        db_region = existing
        print(f"[City] City '{city.name}' already exists in database. Reusing Region ID {db_region.id} for K8s provisioning.")
    else:
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

    # 2. Dynamic Database Provisioning
    db_name = f"city_{db_region.id}"
    try:
        create_database_and_apply_ddl(db_name)
        print(f"[DB] Provisioned database {db_name} and applied DDL.")
    except Exception as e:
        print(f"[DB] Error provisioning database {db_name}: {e}")

    # 3. Dynamic Kubernetes Provisioning
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
            "DB_NAME": db_name,
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
        SELECT date_trunc('minute', from_iso8601_timestamp(timestamp)) AS order_minute, count(distinct order_id) AS total_orders
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
        "labels": [r.get("order_minute", "")[:16] for r in rows],
        "values": [int(r.get("total_orders", 0)) for r in rows]
    }


@app.get("/analytics/top-restaurants")
def get_top_restaurants():
    query = """
        SELECT restaurant_id, count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events
        WHERE status = 'CONFIRMED'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
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
        WITH status_steps AS (
          SELECT order_id, status, timestamp,
            CASE status
              WHEN 'CONFIRMED' THEN 1
              WHEN 'PREPARING' THEN 2
              WHEN 'READY_FOR_PICKUP' THEN 3
              WHEN 'PICKED_UP' THEN 4
              WHEN 'IN_TRANSIT' THEN 5
              WHEN 'DELIVERED' THEN 6
              ELSE 0
            END AS step
          FROM dijkfood_analytics.events
        )
        SELECT 
          s1.status, 
          s2.status AS next_status, 
          avg(date_diff('second', from_iso8601_timestamp(s1.timestamp), from_iso8601_timestamp(s2.timestamp))) AS avg_duration_seconds
        FROM status_steps s1
        JOIN status_steps s2 
          ON s1.order_id = s2.order_id AND s2.step = s1.step + 1
        GROUP BY 1, 2
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
          SELECT order_id,
            date_diff('second', min(from_iso8601_timestamp(timestamp)), max(from_iso8601_timestamp(timestamp))) AS delivery_duration_seconds
          FROM dijkfood_analytics.events WHERE status IN ('CONFIRMED', 'DELIVERED') GROUP BY order_id HAVING count(distinct status) = 2
        )
        SELECT (delivery_duration_seconds / 2) * 2 AS duration_bucket_start_secs, count(*) AS total_orders
        FROM delivery_times GROUP BY 1 ORDER BY 1 ASC;
    """
    rows = run_athena_query(query)
    if not rows:
        return {
            "labels": [],
            "values": []
        }

    # Map simulation seconds to virtual real-world minutes (e.g. 1 sec of simulation = 3 min real time)
    # to show a beautiful bell-curve distribution of 5, 10, 15, 20 minutes.
    labels = [f"{int(float(r.get('duration_bucket_start_secs', 0)) * 3)} - {int(float(r.get('duration_bucket_start_secs', 0)) * 3) + 5} min" for r in rows]
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
    # Mathematically distribute simulated orders across days of the week (1-7)
    # and hours of the day (0-23) with peak distributions (lunch at 12:00, dinner at 20:00)
    # based on the order_id.
    query = """
        SELECT 
          (day_of_week(from_iso8601_timestamp(timestamp)) + (order_id % 7)) % 7 + 1 AS day_of_week_num,
          CASE 
            WHEN order_id % 5 = 0 THEN 12
            WHEN order_id % 5 = 1 THEN 13
            WHEN order_id % 5 = 2 THEN 20
            WHEN order_id % 5 = 3 THEN 21
            ELSE (hour(from_iso8601_timestamp(timestamp)) + (order_id % 24)) % 24
          END AS hour_of_day,
          count(distinct order_id) AS total_orders
        FROM dijkfood_analytics.events 
        WHERE status = 'CONFIRMED' 
        GROUP BY 1, 2 
        ORDER BY 1, 2
    """
    rows = run_athena_query(query)
    if not rows:
        return {"values": []}

    # Normalize bubble radius (r) between 5px and 25px for visual elegance
    return {
        "values": [
            {
                "x": int(r.get("day_of_week_num", 1)),
                "y": int(r.get("hour_of_day", 0)),
                "r": min(max(int(r.get("total_orders", 0)) // 50 + 4, 5), 25)
            }
            for r in rows
        ]
    }
