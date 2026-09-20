"""Population consensus, exact union-find families, and proposal-only tiers."""
import hashlib
import json
from collections import defaultdict
from typing import Final, assert_never

import numpy as np

from . import db
from .config import Settings
from .references import normalize

GROUPING_PROFILE_ID: Final = "phash6-or-phash10-cosine096-connected-v1"


def zscore(values: np.ndarray) -> np.ndarray:
    deviation = values.std(ddof=0)
    return (values - values.mean()) / deviation if deviation > 1e-12 else np.zeros_like(values)


def components(hashes: list[int], embeddings: np.ndarray) -> list[list[int]]:
    parent = list(range(len(hashes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(hashes)):
        for j in range(i):
            distance = (hashes[i] ^ hashes[j]).bit_count()
            if distance <= 6 or (distance <= 10 and float(embeddings[i] @ embeddings[j]) >= 0.96):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(hashes)):
        groups[find(i)].append(i)
    return list(groups.values())


def cluster(settings: Settings) -> None:
    rows = db.load_rows(settings.out)
    quality_signals: tuple[str, ...] = ("aes_v25", "topiq_iaa", "topiq_nr", "qrealign")
    match settings.quality_profile:
        case "five-means-v1":
            quality_signals += ("hpsv3_mu",)
        case "four-means-v1":
            pass
        case unreachable:
            assert_never(unreachable)
    required = quality_signals + (("hpsv3_sigma",) if "hpsv3_mu" in quality_signals else ())
    missing = [[name for name in (*required, "identity_sim", "nsfw_prob")
                if getattr(row, name) is None] for row in rows]
    quality_complete = not any(set(names).intersection(required) for names in missing)
    identity_complete = all(row.identity_sim is not None for row in rows)
    hps_means = [row.hpsv3_mu for row in rows if row.hpsv3_mu is not None]
    hps_scale = float(np.std(hps_means, ddof=0)) if hps_means else 0.0
    standardized: list[list[float]] = [[] for _ in rows]
    # Unknown completion bounds invalidate population statistics for the entire cohort.
    # Do not compute even a display-only surviving-scorer mean under this policy.
    for column in quality_signals if quality_complete else ():
        values = np.asarray([getattr(row, column) for row in rows], dtype=np.float64)
        if len(values):
            for i, value in enumerate(zscore(values)):
                standardized[i].append(float(value))
    consensus = zscore(np.asarray([np.mean(values) for values in standardized])) if rows and quality_complete else []
    for i, (row, scores) in enumerate(zip(rows, standardized, strict=True)):
        row.consensus_z = float(consensus[i]) if quality_complete else None
        row.disagreement = None
        if not quality_complete:
            continue
        native_variance = ((row.hpsv3_sigma / hps_scale) ** 2 / len(scores)
                           if "hpsv3_mu" in quality_signals and row.hpsv3_sigma is not None and hps_scale > 1e-12 else 0.0)
        row.disagreement = float(np.sqrt(np.var(scores, ddof=0) + native_variance))
    ids = json.loads((settings.out / "embeddings_ids.json").read_text(encoding="utf-8"))
    if ids != [r.sha16 for r in rows]:
        raise ValueError("Embedding row alignment mismatch; rerun score --pass siglip")
    matrix = normalize(np.load(settings.out / "embeddings.npy", allow_pickle=False))
    families = components([int(r.phash, 16) for r in rows], matrix)
    families.sort(key=lambda group: min(rows[i].sha256 for i in group))
    champions: dict[str, float] = {}
    family_json = []
    winner_indices: set[int] = set()
    for group in families:
        member_content_ids = sorted({rows[i].sha256 for i in group})
        canonical = json.dumps([GROUPING_PROFILE_ID, member_content_ids], ensure_ascii=True, separators=(",", ":"))
        family_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        ranked = sorted(group, key=lambda i: (-(rows[i].consensus_z or 0.0), rows[i].sha256))
        winner_indices.add(ranked[0])
        champions[family_id] = rows[ranked[0]].consensus_z or 0.0
        for i in group:
            rows[i].family_id = family_id
        family_json.append({"family_id": family_id, "members": [rows[i].sha16 for i in group],
                            "grouping_profile_id": GROUPING_PROFILE_ID,
                            "member_content_ids": member_content_ids,
                            "family_id_schema": "content-set-json-v1",
                            "champion": rows[ranked[0]].sha16 if quality_complete else None,
                            "runner_up": rows[ranked[1]].sha16 if quality_complete and len(ranked) > 1 else None})
    identities = [row.identity_sim for row in rows if row.identity_sim is not None]
    thresholds = {
        "identity_route": float(np.quantile(identities, settings.identity_route_quantile)) if identities and identity_complete else None,
        "identity_queue": float(np.quantile(identities, settings.identity_queue_quantile)) if identities and identity_complete else None,
        "queue": float(np.quantile(consensus, settings.queue_quantile)) if len(consensus) else None,
        "review": float(np.quantile(consensus, settings.review_quantile)) if len(consensus) else None,
    }
    for i, row in enumerate(rows):
        flags = [f"signal_unavailable:{name}" for name in missing[i]]
        if not quality_complete:
            flags.append("quality_population_unavailable")
        if not identity_complete:
            flags.append("identity_population_unavailable")
        if row.disagreement is not None and row.disagreement > settings.uncertain:
            flags.append("uncertain")
        if row.gaming_delta is not None and row.gaming_delta > settings.gaming_suspect:
            flags.append("gaming_suspect")
        if row.nsfw_prob is not None and row.nsfw_prob >= settings.nsfw_route:
            flags.append("nsfw")
        identity_low = (row.identity_sim is not None and thresholds["identity_route"] is not None
                        and row.identity_sim < thresholds["identity_route"]
                        and (row.confusable_margin is None or row.confusable_margin < settings.confusable_margin))
        if quality_complete and i not in winner_indices:
            flags.append("near_dup_runnerup")
        if "nsfw" in flags:
            row.proposed_tier = "route_nsfw"
        elif identity_low:
            row.proposed_tier = "route_identity"
            flags.append("id_low")
        elif (not flags and row.consensus_z is not None and thresholds["queue"] is not None
              and thresholds["identity_queue"] is not None and row.consensus_z >= thresholds["queue"]
              and row.nsfw_prob is not None and row.nsfw_prob < settings.nsfw_queue
              and row.identity_sim is not None and row.identity_sim >= thresholds["identity_queue"]
              and (i in winner_indices or champions[row.family_id] - row.consensus_z <= settings.champion_slack)):
            row.proposed_tier = "queue"
        elif not flags and row.consensus_z is not None and thresholds["review"] is not None and row.consensus_z < thresholds["review"]:
            row.proposed_tier = "archive_candidate"
            if int(row.sha16[:8], 16) % 20 == 0:
                flags.append("audit_sample")
                row.proposed_tier = "review"
        else:
            row.proposed_tier = "review"
        row.flags = "|".join(flags)
    db.save_rows(settings.out, rows)
    db.write_json(settings.out / "families.json", family_json)
    db.meta(settings.out, "thresholds", json.dumps(thresholds))
    db.meta(settings.out, "quality_policy", json.dumps({"version": "completion-abstain-v1",
            "profile": settings.quality_profile, "required_signals": required,
            "quality_population_complete": quality_complete}))
