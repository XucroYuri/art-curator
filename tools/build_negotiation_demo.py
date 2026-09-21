# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow"]
# ///
# Run: uv run tools/build_negotiation_demo.py
"""Generate analytic UI evidence, not a real-corpus measurement or consent receipt."""
import copy
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> None:
    """Derive copy from the frozen fixture, never maintain a second set of literals."""
    root = Path(__file__).resolve().parents[1]
    output = root / "tests/fixtures/gallery"
    report = json.loads((root / "tests/fixtures/negotiation-report.example.json").read_text(encoding="utf-8"))
    templates = report["presentation"]["templates"]
    report["limitations"].insert(0, "SYNTHETIC-UI-FIXTURE: analytic values, not measured model performance; never apply")
    base = copy.deepcopy(report["folders"][1])
    report["folders"] = []
    report["members"] = []
    report["presentation"]["folder_text"] = {}
    report["labels"] = {"labels": [], "targets": {}, "target_types": {}}
    regimes = [
        ("session-set", "同场景长目录名称／角色尚未核实", .94, .9, 1, .1, None),
        ("mixed-pile", "混合素材／不同角色与背景", .7, .4, 4, .2, None),
        ("scenario/documentary", "场景记录／不推断无人物", .87, .6, 2, .7, None),
        ("artist-portfolio", "作者作品集／人工作者标签", .7, .6, 2, .2, .9),
    ]
    for index, (regime, path, coherence, face_share, clusters, multi, artist) in enumerate(regimes):
        folder = copy.deepcopy(base)
        folder_id = digest(path)
        images = [digest(f"synthetic-{index}-{n}") for n in range(40)]
        folder.update(folder_id=folder_id, path=path, population_ids=images, sample_ids=images,
                      population_digest=digest("".join(images)), sample_digest=digest("".join(images)),
                      population=40, sample=40, occurrences=40, duplicates=0, coverage=1,
                      representation="synthetic-whole-image", vector_profile="analytic-ui-fixture-v1",
                      purity_identity=None, independent_labels=0, unresolved_labels=40, target=None,
                      model_coverage=None, identity_prior_admitted=False, coherence_admitted=index == 0)
        folder["coherence"].update(denominator=40, valid=40, missing=0, median=coherence,
                                   p10=round(coherence - .04, 2), scores=[coherence] * 40)
        for key in ("purity", "target_purity", "weak_agreement", "unresolved_proxy_D", "unknown_U", "conflict_C", "artist_agreement"):
            folder[key].update(numerator=None, denominator=40, value=None, interval=None, method="unavailable")
        if index == 3:
            folder["artist_agreement"].update(numerator=36, value=.9, method="census-exact")
        features = {"valid_images": 40, "eligible_faces": 40, "V": coherence, "F": face_share,
                    "K": clusters, "Q": multi, "A": artist, "artist_labels": 40 if artist else 0,
                    "entities": 4 if artist else 0}
        folder["regimes"].update(features=features, passing=[regime], status="recommended")
        for detector in folder["regimes"]["detectors"]:
            for gate in detector["gates"]:
                value = features[gate["feature"]]
                gate["value"] = value
                gate["passed"] = None if value is None else value >= gate["threshold"] if gate["operator"] == ">=" else value < gate["threshold"]
            detector["status"] = "unavailable" if any(g["passed"] is None for g in detector["gates"]) else "pass" if all(g["passed"] for g in detector["gates"]) else "fail"
        report["folders"].append(folder)
        report["presentation"]["folder_text"][folder_id] = templates["measured_evidence"].format(
            method=folder["coherence"]["method"], sample=40, population=40,
            coverage="40/40 有效向量", confidence="synthetic UI fixture · heuristic/unvalidated")
        report["members"].extend({"image_id": image, "occurrence_id": digest(f"occurrence-{image}"),
                                  "path": f"{path}/{n}.png", "folder_id": folder_id} for n, image in enumerate(images))
    images = report["folders"][0]["sample_ids"][:12]
    representatives = []
    for index, image_id in enumerate(images):
        name = f"negotiation-synthetic-{index}.png"
        image = Image.new("RGB", (160, 160), [(40, 67, 86), (54, 78, 68), (83, 63, 44)][index % 3])
        draw = ImageDraw.Draw(image)
        draw.rectangle((28, 24, 132, 136), outline=(190, 205, 210), width=3)
        draw.ellipse((56, 42, 104, 90), fill=(140, 160, 170))
        draw.rectangle((44, 104, 116, 124), fill=(140, 160, 170))
        draw.text((8, 142), f"SYNTHETIC {index + 1:02}", fill=(210, 220, 225))
        image.save(output / name)
        representatives.append({"image_id": image_id, "face_id": f"synthetic-face-{index}", "image_ref": name, "crop_ref": None})
    report["clusters"] = [{
        "cluster_id": 1, "member_digest": digest("".join(images)), "image_ids": images,
        "face_ids": [f"synthetic-face-{i}" for i in range(12)], "unique_images": 12, "faces": 12,
        "outlier_fraction": 0, "coherence": report["folders"][0]["coherence"], "eligible": True,
        "eligibility_reasons": [], "representation": "synthetic-face-crop", "representatives": representatives,
        "candidates": [{"name": "演示候选 A（合成证据，未核实）", "source": "model", "score": .93,
                        "margin_vs_runner_up": .18, "verified": False}], "names": [],
        "source_concentration": 1, "source_concentration_basis": "12/12 synthetic images from one folder; not identity purity",
        "reference_support_ref": None, "profile": "analytic-ui-fixture-v1",
    }]
    report["clusters"][0]["coherence"] = {**report["folders"][0]["coherence"], "denominator": 12,
                                          "valid": 12, "scores": [.94] * 12}
    report["eligible_cluster_ids"] = [1]
    report["remaining_cluster_ids"] = []
    report["presentation"]["text"]["coherent_clusters"] = templates["coherent_clusters"].format(count=1, images=12)
    report["global_evidence"].update(files=160, unique_images=160, faces=160, processed_images=160,
                                     scope="SYNTHETIC UI fixture · analytic values, not corpus measurements",
                                     unavailable_signals=["vocabulary", "reference-support"], costs=[],
                                     model_profiles=["analytic-ui-fixture-v1"])
    report["recommendations"].update(eligible_clusters=1, covered_images=12, valid_images=160, cluster_coverage=.075)
    report["g1_report_ref"] = "negotiation-g1.json"
    for key in ("snapshot_digest", "profile_digest", "analysis_profile_digest", "seal_digest", "labels_digest"):
        report[key] = digest(f"synthetic-ui-fixture-{key}")
    report["report_digest"] = digest(json.dumps(report, ensure_ascii=False, sort_keys=True))
    (output / "negotiation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "negotiation-g1.json").write_text(json.dumps({"fixture": "synthetic UI only", "measured": False}), encoding="utf-8")
    print("Wrote synthetic negotiation fixture; frozen example unchanged")


if __name__ == "__main__":
    main()
