from __future__ import annotations

import heapq


# ---------------------------------------------------------------------------
# Dijkstra's algorithm
# ---------------------------------------------------------------------------

def dijkstra(graph: dict[int, list[tuple[int, float]]], source: int) -> dict[int, float]:
    """
    Single-source shortest paths using Dijkstra's algorithm with a min-heap.

    Parameters
    ----------
    graph  : adjacency list — dict[node, list[(neighbour, weight)]]
    source : starting node id

    Returns
    -------
    dict mapping each reachable node to its shortest distance from source.
    """
    dist: dict[int, float] = {source: 0.0}
    heap: list[tuple[float, int]] = [(0.0, source)]

    while heap:
        d_u, u = heapq.heappop(heap)

        # Skip stale heap entries (lazy deletion)
        if d_u > dist.get(u, float("inf")):
            continue

        for v, w in graph.get(u, []):
            alt = d_u + w
            if alt < dist.get(v, float("inf")):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))

    return dist