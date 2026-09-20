# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow"]
# ///
# How to run: uv run tools/build_identity_fixture.py
"""Generate only solid-color synthetic placeholder crops for the studio fixture."""
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "tests/fixtures/identity/faces"
    directory.mkdir(parents=True, exist_ok=True)
    for index, color in enumerate(("#7c91b5", "#ba9878", "#88a998"), 1):
        with Image.new("RGB", (256, 256), color) as image:
            draw = ImageDraw.Draw(image)
            draw.ellipse((64, 32, 192, 192), fill="#e2d8c5")
            draw.rectangle((36, 194, 220, 256), fill="#4e596e")
            image.save(directory / f"f_{index:08x}.jpg", "JPEG", quality=90, subsampling=0)


if __name__ == "__main__":
    main()
