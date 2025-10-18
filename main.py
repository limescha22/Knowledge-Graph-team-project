# --- Imports ---
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, OWL, XSD
from SPARQLWrapper import SPARQLWrapper, JSON

# --- SPARQL Endpoints ---
DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

db_sparql = SPARQLWrapper(DBPEDIA_SPARQL)
db_sparql.setReturnFormat(JSON)

wd_sparql = SPARQLWrapper(WIKIDATA_SPARQL)
wd_sparql.setReturnFormat(JSON)

# =====================================================
# STEP 1: Build DBpedia URI
# =====================================================
def to_dbpedia_uri(location_string):
    clean = location_string.strip().replace(" ", "_")
    return f"http://dbpedia.org/resource/{clean}"

# =====================================================
# STEP 2: Resolve Redirects
# =====================================================
def resolve_redirect(uri):
    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    SELECT ?target WHERE {{
      <{uri}> dbo:wikiPageRedirects ?target .
    }}
    """
    db_sparql.setQuery(query)
    results = db_sparql.query().convert()
    bindings = results["results"]["bindings"]
    return bindings[0]["target"]["value"] if bindings else uri

# =====================================================
# STEP 3: Get owl:sameAs links
# =====================================================
def get_sameas_links(dbpedia_uri):
    query = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?same WHERE {{
      <{dbpedia_uri}> owl:sameAs ?same .
    }}
    """
    db_sparql.setQuery(query)
    results = db_sparql.query().convert()
    return [b["same"]["value"] for b in results["results"]["bindings"]]



# =====================================================
# STEP 4: Check if Wikidata entity is a city
# =====================================================
def is_city_wikidata(wd_uri):
    query = f"""
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wd: <http://www.wikidata.org/entity/>
    ASK {{
      <{wd_uri}> (wdt:P31/wdt:P279*) wd:Q515 .
    }}
    """
    wd_sparql.setQuery(query)
    return wd_sparql.query().convert()["boolean"]

# =====================================================
# STEP 5: Combine steps for one location
# =====================================================
def link_poi_to_city(location_string):
    db_uri = to_dbpedia_uri(location_string)
    resolved = resolve_redirect(db_uri)
    links = get_sameas_links(resolved)

    wd_links = [l for l in links if "wikidata.org/entity" in l]
    # print(wd_links)
    geo_links = [l for l in links if "geonames.org" in l]
    # print(geo_links)

    is_city = False
    verified_wd_uri = None

    # Go through every wd_links entry until a Wikidata city is found
    for wd_uri in wd_links:
        if is_city_wikidata(wd_uri):
            is_city = True
            verified_wd_uri = wd_uri
            break  # stop at the first verified city

    # If no city found, is_city remains False and we continue

    verified_geo_uri = None
    if geo_links:
        # Choose the GeoNames URI that is not equal to verified_wd_uri
        for geo_uri in geo_links:
            if geo_uri != verified_wd_uri:
                verified_geo_uri = geo_uri
                break



    return {
        "location_string": location_string,
        "dbpedia_uri": resolved,
        "wikidata_uri": verified_wd_uri,
        "geonames_uri": verified_geo_uri,
        "is_city": is_city
    }

# =====================================================
# STEP 6: Create RDF triples
# =====================================================
def create_poi_city_triples(poi_uri, type_string, location_info):
    g = Graph()

    EX = Namespace("http://example.org/ontology/")
    DBR = Namespace("http://dbpedia.org/resource/")
    WD = Namespace("http://www.wikidata.org/entity/")
    GEO = Namespace("http://sws.geonames.org/")
    
    poi = URIRef(poi_uri)
    city = URIRef(location_info["dbpedia_uri"])

    # POI triples
    g.add((poi, RDF.type, EX[type_string]))
    g.add((poi, EX.locatedIn, city))
    g.add((poi, EX.typeString, Literal(type_string)))
    g.add((poi, EX.locationString, Literal(location_info["location_string"])))

    # City triples
    g.add((city, RDF.type, EX.City))
    if location_info.get("wikidata_uri"):
        g.add((city, OWL.sameAs, URIRef(location_info["wikidata_uri"])))
    if location_info.get("geonames_uri"):
        g.add((city, OWL.sameAs, URIRef(location_info["geonames_uri"])))
    g.add((city, EX.isVerifiedCity, Literal(location_info["is_city"], datatype=XSD.boolean)))

    return g

# =====================================================
# STEP 7: Run for 3 example locations
# =====================================================
locations = ["Barcelona", "Madrid", "Valencia"]

graphs = []
for loc in locations:
    info = link_poi_to_city(loc)
    g = create_poi_city_triples(f"http://dbpedia.org/resource/POI_in_{loc}", "Attraction", info)
    graphs.append(g)

# Merge and print
final_graph = Graph()
for g in graphs:
    final_graph += g

print(final_graph.serialize(format="turtle"))


import networkx as nx
import matplotlib.pyplot as plt
from rdflib import URIRef

def rdf_to_networkx(graph):
    G = nx.DiGraph()  # Directed graph
    for s, p, o in graph:
        # Only include URI nodes for clarity
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            G.add_edge(s, o, label=p.split('#')[-1] if '#' in p else str(p).split('/')[-1])
    return G

# Example: convert your final_graph from previous steps
G = rdf_to_networkx(final_graph)

plt.figure(figsize=(12,8))
pos = nx.spring_layout(G, k=0.5)  # Force-directed layout
nx.draw(G, pos, with_labels=True, node_size=1500, node_color="lightblue", font_size=10, arrows=True)
edge_labels = nx.get_edge_attributes(G, 'label')
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='red')
plt.title("POI → City Knowledge Graph")
plt.show()


node_colors = []
for node in G.nodes():
    if "POI_in" in str(node):
        node_colors.append("orange")
    else:
        node_colors.append("lightgreen")

nx.draw(G, pos, with_labels=True, node_color=node_colors, node_size=1500, arrows=True)



# from pyvis.network import Network

# net = Network(height='600px', width='100%', directed=True)

# for node in set([n for n in G.nodes()]):
#     net.add_node(str(node), label=str(node).split('/')[-1], title=str(node))

# for u, v, data in G.edges(data=True):
#     net.add_edge(str(u), str(v), title=data.get('label',''))

# net.show("poi_city_graph.html")


