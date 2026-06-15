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
def download_graph(place: str, network_type: str, city: str):
    city_lower = city.lower()
    place_lower = place.lower()

    if "são paulo" in city_lower or "sao paulo" in city_lower or "são paulo" in place_lower or "sao paulo" in place_lower:
        print(f"[download] São Paulo detected. Using graph_from_point (2km radius around Sé) to avoid OOM.")
        graph = ox.graph_from_point((-23.5505, -46.6333), dist=2000, network_type=network_type)
    else:
        print(f"[download] Fetching '{network_type}' network for '{city}, {place}' …")
        graph = ox.graph_from_place(f"{city}, {place}", network_type=network_type)

    print(f"[download] Done")
    return graph