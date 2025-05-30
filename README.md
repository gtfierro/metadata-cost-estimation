Install [uv](https://docs.astral.sh/uv/) to get started running this yourself.

Run the notebook with `uv run marimo edit point_costs.py`

## Files

- `point_costs.py`: Defines the cost model and generates sample costs for a provided Brick model and application file.
- `applicationsuite.py`: calculates the number of points per application per equipment for a provided Brick model and application file. Uses [BuildingMOTIF](https://github.com/NREL/BuildingMOTIF)
- `transform.py`: turns an application file into SHACL shapes
- `rules/`: contains JSON files of the applications (right now just FDD rules)

`bldg30.ttl` is from the Mortar dataset.
