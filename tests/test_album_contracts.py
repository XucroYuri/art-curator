import importlib.util

import pytest


def test_v2_label_dispatch_when_disposition_added() -> None:
    # Given a full-content bound new action.
    assert importlib.util.find_spec("artcurator.album_contracts"), "additive contracts missing"
    from artcurator.album_contracts import read_labels
    from artcurator.identity_schema import LabelEnvelope
    import json
    payload = json.dumps({"version": 2, "source": "review-studio", "corpus_fingerprint": "a" * 64,
        "labels": [{"action": "set_disposition", "image_id": "b" * 64, "subject_id": "face",
        "crop_id": "c" * 64, "profile": "d" * 64, "disposition": "deferred"}]}).encode()
    # When dispatching v2, then v1 remains strict and v2 retains the state.
    assert read_labels(payload).version == 2
    with pytest.raises(ValueError):
        LabelEnvelope.model_validate_json(payload)


def test_consent_stays_zero_when_execution_count_supplied() -> None:
    # Given an additive authority receipt, not a commit receipt.
    assert importlib.util.find_spec("artcurator.album_contracts"), "additive contracts missing"
    from artcurator.album_contracts import ConsentV2
    # When a caller tries to claim execution in consent, then parsing refuses it.
    with pytest.raises(ValueError):
        ConsentV2(receipt_id="a" * 64, preview_digest="b" * 64, parent={
            "library_id": "library", "revision": 0, "root_digest": "c" * 64},
            actor="human", mapping_mutations=1)
