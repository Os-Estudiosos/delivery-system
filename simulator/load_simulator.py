from __future__ import annotations

import csv
from collections import defaultdict
import time
from utils.cheapest_path import dijkstra


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def load_graph(path: str) -> dict[int, list[tuple[int, float]]]:
    """
    Load a weighted directed graph from a CSV edge-list file.

    Parameters
    ----------
    path : str
        Path to the CSV file with columns: from_node, to_node, weight.

    Returns
    -------
    dict mapping each node id to a list of (neighbour, weight) tuples.
    """
    graph: dict[int, list[tuple[int, float]]] = defaultdict(list)
    total_edges = 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            u = int(row["from_node"])
            v = int(row["to_node"])
            w = float(row["weight"])
            graph[u].append((v, w))
            total_edges += 1

    print(f"[load_graph] {len(graph):,} nodes | {total_edges:,} edges loaded from '{path}'")
    return graph


# ---------------------------------------------------------------------------
# Query loading
# ---------------------------------------------------------------------------

def load_queries(path: str) -> list[tuple[int, int]]:
    """
    Load source-destination pairs from a CSV file.

    Parameters
    ----------
    path : str
        Path to the CSV file with columns: source, destination.

    Returns
    -------
    List of (source, destination) integer tuples.
    """
    queries: list[tuple[int, int]] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            queries.append((int(row["source"]), int(row["destination"])))

    print(f"[load_queries] {len(queries):,} queries loaded from '{path}'")
    return queries

def simulation(api_url: str) -> None:
    """Run API health/load simulation against the deployed AWS URL."""
    pass

def main() -> None:
    pass


# Exemplo
# def main() -> None:
#     parser = argparse.ArgumentParser(description="Dijkstra shortest-path benchmark")
#     parser.add_argument("--graph",   default="graph.csv",   help="Path to edge-list CSV")
#     parser.add_argument("--queries", default="queries.csv", help="Path to queries CSV")
#     args = parser.parse_args()

#     # Load data
#     graph = load_graph(args.graph)
#     queries = load_queries(args.queries)

#     # Run all queries and measure time
#     print(f"\nRunning {len(queries):,} shortest-path queries …")

#     not_found = 0
#     t_start = time.perf_counter()

#     for source, destination in queries:
#         dist = dijkstra(graph, source)
#         if destination not in dist:
#             not_found += 1

#     t_end = time.perf_counter()
#     elapsed = t_end - t_start

#     # Report results
#     print("\n========================================")
#     print(f"  Queries executed : {len(queries):,}")
#     print(f"  Unreachable pairs: {not_found:,}")
#     print(f"  Total time       : {elapsed:.4f} s")
#     print("========================================\n")


if __name__ == "__main__":
    main()