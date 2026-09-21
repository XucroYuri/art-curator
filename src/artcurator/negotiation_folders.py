"""Seeded distinct-image folder measurements, including unresolved denominators."""
import random
from collections import Counter
from typing import Final

from .identity_store import digest
from .ingest_schema import Frozen
from .negotiation_metrics import Coherence, HumanLabel, ImageEvidence, Labels, Proportion, coherence, proportion
from .negotiation_regimes import Features, Regimes, detect

SEED: Final = 20260921


class FolderPopulation(Frozen):
    folder_id: str
    path: str
    images: tuple[ImageEvidence, ...]
    occurrences: int
    unavailable_occurrences: int = 0


class FolderReport(Frozen):
    folder_id: str
    path: str
    population_ids: tuple[str, ...]
    population_digest: str
    sample_ids: tuple[str, ...]
    sample_digest: str
    seed: int
    design: str = "seeded simple random sampling without replacement, sorted full hashes, up to 100"
    population: int
    sample: int
    occurrences: int
    duplicates: int
    unavailable_occurrences: int
    coverage: float | None
    vector_profile: str | None
    representation: str
    coherence: Coherence
    purity: Proportion
    purity_identity: str | None
    independent_labels: int
    unresolved_labels: int
    target: str | None
    target_purity: Proportion
    weak_agreement: Proportion
    unresolved_proxy_D: Proportion
    unknown_U: Proportion
    conflict_C: Proportion
    model_coverage: float | None
    artist_agreement: Proportion
    regimes: Regimes
    coherence_admitted: bool
    identity_prior_admitted: bool
    identity_recommendation: bool
    context_enabled: bool = False
    manual_collection_available: bool = True
    thresholds: str = "ADR: valid>=30, Vmedian>=0.90, p10>=0.80; identity labels>=30 and lower>=0.90"
    limitations: tuple[str, ...]


def measure(population: FolderPopulation, labels: Labels) -> FolderReport:
    """Measurements never use path text as features; targets are explicit declarations."""
    unique = {i.image_id: i for i in population.images}
    ids = tuple(sorted(unique))
    sample_ids = tuple(sorted(random.Random(SEED).sample(ids, min(100, len(ids)))))
    sampled = [unique[key] for key in sample_ids]
    n, total = len(sampled), len(ids)
    profiles = {i.profile for i in sampled if i.vector is not None}
    representations = {i.representation for i in sampled if i.vector is not None}
    compatible = len(profiles) == len(representations) == 1 and None not in profiles
    stats = coherence(tuple(i.vector if compatible else None for i in sampled))
    representation = next(iter(representations)) if compatible else "unavailable"
    independent = {label.image_id: label for label in labels.labels if label.independent}
    selected: list[HumanLabel] = [independent[key] for key in sample_ids if key in independent]
    identities = Counter(label.identity for label in selected if label.identity)
    largest = identities.most_common(1)
    purity = proportion(largest[0][1] if largest else None, n, total)
    target = labels.targets.get(population.folder_id)
    target_purity = proportion(identities.get(target, 0) if target and identities else None, n, total)
    artists = Counter(label.artist for label in selected if label.artist)
    artist = proportion(max(artists.values()) if artists else None, n, total)
    known = [i for i in sampled if i.candidates is not None]
    # Partial model coverage is descriptive on observed rows, not a population estimate.
    unknown = proportion(sum(not i.candidates for i in known) if known else None, len(known), len(known))
    conflicts = [i for i in sampled if i.conflict is not None]
    conflict = proportion(sum(i.conflict is True for i in conflicts) if conflicts else None,
                          len(conflicts), len(conflicts))
    applicable = target is not None and labels.target_types.get(population.folder_id) in {"character", "work"}
    agreement = proportion(sum(target in (i.candidates or ()) for i in known)
                           if applicable and len(known) == n else None, n, total)
    unresolved = proportion(sum(len(i.candidates or ()) != 1 or target not in (i.candidates or ()) for i in known)
                            if applicable and len(known) == n else None, n, total)
    detected = [i for i in sampled if i.face_clusters is not None]
    faces = [c for i in detected for c in (i.face_clusters or ())]
    counts = Counter(c for c in faces if c is not None)
    supported = Counter(c for i in detected for c in set(i.face_clusters or ()) if c is not None)
    # Q must describe all sampled images, not an observed-only estimate when detections are missing.
    q = sum(len(i.face_clusters or ()) != 1 for i in detected) / n if n and len(detected) == n else None
    features = Features(valid_images=stats.valid, eligible_faces=len(faces),
        V=stats.median if representation == "whole-image" else None,
        F=max(counts.values(), default=0) / len(faces) if faces else None,
        K=sum(count >= 3 for count in supported.values()) if len(detected) == n and n else None,
        Q=q, A=artist.value, artist_labels=sum(artists.values()),
        entities=len({label.entity for label in selected if label.artist and label.entity}))
    admitted = (stats.valid >= 30 and stats.median is not None and stats.median >= .90
                and stats.p10 is not None and stats.p10 >= .80
                and sum(s is not None for s in stats.scores) == stats.valid)
    lower = target_purity.interval[0] if target_purity.interval else target_purity.value
    identity_admitted = bool(admitted and sum(identities.values()) >= 30 and lower is not None and lower >= .90)
    # NEGOTIATE recommendation intentionally stricter than census ADR admission: Wilson lower always.
    recommendation_lower = proportion(largest[0][1], n, max(total, n+1)).interval if largest else None
    recommended = bool(admitted and features.V is not None and features.V >= .90
                       and sum(identities.values()) >= 30 and recommendation_lower
                       and recommendation_lower[0] >= .90)
    return FolderReport(folder_id=population.folder_id, path=population.path,
        population_ids=ids, population_digest=digest("\n".join(ids).encode()),
        sample_ids=sample_ids, sample_digest=digest("\n".join(sample_ids).encode()), seed=SEED,
        population=total, sample=n, occurrences=population.occurrences,
        duplicates=max(0, population.occurrences-population.unavailable_occurrences-total),
        unavailable_occurrences=population.unavailable_occurrences, coverage=n/total if total else None,
        vector_profile=next(iter(profiles)) if compatible else None, representation=representation,
        coherence=stats, purity=purity, purity_identity=largest[0][0] if largest else None,
        independent_labels=sum(identities.values()), unresolved_labels=n-sum(identities.values()),
        target=target, target_purity=target_purity, weak_agreement=agreement, unresolved_proxy_D=unresolved,
        unknown_U=unknown, conflict_C=conflict, model_coverage=len(known)/n if n else None,
        artist_agreement=artist, regimes=detect(features), coherence_admitted=admitted,
        identity_prior_admitted=identity_admitted, identity_recommendation=recommended,
        limitations=("Labels must be independently human supplied; attestations are not externally audited.",
                     "Exact duplicates removed; near-duplicate dependence is unestablished.",
                     "No whole-image vector means V-dependent regimes unavailable; crop coherence is not V.",
                     "No-face is detector missingness, not non-character truth.",
                     "Missing target/vocabulary coverage means D and weak agreement unavailable.",
                     "Measured admission is not contextual-use authorization; G2 enables no grouping."))
