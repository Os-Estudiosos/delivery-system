from __future__ import annotations
import heapq


# Algoritmo de Dijkstra usando um min-heap (priority queue) para encontrar os caminhos mais baratos
# de todos os nós a partir de um nó fonte. Retorna um dicionário de distâncias mínimas 
# do nó fonte a cada nó alcançável.
def dijkstra(graph: dict[int, list[tuple[int, float]]], source: int) -> dict[int, float]:

    dist: dict[int, float] = {source: 0.0}
    heap: list[tuple[float, int]] = [(0.0, source)]

    while heap:
        d_u, u = heapq.heappop(heap)

        # lazy deletion
        if d_u > dist.get(u, float("inf")):
            continue

        for v, w in graph.get(u, []):
            alt = d_u + w
            if alt < dist.get(v, float("inf")):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))

    return dist