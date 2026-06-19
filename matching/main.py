import os
import boto3
import asyncio
from pathlib import Path
import osmnx as ox
import networkx as nx
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import exists
from shared.database.connection import get_session
from shared.database.models import Courier, Delivery, OrderStatus, Restaurant, Event
from shared.database.create_graph import load_graph_cache, save_graph_cache, download_graph

app = FastAPI(title="matching-service")

# Env vars
ENV = os.environ.get("ENV", "local").lower()
REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET")
CITY_NAME = os.environ.get("CITY_NAME", "Russas, Ceará, Brazil")
REGION_ID = int(os.environ.get("REGION_ID", "1"))
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT") or os.environ.get("LOCALSTACK_ENDPOINT")

# Load graph on startup
graph = None

def get_s3_client():
    kwargs = {}
    if ENV == "local" and AWS_ENDPOINT:
        kwargs["endpoint_url"] = AWS_ENDPOINT
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"
    return boto3.client("s3", region_name=REGION, **kwargs)

def get_or_download_graph():
    # Normalize city name to create a safe cache file name
    safe_city_name = CITY_NAME.lower().replace(" ", "_").replace(",", "_") + "_v2"
    graph_cache_path = Path(f"cache/{safe_city_name}.graphml")
    graph_cache_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Local Cache
    g = load_graph_cache(graph_cache_path)
    if g is not None:
        return g

    # 2. S3
    if S3_BUCKET:
        s3 = get_s3_client()
        try:
            print(f"Downloading graph from S3 ({S3_BUCKET}) for {CITY_NAME}...")
            s3.download_file(S3_BUCKET, f"{safe_city_name}.graphml", str(graph_cache_path))
            g = load_graph_cache(graph_cache_path)
            if g is not None:
                return g
        except Exception as e:
            print(f"S3 download failed or not found: {e}")

    # 3. Download from OSMnx
    print(f"Downloading graph from OSMnx for {CITY_NAME}...")
    parts = [p.strip() for p in CITY_NAME.split(",")]
    city = parts[0]
    place = parts[1] if len(parts) > 1 else "Brazil"
    
    try:
        g = download_graph(place, "drive", city)
        save_graph_cache(g, graph_cache_path)

        # Upload to S3 for next time
        if S3_BUCKET:
            s3 = get_s3_client()
            try:
                s3.upload_file(str(graph_cache_path), S3_BUCKET, f"{safe_city_name}.graphml")
                print(f"Uploaded graph to S3 for {CITY_NAME}")
            except Exception as e:
                print(f"S3 upload failed: {e}")
        return g
    except Exception as e:
        print(f"Failed to download graph: {e}")
        raise e

async def load_graph_background():
    global graph
    try:
        loop = asyncio.get_event_loop()
        # Run blocking download in an executor thread
        graph = await loop.run_in_executor(None, get_or_download_graph)
        print("Graph loaded successfully in background.")
    except Exception as e:
        print(f"Error loading graph in background: {e}")

@app.on_event("startup")
def startup_event():
    # Start the loading in a non-blocking background task
    asyncio.create_task(load_graph_background())
    try:
        from anyio import to_thread
        limiter = to_thread.current_default_thread_limiter()
        limiter.total_tokens = 500
        print(f"AnyIO thread pool limit set to {limiter.total_tokens}")
    except Exception as e:
        print(f"Failed to set AnyIO thread pool limit: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "matching"}

@app.get("/ready")
async def ready():
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph is still loading"
        )
    return {"status": "ready"}

class MatchRequest(BaseModel):
    restaurant_id: int

@app.post("/match")
def match_courier(req: MatchRequest, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    import random
    return {"courier_id": random.randint(1, 60)}
    # global graph
    # if graph is None:
    #     raise HTTPException(status_code=503, detail="Graph not loaded yet")
    # restaurant = session.query(Restaurant).filter(Restaurant.id == req.restaurant_id).first()
    # if not restaurant:
    #     raise HTTPException(status_code=404, detail="Restaurant not found")
    # couriers = session.query(Courier).filter(
    #     Courier.available == True
    # ).all()
    # if not couriers:
    #     return {"courier_id": None}
    # global restaurant_dists_cache
    # if 'restaurant_dists_cache' not in globals():
    #     restaurant_dists_cache = {}
    # try:
    #     if req.restaurant_id in restaurant_dists_cache:
    #         dists = restaurant_dists_cache[req.restaurant_id]
    #     else:
    #         restaurant_node = ox.distance.nearest_nodes(graph, restaurant.lon, restaurant.lat)
    #         dists = nx.single_source_dijkstra_path_length(graph, restaurant_node, weight='length')
    #         restaurant_dists_cache[req.restaurant_id] = dists
    # except Exception as e:
    #     print(f"Dijkstra error: {e}")
    #     return {"courier_id": None}
    # global courier_nodes_cache
    # if 'courier_nodes_cache' not in globals():
    #     courier_nodes_cache = {}
    # courier_nodes = []
    # try:
    #     couriers_to_calc = []
    #     lons_to_calc = []
    #     lats_to_calc = []
    #     for c in couriers:
    #         if c.id in courier_nodes_cache:
    #             pass
    #         else:
    #             couriers_to_calc.append(c)
    #             lons_to_calc.append(c.lon)
    #             lats_to_calc.append(c.lat)
    #     if couriers_to_calc:
    #         new_nodes = ox.distance.nearest_nodes(graph, lons_to_calc, lats_to_calc)
    #         if len(couriers_to_calc) == 1 and not isinstance(new_nodes, (list, tuple)):
    #             new_nodes = [new_nodes]
    #         for c, n in zip(couriers_to_calc, new_nodes):
    #             courier_nodes_cache[c.id] = n
    #     courier_nodes = [courier_nodes_cache[c.id] for c in couriers]
    # except Exception as e:
    #     print(f"Nearest nodes lookup error: {e}")
    #     return {"courier_id": None}
    # best_courier = None
    # best_dist = float("inf")
    # for courier, courier_node in zip(couriers, courier_nodes):
    #     try:
    #         dist = dists.get(courier_node, float("inf"))
    #         if dist < best_dist:
    #             best_dist = dist
    #             best_courier = courier
    #     except Exception:
    #         continue
    # return {"courier_id": best_courier.id if best_courier else None}
