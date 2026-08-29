"""Build the plate hierarchy (rotation tree) from a parsed rotation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .parser import RotationModel

ANCHOR = 0  # spin axis / mantle anchor by GPlates convention


@dataclass
class PlateNode:
    plate_id: int
    name: str = ""
    children: list["PlateNode"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def n_leaves(self) -> int:
        if not self.children:
            return 1
        return sum(c.n_leaves for c in self.children)

    @property
    def depth(self) -> int:
        if not self.children:
            return 0
        return 1 + max(c.depth for c in self.children)


def build_tree(
    model: RotationModel,
    time: float = 0.0,
    include_disabled: bool = False,
    anchor: int = ANCHOR,
) -> PlateNode:
    """Rotation tree at ``time`` Ma, rooted at ``anchor``.

    Every moving plate defined at ``time`` hangs from its fixed plate.
    Plates whose parent chain does not reach ``anchor`` are attached to a
    synthetic ``orphans`` branch so nothing silently disappears.
    """
    names = model.plate_names()
    parent: dict[int, int] = {}
    for plate in model.moving_plates:
        if plate == 999 and not include_disabled:
            continue
        p = model.parent_of(plate, time)
        if p is not None and p != plate:
            parent[plate] = p

    nodes: dict[int, PlateNode] = {}

    def node(pid: int) -> PlateNode:
        if pid not in nodes:
            nodes[pid] = PlateNode(plate_id=pid, name=names.get(pid, ""))
        return nodes[pid]

    root = node(anchor)
    orphans: list[PlateNode] = []
    for plate, fixed in sorted(parent.items()):
        # ensure the fixed plate exists as a node even if it never moves
        child, parent_node = node(plate), node(fixed)
        parent_node.children.append(child)

    # find nodes not connected to the root
    connected = {n.plate_id for n in root.walk()}
    for pid, n in sorted(nodes.items()):
        if pid not in connected:
            top = n
            seen = {pid}
            while True:
                holder = next(
                    (m for m in nodes.values() if top in m.children), None
                )
                if holder is None or holder.plate_id in seen:
                    break
                seen.add(holder.plate_id)
                top = holder
            if top.plate_id not in connected and all(
                top is not o for o in orphans
            ):
                orphans.append(top)
    if orphans:
        orphan_branch = PlateNode(
            plate_id=-1,
            name="orphans (undefined at this age or no path to anchor)",
        )
        # deduplicate: only keep subtree tops
        tops = []
        for o in orphans:
            if not any(o in other.walk() and other is not o for other in orphans):
                tops.append(o)
        orphan_branch.children = tops
        root.children.append(orphan_branch)

    for n in nodes.values():
        n.children.sort(key=lambda c: (c.plate_id < 0, c.plate_id))
    return root


def all_crossovers(model: RotationModel) -> list[tuple[int, float, int, int]]:
    """(moving_plate, time, old_fixed, new_fixed) across the whole model."""
    out: list[tuple[int, float, int, int]] = []
    for plate in model.moving_plates:
        for time, old, new in model.crossovers(plate):
            out.append((plate, time, old, new))
    return sorted(out, key=lambda item: (item[1], item[0]))
