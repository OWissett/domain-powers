import json
from pathlib import Path

import core
import pytest

BASE: dict[str, int | None] = {
    "unit_cycle_members": 0,
    "edges_into_internals": 1,
    "escapes": 3,
    "framework_refs_non_generic": 2,
    "unassigned_units": 4,
}
TARGET_A: dict[str, object] = {"contexts": {"a": {"paths": ["a/*"]}}}
TARGET_B: dict[str, object] = {"contexts": {"b": {"paths": ["b/*"]}}}


def result(
    ratchet: dict[str, int | None], target: dict[str, object] | None = None
) -> dict[str, object]:
    return {"schema": core.RESULT_SCHEMA, "target": target, "ratchet": ratchet}


def row(report: str, metric: str) -> list[str]:
    for line in report.splitlines():
        if line.split()[:1] == [metric]:
            return line.split()
    raise AssertionError(f"no row {metric}")


def test_increase_fails() -> None:
    code, text = core.compare(result(BASE), result({**BASE, "escapes": 4}))
    assert code == 1
    assert row(text, "escapes") == ["escapes", "3", "4", "+1", "INCREASED"]


def test_equal_passes() -> None:
    code, text = core.compare(result(BASE), result(BASE))
    assert code == 0
    assert {row(text, m)[-1] for m in core.RATCHET_METRICS} == {"ok"}
    assert text.splitlines()[0].split() == ["metric", "baseline", "current", "delta", "status"]


def test_decrease_is_progress() -> None:
    code, text = core.compare(result(BASE), result({**BASE, "escapes": 1}))
    assert code == 0
    assert row(text, "escapes") == ["escapes", "3", "1", "-2", "progress"]


def test_schema_mismatch() -> None:
    bad = {**result(BASE), "schema": "other/9"}
    code, text = core.compare(bad, result(BASE))
    assert code == 2
    assert text == f"baseline schema other/9, current schema {core.RESULT_SCHEMA}"


def test_differing_targets_skip_target_dependent() -> None:
    code, text = core.compare(
        result(BASE, TARGET_A), result({**BASE, "edges_into_internals": 9}, TARGET_B)
    )
    assert code == 0
    assert text.splitlines()[0] == "targets differ: checking target-independent metrics only"
    assert row(text, "edges_into_internals")[-1] == "n/a"
    assert row(text, "escapes")[-1] == "ok"


def test_baseline_without_target() -> None:
    code, text = core.compare(result(BASE), result({**BASE, "unassigned_units": 99}, TARGET_A))
    assert code == 0
    assert text.startswith("targets differ")
    assert row(text, "unassigned_units")[-1] == "n/a"


def test_same_target_checks_target_dependent() -> None:
    code, _ = core.compare(
        result(BASE, TARGET_A), result({**BASE, "unassigned_units": 5}, TARGET_A)
    )
    assert code == 1


def test_null_metric_is_not_applicable() -> None:
    code, text = core.compare(result(BASE), result({**BASE, "escapes": None}))
    assert code == 0
    assert row(text, "escapes") == ["escapes", "3", "n/a", "n/a", "n/a"]


@pytest.mark.parametrize(
    "bad",
    [
        {"schema": core.RESULT_SCHEMA, "target": None},
        {"schema": core.RESULT_SCHEMA, "target": None, "ratchet": []},
        {"schema": core.RESULT_SCHEMA, "target": None, "ratchet": {**BASE, "escapes": "3"}},
        result({k: v for k, v in BASE.items() if k != "escapes"}),
    ],
)
def test_malformed_ratchet_is_schema_error(bad: object) -> None:
    code, text = core.compare(result(BASE), bad)
    assert code == 2
    assert "ratchet" in text


def test_non_object_is_schema_error() -> None:
    assert core.compare([], result(BASE))[0] == 2


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base, cur = tmp_path / "b.json", tmp_path / "c.json"
    base.write_text(json.dumps(result(BASE)))
    cur.write_text(json.dumps(result(BASE)))
    assert core.main(["compare", "--baseline", str(base), "--current", str(cur)]) == 0
    assert "escapes" in capsys.readouterr().out
    cur.write_text(json.dumps(result({**BASE, "escapes": 9})))
    assert core.main(["compare", "--baseline", str(base), "--current", str(cur)]) == 1
    capsys.readouterr()
    missing = str(tmp_path / "none.json")
    assert core.main(["compare", "--baseline", missing, "--current", str(cur)]) == 2
    assert capsys.readouterr().err
    cur.write_text("not json")
    assert core.main(["compare", "--baseline", str(base), "--current", str(cur)]) == 2
