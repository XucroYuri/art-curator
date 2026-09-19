# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run from the repository root: uv run --no-project tools/build_demo.py
"""Build the synthetic demo without embedding a machine-specific source path."""
from pathlib import Path

from build_gallery import build_payload, read_scores, write_gallery


def main() -> None:
    """Use only the checked-in synthetic CSV and relative provenance."""
    directory = Path("tests/fixtures/gallery")
    source = directory / "scores.csv"
    payload = build_payload(directory, read_scores(source))
    payload["source"] = source.as_posix()
    destination = write_gallery(directory, payload, "Synthetic demo", "Placeholder data only")
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
