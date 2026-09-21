"""Analytic cold-start and contradiction cases; scores are not accuracy labels."""
import pytest
from pathlib import Path

from artcurator.candidates_schema_v2 import Option


@pytest.mark.parametrize("scores,accepted,margin", [
    ([.85, .65], True, .20), ([.849, .4], False, None),
    ([.95, .76], False, None), ([.95, .95], False, None),
    ([.99], True, .64), ([], False, None),
])
def test_gate_when_scores_compete(scores: list[float], accepted: bool, margin: float | None) -> None:
    # Given ordered compact WD candidates.
    from artcurator.model_suggestions import propose
    rows = [Option(name=f"hero-{i}", source="model", score=score) for i, score in enumerate(scores)]
    # When applying the model-only gate.
    result = propose(rows)
    # Then only score AND margin pass; singleton uses the omitted-score bound.
    assert (result is not None) == accepted
    if result:
        assert result.margin_vs_runner_up == pytest.approx(margin)
        assert result.verified is False


@pytest.mark.parametrize("name,score,conflicts", [("other", .9, True), ("hero", .9, False), ("other", .35, False)])
def test_disagreement_when_visual_evidence_exists(name: str, score: float, conflicts: bool) -> None:
    # Given an unverified model winner and independent visual evidence.
    from artcurator.model_suggestions import disagreement, propose
    model = propose([Option(name="hero", source="model", score=.99)])
    reference = [Option(name=name, source="memory", score=score)]
    # When comparing canonical names.
    result = disagreement(model, reference, "memory")
    # Then contradictory support is recorded without inventing verification.
    assert bool(result) == conflicts
    if result:
        assert result[0].evidence_name == "other"
        assert result[0].model_name == "hero"


def test_v2_when_read_by_new_schema() -> None:
    # Given an old v2 face; when parsed; then legacy abstention and absent tier remain valid.
    from artcurator.candidates_schema_v2 import CandidateDocumentV2
    document = CandidateDocumentV2.model_validate({"version": 2, "faces": [{
        "face_id": "f_00000001", "image_sha16": "a" * 16, "candidates": [
            {"name": "其他", "source": "bucket"}, {"name": "新建角色", "source": "action"}]}]})
    assert document.faces[0].suggested_model is None
    assert document.faces[0].suggested_verified is None


@pytest.mark.parametrize("references", [False, True])
def test_pipeline_when_wd_has_confident_unknown(tmp_path: Path, references: bool) -> None:
    # Given real saved vectors and compact WD evidence, optionally with anchors.
    from test_identity_grouping_exports import fixture
    from artcurator.identity_store import save_model
    from artcurator.wd_schema import Evidence, Handshake, Tag, TagDocument, TaggedFace
    from artcurator.identity_candidates_v2 import emit
    fixture(tmp_path)
    if not references:
        (tmp_path / "anchors.json").unlink()
    save_model(tmp_path / "wd-tagger.json", TagDocument(
        handshake=Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={}),
        corpus_fingerprint="c" * 64, faces=[TaggedFace(face_id="f_00000001", image_sha16="a" * 16,
        crop_sha256="1" * 64, evidence=Evidence(characters=[Tag(tag="unknown_hero", score=.99)]))]))
    # When running the actual producer (no model inference or mocks).
    face = emit(tmp_path).faces[0]
    # Then cold-start is useful, reference contradiction demotes, neither fabricates verification.
    assert face.suggested_model is not None
    assert face.suggested_model.verified is False
    assert face.model_demoted == references
    assert face.suggested is face.suggested_verified is None
    assert face.abstained
    if references:
        assert face.disagreements[0].evidence_name == "A"
        assert face.disagreements[0].source == "reference"
