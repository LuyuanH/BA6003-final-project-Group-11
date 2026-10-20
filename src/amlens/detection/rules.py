"""Read the detection ruleset from the package."""

import json
from importlib.resources import files

FAMILIES = (
    "FAN-IN",
    "FAN-OUT",
    "CYCLE",
    "GATHER-SCATTER",
    "SCATTER-GATHER",
    "BIPARTITE",
    "STACK",
    "RANDOM",
)


def load_ruleset() -> dict:
    """Return a new copy. Changes to this copy do not affect later calls."""
    return json.loads(
        files(__package__).joinpath("frozen_ruleset.json").read_text(encoding="utf-8")
    )
