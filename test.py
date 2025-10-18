from SPARQLWrapper import SPARQLWrapper, JSON
import re
import pandas as pd
from tqdm import tqdm
from rdflib import Graph, URIRef, Literal, Namespace, RDF, RDFS, OWL

# -------------------------------
# 1. Setup SPARQL endpoints
# -------------------------------
DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
sparql_db = SPARQLWrapper(DBPEDIA_SPARQL)
sparql_db.setReturnFormat(JSON)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
sparql_wd = SPARQLWrapper(WIKIDATA_SPARQL)
sparql_wd.setReturnFormat(JSON)

# Namespaces
DCT = Namespace("http://purl.org/dc/terms/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
EX = Namespace("http://example.org/kg/")
DBR = Namespace("http://dbpedia.org/resource/")

# -------------------------------
# 2. Regex for category parsing
# -------------------------------
CATEGORY_REGEX = re.compile(r"http://dbpedia\.org/resource/Category:(.+?)_(in|of)_(.+)")

def parse_category_uri(category_uri):
    m = CATEGORY_REGEX.match(category_uri)
    if m:
        type_str = m.group(1).replace("_", " ")
        location_str = m.group(3).replace("_", " ")
        return type_str, location_str
    return None, None

# -------------------------------
# 3. Get visitor attraction categories
# -------------------------------
def get_visitor_attraction_categories(limit=50):
    query = f"""
    SELECT DISTINCT ?category WHERE {{
      ?category a skos:Concept .
      FILTER regex(str(?category), "^http://dbpedia.org/resource/Category:Tourist_attractions_in_")
    }} LIMIT {limit}
    """
    sparql_db.setQuery(query)
    results = sparql_db.query().convert()
    return [r['category']['value'] for r in results['results']['bindings']]

# -------------------------------
# 4. Get POIs for a category
# -------------------------------
def get_pois_for_category(category_uri):
    query = f"""
    SELECT DISTINCT ?POI ?category WHERE {{
      ?POI <http://purl.org/dc/terms/subject> ?category .
      ?category <http://www.w3.org/2004/02/skos/core#broader> <{category_uri}> .
    }}
    """
    sparql_db.setQuery(query)
    results = sparql_db.query().convert()
    pois = []
    for r in results['results']['bindings']:
        poi = r['POI']['value']
        cat = r['category']['value']
        pois.append((poi, cat))
    return pois

# -------------------------------
# 5. Get Wikidata mapping for POI
# -------------------------------
def get_wikidata_mapping(poi_uri):
    query = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?wikidata WHERE {{
      <{poi_uri}> owl:sameAs ?wikidata .
      FILTER(STRSTARTS(STR(?wikidata), "http://www.wikidata.org/entity/"))
    }}
    """
    sparql_db.setQuery(query)
    results = sparql_db.query().convert()
    return [r["wikidata"]["value"] for r in results["results"]["bindings"]]

# -------------------------------
# 6. Get Wikidata type hierarchy (P279 3-level)
# -------------------------------
def get_wikidata_type_hierarchy(wd_uri):
    query = f"""
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX bd: <http://www.bigdata.com/rdf#>

    SELECT DISTINCT ?super ?superLabel WHERE {{
      <{wd_uri}> (wdt:P279 | wdt:P279/wdt:P279 | wdt:P279/wdt:P279/wdt:P279) ?super .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    sparql_wd.setQuery(query)
    results = sparql_wd.query().convert()
    return [(r["super"]["value"], r["superLabel"]["value"]) for r in results["results"]["bindings"]]

# -------------------------------
# 7. Build RDF knowledge graph
# -------------------------------
def build_kg(df):
    g = Graph()
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Building KG"):
        poi_uri = URIRef(row["POI"])
        city_uri = URIRef(DBR[row["Location"].replace(" ", "_")])
        type_str = row["Type"]

        # POI triples
        g.add((poi_uri, RDF.type, EX.POI))
        g.add((poi_uri, EX.locatedIn, city_uri))
        g.add((poi_uri, EX.typeString, Literal(type_str)))

        # City triples
        g.add((city_uri, RDF.type, EX.City))

        # Wikidata mapping
        wd_links = get_wikidata_mapping(row["POI"])
        if wd_links:
            g.add((poi_uri, OWL.sameAs, URIRef(wd_links[0])))

            # Type hierarchy
            hierarchy = get_wikidata_type_hierarchy(wd_links[0])
            prev_type_uri = URIRef(EX[type_str.replace(" ", "_")])
            g.add((poi_uri, EX.hasType, prev_type_uri))
            g.add((prev_type_uri, RDF.type, EX.AttractionType))
            for super_uri, label in hierarchy:
                super_ref = URIRef(super_uri)
                g.add((prev_type_uri, RDFS.subClassOf, super_ref))
                prev_type_uri = super_ref

    return g

# -------------------------------
# 8. Main pipeline
# -------------------------------
all_records = []

categories = get_visitor_attraction_categories(limit=5)
print(f"Found {len(categories)} categories")

for cat_uri in tqdm(categories, desc="Processing categories"):
    pairs = get_pois_for_category(cat_uri)
    for poi_uri, category_uri in pairs:
        type_str, location_str = parse_category_uri(category_uri)
        if type_str and location_str:
            all_records.append({
                "POI": poi_uri,
                "Category": category_uri,
                "Type": type_str,
                "Location": location_str
            })

df = pd.DataFrame(all_records)
print(f"Total POIs extracted: {len(df)}")

# Build and serialize KG
kg = build_kg(df)
kg.serialize("tourist_kg.ttl", format="turtle")
print("Knowledge graph saved to tourist_kg.ttl")
