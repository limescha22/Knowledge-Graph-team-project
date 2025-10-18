import networkx as nx
import matplotlib.pyplot as plt
from rdflib import Graph

# Load the knowledge graph you created earlier
g = Graph()
g.parse("tourist_kg.ttl", format="turtle")

# Convert RDFLib graph to NetworkX
G = nx.DiGraph()
for s, p, o in g:
    G.add_edge(str(s), str(o), predicate=str(p))

# --- Helper function to simplify labels ---
def short_label(uri):
    """Return a human-readable version of an RDF URI or literal."""
    if uri.startswith("http://dbpedia.org/resource/Category:"):
        return uri.split("Category:")[-1].replace("_", " ")
    elif uri.startswith("http://dbpedia.org/resource/"):
        return uri.split("resource/")[-1].replace("_", " ")
    elif uri.startswith("http://www.wikidata.org/entity/"):
        return uri.split("/")[-1]  # keep QID
    elif uri.startswith("http://example.org/kg/"):
        return uri.split("/")[-1]
    elif "http" not in uri:
        return uri
    else:
        return uri.split("/")[-1]

# Apply label simplification
labels = {node: short_label(node) for node in G.nodes()}

# --- Filter only one city and its connected nodes ---
# You can pick any city in your graph:
city_name = "Barcelona"  # change as needed
city_uri = f"http://dbpedia.org/resource/{city_name}"
neighbors = list(G.neighbors(city_uri)) + [city_uri]
subG = G.subgraph(neighbors)

# --- Plot ---
plt.figure(figsize=(10, 8))
pos = nx.spring_layout(subG, k=0.6, iterations=40)
nx.draw_networkx_nodes(subG, pos, node_color="lightblue", node_size=900)
nx.draw_networkx_edges(subG, pos, arrows=True, alpha=0.5)
nx.draw_networkx_labels(subG, pos, labels=labels, font_size=9)
plt.title(f"Knowledge Graph for Tourist Attractions in {city_name}")
plt.axis("off")
plt.show()
