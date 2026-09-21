"""Read-only saved-vector adapter and representative-wall data, without UI."""
from pathlib import Path

from .album_map_discovery import DiscoveryInput, VectorMember
from .album_map_exchange import Manifest
from .album_map_schema import Identifier, MappingError, Model
from .identity_schema import IdentityOptions
from .identity_store import load_document, load_provenance, load_vectors
from .negotiation_clusters import representative_indices


class SavedVectors(Model):
    directory: Path
    manifest: Manifest
    options: IdentityOptions


class Wall(Model):
    members: tuple[VectorMember, ...]
    representatives: tuple[Identifier, ...] = ()
    confirmation_scope: str = "selected-members-only-not-representative-sample"


def saved_vectors(request: SavedVectors) -> DiscoveryInput:
    """Reuse the payload/order/profile verifier; never infer full hashes from aliases."""
    document = load_document(request.directory)
    provenance = load_provenance(request.directory)
    values = load_vectors(request.directory, document)
    faces = {face.face_id: (index, face) for index, face in enumerate(document.faces)}
    members = []
    for member in request.manifest.members:
        entry = faces.get(member.legacy_id)
        if entry is None:
            members.append(VectorMember(**member.model_dump(), vector=None))
            continue
        index, face = entry
        if (provenance.contents.get(face.image_sha16) != member.image_id
                or provenance.crops.get(face.face_id) != member.crop_id
                or provenance.semantic_profile != member.profile):
            raise MappingError("saved-vector-manifest-binding")
        members.append(VectorMember(**member.model_dump(), vector=tuple(float(v) for v in values[index])))
    return DiscoveryInput(profile=provenance.semantic_profile, options=request.options, vectors=tuple(members))


def representative_wall(request: Wall) -> Wall:
    """One crop per distinct image, stable full-content tie breaks and at most twelve."""
    ordered = sorted(request.members, key=lambda m: (m.image_id, m.subject_id, m.crop_id))
    unique = {m.image_id: m for m in reversed(ordered)}
    ids = tuple(sorted(unique))
    if not ids:
        return request.model_copy(update={"representatives": ()})
    selected = representative_indices(ids, tuple(unique[key].vector for key in ids))
    return request.model_copy(update={"representatives": tuple(unique[ids[i]].legacy_id for i in selected)})
