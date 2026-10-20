"""Find scatter-gather structures with two or more different intermediate accounts."""

from collections.abc import Callable


def detect_scatter_gather(pairs: list[tuple[dict, dict]], emit: Callable) -> None:
    if 2 <= len({first["dst"] for first, _ in pairs}) and len(pairs) <= 32:
        emit("SCATTER-GATHER", [edge for pair in pairs for edge in pair])
