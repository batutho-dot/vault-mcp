"""MCP server exposing a Markdown vault through four read-only tools.

Run:  python -m vault_mcp.server --vault path/to/notes
Logs go to stderr; stdout carries the MCP messages and must stay clean.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from vault_mcp.vault import Vault, VaultError

log = logging.getLogger("vault_mcp")

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
DEFAULT_VAULT = Path(__file__).resolve().parents[2] / "toy-vault"


def build_server(vault_root: str | os.PathLike[str]) -> MCPServer:
    vault = Vault(vault_root)
    mcp = MCPServer(
        "vault-mcp",
        instructions=(
            "Read-only access to a folder of Markdown notes. Paths are relative to the vault "
            "root. There are no tools that create, change or delete files."
        ),
    )

    def guarded(fn, *args):
        try:
            return fn(*args)
        except VaultError as exc:
            log.info("refused: %s", exc)
            raise ToolError(str(exc)) from None

    @mcp.tool(annotations=READ_ONLY)
    def list_pages(folder: str = "") -> list[dict[str, str]]:
        """List every Markdown page in the vault with its title.

        Args:
            folder: Optional subfolder to list, relative to the vault root (for example "lca").
        """
        return guarded(vault.list_pages, folder)

    @mcp.tool(annotations=READ_ONLY)
    def read_page(path: str) -> str:
        """Return the full Markdown text of one page.

        Args:
            path: Path relative to the vault root, as returned by list_pages
                (for example "lca/Allocation.md").
        """
        return guarded(vault.read_page, path)

    @mcp.tool(annotations=READ_ONLY)
    def search(query: str, limit: int = 10) -> list[dict]:
        """Find pages containing all the words in the query (case-insensitive).

        Results are ranked by how often the words occur and show up to three matching lines.

        Args:
            query: One or more words; a page must contain every word to match.
            limit: Maximum number of pages to return (1 to 50).
        """
        return guarded(vault.search, query, limit)

    @mcp.tool(annotations=READ_ONLY)
    def broken_links() -> list[dict]:
        """List [[wikilinks]] that point to a page that does not exist in the vault.

        Links inside code blocks and inline code are ignored. Each result gives the page the
        link is on, the line number and the missing target.
        """
        return [b.__dict__ for b in guarded(vault.broken_links)]

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        default=os.environ.get("VAULT_ROOT", str(DEFAULT_VAULT)),
        help="folder of Markdown notes (default: the bundled toy vault, or $VAULT_ROOT)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    log.info("serving vault %s", Path(args.vault).resolve())
    build_server(args.vault).run(transport="stdio")


if __name__ == "__main__":
    main()
