"""One bounded producer overlaps CPU decode/official resize with GPU batches."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from . import db
from .models import Predictor
from .parallel import ordered_map
from .scan import pixels

if TYPE_CHECKING:
    from torch import Tensor


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    rows: list[db.Row]
    images: list[Image.Image]
    tensors: list[Tensor]


@dataclass(frozen=True, slots=True)
class Prefetch:
    batch_size: int = 16
    workers: int = 8
    batches: int = 2
    transform: Callable[[Image.Image], Image.Image] | None = None


@contextmanager
def batches(rows: list[db.Row], predictor: Predictor, options: Prefetch) -> Iterator[Iterator[PreparedBatch]]:
    """At most batches CPU batches ahead plus the active inference batch.

    A single producer owns the processor. Decode work uses an independent
    worker pool, preventing nested-pool starvation. CUDA stays on the caller.
    batches=0 disables overlap for comparison; workers=1 disables parallel decode.
    """
    def decode(row: db.Row) -> Image.Image:
        image = pixels(Path(row.abs_path))
        if options.transform is None:
            return image
        try:
            return options.transform(image)
        finally:
            image.close()

    with ThreadPoolExecutor(max_workers=options.workers, thread_name_prefix="curator-decode") as pool:
        def prepare(group: list[db.Row]) -> PreparedBatch:
            images = list(pool.map(decode, group))
            if predictor.cpu is None:
                return PreparedBatch(group, images, [])
            try:
                return PreparedBatch(group, [], predictor.cpu.prepare(images))
            finally:
                for image in images:
                    image.close()

        groups = (rows[start:start + options.batch_size] for start in range(0, len(rows), options.batch_size))
        if options.batches == 0:
            yield map(prepare, groups)
        else:
            with ordered_map(prepare, groups, workers=1, capacity=options.batches + 1) as prepared:
                yield prepared
