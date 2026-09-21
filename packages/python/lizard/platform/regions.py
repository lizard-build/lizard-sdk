from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Region:
    id: str
    name: str | None = None
    label: str | None = None
    country: str | None = None
    city: str | None = None
    #: False for a region that exists but is not accepting new workloads.
    available: bool = True
    is_default: bool = False

    @classmethod
    def _from_dict(cls, d: dict) -> "Region":
        return cls(
            id=d["id"],
            name=d.get("name"),
            label=d.get("label"),
            country=d.get("country"),
            city=d.get("city"),
            available=bool(d.get("available", True)),
            is_default=bool(d.get("isDefault", False)),
        )


class RegionsAPI:
    """
    The regions workloads can be placed in.

    Region ids are what ``Sandbox.create(region=...)`` and
    ``Volume.create(region=...)`` take, so this is how you discover a valid value
    rather than hardcoding one::

        regions = lizard.regions.list()
        print([r.id for r in regions])  # ['eu-west-lim-a', 'us-east-1', ...]
    """

    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self) -> list[Region]:
        """List every region, including ones not currently accepting workloads."""
        return [Region._from_dict(r) for r in self._client.get("/api/regions")]
