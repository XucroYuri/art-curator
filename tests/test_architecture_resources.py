"""Deterministic reservation accounting, independent of installed capacity."""
import pytest
from pathlib import Path


def test_budgets_when_available_memory_is_low() -> None:
    # Given installed and currently available capacity; when admitted.
    from artcurator.resources import Budgets
    budgets = Budgets.choose(1000, 800, 400, [(1000, 400)])
    # Then availability rather than total capacity limits both pools.
    assert budgets.host_bytes == 300
    assert budgets.gpu_bytes == (340,)


def test_queue_when_two_oversized_images_are_reserved() -> None:
    # Given a byte budget fitting one image but not two.
    from artcurator.resources import ByteBudget, Deferred
    queue = ByteBudget(100)
    # When a second reservation would exceed the budget; then it is deferred.
    with queue.reserve(60):
        with pytest.raises(Deferred):
            with queue.reserve(60):
                pytest.fail("overcommitted")
        assert queue.used == 60
    assert queue.used == 0
    assert queue.events[0]["reason"] == "byte_budget_exceeded"


def test_prefetch_when_decode_reservation_exceeds_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given two real small files whose admitted decode estimate exceeds a tiny budget.
    import numpy as np
    from PIL import Image
    from artcurator import prefetch
    from artcurator.models import Predictor
    from artcurator.resources import ByteBudget, Deferred
    from artcurator.scan import inspect
    rows = []
    for i in range(2):
        path = tmp_path / f"{i}.png"
        Image.new("RGB", (4, 4)).save(path)
        rows.append(inspect(path, tmp_path))
    budget = ByteBudget(100)
    monkeypatch.setattr(prefetch, "decode_estimate", lambda path: 60)
    monkeypatch.setattr(prefetch, "pixels", lambda path: pytest.fail("decoded before reservation"))
    predictor = Predictor("stub", "v1", "rgb", lambda images: np.zeros(len(images)))
    # When prefetched; then no decode happens and the byte limit is recorded.
    with pytest.raises(Deferred):
        with prefetch.batches(rows, predictor, prefetch.Prefetch(batch_size=2, budget=budget)) as batches:
            next(batches)
    assert budget.peak == 0 and budget.events[0]["requested_bytes"] == 120
