"""Worker-side image preprocessing, shared by inference and the cache identity.

The preprocessing *code* plus the declared :data:`~artcurator.wd_schema.PREPROCESS` profile
form the cache's preprocess digest, so an implementation edit without a profile bump still
invalidates model-space results instead of silently reusing them.
"""
import hashlib
import inspect
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .wd_schema import PREPROCESS


def preprocess(path: Path) -> NDArray[np.float32]:
    """White alpha composite, centered square, bicubic 448, unnormalized BGR NHWC."""
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "WHITE")
        white.alpha_composite(rgba)
        image = white.convert("RGB")
        side = max(image.size)
        square = Image.new("RGB", (side, side), "WHITE")
        square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
        return np.asarray(square.resize((448, 448), Image.Resampling.BICUBIC), dtype=np.float32)[:, :, ::-1]


def preprocess_digest() -> str:
    """Digest of the declared profile and the implementation that produced cached vectors."""
    try:
        source = inspect.getsource(preprocess).encode()
    except (OSError, TypeError):  # pragma: no cover - source is present in a checkout
        source = b"source-unavailable"
    return hashlib.sha256(b"wd-preprocess-v1\0" + PREPROCESS.encode() + b"\0" + source).hexdigest()
