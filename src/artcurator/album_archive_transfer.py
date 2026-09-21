"""No-replace Windows rename: explicit opt-in, inode-bound durable intent."""
import os

from ._moves import safe_path, sha256
from .album_archive_ledger import Ledger, entry_for
from .album_archive_plan import same_volume
from .album_archive_schema import Item, Stamp
from .album_map_schema import MappingError
from .journal import Record


def rename(ledger: Ledger, item: Item) -> None:
    if os.name != "nt" or not same_volume(item.src, item.dst):
        raise MappingError("archive-no-replace-rename-requires-windows-same-volume")
    ledger.append(item, ("rename-intent", None))
    safe_path(item.dst).parent.mkdir(parents=True, exist_ok=True)
    if Stamp.capture(item.src) != item.stamp or sha256(item.src) != item.sha256:
        raise MappingError("archive-rename-source-changed")
    # On Windows os.rename fails if the destination exists; NEVER os.replace.
    os.rename(safe_path(item.src), safe_path(item.dst))
    if Stamp.capture(item.dst) != item.stamp or sha256(item.dst) != item.sha256:
        raise MappingError("archive-rename-target-changed-preserved")
    ledger.append(item, (Stamp.capture(item.dst).model_dump_json(), entry_for(item)))


def recover_rename(ledger: Ledger, item: Item) -> Record | None:
    """A missing source and identical inode/mtime/hash prove the intended rename."""
    prior = ledger.latest(item)
    if prior is not None and prior.entry is None and prior.detail == "rename-intent":
        if (not item.src.exists() and item.dst.is_file() and Stamp.capture(item.dst) == item.stamp
                and sha256(item.dst) == item.sha256):
            ledger.append(item, (Stamp.capture(item.dst).model_dump_json(), entry_for(item)))
            return ledger.latest(item)
    return prior
