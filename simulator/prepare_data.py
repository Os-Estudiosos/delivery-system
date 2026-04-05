import argparse
import csv
import random
import sys
import osmnx as ox


# Puxando o grafo da OpenStreetMap usando OSMnx
def download_graph(place: str, network_type: str):

    print(f"[download] Fetching '{network_type}' network for '{place}' …")
    graph = ox.graph_from_place(place, network_type=network_type)
    print(f"[download] Done")

    return graph


# Salvando o grafo em um arquivo CSV no formato de lista de arestas (edge list)
def save_graph_csv(graph, output_path: str) -> list[int]:

    seen: dict[tuple[int, int], float] = {}
    for u, v, data in graph.edges(data=True):
        w = float(data.get("length", 1.0))   # fallback para peso 1.0 se 'length' não estiver presente
        key = (u, v)
        if key not in seen or w < seen[key]:
            seen[key] = w

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["from_node", "to_node", "weight"])
        for (u, v), w in sorted(seen.items()):
            writer.writerow([u, v, f"{w:.4f}"])

    node_ids = sorted(graph.nodes())
    print(f"[save_graph] {len(node_ids):,} nodes | {len(seen):,} edges → '{output_path}'")

    return node_ids


# Gerando consultas aleatórias e salvando em um arquivo CSV
def generate_queries(node_ids: list[int], n_queries: int, output_path: str, seed: int = 42) -> None:

    if len(node_ids) < 2:
        print("[error] Graph has fewer than 2 nodes — cannot generate queries.")
        sys.exit(1)

    if n_queries > len(node_ids) ** 2:
        print(f"[warn] Requested {n_queries:,} queries but graph only supports "
              f"{len(node_ids) ** 2:,} distinct pairs. Capping.")
        n_queries = len(node_ids) ** 2

    rng = random.Random(seed)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "destination"])
        generated = 0
        while generated < n_queries:
            src, dst = rng.sample(node_ids, 2)
            writer.writerow([src, dst])
            generated += 1

    print(f"[generate_queries] {n_queries:,} queries (seed={seed}) → '{output_path}'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download São Paulo road network and generate search queries"
    )
    parser.add_argument(
        "--place",
        default="São Paulo, Brazil",
        help="Place name for OSMnx (default: 'São Paulo, Brazil')"
    )
    parser.add_argument(
        "--network",
        default="drive",
        choices=["drive", "walk", "bike", "all"],
        help="Road network type (default: drive)"
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=100,
        help="Number of queries to generate (default: 100)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    parser.add_argument(
        "--graph-out",
        default="graph.csv",
        help="Output path for the edge-list CSV (default: graph.csv)"
    )
    parser.add_argument(
        "--queries-out",
        default="queries.csv",
        help="Output path for the queries CSV (default: queries.csv)"
    )
    args = parser.parse_args()

    graph = download_graph(args.place, args.network)
    node_ids = save_graph_csv(graph, args.graph_out)
    generate_queries(node_ids, args.queries, args.queries_out, seed=args.seed)

    print("\nAll done!")


if __name__ == "__main__":
    main()
