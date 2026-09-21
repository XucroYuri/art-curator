"""Typed member commands shared by journal translation and cluster planning."""
from typing import Literal

from pydantic import Field

from .album_map_schema import ClusterMembership, Disposition, EntityType, Identifier, Model


class Entity(Model):
    entity_id: Identifier
    entity_type: EntityType
    name: Identifier


class Command(Model):
    action: Literal["set_disposition", "confirm_relation", "cluster_membership"]
    members: tuple[Identifier, ...] = Field(min_length=1)
    scope: Literal["image", "subject"] = "subject"
    disposition: Disposition = "assigned"
    entity: Entity | None = None
    notes: str | None = None
    role: Literal["depicts", "baseline", "variant"] = "depicts"
    cluster_membership: ClusterMembership | None = None
    confirmation_basis: Literal["individual-inspection", "cluster-selected-members"] = "individual-inspection"
