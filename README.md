This is a strawman cost model for estimating how much can be saved through adopting semantic metadata for automated configuratiion of rules/controls/other applications in smart buildings.

Leave feedback or make changes! We all need a better way of estimating the cost benefit of semantic metadata. In particular we need:
- data from real projects, contracts
- more applications and rules

To avoid you needing to run the code yourself (though you can, see below!) I am checking in different versions of the notebook in the `checkpoints/` folder:

- [2025-04-29](https://github.com/gtfierro/metadata-cost-estimation/blob/main/checkpoints/point_cost-2025-04-29.ipynb)

## How to run

Install [uv](https://docs.astral.sh/uv/) to get started running this yourself.

Run the notebook with `uv run marimo edit point_costs.py`

## Files

- `point_costs.py`: Defines the cost model and generates sample costs for a provided Brick model and application file.
- `applicationsuite.py`: calculates the number of points per application per equipment for a provided Brick model and application file. Uses [BuildingMOTIF](https://github.com/NREL/BuildingMOTIF)
- `transform.py`: turns an application file into SHACL shapes
- `rules/`: contains JSON files of the applications (right now just FDD rules)

`bldg30.ttl` is from the Mortar dataset.
