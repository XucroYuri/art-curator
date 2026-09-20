"""Raw HPS evidence survives the generated offline payload."""
import base64
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from artcurator import db
from tools import build_gallery
from test_build_gallery import _write_scores_csv


@pytest.mark.parametrize(("mu", "sigma"), [("5.251234567", "0.031234567"), ("", ""), ("0", "0")])
def test_gallery_hps_round_trip(tmp_path: Path, mu: str, sigma: str) -> None:
    # Given present, missing or zero-valued HPS evidence and an unknown future column.
    columns = db.COLUMNS + ("future_metric",)
    _write_scores_csv(tmp_path / "scores.csv", columns, hpsv3_mu=mu, hpsv3_sigma=sigma, future_metric="opaque")
    # When building the actual compressed offline report.
    result = build_gallery.build_gallery_with_metrics(tmp_path)
    html = result.path.read_text(encoding="utf-8")
    encoded = re.search(r'<script id="gallery-payload" type="application/octet-stream">(.*?)</script>', html, re.S)
    assert encoded is not None
    payload = json.loads(gzip.decompress(base64.b64decode(encoded[1])))
    # Then raw precision and missing/zero distinction survive without changing row counts.
    assert payload["c"]["hm"] == [float(mu) if mu else None]
    assert payload["c"]["hs"] == [float(sigma) if sigma else None]
    assert payload["n"] == result.rows == 1
    assert 'hpsv3_mu:column("hm",index)' in html
    assert 'hpsv3_sigma:column("hs",index)' in html
    assert 'hpsv3_mu:"HPSv3 μ"' in html
    assert 'hpsv3_sigma:"HPSv3 σ"' in html
    assert '<dt>HPSv3 μ</dt>' in html and '<dt>HPSv3 σ</dt>' in html


def test_legacy_gallery_exposes_missing_hps(tmp_path: Path) -> None:
    # Given an older CSV with neither HPS field.
    columns = tuple(column for column in db.COLUMNS if not column.startswith("hpsv3_"))
    _write_scores_csv(tmp_path / "scores.csv", columns)
    # When parsed and compacted.
    rows = build_gallery.read_scores(tmp_path / "scores.csv")
    payload = build_gallery.compact_payload(build_gallery.build_payload(tmp_path, rows, columns))
    # Then the detail view receives explicit unavailable values, never fabricated zero.
    assert payload["c"]["hm"] == [None]
    assert payload["c"]["hs"] == [None]
    assert payload["n"] == 1


@pytest.mark.parametrize("field", ["hpsv3_mu", "hpsv3_sigma"])
def test_hps_invalid_numeric_rejected(tmp_path: Path, field: str) -> None:
    # Given nonfinite upstream evidence.
    _write_scores_csv(tmp_path / "scores.csv", db.COLUMNS, **{field: "NaN"})
    # When parsing, then the normal finite-numeric boundary also applies to HPS.
    with pytest.raises(build_gallery.GalleryInputError):
        build_gallery.read_scores(tmp_path / "scores.csv")


@pytest.mark.parametrize("mu", ["5.251234567", ""])
def test_hps_detail_and_inspector_dom(tmp_path: Path, mu: str) -> None:
    # Given a synthetic report and the optional Node unit-test runtime.
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the isolated JavaScript DOM unit harness")
    _write_scores_csv(tmp_path / "scores.csv", db.COLUMNS, hpsv3_mu=mu, hpsv3_sigma="0")
    html = build_gallery.build_gallery(tmp_path)
    # When executing the report's real decoder, metric renderer and detail function.
    result = subprocess.run([node, str(Path(__file__).with_name("gallery_hps_dom.cjs")), str(html)],
                            capture_output=True, text=True, encoding="utf-8", timeout=10, check=False)
    # Then both surfaces expose HPS values, raw precision and missingness; the drawer opens.
    assert result.returncode == 0, result.stdout + result.stderr
