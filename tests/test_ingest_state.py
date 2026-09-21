"""G1 transition guards: AC-FR-ALBUM-INGEST-001-01 scoped to G1."""
import importlib

import pytest


@pytest.mark.parametrize("target", ["CONFIRM", "FIRST-PASS", "REVIEW", "ARCHIVE"])
def test_future_stage_is_explicitly_guarded(target: str) -> None:
    # Given: a sealed G1 proposal, with no authority to mutate mappings.
    module = importlib.import_module("artcurator.ingest_schema")
    # When / Then: G2-G6 cannot silently succeed.
    with pytest.raises(NotImplementedError):
        module.transition("PROPOSE", target)


@pytest.mark.parametrize("source,target", [
    ("IDLE", "INGEST"), ("INGEST", "ANALYZE"), ("ANALYZE", "PROPOSE"),
    ("PROPOSE", "INGEST"),
])
def test_transition_when_valid(source: str, target: str) -> None:
    # Given
    module = importlib.import_module("artcurator.ingest_schema")
    # When
    result = module.transition(source, target)
    # Then
    assert result == target


def test_transition_when_stage_is_skipped() -> None:
    # Given
    module = importlib.import_module("artcurator.ingest_schema")
    # When / Then
    with pytest.raises(ValueError):
        module.transition("IDLE", "PROPOSE")
