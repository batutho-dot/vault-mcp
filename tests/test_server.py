"""End-to-end tests through a real MCP client connected in-process."""

import shutil
from pathlib import Path

import pytest
from mcp import Client

from vault_mcp.server import build_server

TOY = Path(__file__).resolve().parents[1] / "toy-vault"
EXPECTED_TOOLS = {"list_pages", "read_page", "search", "broken_links"}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "vault"
    shutil.copytree(TOY, root)
    (tmp_path / "secret.md").write_text("# Secret\n", encoding="utf-8")
    return build_server(root)


async def test_only_read_only_tools_are_offered(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False


@pytest.mark.parametrize("name", ["write_page", "delete_page", "create_page", "edit_page"])
async def test_write_tools_do_not_exist(server, name):
    async with Client(server) as client:
        try:
            result = await client.call_tool(name, {"path": "index.md", "content": "x"})
        except Exception:
            return  # refused at protocol level
    assert result.is_error


@pytest.mark.parametrize(
    "path", ["../secret.md", "C:\\Windows\\win.ini", "/etc/passwd", "lca/../../secret.md"]
)
async def test_read_page_refuses_outside_paths(server, path):
    async with Client(server) as client:
        result = await client.call_tool("read_page", {"path": path})
    assert result.is_error
    assert "Secret" not in str(result.content)


async def test_read_and_broken_links_work(server):
    async with Client(server) as client:
        page = await client.call_tool("read_page", {"path": "ptx/Electrolysis.md"})
        links = await client.call_tool("broken_links", {})
    assert not page.is_error and "Alkaline" in page.content[0].text
    assert len(links.structured_content["result"]) == 7


async def test_list_pages_unknown_folder_is_a_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool("list_pages", {"folder": "no-such-folder"})
    assert result.is_error
    assert "no such folder" in result.content[0].text


async def test_search_empty_query_is_a_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool("search", {"query": "   "})
    assert result.is_error
    assert "query is empty" in result.content[0].text


def test_missing_vault_exits_with_a_message(tmp_path, capsys):
    from vault_mcp.server import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--vault", str(tmp_path / "missing")])
    assert exit_info.value.code == 2
    assert "vault root is not a folder" in capsys.readouterr().err


def test_default_vault_is_the_toy_vault():
    from vault_mcp.server import DEFAULT_VAULT

    assert DEFAULT_VAULT.is_dir() and (DEFAULT_VAULT / "index.md").is_file()
