"""Decode fallback, bounded cancellation and staged-copy failure contracts."""
from pathlib import Path
from threading import Barrier

import pytest
from PIL import Image, ImageFile, PngImagePlugin

from artcurator import _moves, scan


def test_fallback_preserves_pixels_and_excludes_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    path = tmp_path / "source.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("description", "metadata must not reach parser")
    Image.new("RGB", (33, 17), "green").save(path, pnginfo=metadata)
    expected = scan.pixels(path).tobytes()
    original = Image.open
    attempts = []

    def transient(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= 2:
            raise OSError("broken data stream")
        return original(*args, **kwargs)

    monkeypatch.setattr(Image, "open", transient)
    # When
    image, mode = scan.decoded(path)
    # Then
    assert image.tobytes() == expected and mode == "RGB"
    assert image.info == {} and ImageFile.LOAD_TRUNCATED_IMAGES is False


def test_persistent_corruption_is_rejected(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    # When / Then
    with pytest.raises(OSError, match="3 attempts"):
        scan.pixels(path)


def test_prefetch_early_exit_does_not_exhaust_source(tmp_path: Path) -> None:
    # Given
    from artcurator.parallel import ordered_map
    consumed = []

    def source():
        for value in range(100):
            consumed.append(value)
            yield value

    # When
    with ordered_map(lambda value: value, source(), workers=2, capacity=3) as results:
        assert next(results) == 0
    # Then
    assert consumed == [0, 1, 2]


def moves_at(tmp_path: Path) -> list[_moves.Move]:
    character = tmp_path / "character"
    source = character / "source"
    source.mkdir(parents=True)
    moves = []
    for index in range(4):
        path = source / f"{index}.png"
        path.write_bytes(bytes([index]) * 1024)
        digest = _moves.sha256(path)
        moves.append(_moves.Move(src=path, dst=character / "dest" / path.name,
                                 character=character, sha16=digest[:16], bytes=1024,
                                 sha256=digest, tier="route_identity"))
    return moves


def test_copy_wave_is_parallel_and_matches_serial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: barrier fails rather than hangs if execution is secretly serial.
    moves = moves_at(tmp_path)
    barrier = Barrier(4, timeout=10)
    original = _moves.copy_bytes

    def synchronized(src: Path, dst: Path) -> None:
        barrier.wait()
        original(src, dst)

    monkeypatch.setattr(_moves, "copy_bytes", synchronized)
    # When
    results = list(_moves.staged_copies(moves, workers=4))
    # Then
    assert [item.after for item in results] == [move.sha256 for move in moves]
    assert all(item.dst.read_bytes() == item.move.src.read_bytes() for item in results)


def test_copy_wave_preserves_sources_on_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    moves = moves_at(tmp_path)
    original = _moves.copy_bytes

    def corrupt(src: Path, dst: Path) -> None:
        original(src, dst)
        if src == moves[1].src:
            dst.write_bytes(b"broken")

    monkeypatch.setattr(_moves, "copy_bytes", corrupt)
    # When
    results = list(_moves.staged_copies(moves, workers=4))
    # Then
    assert isinstance(results[1].error, _moves.MoveError)
    assert all(_moves.sha256(move.src) == move.sha256 for move in moves)
    assert results[1].dst.read_bytes() == b"broken"
