
from typing import Tuple, List, Dict
from pathlib import Path
import logging

from shared.database.connection import _s3_client, S3_BUCKET


try:
    import osmnx as ox  # type: ignore
except Exception:
    ox = None


def compute_route(start: Tuple[float, float], via: Tuple[float, float], end: Tuple[float, float]) -> List[Dict[str, float]]:
    """Placeholder route: returns polyline of points.

    When a prepared graph is available, this should be replaced with
    shortest-path computations using `osmnx`/NetworkX.
    """
    return [
        {"lat": start[0], "lon": start[1]},
        {"lat": via[0], "lon": via[1]},
        {"lat": end[0], "lon": end[1]},
    ]


def _cache_path_for(city: str, mode: str = "drive") -> Path:
    safe = city.replace(" ", "_")
    p = Path("cache") / f"{safe}_{mode}.graphml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_graph_cache(path: Path):
    if not path.exists():
        return None
    try:
        if ox:
            return ox.load_graphml(str(path))
        else:
            import networkx as nx

            return nx.read_graphml(str(path))
    except Exception:
        logging.exception("failed to load graph cache")
        return None


def save_graph_cache(graph_obj, path: Path):
    try:
        if ox:
            ox.save_graphml(graph_obj, str(path))
        else:
            import networkx as nx

            nx.write_graphml(graph_obj, str(path))
        return True
    except Exception:
        logging.exception("failed to save graph cache")
        return False


def upload_to_s3(local_path: Path, s3_key: str) -> bool:
    if not S3_BUCKET:
        return False
    try:
        client = _s3_client()
        client.upload_file(str(local_path), S3_BUCKET, s3_key)
        return True
    except Exception:
        logging.exception("failed to upload graph to s3")
        return False


def download_from_s3(s3_key: str, local_path: Path) -> bool:
    if not S3_BUCKET:
        return False
    try:
        client = _s3_client()
        client.download_file(S3_BUCKET, s3_key, str(local_path))
        return True
    except Exception:
        logging.exception("failed to download graph from s3")
        return False


def get_or_download_graph(city: str = "São Paulo, Brazil", mode: str = "drive"):
    """Returns a graph object for `city`.

    1. Try local cache.
    2. Try S3 (if configured).
    3. Download from OpenStreetMap via osmnx and cache/upload.
    Returns graph object or None if unable.
    """
    cache_path = _cache_path_for(city, mode)

    # 1. Local cache
    graph_obj = load_graph_cache(cache_path)
    if graph_obj is not None:
        return graph_obj

    # 2. S3
    s3_key = cache_path.name
    if S3_BUCKET:
        ok = download_from_s3(s3_key, cache_path)
        if ok:
            graph_obj = load_graph_cache(cache_path)
            if graph_obj is not None:
                return graph_obj

    # 3. Build from OSM
    if not ox:
        logging.warning("osmnx not available; cannot download graph from OSM")
        return None

    try:
        graph_obj = ox.graph_from_place(city, network_type=mode)
        save_graph_cache(graph_obj, cache_path)
        if S3_BUCKET:
            upload_to_s3(cache_path, s3_key)
        return graph_obj
    except Exception:
        logging.exception("failed to build graph from OSM")
        return None
