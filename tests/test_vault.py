import hashlib
import os
import shutil
import sys
from pathlib import Path

import pytest

from vault_mcp.vault import Vault, VaultError

REPO = Path(__file__).resolve().parents[1]
TOY = REPO / "toy-vault"

# The broken links planted on purpose in the toy vault: (page, missing target).
PLANTED = {
    ("energy/District Heating.md", "Heat Pump"),
    ("energy/Energy Storage.md", "Battery Chemistry"),
    ("energy/Wind Power.md", "Offshore Wind"),
    ("lca/Allocation.md", "Consequential LCA"),
    ("lca/Impact Assessment.md", "Endpoint Indicators"),
    ("lca/System Boundary.md", "Cutoff Rules"),
    ("ptx/Power-to-X.md", "Carbon Capture and Storage"),
}


@pytest.fixture
def vault_dir(tmp_path):
    """A private copy of the toy vault plus a secret file just outside it."""
    root = tmp_path / "vault"
    shutil.copytree(TOY, root)
    (tmp_path / "secret.md").write_text("# Secret\noutside the vault\n", encoding="utf-8")
    (root / "notes.txt").write_text("not markdown\n", encoding="utf-8")
    return root


@pytest.fixture
def vault(vault_dir):
    return Vault(vault_dir)


# ---- normal use --------------------------------------------------------------------------


def test_lists_all_toy_pages():
    pages = Vault(TOY).list_pages()
    assert len(pages) == 21
    assert {"path": "lca/Allocation.md", "title": "Allocation"} in pages


def test_list_subfolder():
    assert {p["path"] for p in Vault(TOY).list_pages("ptx")} == {
        "ptx/Electrolysis.md",
        "ptx/Green Hydrogen.md",
        "ptx/Power-to-X.md",
    }


def test_read_page():
    assert Vault(TOY).read_page("lca/Functional Unit.md").count("reference flow") == 1


def test_search_needs_every_word():
    paths = [h["path"] for h in Vault(TOY).search("coefficient performance")]
    assert paths == ["energy/Heat Pumps.md"]


def test_broken_links_match_planted_set():
    found = {(b.source, b.target) for b in Vault(TOY).broken_links()}
    assert found == PLANTED


def test_links_in_code_are_ignored():
    text = "```\n[[In Fence]]\n```\nuse `[[Inline]]` then [[Real|alias]] and [[Page#Head]]\n"
    assert Vault.links_in(text) == [(4, "Real"), (4, "Page")]


# ---- refusals: paths outside the vault ------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../secret.md",
        "lca/../../secret.md",
        "..\\secret.md",
        "lca\\..\\..\\secret.md",
        "/etc/passwd",
        "\\Windows\\win.ini",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "C:secret.md",
        "\\\\server\\share\\x.md",
        "~/secret.md",
        "lca/Allocation.md\x00.txt",
        "",
        "   ",
    ],
)
def test_refuses_escaping_paths(vault, bad):
    with pytest.raises(VaultError):
        vault.read_page(bad)


def test_refuses_dotdot_even_when_it_stays_inside(vault):
    with pytest.raises(VaultError, match=r"'\.\.'"):
        vault.read_page("lca/../index.md")


def test_refuses_absolute_path_even_inside_vault(vault, vault_dir):
    with pytest.raises(VaultError, match="absolute"):
        vault.read_page(str(vault_dir / "index.md"))


def test_refuses_non_markdown(vault):
    with pytest.raises(VaultError, match=r"\.md"):
        vault.read_page("notes.txt")


def test_refuses_folder(vault):
    with pytest.raises(VaultError):
        vault.read_page("lca")


def test_list_refuses_parent_folder(vault):
    with pytest.raises(VaultError):
        vault.list_pages("../")


# ---- refusals: symlinks and junctions --------------------------------------------------------


def _symlink_or_skip(link: Path, target: Path, is_dir: bool):
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


def test_refuses_symlinked_file(vault, vault_dir):
    _symlink_or_skip(vault_dir / "leak.md", vault_dir.parent / "secret.md", is_dir=False)
    with pytest.raises(VaultError, match="symlink"):
        vault.read_page("leak.md")
    assert "leak.md" not in {p["path"] for p in vault.list_pages()}


def test_refuses_symlinked_folder(vault, vault_dir):
    outside = vault_dir.parent / "outside"
    outside.mkdir()
    (outside / "x.md").write_text("# X\n", encoding="utf-8")
    _symlink_or_skip(vault_dir / "linked", outside, is_dir=True)
    with pytest.raises(VaultError, match="symlink"):
        vault.read_page("linked/x.md")
    assert not any(p["path"].startswith("linked/") for p in vault.list_pages())
    assert all(h["path"] != "linked/x.md" for h in vault.search("x"))


@pytest.mark.skipif(sys.platform != "win32", reason="junctions exist only on Windows")
def test_refuses_windows_junction(vault, vault_dir):
    import _winapi

    outside = vault_dir.parent / "outside_j"
    outside.mkdir()
    (outside / "x.md").write_text("# X\n", encoding="utf-8")
    _winapi.CreateJunction(str(outside), str(vault_dir / "junction"))
    with pytest.raises(VaultError, match="symlink"):
        vault.read_page("junction/x.md")
    assert not any(p["path"].startswith("junction/") for p in vault.list_pages())


def test_symlink_check_runs_on_every_path_part(vault, monkeypatch):
    """Runs everywhere, even where creating real symlinks needs admin rights (Windows)."""
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "lca" or real(p))
    with pytest.raises(VaultError, match="symlink"):
        vault.read_page("lca/Allocation.md")
    assert not any(p["path"].startswith("lca/") for p in vault.list_pages())


@pytest.mark.skipif(sys.platform != "win32", reason="junctions exist only on Windows")
def test_refuses_junction_root(vault_dir):
    import _winapi

    link = vault_dir.parent / "root_junction"
    _winapi.CreateJunction(str(vault_dir), str(link))
    with pytest.raises(VaultError, match="symlink"):
        Vault(link)


def test_refuses_symlinked_root(vault_dir):
    link = vault_dir.parent / "root_link"
    _symlink_or_skip(link, vault_dir, is_dir=True)
    with pytest.raises(VaultError, match="symlink"):
        Vault(link)


# ---- refusals: writes ------------------------------------------------------------------------


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_no_call_changes_any_file(vault, vault_dir):
    before = _fingerprint(vault_dir)
    vault.list_pages()
    for page in vault.list_pages():
        vault.read_page(page["path"])
    vault.search("energy")
    vault.broken_links()
    assert _fingerprint(vault_dir) == before


def test_source_has_no_write_calls():
    import re

    banned = ("write_text", "write_bytes", "unlink", "rmtree", "rename", "os.remove",
              "mkdir", "touch(", "shutil", "os.symlink")
    for path in (REPO / "src" / "vault_mcp").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text, f"{path.name} contains {word}"
        for call in re.findall(r"\bopen\([^)]*\)", text):
            assert '"r"' in call, f"{path.name}: {call} is not read-only"


def test_list_unknown_folder_is_refused(vault):
    with pytest.raises(VaultError, match="no such folder"):
        vault.list_pages("nope")


def test_list_folder_that_is_a_file_is_refused(vault):
    with pytest.raises(VaultError, match="no such folder"):
        vault.list_pages("index.md")
