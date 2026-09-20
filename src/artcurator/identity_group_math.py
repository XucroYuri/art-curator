"""Pixel-vector retrieval only: this module never receives image paths or filenames."""
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .identity_group_schema import Calibration, Decision, GroupingError, Thresholds
from .identity_store import normalized


@dataclass(frozen=True, slots=True)
class ReferenceBank:
    vectors: NDArray[np.float32]
    labels: tuple[str, ...]
    crops: tuple[str, ...]


def similarities(query: NDArray[np.float32], bank: ReferenceBank) -> tuple[list[str], NDArray, NDArray]:
    names = sorted(set(bank.labels))
    centers = []
    individual = []
    supported = []
    values = normalized(bank.vectors)
    for name in names:
        members = values[np.array([label == name for label in bank.labels])]
        center = members.mean(axis=0)
        length = np.linalg.norm(center)
        if length <= 1e-12:
            continue
        supported.append(name)
        centers.append(float(np.clip(query @ (center / length), -1, 1)))
        individual.append(float(np.clip(np.max(members @ query), -1, 1)))
    return supported, np.array(centers), np.array(individual)


def decide(queries: NDArray, bank: ReferenceBank, gates: Thresholds) -> list[Decision]:
    """Require centroid and individual-anchor margins to support the same winner."""
    result = []
    for query in normalized(queries):
        names, scores, individuals = similarities(query, bank)
        if len(names) < 2:
            result.append(Decision())
            continue
        best = int(np.argmax(scores))
        centroid_margin = float(scores[best] - np.max(np.delete(scores, best)))
        individual_margin = float(individuals[best] - np.max(np.delete(individuals, best)))
        margin = min(centroid_margin, individual_margin)
        accepted = scores[best] >= gates.min_sim and margin >= gates.min_margin and margin > 0
        result.append(Decision(character=names[best] if accepted else None, sim=float(scores[best]),
                               margin=margin, centroid_margin=centroid_margin,
                               individual_margin=individual_margin))
    return result


def without_crop(bank: ReferenceBank, crop: str) -> ReferenceBank:
    indices = [i for i, item in enumerate(bank.crops) if item != crop]
    return ReferenceBank(bank.vectors[indices], tuple(bank.labels[i] for i in indices),
                         tuple(bank.crops[i] for i in indices))


def calibrate(bank: ReferenceBank) -> Calibration:
    """Predeclared reference-only quantiles; never tune on query assignment yield."""
    genuine, impostor, margins = [], [], []
    for vector, label, crop in zip(normalized(bank.vectors), bank.labels, bank.crops, strict=True):
        names, scores, individuals = similarities(vector, without_crop(bank, crop))
        if len(names) < 2 or label not in names:
            continue
        own = names.index(label)
        wrong = float(np.max(np.delete(scores, own)))
        stable = min(float(scores[own]) - wrong,
                     float(individuals[own] - np.max(np.delete(individuals, own))))
        genuine.append(float(scores[own]))
        impostor.append(wrong)
        margins.append(stable)
    positives = [value for value in margins if value > 0]
    if not positives or not impostor:
        raise GroupingError("reference-only calibration needs separable examples of at least two characters")
    return Calibration(samples=len(genuine), genuine=genuine, impostor=impostor, stable_margin=margins,
                       defaults=Thresholds(min_sim=float(np.quantile(impostor, .95)),
                                           min_margin=max(.005, float(np.quantile(positives, .1)))))
