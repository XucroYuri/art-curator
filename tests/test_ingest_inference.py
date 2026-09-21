"""Real identity/cache stages with deterministic synthetic inference, not GPU qualification."""

import numpy as np
import pytest
from PIL import Image

from artcurator import db, ingest, identity_detect, identity_embed
from artcurator.config import Settings
from artcurator.identity_detector import Detection, Detector
from artcurator.identity_embed import CropEmbedder
from artcurator.identity_profiles import ExecutionProfile
from artcurator.identity_schema import DetectorInfo
from artcurator.ingest_adapters import Request, Result, execute
from artcurator.ingest_schema import Options
from test_ingest import corpus as corpus


def test_incremental_inference_when_new_image_and_duplicate_added(corpus: Settings,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: genuine detect/embed/cache/cluster/candidate code, tiny fixed test predictors.
    detected: list[int] = []
    embedded: list[int] = []
    def predict_faces(image: Image.Image):
        detected.append(1)
        return [Detection(bbox=(0, 0, image.width, image.height), score=.99)]
    detector = Detector(info=DetectorInfo(name="fixture", model="synthetic", revision="v1"),
                        artifact_sha256="a" * 64, predict=predict_faces)
    monkeypatch.setattr(identity_detect, "load_detector", lambda _: detector)
    def predict_vectors(images: list[Image.Image]):
        embedded.extend([1] * len(images))
        return np.asarray([[float(np.asarray(image).mean()), 1., 2., 3.] for image in images], dtype=np.float32)
    execution = ExecutionProfile(device="cpu", precision="float32", batch_size=1, runtime={"fixture": "v1"})
    embedder = CropEmbedder("synthetic", "v1", "test-fixed-pixels", predict_vectors, execution)
    monkeypatch.setattr(identity_embed, "load_embedder", lambda *_: embedder)
    reference = corpus.out.parent / "profile"
    reference.mkdir()
    db.save_rows(reference, [])
    db.meta(reference, "model_siglip", "synthetic|v1")
    configured = corpus.model_copy(update={"identity": corpus.identity.model_copy(update={"device": "cpu", "cluster": "dbscan"})})
    options = Options(profile_from=reference, reserve_bytes=0)
    def selected(request: Request) -> Result:
        if request.action == "tag":
            return Result(outcome="unavailable", reason="synthetic fixture has no WD inference oracle")
        return execute(request)
    first = ingest.run(configured, options, execute=selected)
    assert len(detected) == len(embedded) == 2
    (corpus.input / "another-copy.png").write_bytes((corpus.input / "folder-a/red.png").read_bytes())
    Image.new("RGB", (24, 24), "green").save(corpus.input / "new.png")
    # When
    second = ingest.run(configured, options, execute=selected)
    unchanged = ingest.run(configured, options, execute=selected)
    # Then
    assert len(detected) == len(embedded) == 3
    assert first.revision != second.revision == unchanged.revision
    assert (corpus.out / "revisions" / second.revision / "identity-candidates.json").is_file()
