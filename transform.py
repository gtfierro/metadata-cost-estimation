from rdflib import Namespace, Graph, Literal, URIRef, BNode
import logging
import sys
import json
from functools import reduce
import random
import string
from rdflib.collection import Collection
from rdflib import RDF, SH, BRICK, OWL
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def gensym():
    """generates random sparql variable name"""
    return "shape" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=4)
    )


def definition_to_sparql(self, classname, defn, variable):
    """
    defn is a JSON structure like this:
        "Chilled_Water_Valve_Command": {
            "choice": [
                {"hasPoint": "Chilled_Water_Valve_Command"},
                {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
            ]
        },
    This method turns this into a SPARQL query which retrieves values into a variable
    named whatever the top-level key is
    """
    query = f"""SELECT ?root ?{variable} WHERE {{ 
        ?root rdf:type {classname.n3()} .
        {self.sparql_recurse(defn, variable, hook="root")} 
    }}"""
    return query


def definition_to_shape(rulename: str, defn: Dict[str, Any], ns: Namespace) -> Graph:
    """
    Here's an example JSON rule:
        "SimultaneousHeatingAndCooling" : {
            "name" : "Simultaneous Heating and Cooling",
            "aftype" : "analysis",
            "aftimerule" : "Periodic",
            "frequency" : 900,
            "applicability" : ["AHU", "RTU", "RVAV"],
            "definitions": {
                "Chilled_Water_Valve_Command": {
                    "choice": [
                        {"hasPoint": "Chilled_Water_Valve_Command"},
                        {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
                    ]
                },
                "Hot_Water_Valve_Command": {
                    "choice": [
                        {"hasPoint": "Hot_Water_Valve_Command"},
                        {"hasPart": {"Hot_Water_Valve": {"hasPoint": "Valve_Command"}}}
                    ]
                }
            },
            "output" : "IF Chilled_Water_Valve_Command AND Hot_Water_Valve_Command THEN True ELSE False"
        },

    need to produce a shape like this:

    :Chilled_Water_Valve a sh:NodeShape ;
        sh:class brick:Chilled_Water_Valve ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:qualifiedValueShape [ sh:class brick:Valve_Command ]
            sh:qualifiedMinCount 1 ;
        ] ;
    .
    :Hot_Water_Valve a sh:NodeShape ;
        sh:class brick:Hot_Water_Valve ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:qualifiedValueShape [ sh:class brick:Valve_Command ]
            sh:qualifiedMinCount 1 ;
        ] ;
    .

    :SimultaneousHeatingAndCooling a sh:NodeShape ;
        sh:targetClass brick:AHU, brick:RTU, brick:RVAV ;
        sh:or (
            [ sh:name "Chilled_Water_Valve_Command" ; sh:path brick:hasPoint ; sh:qualifiedValueShape [ sh:class brick:Chilled_Water_Valve_Command ] ; sh:qualifiedMinCount 1 ],
            [ sh:name "Chilled_Water_Valve_Command" ; sh:path brick:hasPart ; sh:qualifiedValueShape [ sh:node :Chilled_Water_Valve ] ; sh:qualifiedMinCount 1 ],
        ) ;
        sh:or (
            [ sh:name "Hot_Water_Valve_Command" ; sh:path brick:hasPoint ; sh:qualifiedValueShape [ sh:class brick:Hot_Water_Valve_Command ] ; sh:qualifiedMinCount 1 ],
            [ sh:name "Hot_Water_Valve_Command" ; sh:path brick:hasPart ; sh:qualifiedValueShape [ sh:node :Hot_Water_Valve ] ; sh:qualifiedMinCount 1 ],
        ) ;
    .
    """
    shape = Graph()
    shapename = ns[rulename.replace(" ", "_")]
    shape.add((shapename, RDF["type"], SH["NodeShape"]))
    shape.add((shapename, RDF["type"], OWL["Class"]))
    shape.add((shapename, RDF["type"], ns["InferredRuleShape"]))
    for target in defn["applicability"]:
        shape.add((shapename, SH["targetClass"], BRICK[target]))

    for key, value in defn["definitions"].items():
        varname = ns[key]
        defn_to_shape(shapename, varname, value, shape, ns)

    return shape


def defn_to_shape(shapename, varname, defn, shape_graph, ns, path=None):
    varname = ns[gensym()]
    if isinstance(defn, str):
        return string_to_shape(shapename, shape_graph, varname, defn, path=path)
    elif isinstance(defn, dict):
        if "union" in defn:
            return union_to_shape(
                shapename, shape_graph, varname, defn.pop("union"), ns
            )
        # handle choice if it is present
        if "choice" in defn:
            return choice_to_shape(
                shapename, shape_graph, varname, defn.pop("choice"), ns
            )
        # treat the keys as properties
        for key, value in defn.items():
            propname = BRICK[key]
            prop_to_shape(shapename, shape_graph, varname, propname, value, ns)
    return varname


def string_to_shape(
    shapename: URIRef, shape_graph: Graph, varname: URIRef, string_value: str, path=None
):
    """
    Given a string value, create a SHACL shape that requires the sh:class to be that BRICK[string_value]
    """
    if shapename is not None:
        shape_graph.add((shapename, SH["property"], varname))
    shape_graph.add((varname, RDF["type"], SH["PropertyShape"]))
    if path is not None:
        shape_graph.add((varname, SH["path"], path))
    else:
        shape_graph.add((varname, SH["path"], BRICK["hasPoint"]))
    class_shape = BNode()
    shape_graph.add((varname, SH["qualifiedValueShape"], class_shape))
    shape_graph.add((class_shape, SH["class"], BRICK[string_value]))
    shape_graph.add((varname, SH["qualifiedMinCount"], Literal(1)))
    return varname


