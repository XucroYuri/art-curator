"""CANDIDATES-SYN-v1: enumerated evidence is not a forced assignment."""
import importlib

import numpy as np
import pytest

from artcurator.identity_group_math import ReferenceBank, decide
from artcurator.identity_group_schema import Thresholds


def test_top_five_when_six_characters_compete() -> None:
    # Given six orthogonal references and an analytically ordered query.
    module = importlib.import_module("artcurator.identity_candidates")
    bank = ReferenceBank(np.eye(6, dtype=np.float32), tuple("FEDCBA"), tuple("abcdef"))
    query = np.arange(1, 7, dtype=np.float32)
    # When ranking all characters before truncation.
    result = module.rank_candidates(query, bank)
    # Then five distinct scores descend, with margins against strongest others.
    assert [c.character for c in result] == list("ABCDE")
    assert result[0].score == pytest.approx(6 / np.sqrt(91))
    assert result[0].margin_vs_runner_up == pytest.approx(1 / np.sqrt(91))
    assert result[1].margin_vs_runner_up == pytest.approx(-1 / np.sqrt(91))
    assert all(c.source == "anchor" for c in result)


@pytest.mark.parametrize("size", [0, 1, 4])
def test_ranking_when_support_is_limited(size: int) -> None:
    # Given a tied query and zero, one or four supported characters.
    module = importlib.import_module("artcurator.identity_candidates")
    bank = ReferenceBank(np.eye(4, dtype=np.float32)[:size], tuple("DCBA"[:size]), tuple("abcd"[:size]))
    # When enumerating.
    result = module.rank_candidates(np.ones(4, dtype=np.float32), bank)
    # Then names break ties for display only and singleton margin is unavailable.
    assert [c.character for c in result] == sorted("DCBA"[:size])
    if size == 1:
        assert result[0].margin_vs_runner_up is None


def test_abstention_when_individual_anchor_disagrees() -> None:
    # Given the existing disagreement veto, despite a strong centroid winner.
    module = importlib.import_module("artcurator.identity_candidates")
    bank = ReferenceBank(np.array([[.9, .4359], [.9, -.4359], [1., 0.], [0., 1.]], dtype=np.float32),
                         ("A", "A", "B", "B"), tuple("abcd"))
    query = np.array([1., 0.], dtype=np.float32)
    decision = decide(query[None], bank, Thresholds(min_sim=.9, min_margin=.01))[0]
    # When formatting an abstained face.
    face = module.FaceCandidates(face_id="f_00000001", image_sha16="a" * 16,
        candidates=module.rank_candidates(query, bank), suggested=decision.character, abstained=True)
    # Then choices remain and JSON uses an actual null/boolean.
    assert face.candidates[0].character == "A"
    assert '"suggested":null,"abstained":true' in face.model_dump_json()


def test_attributes_when_future_evidence_is_present() -> None:
    # Given an additive evidence block.
    module = importlib.import_module("artcurator.identity_candidates")
    raw = {"character": "A", "score": .8, "margin_vs_runner_up": .1,
           "source": "anchor", "attributes": {"version": 1, "hair": {"score": .2}}}
    # When parsing and serializing with the current consumer.
    actual = module.Candidate.model_validate(raw).model_dump()
    # Then unknown evidence survives, without changing required fields.
    assert actual == raw


@pytest.mark.parametrize("field,value", [("score", float("nan")), ("source", "invented")])
def test_contract_when_invalid_evidence(field: str, value: str | float) -> None:
    # Given malformed evidence; when parsed; then fail closed.
    module = importlib.import_module("artcurator.identity_candidates")
    raw = {"character": "A", "score": .8, "margin_vs_runner_up": None, "source": "anchor", field: value}
    with pytest.raises(ValueError):
        module.Candidate.model_validate(raw)


def test_face_record_when_suggestion_is_not_top() -> None:
    # Given a ranked list whose winner is A.
    module = importlib.import_module("artcurator.identity_candidates")
    ranked = [module.Candidate(character="A", score=.9, margin_vs_runner_up=.2, source="anchor"),
              module.Candidate(character="B", score=.7, margin_vs_runner_up=-.2, source="anchor")]
    # When a different suggestion is claimed; then the contract fails closed.
    with pytest.raises(ValueError, match="top ranked"):
        module.FaceCandidates(face_id="f_00000001", image_sha16="a" * 16, candidates=ranked,
                              suggested="B", abstained=False)
