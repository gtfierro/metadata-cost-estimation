This is a strawman cost model for estimating how much can be saved through adopting semantic metadata for automated configuratiion of rules/controls/other applications in smart buildings.

Leave feedback or make changes! We all need a better way of estimating the cost benefit of semantic metadata. In particular we need:
- data from real projects, contracts
- more applications and rules

To avoid you needing to run the code yourself (though you can, see below!) I am checking in different versions of the notebook in the `checkpoints/` folder:

- [2025-04-30](https://github.com/gtfierro/metadata-cost-estimation/blob/main/checkpoints/point_cost-2025-04-30.ipynb) (includes G36 4.1 and 4.2 point lists)
- [2025-04-29](https://github.com/gtfierro/metadata-cost-estimation/blob/main/checkpoints/point_cost-2025-04-29.ipynb) (uses FDD rules from G36 5.16)

## How to run

Install [uv](https://docs.astral.sh/uv/) to get started running this yourself.

Run the notebook with `uv run marimo edit point_costs.py`

### Adding new applications

There are 2 ways to add new applications. You can add FDD rules using a JSON encoding:

```json
{
    "G36AHU_FC2": {
        "name": "Guideline 36 - FC#2 - MAT too low; should be between OAT and RAT",
        "aftype": "analysis",
        "aftimerule": "Periodic",
        "frequency": 900,
        "applicability": [
            "Air_Handling_Unit"
        ],
        "definitions": {
            "Mixed_Air_Temperature": {
                "hasPoint": "Mixed_Air_Temperature_Sensor"
            },
            "Return_Air_Temperature": {
                "hasPoint": "Return_Air_Temperature_Sensor"
            },
            "Outside_Air_Temperature": {
                "hasPoint": "Outside_Air_Temperature_Sensor"
            }
        },
        "output": "IF ((Mixed_Air_Temperature - Mixed_Air_Temperature_Error_Threshold) < MAX((Return_Air_Temperature + Return_Air_Temperature_Error_Threshold), (Outside_Air_Temperature + Outside_Air_Temperature_Error_Threshold))) THEN True ELSE False"
    },
    # ... etc ...
}
```

The important parts here are the `applicability` and `definitions` fields. The applicability field is a list of Brick classes that the application applies to, and the definitions field is a mapping of Brick properties to points that are used in the application.

---

The other way is to supply a SHACL file that defines the shapes of the equipment required to run the applications. Here's an example:

```ttl
:VAVTerminalUnitCoolingOnlyShape a sh:NodeShape, owl:Class, rules:InferredRuleShape ;
    sh:targetClass brick:Variable_Air_Volume_Box, brick:VAV ;
    rdfs:label "VAV Terminal Unit - Cooling Only Shape" ;
    rdfs:comment "Validates VAV boxes have all required parts and points for cooling only operation" ;

    # Required: VAV box damper with actuator
    sh:property [
        sh:path brick:hasPart ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:name "VAV_Damper" ;
        sh:description "VAV box must have a damper" ;
        sh:node :DamperShape ;
    ] ;

    # Required: Discharge air flow measurement (differential pressure transducer)
    sh:property [
        sh:path brick:hasPoint ;
        sh:node brick:Air_Flow_Sensor ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:name "Discharge_Air_Flow_Sensor" ;
        sh:description "Required air flow sensor using differential pressure transducer" ;
    ] ;

    # Required: Zone temperature measurement
    sh:property [
        sh:path brick:hasPoint ;
        sh:node brick:Zone_Air_Temperature_Sensor ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:name "Zone_Temperature_Sensor" ;
        sh:description "Required zone temperature sensor" ;
    ] ;

    # etc.
```

Two things need to be true for this to work:
- values of `sh:name` must not have spaces (they need to be serialized as URIs)
- use `sh:node` to point to a Brick class or property, not `sh:class`. We currently need this so that buildingmotif correctly picks up on the dependencies on Brick / external classes.

## Files

- `point_costs.py`: Defines the cost model and generates sample costs for a provided Brick model and application file.
- `applicationsuite.py`: calculates the number of points per application per equipment for a provided Brick model and application file. Uses [BuildingMOTIF](https://github.com/NREL/BuildingMOTIF)
- `transform.py`: turns an application file into SHACL shapes
- `rules/`: contains JSON files of the applications (right now just FDD rules)

`bldg30.ttl` is from the Mortar dataset.