def union_to_shape(
    shapename: URIRef, shape_graph: Graph, varname: URIRef, union: Dict[str, Any], ns
):
    """
    "union": [
    "AFDD_rule_a",
    "AFDD_rule_b
    ]

    Given the options list, create a shape for each rule in the options list
    and add them to the shape graph. Then add to the shapename an sh:and that
    includes all the options.
    """
    and_list = []
    for option in union:
        oshape = defn_to_shape(None, varname, option, shape_graph, ns)
        and_list.append(oshape)

    and_list_name = BNode()
    Collection(shape_graph, and_list_name, and_list)
    shape_graph.add((shapename, SH["and"], and_list_name))

    return varname


def choice_to_shape(
    shapename: URIRef, shape_graph: Graph, varname: URIRef, choice: Dict[str, Any], ns
):
    """
    "choice": [
    {"hasPoint": "Chilled_Water_Valve_Command"},
    {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
    ]

    Given the choice list, create a shape for each option in the choice list
    and add them to the shape graph. Then add to the shapename an sh:or that
    includes all the options.
    """
    or_list = []
    for option in choice:
        oshape = defn_to_shape(None, varname, option, shape_graph, ns)
        or_list.append(oshape)

    or_list_name = BNode()
    Collection(shape_graph, or_list_name, or_list)
    shape_graph.add((shapename, SH["or"], or_list_name))

    return varname


def prop_to_shape(
    shapename: URIRef,
    shape_graph: Graph,
    varname: URIRef,
    propname: URIRef,
    value: Any,
    ns,
):
    """
    Given a property name and value, create a shape that requires the sh:path to be that propname
    and the sh:qualifiedValueShape to be the shape of the value
    """
    if isinstance(value, str):
        # treat like a property shape
        return string_to_shape(shapename, shape_graph, varname, value)

    possible_edges = [
        "hasPoint",
        "hasPart",
        "feeds",
        "hasLocation",
        "isPartOf",
        "isLocationOf",
        "isPointOf",
        "isFedBy",
    ]

    def _consume_edges(vdict, edge_stack):
        key, value = list(vdict.items())[0]
        edge_stack.append(BRICK[key])
        if isinstance(value, dict):
            # are there any edges?
            if any([key.startswith(edge) for edge in possible_edges]):
                return _consume_edges(value, edge_stack)
            # if no edges, then treat 'value' like a shape
            property_path = edge_list_to_property_path(edge_stack, shape_graph)
            return defn_to_shape(
                shapename, varname, value, shape_graph, ns, path=property_path
            )
        # if value is a string, treat it like a property
        property_path = edge_list_to_property_path(edge_stack, shape_graph)
        return string_to_shape(
            shapename, shape_graph, varname, value, path=property_path
        )

    # args are
    for key, vdict in value.items():
        # if the key is an edge, then we need to consume the edges
        if any([key.startswith(edge) for edge in possible_edges]):
            edge_stack = [propname]
            leftover = _consume_edges({key: vdict}, edge_stack)
        else:
            # if key is not an edge, then it is a class name
            property_path = propname

            if shapename is not None:
                shape_graph.add((shapename, SH["property"], varname))
            shape_graph.add((varname, RDF["type"], SH["PropertyShape"]))
            shape_graph.add((varname, SH["path"], property_path))

            # key is a 'class'
            qvs = BNode()
            shape_graph.add((varname, SH["qualifiedValueShape"], qvs))
            shape_graph.add((varname, SH["qualifiedMinCount"], Literal(1)))
            shape_graph.add((qvs, SH["class"], BRICK[key]))
            # the 'leftover' is a property shape on qvs
            leftover = defn_to_shape(shapename, varname, vdict, shape_graph, ns)
            shape_graph.add((qvs, SH["property"], leftover))


def edge_list_to_property_path(edge_list, shape_graph):
    """
    Given a list of edges, return a string that represents the path.
    The edges might end with '?' or '*' or '+'; in which case that needs to be stripped
    and turned into a ZeroOrOne, ZeroOrMore, or OneOrMore
    """
    property_path = BNode()
    edges = []
    for edge in edge_list:
        if edge.endswith("?"):
            edge = URIRef(edge[:-1])
            # make a [ sh:zeroOrOnePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["zeroOrOnePath"], edge))
            edges.append(edge_name)
        elif edge.endswith("*"):
            edge = URIRef(edge[:-1])
            # make a [ sh:zeroOrMorePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["zeroOrMorePath"], edge))
            edges.append(edge_name)
        elif edge.endswith("+"):
            edge = URIRef(edge[:-1])
            # make a [ sh:oneOrMorePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["oneOrMorePath"], edge))
            edges.append(edge_name)
        else:
            edges.append(edge)
    if len(edges) == 1:
        return edges[0]
    Collection(shape_graph, property_path, edges)
    return property_path


def main(rules, ns: Namespace, output_file=None, imports: Optional[list[str]] = None):
    shapes = []
    for rule, definition in rules.items():
        logger.info(f"Processing rule {rule} {definition} in ns {ns}")
        sg = definition_to_shape(rule, definition, ns)
        shapes.append(sg)
    shape_graph = reduce(lambda x, y: x + y, shapes)
    # add the imports and ontology declaration
    shape_graph.add((URIRef(ns), RDF["type"], OWL["Ontology"]))
    for import_uri in imports or []:
        shape_graph.add((URIRef(ns), OWL["imports"], URIRef(import_uri)))
    if output_file is not None:
        shape_graph.serialize(output_file, format="ttl")
    return shape_graph


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <rules_file> <output_file>")
        sys.exit(1)

    rules_file = sys.argv[1]
    output_file = sys.argv[2]
    rules = json.load(open(rules_file))
    ns = Namespace("http://example.org/building#")
    main(rules, ns, output_file)
