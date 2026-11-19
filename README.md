# vault-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that lets an AI assistant (Claude Code, Claude Desktop or any MCP client) search and read a folder of Markdown notes, such as an Obsidian vault, and list its broken `[[wikilinks]]`.

[![tests](https://github.com/batutho-dot/vault-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/batutho-dot/vault-mcp/actions/workflows/tests.yml)

**Result:** 10 / 10 questions answered correctly (scored by hand against the notes), using Claude Code with only this server's four tools.

## Run it

Python 3.11 or newer.

```bash
pip install -e ".[test]"
```

```bash
vault-mcp --vault path/to/your/notes
```

## Read-only

It cannot change, create or delete anything. All four tools are marked `readOnlyHint: true`, and no code path writes. It accepts only vault-relative paths and refuses `..`, absolute paths (POSIX, drive letters, UNC), `~`, null bytes, symlinks and Windows junctions, and non-`.md` files. It never follows symlinked folders when listing or searching.

| Tool | What it returns |
|---|---|
| `list_pages(folder="")` | Every `.md` page (path and title), optionally in one subfolder |
| `read_page(path)` | The full text of one page |
| `search(query, limit=10)` | Pages containing every word of the query, ranked by hits, with up to 3 matching lines each |
| `broken_links()` | Each `[[link]]` whose target page does not exist: page, line, target. Links in code are ignored; `[[Page\|alias]]` and `[[Page#Heading]]` are handled |

The checks and a `file:line` table: [docs/architecture.md](docs/architecture.md).

## Results

One run with Claude Code in print mode (`claude -p`, model `sonnet`, 2026-11-19), built-in file tools blocked.

| Check | Result |
|---|---|
| Questions answered correctly (scored by hand against the notes) | **10 / 10** |
| Of those, questions with no answer in the vault, correctly answered "not in the vault" | 2 / 2 |
| Planted broken links found | **7 / 7**, 0 false positives |
| Link inside a code block (should be ignored) | ignored |
| `read_page("../README.md")` | refused: `'..' is refused; paths must stay inside the vault` |
| Cost and time of the run, as reported by Claude Code | 0.195 USD, 17 turns, 19 s |

Test breakdown, method and failures: [docs/details.md](docs/details.md).

## Limits

- One run of 10 questions is a smoke test. I wrote the questions and the notes.
- Search is plain word matching, no stemming, ranked by hit count. Fine for a few hundred notes, not for tens of thousands.
- Pages are read up to 200 kB each.
- Read-only is enforced by the code, not the operating system. For a hard guarantee, run the server as a user with read-only rights on the folder.
- Not tested on macOS. Only Claude Code was tried, not Claude Desktop.

## Data and licence

A toy vault of 21 notes on basic energy and life cycle assessment (LCA) concepts is bundled, so it runs without private notes. I wrote it for this repository; reuse it freely. Code and toy vault: MIT.
