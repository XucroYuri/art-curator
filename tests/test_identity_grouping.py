"""GROUP-SYN-v1: pixel-only retrieval, independent of pretrained downloads."""
import importlib
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from artcurator.identity_detect import crop_bytes
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import digest
from artcurator.scan import pixels


def test_grouping_options_when_defaults_requested() -> None:
    # Given the existing options boundary; when constructed; then sampling is bounded.
    options = IdentityOptions()
    assert getattr(options, "anchor_faces_per_character", None) == 64


@pytest.mark.parametrize("query,minimum,margin,expected", [
    ([1, 0, 0], .9, .1, "A"),
    ([0, 1, 0], .9, .1, "B"),
    ([0, 0, 1], .9, .1, None),
    ([1, 1, 0], .5, .01, None),
    ([1, 0, 0], 1., 1., "A"),
])
def test_assignment_when_thresholds_applied(query: list[float], minimum: float,
                                            margin: float, expected: str | None) -> None:
    # Given two orthogonal character anchors and explicit thresholds.
    module = importlib.import_module("artcurator.identity_group_math")
    bank = module.ReferenceBank(np.eye(3, dtype=np.float32)[:2], ("A", "B"), ("a", "b"))
    thresholds = module.Thresholds(min_sim=minimum, min_margin=margin)
    # When scoring pixel-derived features only.
    result = module.decide(np.asarray([query], dtype=np.float32), bank, thresholds)[0]
    # Then unknown/tied faces abstain and exact boundaries are inclusive.
    assert result.character == expected


def test_assignment_when_only_one_character() -> None:
    # Given no competing character.
    module = importlib.import_module("artcurator.identity_group_math")
    bank = module.ReferenceBank(np.array([[1., 0.]]), ("A",), ("a",))
    # When scoring; then no fabricated margin authorizes a match.
    assert module.decide(np.array([[1., 0.]]), bank, module.Thresholds(min_sim=0, min_margin=0))[0].character is None


def test_visual_input_when_file_renamed_and_moved(tmp_path: Path) -> None:
    # Given a real image file and fixed references; labels in query paths are misleading.
    module = importlib.import_module("artcurator.identity_group_math")
    source = tmp_path / "original.png"
    Image.new("RGB", (40, 40), "red").save(source)
    def features(path: Path) -> tuple[bytes, np.ndarray]:
        with pixels(path) as image:
            encoded = crop_bytes(image, (0, 0, 40, 40))
        with Image.open(io.BytesIO(encoded)) as crop:
            return encoded, np.asarray(crop, dtype=np.float32).mean(axis=(0, 1))[None]
    before_bytes, before = features(source)
    destination = tmp_path / "Character B" / "wrong-label.png"
    destination.parent.mkdir()
    bank = module.ReferenceBank(np.array([[1., 0., 0.], [0., 1., 0.]]), ("A", "B"), ("a", "b"))
    gates = module.Thresholds(min_sim=.9, min_margin=.1)
    # When the same file is moved and decoded/cropped again.
    source.rename(destination)
    after_bytes, after = features(destination)
    # Then pixels, scores and assignment are exactly invariant, not path-predicted.
    assert digest(before_bytes) == digest(after_bytes)
    assert module.decide(before, bank, gates) == module.decide(after, bank, gates)
    assert module.decide(after, bank, gates)[0].character == "A"


def test_sampling_when_duplicate_and_low_score() -> None:
    # Given candidate crop hashes and scores; when admitted greedily; then dedup/filter apply.
    module = importlib.import_module("artcurator.identity_anchor_sources")
    options = IdentityOptions()
    assert module.accept_sample(.9, 0, [0], options) is False
    assert module.accept_sample(.2, 65535, [0], options) is False
    assert module.accept_sample(.9, 65535, [0], options) is True


def test_sampling_when_cap_reached() -> None:
    # Given the face cap; when another distinct crop is considered; then it is rejected.
    module = importlib.import_module("artcurator.identity_anchor_sources")
    options = IdentityOptions(anchor_faces_per_character=1)
    assert module.accept_sample(.9, 65535, [0], options) is False


def test_assignment_when_individual_anchor_disagrees() -> None:
    # Given an A centroid facing the query but a closer individual B anchor.
    module = importlib.import_module("artcurator.identity_group_math")
    bank = module.ReferenceBank(np.array([[.9, .4359], [.9, -.4359], [1., 0.], [0., 1.]]),
                                ("A", "A", "B", "B"), ("a", "b", "c", "d"))
    # When centroid winner A competes with individual anchors; then it abstains.
    decision = module.decide(np.array([[1., 0.]]), bank, module.Thresholds(min_sim=.9, min_margin=.01))[0]
    assert decision.character is None
    assert decision.centroid_margin > .2
    assert decision.individual_margin < 0


def test_self_reference_when_crop_is_identical() -> None:
    # Given only one A reference, which is the query itself.
    module = importlib.import_module("artcurator.identity_group_math")
    bank = module.ReferenceBank(np.array([[1., 0.], [0., 1.]]), ("A", "B"), ("self", "other"))
    # When that crop is omitted; then remaining single-character support cannot assign.
    actual = module.decide(np.array([[1., 0.]]), module.without_crop(bank, "self"),
                           module.Thresholds(min_sim=0, min_margin=0))[0]
    assert actual.character is None


def test_calibration_when_reference_distributions_measured() -> None:
    # Given symmetric, labelled, independent references.
    module = importlib.import_module("artcurator.identity_group_math")
    bank = module.ReferenceBank(np.array([[1., .1], [1., -.1], [.1, 1.], [-.1, 1.]]),
                                ("A", "A", "B", "B"), ("a", "b", "c", "d"))
    # When calibrating on references only; then known analytic wrong-centroid P95 is selected.
    result = module.calibrate(bank)
    assert result.samples == 4
    assert result.defaults.min_sim == pytest.approx(.1 / np.sqrt(1.01), abs=1e-6)
    assert result.defaults.min_margin >= .005


def test_sampling_when_directories_excluded(tmp_path: Path) -> None:
    # Given real synthetic images and a narrow deterministic detector adapter.
    sources = importlib.import_module("artcurator.identity_anchor_sources")
    config = importlib.import_module("artcurator.config")
    detector = importlib.import_module("artcurator.identity_detector")
    schema = importlib.import_module("artcurator.identity_schema")
    root = tmp_path / "characters"
    root.mkdir()
    for name in ("A", "B", "output"):
        (root / name).mkdir()
        Image.new("RGB", (32, 32), "red").save(root / name / "one.png")
    out = tmp_path / "out" / "library"
    out.mkdir(parents=True)
    settings = config.Settings(input=root / "B", references=root / "A", posted=root / "A",
        characters_root=root, out=out, identity=schema.IdentityOptions(anchor_exclude_folders=["output"]))
    adapter = detector.Detector(schema.DetectorInfo(name="synthetic", model="synthetic", revision="fixed"),
                                 "a" * 64, lambda image: [detector.Detection((0, 0, 32, 32), .9)])
    # When sampling; then configured query/output directories supply no labels or anchors.
    result = sources.collect(settings, adapter)
    assert [anchor.character for anchor in result.anchors] == ["A"]
    assert set(result.excluded) == {"B", "output"}
    assert result.folders["A"]["accepted"] == 1
