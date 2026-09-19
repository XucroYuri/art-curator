"""Wave 2 contracts, exclusively generated tmp_path pixels."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PIL import Image

from artcurator import db, scan
from artcurator.config import Settings


def settings_at(tmp_path: Path, workers: int = 8) -> Settings:
    source = tmp_path / "input"
    source.mkdir(exist_ok=True)
    out = tmp_path / f"out-{workers}"
    out.mkdir(exist_ok=True)
    return Settings(input=source, references=source, posted=source,
                    characters_root=tmp_path, out=out, workers=workers)


def test_parallel_scan_matches_serial(tmp_path: Path) -> None:
    # Given
    serial = settings_at(tmp_path, 1)
    parallel = settings_at(tmp_path, 8)
    for index in range(9):
        Image.new("RGB", (97 + index, 61), (index * 20, 70, 123)).save(serial.input / f"{index}.png")
    expected = scan.scan(serial, None)
    # When
    actual = scan.scan(parallel, None)
    # Then
    assert actual == expected
    assert all((serial.out / row.thumb_rel).read_bytes() == (parallel.out / row.thumb_rel).read_bytes()
               for row in actual)


def test_previews_dimensions_metadata_skip_and_duplicates(tmp_path: Path) -> None:
    # Given
    from artcurator.previews import previews
    settings = settings_at(tmp_path)
    path = settings.input / "large.png"
    Image.new("RGB", (2048, 1024), "red").save(path)
    row = scan.inspect(path, settings.input)
    db.save_rows(settings.out, [row, row.model_copy()])
    # When
    result = previews(settings)
    destination = settings.out / "previews" / f"{row.sha16}.jpg"
    stamp = destination.stat().st_mtime_ns
    again = previews(settings)
    # Then
    assert result.rows == 2 and result.unique == result.generated == 1
    assert again.generated == 0 and destination.stat().st_mtime_ns == stamp
    with Image.open(destination) as image:
        assert image.size == (1024, 512)
        assert not image.getexif() and "icc_profile" not in image.info
    assert 0 < destination.stat().st_size < path.stat().st_size * 3


def test_prefetch_bound_order_and_overlap(tmp_path: Path) -> None:
    # Given
    from artcurator.parallel import ordered_map
    seen = []
    second = Event()

    def source():
        for i in range(10):
            seen.append(i)
            yield i

    def work(i: int) -> int:
        if i == 1:
            second.set()
        return i * i

    # When
    with ordered_map(work, source(), workers=2, capacity=2) as results:
        first = next(results)
        assert second.wait(5)
        assert len(seen) == 2
        rest = list(results)
    # Then
    assert [first, *rest] == [i * i for i in range(10)]


def test_prefetch_propagates_error(tmp_path: Path) -> None:
    # Given
    from artcurator.parallel import ordered_map

    def fail(i: int) -> int:
        raise OSError("decode failed")

    # When / Then
    with pytest.raises(OSError, match="decode failed"):
        with ordered_map(fail, [1, 2], workers=2, capacity=2) as results:
            list(results)


def test_decode_retries_strictly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    path = tmp_path / "image.png"
    Image.new("RGB", (19, 13), "blue").save(path)
    original = Image.Image.load
    calls = []

    def transient(image, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("broken data stream")
        return original(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "load", transient)
    # When
    image = scan.pixels(path)
    # Then
    assert image.size == (19, 13) and image.getpixel((0, 0)) == (0, 0, 255)


def test_scan_records_thumbnail_decode_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    settings = settings_at(tmp_path)
    for name in ("good", "bad"):
        Image.new("RGB", (32, 32), "red" if name == "good" else "blue").save(settings.input / f"{name}.png")
    original = scan.pixels

    def fail(path: Path):
        if path.stem == "bad":
            raise OSError("broken data stream")
        return original(path)

    monkeypatch.setattr(scan, "pixels", fail)
    # When
    rows = scan.scan(settings, None)
    # Then
    assert len(rows) == 1
    rejected = json.loads((settings.out / "scan-rejected.json").read_text())
    assert rejected[0]["stage"] == "thumbnail"


def test_inference_parallel_values_match(tmp_path: Path) -> None:
    # Given
    from artcurator.cache import Pass, infer
    from artcurator.models import Predictor
    settings = settings_at(tmp_path)
    Image.new("RGB", (32, 32), "blue").save(settings.input / "a.png")
    rows = [scan.inspect(settings.input / "a.png", settings.input)] * 3
    predictor = Predictor("test", "v1", "native", lambda images: np.array(
        [np.asarray(image).mean() for image in images], dtype=np.float32))
    one = tmp_path / "serial"
    eight = tmp_path / "parallel"
    one.mkdir()
    eight.mkdir()
    # When
    expected = infer(rows, Pass(one, "test", 2, predictor, workers=1, prefetch_batches=0))
    actual = infer(rows, Pass(eight, "test", 2, predictor, workers=8))
    # Then
    assert np.array_equal(expected, actual)


def test_parallel_verified_copy_equivalence(tmp_path: Path) -> None:
    # Given
    from artcurator._moves import sha256, verified_copy
    src = tmp_path / "source"
    src.write_bytes(b"pixel" * 10000)
    digest = sha256(src)
    # When
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: verified_copy(src, tmp_path / str(i), digest), range(12)))
    # Then
    assert results == [digest] * 12
    assert src.read_bytes() == b"pixel" * 10000
