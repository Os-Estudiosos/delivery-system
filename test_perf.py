import time
import osmnx as ox
import networkx as nx

g = ox.graph_from_place('Russas, Brazil', network_type='drive')
t0=time.time()
nodes = ox.distance.nearest_nodes(g, [-37.9725]*100, [-4.9416]*100)
print('nearest_nodes time for 100 queries:', time.time()-t0)

dists = nx.single_source_dijkstra_path_length(g, nodes[0], weight='length')
print('dijkstra time:', time.time()-t0)
