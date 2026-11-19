"""Check this repository end to end. Prints `verify: PASS` or `verify: FAIL at <step>: <reason>`.

Steps: compile, tests, a real run of the server over stdio on the toy vault, then a wheel
build that must carry the toy vault (needs pip to fetch hatchling once, so network on a cold cache).
Usage: python verify.py   (uses .venv's Python if present). Changes nothing in the repo.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY if VENV_PY.exists() else Path(sys.executable))
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}


class Fail(Exception):
    pass


def step_compile():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            raise Fail(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    return "all .py files compile"


def step_tests():
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", tmp],
            cwd=ROOT, env=ENV, capture_output=True, text=True,
        )
    last = (r.stdout.strip().splitlines() or ["no output"])[-1]
    if r.returncode != 0:
        raise Fail(last)
    return last


def step_real_run():
    from mcp import Client, StdioServerParameters

    expected = json.loads((ROOT / "verify-features" / "expected_broken_links.json").read_text())
    params = StdioServerParameters(
        command=PY, args=["-m", "vault_mcp.server", "--vault", str(ROOT / "toy-vault")], env=ENV
    )

    async def run():
        async with Client(params) as c:
            pages = (await c.call_tool("list_pages", {})).structured_content["result"]
            page = await c.call_tool("read_page", {"path": "ptx/Electrolysis.md"})
            hits = (await c.call_tool("search", {"query": "coefficient performance"}))
            links = (await c.call_tool("broken_links", {})).structured_content["result"]
            escape = await c.call_tool("read_page", {"path": "../README.md"})
        return pages, page, hits.structured_content["result"], links, escape

    pages, page, hits, links, escape = asyncio.run(run())
    if len(pages) != 21:
        raise Fail(f"list_pages gave {len(pages)} pages, expected 21")
    if page.is_error or "Alkaline" not in page.content[0].text:
        raise Fail("read_page did not return Electrolysis text")
    if [h["path"] for h in hits] != ["energy/Heat Pumps.md"]:
        raise Fail(f"search gave {[h['path'] for h in hits]}")
    if links != expected:
        raise Fail(f"broken_links differs from known-good ({len(links)} vs {len(expected)})")
    if not escape.is_error:
        raise Fail("read_page('../README.md') was not refused")
    return f"stdio server: 21 pages, search ok, broken links {len(links)}/{len(expected)} match, '..' refused"


def step_wheel():
    """The built wheel carries the toy vault, so `pip install .` and `uvx` serve it without --vault."""
    with tempfile.TemporaryDirectory() as out:
        r = subprocess.run(
            [PY, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-q", "-w", out],
            cwd=out, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise Fail("pip wheel failed: " + (r.stderr.strip().splitlines() or ["no output"])[-1])
        (wheel,) = Path(out).glob("vault_mcp-*.whl")
        with zipfile.ZipFile(wheel) as z:
            pages = [n for n in z.namelist() if n.startswith("vault_mcp/toy-vault/") and n.endswith(".md")]
    if len(pages) != 21:
        raise Fail(f"wheel holds {len(pages)} toy-vault pages, expected 21")
    return f"{wheel.name} holds the 21 toy-vault pages"


STEPS = [("compile", step_compile), ("tests", step_tests), ("real-run", step_real_run), ("wheel", step_wheel)]


def main() -> int:
    print(f"verify-repo: {ROOT}")
    for name, fn in STEPS:
        try:
            print(f"{name}: {fn()}")
        except Fail as exc:
            print(f"verify: FAIL at {name}: {exc}")
            return 1
        except Exception as exc:  # an unexpected crash is a failure of that step
            print(f"verify: FAIL at {name}: {type(exc).__name__}: {exc}")
            return 1
    print("verify: PASS")
    return 0


if __name__ == "__main__":
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        sys.exit(subprocess.run([PY, __file__, *sys.argv[1:]]).returncode)
    sys.exit(main())
