"""Verify Wave 2 artifacts without modifying manifests, scores, or source images."""
import base64
import gzip
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from PIL import Image

from artcurator import db
from artcurator.config import ROOT, confine_writes, environment


def main() -> None:
    out = ROOT / "out/wave2-benchmark"
    environment(out)
    confine_writes()
    before = json.loads((out / "before/receipt.json").read_text(encoding="utf-8"))
    reports = []
    for name in ("library", "review", "similarity"):
        directory = ROOT / "out" / name
        with sqlite3.connect(f"{(directory / 'manifest.sqlite').as_uri()}?mode=ro", uri=True) as connection:
            rows = [db.Row.model_validate_json(item[0]) for item in connection.execute(
                "SELECT payload FROM images ORDER BY position")]
        digest = hashlib.sha256((directory / "scores.csv").read_bytes()).hexdigest()
        assert digest == before["scores_sha256"][name], f"CSV changed: {name}"
        assets = list((directory / "previews").glob("*.jpg"))
        keys = {row.sha16 for row in rows}
        assert {path.stem for path in assets} == keys
        for path in assets:
            with Image.open(path) as image:
                image.load()
                assert max(image.size) <= 1024 and image.format == "JPEG"
                assert not image.getexif() and "icc_profile" not in image.info
        gallery = (directory / "gallery.html").read_text(encoding="utf-8")
        encoded = max(re.findall(r"[A-Za-z0-9+/=]{100,}", gallery), key=len)
        payload = json.loads(gzip.decompress(base64.b64decode(encoded)))
        assert payload["n"] == len(rows) and all(payload["c"]["pr"])
        reports.append({"name": name, "rows": len(rows), "preview_files": len(assets),
                        "covered_rows": sum((directory / "previews" / f"{r.sha16}.jpg").is_file() for r in rows),
                        "gallery_rows": payload["n"], "all_gallery_previews": all(payload["c"]["pr"]),
                        "preview_bytes": sum(path.stat().st_size for path in assets),
                        "thumb_bytes": sum(path.stat().st_size for path in (directory / "thumbs").glob("*.jpg")),
                        "source_bytes": sum(r.filesize for r in rows), "scores_sha256": digest})
    db.write_json(out / "assets-receipt.json", reports)
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
