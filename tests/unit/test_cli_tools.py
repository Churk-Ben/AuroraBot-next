"""验证版本事务、工具分派和终端表格边界。"""

import asyncio
import tomllib
from io import StringIO

import pytest
from aurora_cli.commander import run_cli
from aurora_cli.commands import check, donk
from aurora_cli.utils.table import render_table
from rich.cells import cell_len


def workspace(root):
    (root / "pyproject.toml").write_text(
        '# 根包注释\n[project]\nname = "aurorabot-ai"\nversion = "1.2.3"\n'
        'dependencies = ["aurora-core>=1.2.3"]\n'
        '[tool.uv.workspace]\nmembers = ["packages/core"]\n'
        "[tool.uv.sources]\naurora-core = { workspace = true }\n",
        encoding="utf-8",
    )
    member = root / "packages" / "core"
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text(
        '[project]\nname = "aurora-core"\nversion = "1.2.3"\ndependencies = []\n', encoding="utf-8"
    )
    return [root / "pyproject.toml", member / "pyproject.toml"]


@pytest.mark.parametrize(("action", "expected"), [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4")])
def test_version_update_preserves_comments_and_internal_constraints(tmp_path, monkeypatch, action, expected):
    paths = workspace(tmp_path)

    def lock(command, *, root, output):
        assert command == ["uv", "lock"]
        assert all(tomllib.loads(path.read_text())["project"]["version"] == expected for path in paths)
        (root / "uv.lock").write_text(expected)
        return 0

    monkeypatch.setattr(donk, "run_process", lock)
    assert donk.execute(action, tmp_path, StringIO()) == 0
    assert (tmp_path / "uv.lock").read_text() == expected
    root_content = paths[0].read_text(encoding="utf-8")
    assert "# 根包注释" in root_content
    assert tomllib.loads(root_content)["project"]["dependencies"] == [f"aurora-core>={expected}"]


@pytest.mark.parametrize("existing_lock", [False, True])
def test_lock_failure_restores_all_original_bytes(tmp_path, monkeypatch, existing_lock):
    paths = workspace(tmp_path)
    before = {path: path.read_bytes() for path in paths}
    lock = tmp_path / "uv.lock"
    if existing_lock:
        lock.write_bytes(b"original lock\r\n")

    def fail(command, *, root, output):
        lock.write_text("partial lock")
        return 9

    monkeypatch.setattr(donk, "run_process", fail)
    with pytest.raises(RuntimeError, match="9"):
        donk.execute("patch", tmp_path, StringIO())
    assert {path: path.read_bytes() for path in paths} == before
    assert lock.read_bytes() == b"original lock\r\n" if existing_lock else not lock.exists()


def test_version_mismatch_is_readable_but_cannot_be_bumped(tmp_path):
    paths = workspace(tmp_path)
    paths[1].write_text(paths[1].read_text().replace("1.2.3", "2.0.0"))
    before = {path: path.read_bytes() for path in paths}
    output = StringIO()
    assert donk.execute("show", tmp_path, output) == 0
    assert "aurora-core: 2.0.0" in output.getvalue()
    with pytest.raises(ValueError, match="一致"):
        donk.execute("minor", tmp_path, output)
    assert {path: path.read_bytes() for path in paths} == before


def test_tables_preserve_literals_and_align_multiline_chinese():
    result = render_table(
        ("项目", "内容"),
        [("中文", "第一行\nsecond"), ("标记", "[red]原样[/red]"), ("组合", "e\u0301")],
        banner=("说明", "内容预览"),
    )
    assert "[red]原样[/red]" in result
    assert "\x1b" not in result
    assert result.index("说明") < result.index("项目")
    assert len({cell_len(line) for line in result.splitlines()}) == 1
    with pytest.raises(ValueError, match="列数"):
        render_table(("项目", "内容"), [("缺一列",)])


def test_check_dispatches_flags_and_preserves_failure_status(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check.ts").touch()
    (tmp_path / "package.json").write_text("{}")
    calls = []

    def execute(command, *, root, output):
        calls.append((command, root))
        return 7

    monkeypatch.setattr(check, "run_process", execute)
    status = asyncio.run(run_cli(["--root", str(tmp_path), "check", "--lint", "--fix", "--check"]))
    assert status == 7
    assert calls == [(["pnpm", "run", "check", "--lint", "--fix", "--check"], tmp_path)]
