from transform import main as json_to_shapes
from functools import cached_property, lru_cache
from itertools import product
from rdflib import Namespace
from buildingmotif import BuildingMOTIF
from buildingmotif.namespaces import BRICK
from buildingmotif.dataclasses import Library, ShapeCollection, Model
import json
import pandas as pd


class ApplicationSuite:
    """
    Given a rules file and a model file, this class computes the necessary
    metadata to understand the cost of implementing/configuring these rules.

    - **Set of applications ($A$)**: The set of all possible rules that would run on the building (used implicitly).
    - **Applications per equipment ($A_{c}$)**: The number of applications (e.g., FDD rules) for a given equipment class $c$.
    - **Points for an application ($P_{c,i}$)**: Number of distinct points required for application $i$ on equipment class $c$.
    - **Instances of equipment ($N_{c}$)**: The number of instances of a given equipment class $c$ in the building.
    - **Equipment Classes ($C$)**: The set of all unique equipment classes in the building (e.g., AHU, VAV, Chiller).
    - **Number of Equip Classes ($N_C$)**: The total number of unique equipment classes, i.e., $|C|$.
    """

    def __init__(self, rules_file: str, model_file: str):
        """
        Initialize the ApplicationSuite with the rules file and model file.

        :param rules_file: Path to the JSON rules file OR a SHACL shapes file.
        :param model_file: Path to the model file.
        """
        self.model_file = model_file
        self.bm = BuildingMOTIF("sqlite://", shacl_engine="topquadrant")
        self.brick = Library.load(
            ontology_graph="https://brickschema.org/schema/1.4/Brick.ttl",
            infer_templates=False,
            run_shacl_inference=False,
        )
        self.model = Model.from_file(model_file)

        self.sc = ShapeCollection.create()
        self.rules_file = rules_file

        if rules_file.endswith(".json"):
            self._handle_json_rules()
        elif rules_file.endswith(".ttl"):
            self._handle_shacl_rules()

        # generate templates for each of the shapes; this makes it possible
        # to analyze the requirements of the shapes in an easier manner
        self.lib = Library.create("my-library")
        self.sc.infer_templates(self.lib)

        # compile the model so we get all the inferred classes/etc
        self._compiled = self.model.compile(
            [self.brick.get_shape_collection(), self.sc]
        )

    def _handle_json_rules(self):
        RULES = Namespace("urn:rules/")
        rules = json.load(open(self.rules_file, "r"))
        shapes_graph = json_to_shapes(
            rules, RULES, imports=["https://brickschema.org/schema/1.4/Brick"]
        )
        self.sc.graph += shapes_graph

    def _handle_shacl_rules(self):
        """
        Handle SHACL rules file by loading it into the ShapeCollection.
        This method is not used in the current implementation but can be
        used if a SHACL rules file is provided instead of a JSON file.
        """
        # Load the SHACL rules file into the ShapeCollection
        self.sc.graph.parse(self.rules_file, format="turtle")

    @cached_property
    def app_brick_union_graph(self):
        """
        Returns the union graph of the compiled model and the Brick ontology.

        :return: Union graph of the compiled model and Brick ontology.
        """
        return (
            self._compiled.graph
            + self.brick.get_shape_collection().graph
            + self.sc.graph
        )

    @property
    def compiled(self):
        """
        Returns the compiled model.
        """
        return self._compiled

    @property
    def A(self):
        """
        Returns the set of applications (rules) in the model.
        They are shapes and instances o rules:InferredRuleShape
        """

        # find all shapes whose target class is a subclass of rules:InferredRuleShape
        query = """
            SELECT DISTINCT ?shape
            WHERE {
                ?shape a sh:NodeShape, <urn:rules/InferredRuleShape> .
            }
        """
        # execute the query
        results = self.app_brick_union_graph.query(query)
        return {row[0] for row in results}

    @property
    def C(self):
        """
        Returns the set of equipment classes in the building
        """
        # find all shapes whose target class is a subclass of brick:Equipment
        query = """
            SELECT DISTINCT ?eclass
            WHERE {
                ?inst rdf:type/rdfs:subClassOf* brick:Equipment .
                ?inst rdf:type ?eclass .
            }
        """
        # execute the query
        results = self.app_brick_union_graph.query(query)
        return {row[0] for row in results}

    @property
    def rule_equip_classes(self):
        """
        Returns the set of unique equipment classes for each rule.

        :return: Set of unique equipment classes for each rule.
        """
        # find all shapes whose target class is a subclass of brick:Equipment
        query = """
            SELECT DISTINCT ?target
            WHERE {
                ?shape sh:targetClass ?target .
                ?target rdfs:subClassOf* brick:Equipment .
            }
        """
        # execute the query
        results = self.app_brick_union_graph.query(query)
        return {row[0] for row in results}

    @lru_cache
    def applications_per_equipment(self, equip_class):
        """
        Returns the number of applications (rules) for a given equipment class.

        :param equip_class: The equipment class to query.
        :return: Number of applications for the given equipment class.
        """
        # find all shapes whose target class is the given equipment class
        # or a subclass of the given equipment class
        query = """
            SELECT ?shape
            WHERE {
                ?shape sh:targetClass ?target ;
                       rdf:type <urn:rules/InferredRuleShape> .
                ?equip_class rdfs:subClassOf* ?target .
            }
        """
        # execute the query
        results = self.app_brick_union_graph.query(
            query, initBindings={"equip_class": equip_class}
        )
        return [row[0] for row in results]

    @lru_cache
    def points_for_application(self, application: str) -> list[tuple[str, str]]:
        templates = self.lib.get_template_by_name(application).inline_dependencies()
        body = templates.body + self.brick.get_shape_collection().graph
        # find all of the parameters which are ?x rdf:type/rdf:subClassOf brick:Point
        # using a SPARQL query on the body + Brick ontology
        query = """
            SELECT ?param ?type
            WHERE {
                ?param a/rdfs:subClassOf* brick:Point .
                ?param a ?type .
            }
        """
        params = body.query(query)
        return [(row[0], row[1]) for row in params]

    @lru_cache
    def instances_of_equipment(self, equip_class):
        """
        Returns the number of instances of a given equipment class in the building.

        :param equip_class: The equipment class to query.
        :return: Number of instances of the given equipment class.
        """
        res = self.compiled.graph.query(
            """SELECT ?inst WHERE {
            ?inst rdf:type/rdfs:subClassOf* ?class
        }""",
            initBindings={"class": equip_class},
        )
        return set(res)

    # let's compute the sum using the equation above
    def compute_labor_time(self, T_build, T_point, T_config):
        time = T_build
        # for each unique class of equipment in the building
        for c in self.C:
            instances = self.instances_of_equipment(c)
            N_c = len(instances)
            # print(f"Equipment: {c=} with {N_c=} instances")
            for app in self.applications_per_equipment(c):
                points = self.points_for_application(app)
                # print(f'\t{app} has {len(points)} points')
                time += T_config + N_c * len(points) * T_point
        return time

    def compute_labor_time_df(self, T_builds, T_points, T_configs, C_rates):
        results = []
        # also including 20% overhead on cost + 10% profit margin
        for T_build, T_point, T_config, C_rate in product(
            T_builds, T_points, T_configs, C_rates
        ):
            time = self.compute_labor_time(T_build, T_point, T_config)
            results.append(
                {
                    "C_rate": C_rate,
                    "T_build": T_build,
                    "T_perpoint": T_point,
                    "time": time,
                    "cost": (time * C_rate / 3600)
                    * 1.3,  # convert to hours, add 30% overhead
                }
            )
        df = pd.DataFrame(results)
        return df

    def compute_point_cost(self, C_point):
        # for each unique class of equipment in the building
        cost = 0
        for c in self.C:
            instances = self.instances_of_equipment(c)
            N_c = len(instances)
            # print(f"Equipment: {c=} with {N_c=} instances")
            for app in self.applications_per_equipment(c):
                points = self.points_for_application(app)
                # print(f'\t{app} has {len(points)} points')
                cost += C_point * N_c * len(points)
        return cost

    def compute_point_cost_df(self, C_points):
        results = []
        for C_point in C_points:
            results.append(
                {"C_point": C_point, "cost": self.compute_point_cost(C_point)}
            )
        df = pd.DataFrame(results)
        return df
