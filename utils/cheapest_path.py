from __future__ import annotations
import heapq

# Algoritmo de Dijkstra usando um min-heap (priority queue) para encontrar os caminhos mais baratos
# de todos os nós a partir de um nó fonte. Retorna um dicionário de distâncias mínimas 
# do nó fonte a cada nó alcançável.
# ADAPTADO PARA: MultiDiGraph do NetworkX / OSMnx
def dijkstra(graph, source: int) -> dict[int, float]:

    dist: dict[int, float] = {source: 0.0}
    heap: list[tuple[float, int]] = [(0.0, source)]
    
    # Prevenção: Se o nó de origem não existir no grafo, retorna apenas ele mesmo
    if source not in graph:
        return dist

    while heap:
        d_u, u = heapq.heappop(heap)

        # lazy deletion
        if d_u > dist.get(u, float("inf")):
            continue

        # CORREÇÃO: Iterando nos vizinhos usando as funções nativas do NetworkX
        for v in graph.neighbors(u):
            # Como é um MultiDiGraph, podem existir duas ruas diferentes ligando 'u' e 'v'.
            # Pegamos a menor distância ('length') entre todas as opções possíveis.
            w = min(edge_data.get('length', float('inf')) for edge_data in graph[u][v].values())
            
            alt = d_u + w
            if alt < dist.get(v, float("inf")):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))

    return dist