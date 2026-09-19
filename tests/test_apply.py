"""All move-engine fixtures live exclusively below pytest's tmp_path."""
import csv
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from artcurator.db import COLUMNS


def fixture_files(tmp_path: Path, tiers: tuple[str, ...] = ("route_identity",)) -> tuple[Path, Path, list[Path]]:
    out = tmp_path / "out"
    out.mkdir()
    root = tmp_path / "角色们"
    folder = root / "示例角色" / "queue"
    folder.mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text(json.dumps({"characters_root": str(root)}, ensure_ascii=False), encoding="utf-8")
    sources = []
    with (out / "scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for index, tier in enumerate(tiers):
            source = folder / f"示例_日本語_{index}.png"
            data = f"pixels-{index}".encode()
            source.write_bytes(data)
            sources.append(source)
            writer.writerow({"sha16": hashlib.sha256(data).hexdigest()[:16], "abs_path": str(source),
                             "filesize": len(data), "proposed_tier": tier})
    return out, config, sources


def test_plan_generation_when_all_tiers(tmp_path: Path) -> None:
    # Given
    out, config, sources = fixture_files(tmp_path, ("queue", "route_nsfw", "route_identity", "archive_candidate", "review"))
    apply = importlib.import_module("artcurator.apply")
    # When
    plan = apply.make_plan(out, config)
    # Then
    assert [m.dst.parent.name if m.dst else None for m in plan.moves] == ["queue", "safety-review", "身份待核", "归档候选", None]
    assert all(p.exists() for p in sources)
    assert not (sources[0].parent.parent / "身份待核").exists()
    assert (out / "moves_plan.json").is_file()


FROZEN_SCORE_FIELDS = (
    "sha16", "abs_path", "path_rel", "filename", "width", "height", "filesize", "phash",
    "family_id", "aes_v25", "topiq_iaa", "topiq_nr", "nsfw_prob", "identity_sim",
    "confusable_margin", "novelty", "consensus_z", "disagreement", "gaming_delta",
    "flags", "proposed_tier", "thumb_rel",
)


def test_plan_when_frozen_csv_omits_qrealign(tmp_path: Path) -> None:
    # Given the frozen legacy header (22 columns, no qrealign).
    from artcurator import apply
    out, config, sources = fixture_files(tmp_path)
    rows = list(csv.DictReader((out / "scores.csv").read_text(encoding="utf-8").splitlines()))
    with (out / "scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FROZEN_SCORE_FIELDS, quoting=csv.QUOTE_ALL,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    # When
    plan = apply.make_plan(out, config)
    # Then
    assert len(plan.moves) == 1
    assert plan.moves[0].tier == "route_identity"
    assert sources[0].exists()


def test_plan_refuses_when_required_csv_column_missing(tmp_path: Path) -> None:
    # Given a CSV that omits proposed_tier.
    from artcurator import apply
    from artcurator._moves import MoveError
    out, config, sources = fixture_files(tmp_path)
    text = (out / "scores.csv").read_text(encoding="utf-8")
    (out / "scores.csv").write_text(text.replace("proposed_tier", "other_tier"), encoding="utf-8")
    # When / Then
    with pytest.raises(MoveError):
        apply.make_plan(out, config)
    assert sources[0].exists()


@pytest.mark.parametrize("gate", ["missing", "token", "scores", "tamper"])
def test_execute_refuses_when_gate_invalid(tmp_path: Path, gate: str) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import MoveError
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    token = "APPLY-" + plan.digest[:8]
    match gate:
        case "missing":
            (out / "moves_plan.json").unlink()
        case "token":
            token = "wrong"
        case "scores":
            with (out / "scores.csv").open("a", encoding="utf-8") as handle:
                handle.write("\n")
        case "tamper":
            data = json.loads((out / "moves_plan.json").read_text(encoding="utf-8"))
            data["moves"][0]["dst"] = str(tmp_path / "escape.png")
            (out / "moves_plan.json").write_text(json.dumps(data), encoding="utf-8")
    # When / Then
    with pytest.raises((MoveError, OSError)):
        apply.execute(out, token)
    assert sources[0].read_bytes() == b"pixels-0"


def test_copy_verify_remove_when_cjk_filename(tmp_path: Path) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import read_log
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    # When
    apply.execute(out, "APPLY-" + plan.digest[:8])
    # Then
    assert not sources[0].exists()
    assert plan.moves[0].dst.read_bytes() == b"pixels-0"
    entry = read_log(out / "disposition_log.jsonl")[-1]
    assert entry.status == "done"
    assert entry.sha256_before == entry.sha256_after == hashlib.sha256(b"pixels-0").hexdigest()
    assert "示例_日本語" in (out / "disposition_log.jsonl").read_text(encoding="utf-8")


def test_batch_rolls_back_when_copy_hash_mismatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: corrupt only the second forward copy, not the reverse copies.
    from artcurator import _moves, apply
    out, config, sources = fixture_files(tmp_path, ("route_identity",) * 3)
    plan = apply.make_plan(out, config)
    original = _moves.copy_bytes

    def corrupt(src: Path, dst: Path) -> None:
        original(src, dst)
        if src == sources[1]:
            dst.write_bytes(b"corrupt")

    monkeypatch.setattr(_moves, "copy_bytes", corrupt)
    # When
    with pytest.raises(_moves.MoveError):
        apply.execute(out, "APPLY-" + plan.digest[:8])
    # Then: originals all restored; suspect copy retained, never deleted.
    assert [p.read_bytes() for p in sources] == [b"pixels-0", b"pixels-1", b"pixels-2"]
    statuses = [e.status for e in _moves.read_log(out / "disposition_log.jsonl")]
    assert "failed" in statuses and "rolled_back" in statuses


@pytest.mark.parametrize("identical", [True, False])
def test_collision_when_destination_exists(tmp_path: Path, identical: bool) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import read_log
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    dst = plan.moves[0].dst
    dst.parent.mkdir()
    dst.write_bytes(b"pixels-0" if identical else b"other")
    # When
    apply.execute(out, "APPLY-" + plan.digest[:8])
    # Then
    entry = read_log(out / "disposition_log.jsonl")[-1]
    assert entry.status == ("duplicate" if identical else "done")
    assert sources[0].exists() == identical
    assert dst.read_bytes() == (b"pixels-0" if identical else b"other")
    if not identical:
        assert entry.dst.stem.endswith("__" + plan.moves[0].sha16)


def test_undo_round_trip_when_repeated(tmp_path: Path) -> None:
    # Given
    from artcurator import apply, undo
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    # When
    first = undo.revert(out)
    second = undo.revert(out)
    # Then
    assert first == ["undone"] and second == ["already_undone"]
    assert sources[0].read_bytes() == b"pixels-0"
    assert not plan.moves[0].dst.exists()


def test_limit_when_execute(tmp_path: Path) -> None:
    # Given
    from artcurator import apply
    out, config, sources = fixture_files(tmp_path, ("route_identity",) * 2)
    plan = apply.make_plan(out, config)
    # When
    apply.execute(out, "APPLY-" + plan.digest[:8], limit=1)
    # Then
    assert [p.exists() for p in sources] == [False, True]


@pytest.mark.parametrize("args", [[], ["--execute"], ["--confirm", "wrong"]])
def test_cli_when_default_or_incomplete_authorization(tmp_path: Path, args: list[str]) -> None:
    # Given
    out, config, sources = fixture_files(tmp_path)
    # When: API CLI supports tmp_path outputs via main's project root injection in-process below;
    # subprocess uses --help only, keeping production out confinement intact.
    from artcurator import apply
    result = apply.main(["--out", str(out), "--config", str(config), *args], project=tmp_path)
    # Then
    assert result == (0 if not args else 1)
    assert sources[0].exists()


def test_module_entrypoints_when_help_requested(tmp_path: Path) -> None:
    # Given / When
    results = [subprocess.run([sys.executable, "-m", module, "--help"], cwd=tmp_path,
                             capture_output=True, check=False, env={**os.environ, "PYTHONUTF8": "1"})
               for module in ("artcurator.apply", "artcurator.undo")]
    # Then
    assert [r.returncode for r in results] == [0, 0]


def test_guard_when_source_outside_config_root(tmp_path: Path) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import MoveError
    out, config, _ = fixture_files(tmp_path)
    config.write_text(json.dumps({"characters_root": str(tmp_path / "different")}), encoding="utf-8")
    # When / Then
    with pytest.raises(MoveError):
        apply.make_plan(out, config)


def test_undo_refuses_when_destination_modified(tmp_path: Path) -> None:
    # Given
    from artcurator import apply, undo
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    plan.moves[0].dst.write_bytes(b"external edit")
    # When
    results = undo.revert(out)
    # Then
    assert results == ["undo_failed"]
    assert not sources[0].exists()
    assert plan.moves[0].dst.read_bytes() == b"external edit"


def test_symlink_refused_when_destination_is_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: portable link-detection seam (Windows often disallows creating symlinks).
    from artcurator import apply
    from artcurator._moves import MoveError
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == plan.moves[0].dst.parent or original(p))
    # When / Then
    with pytest.raises(MoveError):
        apply.execute(out, "APPLY-" + plan.digest[:8])
    assert sources[0].exists()


def test_undo_recovers_when_interrupted_before_unlink(tmp_path: Path) -> None:
    # Given: emulate the durable done record and both-present crash state.
    from artcurator import apply, undo
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    sources[0].write_bytes(b"pixels-0")
    # When
    result = undo.revert(out)
    # Then
    assert result == ["undone"]
    assert sources[0].read_bytes() == b"pixels-0"
    assert not plan.moves[0].dst.exists()


@pytest.mark.parametrize("target", ["../escape", "身份自定义"])
def test_config_target_when_override_supplied(tmp_path: Path, target: str) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import MoveError
    out, config, sources = fixture_files(tmp_path)
    data = {"characters_root": str(sources[0].parents[2]), "apply": {"route_identity": target}}
    config.write_text(json.dumps(data), encoding="utf-8")
    # When / Then
    if target.startswith(".."):
        with pytest.raises(MoveError):
            apply.make_plan(out, config)
    else:
        assert apply.make_plan(out, config).moves[0].dst.parent.name == target


def test_queue_when_already_in_target(tmp_path: Path) -> None:
    # Given
    from artcurator import apply
    from artcurator._moves import read_log
    out, config, sources = fixture_files(tmp_path, ("queue",))
    plan = apply.make_plan(out, config)
    # When
    apply.execute(out, "APPLY-" + plan.digest[:8])
    # Then
    assert sources[0].read_bytes() == b"pixels-0"
    assert read_log(out / "disposition_log.jsonl")[-1].status == "duplicate"
