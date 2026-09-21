"""Enumerated anchor evidence; human choices remain independent of suggestions."""
import csv
import io
from pathlib import Path
from typing import Literal, Self

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from .identity_group_math import ReferenceBank, similarities
from .identity_group_schema import GroupingError, GroupProvenance, Thresholds
from .identity_schema import FaceId, Record, ShortHash
from .identity_store import atomic_bytes, normalized


class Candidate(Record):
    character: str = Field(min_length=1)
    score: float = Field(ge=-1, le=1)
    margin_vs_runner_up: float | None = Field(ge=-2, le=2)
    source: Literal["anchor", "cluster"]


class FaceCandidates(Record):
    face_id: FaceId
    image_sha16: ShortHash
    candidates: list[Candidate] = Field(max_length=5)
    suggested: str | None
    abstained: bool

    @model_validator(mode="after")
    def consistent_ranking(self) -> Self:
        names = [candidate.character for candidate in self.candidates]
        if len(names) != len(set(names)) or self.candidates != sorted(
            self.candidates, key=lambda candidate: (-candidate.score, candidate.character)
        ):
            raise GroupingError("candidate ranking must be unique and ordered")
        if self.abstained != (self.suggested is None):
            raise GroupingError("candidate abstention and suggestion disagree")
        if self.suggested is not None and (not names or self.suggested != names[0]):
            raise GroupingError("suggested character must be top ranked")
        return self


class CandidateDocument(Record):
    version: Literal[1] = 1
    provenance: GroupProvenance
    thresholds: Thresholds
    faces: list[FaceCandidates]


def rank_candidates(query: NDArray[np.float32], bank: ReferenceBank) -> list[Candidate]:
    """Score all supported references; expose strongest-other gaps, not gate margins."""
    names, scores, _ = similarities(normalized(query[None])[0], bank)
    order = sorted(range(len(names)), key=lambda index: (-scores[index], names[index]))
    return [Candidate(character=names[index], score=float(scores[index]),
        margin_vs_runner_up=float(scores[index] - np.max(np.delete(scores, index))) if len(names) > 1 else None,
        source="anchor") for index in order[:5]]


def write_candidates_csv(path: Path, document: CandidateDocument) -> None:
    """Non-authoritative spreadsheet view of the JSON candidate contract."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("face_id", "image_sha16", "suggested", "abstained", "rank",
                     "character", "score", "margin_vs_runner_up", "source"))
    for face in document.faces:
        if not face.candidates:
            writer.writerow((face.face_id, face.image_sha16, face.suggested, face.abstained,
                             "", "", "", "", ""))
            continue
        for rank, candidate in enumerate(face.candidates, 1):
            writer.writerow((face.face_id, face.image_sha16, face.suggested, face.abstained, rank,
                             candidate.character, candidate.score, candidate.margin_vs_runner_up,
                             candidate.source))
    atomic_bytes(path, buffer.getvalue().encode("utf-8"))
