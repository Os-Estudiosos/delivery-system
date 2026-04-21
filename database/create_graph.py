import osmnx as ox
from pathlib import Path


def load_graph_cache(graph_path: Path):
    if graph_path.exists():
        print(f"[cache] Loading graph from '{graph_path}' …")
        graph = ox.load_graphml(graph_path)
        print("[cache] Done")
        return graph
    return None


def save_graph_cache(graph, graph_path: Path):
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[cache] Saving graph to '{graph_path}' …")
    ox.save_graphml(graph, graph_path)
    print("[cache] Done")


# Puxando o grafo da OpenStreetMap usando OSMnx
def download_graph(place: str, network_type: str):

    print(f"[download] Fetching '{network_type}' network for '{place}' …")
    graph = ox.graph_from_place(place, network_type=network_type)
    print(f"[download] Done")

    return graph