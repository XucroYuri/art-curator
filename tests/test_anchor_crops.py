"""Content-addressed reference crops: persistence, restore and WD input selection."""
from pathlib import Path

import pytest
from PIL import Image

from artcurator.config import Settings
from artcurator.identity_anchor_sources import persist_crops, restore_crops
from artcurator.identity_detect import crop_bytes
from artcurator.identity_group_schema import Anchor, AnchorDocument, Calibration, GroupingError, Thresholds
from artcurator.identity_profiles import ExecutionProfile
from artcurator.identity_schema import DetectorInfo, ModelInfo
from artcurator.identity_store import digest, file_digest, save_model
from artcurator.identity_tag import verified_anchor_crops
from artcurator.scan import pixels


def anchor_for(source: Path, character: str = "A", bbox: tuple[int, int, int, int] = (4, 4, 32, 32)) -> Anchor:
    with pixels(source) as image:
        crop = crop_bytes(image, bbox)
    return Anchor(character=character, source="folder-derived", source_folder=character,
        image_sha256=file_digest(source), crop_sha256=digest(crop), bbox=bbox, det_score=.9, phash="0")


def document_for(anchors: list[Anchor]) -> AnchorDocument:
    model = ModelInfo(name="siglip", model="synthetic", revision="fixed")
    return AnchorDocument(model=model, preprocess="synthetic",
        execution=ExecutionProfile(device="cpu", precision="float32", batch_size=1, runtime={}),
        detector=DetectorInfo(name="synthetic", model="synthetic", revision="fixed"), detector_sha256="e" * 64,
        detector_options={}, licenses={}, folders={}, excluded_folders=[], anchors=anchors, matrix_sha256="f" * 64,
        calibration=Calibration(samples=0, genuine=[], impostor=[], stable_margin=[],
                                defaults=Thresholds(min_sim=.9, min_margin=.1)), wall_seconds=0)


def settings_for(tmp_path: Path, root: Path, out: Path) -> Settings:
    return Settings(input=tmp_path / "published", references=tmp_path / "reference", posted=tmp_path / "posted",
                    characters_root=root, out=out)


def test_persist_when_crops_accepted_writes_content_addresses(tmp_path: Path) -> None:
    # Given an accepted crop and its recorded content digest.
    crop = b"verified-crop-bytes"
    anchor = Anchor(character="A", source="folder-derived", source_folder="A", image_sha256=digest(b"source"),
                    crop_sha256=digest(crop), bbox=(0, 0, 8, 8), det_score=.9, phash="0")
    # When persisting twice; then the file is written once under its own digest.
    assert persist_crops(tmp_path, [anchor], [crop]) == 1
    assert persist_crops(tmp_path, [anchor], [crop]) == 1
    assert (tmp_path / "anchors" / f"{anchor.crop_sha256}.jpg").read_bytes() == crop


def test_persist_when_digest_mismatches_refuses_before_writing(tmp_path: Path) -> None:
    # Given a healthy crop and one whose bytes do not match the recorded digest.
    healthy = Anchor(character="A", source="folder-derived", source_folder="A", image_sha256=digest(b"one"),
                     crop_sha256=digest(b"one"), bbox=(0, 0, 8, 8), det_score=.9, phash="0")
    broken = healthy.model_copy(update={"crop_sha256": digest(b"two"), "image_sha256": digest(b"source-two")})
    # When persisting; then nothing is written and the mismatch fails closed.
    with pytest.raises(GroupingError, match="digest"):
        persist_crops(tmp_path, [healthy, broken], [b"one", b"tampered"])
    assert not (tmp_path / "anchors" / f"{healthy.crop_sha256}.jpg").exists()


def test_verified_when_crop_missing_or_corrupt_is_omitted(tmp_path: Path) -> None:
    # Given one healthy, one missing and one corrupt persisted reference crop.
    out = tmp_path / "corpus"
    (out / "anchors").mkdir(parents=True)
    healthy = Anchor(character="A", source="folder-derived", source_folder="A", image_sha256=digest(b"src-one"),
                     crop_sha256=digest(b"one"), bbox=(0, 0, 8, 8), det_score=.9, phash="0")
    missing = healthy.model_copy(update={"crop_sha256": digest(b"two"), "image_sha256": digest(b"src-two")})
    corrupt = healthy.model_copy(update={"crop_sha256": digest(b"three"), "image_sha256": digest(b"src-three")})
    (out / "anchors" / f"{healthy.crop_sha256}.jpg").write_bytes(b"one")
    (out / "anchors" / f"{corrupt.crop_sha256}.jpg").write_bytes(b"tampered")
    # When selecting taggable crops; then only the verified file survives, without erroring.
    result = verified_anchor_crops(out, [healthy, missing, corrupt])
    assert [(row.image_sha256, row.crop_sha256) for row in result] == [(healthy.image_sha256, healthy.crop_sha256)]


def test_verified_when_no_anchor_document_returns_empty(tmp_path: Path) -> None:
    # Given no saved reference anchors at all.
    # When selecting taggable crops; then tagging faces alone remains the previous behavior.
    assert verified_anchor_crops(tmp_path, []) == []


def test_restore_when_legacy_corpus_has_sources_reproduces_verified_crops(tmp_path: Path) -> None:
    # Given a corpus anchored before crops were persisted, with one source still on disk.
    root = tmp_path / "characters"
    folder = root / "A"
    folder.mkdir(parents=True)
    source = folder / "one.png"
    Image.new("RGB", (96, 96), (200, 10, 10)).save(source)
    present = anchor_for(source)
    absent = present.model_copy(update={"image_sha256": digest(b"absent-image"),
                                        "crop_sha256": digest(b"absent-crop")})
    out = tmp_path / "corpus"
    out.mkdir()
    save_model(out / "anchors.json", document_for([present, absent]))
    # When restoring from the saved bbox and source digest.
    result = restore_crops(settings_for(tmp_path, root, out))
    # Then the reproducible crop is persisted byte-identically and the missing source is reported.
    assert result.persisted == 1
    assert result.unavailable == (absent.crop_sha256,)
    restored = out / "anchors" / f"{present.crop_sha256}.jpg"
    assert digest(restored.read_bytes()) == present.crop_sha256
