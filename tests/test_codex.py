"""Exercise Codex's documented hook wire format through real subprocesses."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "domain_guard.py"


def run_guard(
    root: Path, tool: str, tool_input: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"cwd": str(root), "tool_name": tool, "tool_input": tool_input}),
        text=True,
        capture_output=True,
        check=False,
        cwd=root,
    )


def test_codex_patch_checks_each_changed_file(tmp_path: Path) -> None:
    (tmp_path / "first.py").write_text("def first(x):\n    return x\n")
    (tmp_path / "second file.py").write_text("from typing import Any\n")
    patch = """*** Begin Patch
*** Add File: first.py
+def first(x):
+    return x
*** Add File: second file.py
+from typing import Any
*** End Patch"""
    result = run_guard(tmp_path, "apply_patch", {"command": patch})
    assert result.returncode == 2
    assert "first.py" in result.stderr
    assert "second file.py" in result.stderr
    assert "UNTYPED" in result.stderr
    assert "ANY" in result.stderr


def test_codex_patch_does_not_report_untouched_legacy_violation(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "def legacy(x):\n    return x\n\ndef added(x: int) -> int:\n    return x\n"
    )
    patch = """*** Begin Patch
*** Update File: module.py
@@
 def legacy(x):
     return x
+
+def added(x: int) -> int:
+    return x
*** End Patch"""
    result = run_guard(tmp_path, "apply_patch", {"command": patch})
    assert result.returncode == 0, result.stderr


def test_codex_patch_checks_moved_file(tmp_path: Path) -> None:
    (tmp_path / "renamed.py").write_text("from typing import Any\n")
    patch = """*** Begin Patch
*** Update File: original.py
*** Move to: renamed.py
@@
-value = 1
+from typing import Any
*** Delete File: gone.py
*** End Patch"""
    result = run_guard(tmp_path, "apply_patch", {"command": patch})
    assert result.returncode == 2
    assert "renamed.py" in result.stderr
    assert "ANY" in result.stderr


def test_codex_move_checks_imports_newly_inside_domain(tmp_path: Path) -> None:
    domain = tmp_path / "domain"
    domain.mkdir()
    (domain / "module.py").write_text("import requests\n")
    result = run_guard(
        tmp_path,
        "apply_patch",
        {
            "command": """*** Begin Patch
*** Update File: module.py
*** Move to: domain/module.py
@@
 import requests
*** End Patch"""
        },
    )
    assert result.returncode == 2
    assert "DOMAIN-DEP" in result.stderr


def test_codex_update_reports_only_added_violation(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("def legacy(x):\n    return x\n\nfrom typing import Any\n")
    result = run_guard(
        tmp_path,
        "apply_patch",
        {
            "command": """*** Begin Patch
*** Update File: module.py
@@
 def legacy(x):
     return x
+
+from typing import Any
*** End Patch"""
        },
    )
    assert result.returncode == 2
    assert "ANY" in result.stderr
    assert "UNTYPED" not in result.stderr


def test_codex_delete_does_not_scan_unmodified_code(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("def legacy(x):\n    return x\n")
    result = run_guard(
        tmp_path,
        "apply_patch",
        {
            "command": """*** Begin Patch
*** Update File: module.py
@@
-from typing import Any
 def legacy(x):
     return x
*** Delete File: removed.py
*** End Patch"""
        },
    )
    assert result.returncode == 0, result.stderr


def test_codex_patch_checks_markdown_language(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "language.md").write_text(
        "| Term | Definition | Not | Avoid |\n|---|---|---|---|\n"
        "| phase | Part of a workflow | A task | stage |\n"
    )
    (tmp_path / "README.md").write_text("Next stage begins.\n")
    result = run_guard(
        tmp_path,
        "apply_patch",
        {
            "command": """*** Begin Patch
*** Add File: README.md
+Next stage begins.
*** End Patch"""
        },
    )
    assert result.returncode == 2
    assert "TERM" in result.stderr


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_claude_file_payload_still_reports_violations(tmp_path: Path, tool: str) -> None:
    path = tmp_path / "module.py"
    path.write_text("from typing import Any\n")
    result = run_guard(
        tmp_path,
        tool,
        {
            "file_path": str(path),
            "new_string": "from typing import Any\n",
        },
    )
    assert result.returncode == 2
    assert "ANY" in result.stderr


def test_codex_manifest_session_hook_loads_filesystem_guidance() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    assert (ROOT / manifest["skills"]).is_dir()
    hooks = json.loads((ROOT / manifest["hooks"]).read_text())["hooks"]
    handler = hooks["SessionStart"][0]["hooks"][0]
    result = subprocess.run(
        ["bash", "-c", handler["command"]],
        env={**os.environ, "PLUGIN_ROOT": str(ROOT)},
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Codex" in output["additionalContext"]
    assert "Read" in output["additionalContext"]
    assert "No Skill tool" in output["additionalContext"]
    assert "modeling-the-domain" in output["additionalContext"]


def test_codex_manifest_patch_hook_reports_real_finding(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("from typing import Any\n")
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    hooks = json.loads((ROOT / manifest["hooks"]).read_text())["hooks"]
    match = next(hook for hook in hooks["PostToolUse"] if re.search(hook["matcher"], "apply_patch"))
    result = subprocess.run(
        ["bash", "-c", match["hooks"][0]["command"]],
        env={
            **os.environ,
            "PLUGIN_ROOT": str(ROOT),
            "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}",
        },
        input=json.dumps(
            {
                "cwd": str(tmp_path),
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": """*** Begin Patch
*** Add File: module.py
+from typing import Any
*** End Patch"""
                },
            }
        ),
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "ANY" in result.stderr


def test_claude_session_hook_keeps_skill_tool_guidance() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "hooks" / "session-start")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert "Load other domain-powers skills with the Skill tool" in output["additionalContext"]
