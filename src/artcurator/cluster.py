"""Population consensus, exact union-find families, and proposal-only tiers."""
import json
from collections import defaultdict

import numpy as np

from . import db
from .config import Settings
from .references import normalize


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
    standardized: list[list[float]] = [[] for _ in rows]
    for column in ("aes_v25", "topiq_iaa", "topiq_nr", "qrealign"):
        indices = [i for i, row in enumerate(rows) if getattr(row, column) is not None]
        values = np.asarray([getattr(rows[i], column) for i in indices], dtype=np.float64)
        if len(values):
            for i, value in zip(indices, zscore(values), strict=True):
                standardized[i].append(float(value))
    if any(not values for values in standardized):
        raise ValueError("Cannot cluster without at least one quality score per image")
    consensus = zscore(np.asarray([np.mean(values) for values in standardized]))
    for row, value, scores in zip(rows, consensus, standardized, strict=True):
        row.consensus_z = float(value)
        row.disagreement = float(np.std(scores, ddof=0))
    ids = json.loads((settings.out / "embeddings_ids.json").read_text(encoding="utf-8"))
    if ids != [r.sha16 for r in rows]:
        raise ValueError("Embedding row alignment mismatch; rerun score --pass siglip")
    matrix = normalize(np.load(settings.out / "embeddings.npy", allow_pickle=False))
    families = components([int(r.phash, 16) for r in rows], matrix)
    families.sort(key=lambda group: min(rows[i].sha16 for i in group))
    champions: dict[str, float] = {}
    family_json = []
    winner_indices: set[int] = set()
    for number, group in enumerate(families, 1):
        family_id = f"fam_{number:04d}"
        ranked = sorted(group, key=lambda i: (-rows[i].consensus_z, rows[i].sha16))
        winner_indices.add(ranked[0])
        champions[family_id] = rows[ranked[0]].consensus_z
        for i in group:
            rows[i].family_id = family_id
        family_json.append({"family_id": family_id, "members": [rows[i].sha16 for i in group],
                            "champion": rows[ranked[0]].sha16,
                            "runner_up": rows[ranked[1]].sha16 if len(ranked) > 1 else None})
    identities = [row.identity_sim for row in rows if row.identity_sim is not None]
    if not identities:
        raise ValueError("Identity scoring must complete before proposing tiers")
    thresholds = {
        "identity_route": float(np.quantile(identities, settings.identity_route_quantile)),
        "identity_queue": float(np.quantile(identities, settings.identity_queue_quantile)),
        "queue": float(np.quantile(consensus, settings.queue_quantile)),
        "review": float(np.quantile(consensus, settings.review_quantile)),
    }
    for i, row in enumerate(rows):
        flags = []
        if row.disagreement > settings.uncertain:
            flags.append("uncertain")
        if row.gaming_delta is not None and row.gaming_delta > settings.gaming_suspect:
            flags.append("gaming_suspect")
        if row.nsfw_prob is not None and row.nsfw_prob >= settings.nsfw_route:
            flags.append("nsfw")
        identity_low = (row.identity_sim is not None and row.identity_sim < thresholds["identity_route"]
                        and (row.confusable_margin is None or row.confusable_margin < settings.confusable_margin))
        if i not in winner_indices:
            flags.append("near_dup_runnerup")
        if "nsfw" in flags:
            row.proposed_tier = "route_nsfw"
        elif identity_low:
            row.proposed_tier = "route_identity"
            flags.append("id_low")
        elif (row.consensus_z >= thresholds["queue"] and not flags
              and row.nsfw_prob is not None and row.nsfw_prob < settings.nsfw_queue
              and row.identity_sim is not None and row.identity_sim >= thresholds["identity_queue"]
              and (i in winner_indices or champions[row.family_id] - row.consensus_z <= settings.champion_slack)):
            row.proposed_tier = "queue"
        elif row.consensus_z < thresholds["review"] and not flags:
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
