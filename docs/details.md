# Details

## Run

Without `--vault` (or `$VAULT_ROOT`) it serves the bundled `toy-vault/`. The wheel carries it, so a plain `pip install .` or, with [uv](https://docs.astral.sh/uv/), `uvx --from . vault-mcp` from a clone serves it too. A `--vault` folder that does not exist stops the server with one line.

Add it to Claude Code from the repository folder:

```bash
claude mcp add vault -- vault-mcp --vault ./toy-vault
```

For Claude Desktop, add an entry under `mcpServers` in `claude_desktop_config.json` with `"command": "vault-mcp"` and `"args": ["--vault", "/absolute/path/to/notes"]`.

## Example

Asked "what is the COP of a heat pump?", the model calls `search(query="coefficient performance")` and gets:

```json
[
  {
    "path": "energy/Heat Pumps.md",
    "title": "Heat Pumps",
    "score": 2,
    "matches": [
      {"line": 11, "text": "Its efficiency is the coefficient of performance (COP): heat delivered divided by electricity"}
    ]
  }
]
```

It then calls `read_page(path="energy/Heat Pumps.md")` for the full note. `read_page(path="../README.md")` comes back as a tool error: `'..' is refused; paths must stay inside the vault`.

## Tests

```bash
pytest -rs
```

49 tests. `tests/test_vault.py` has 35: 6 normal use, 21 refusals (paths and folders), 6 symlink and junction cases, 2 write checks. `tests/test_server.py` has 14 end-to-end cases through a real in-process MCP client, plus start-up checks (missing vault folder, default toy vault). On my machine (Windows 11, Python 3.13, `mcp` 2.3.0): **46 passed, 3 skipped**. The 3 skipped tests create real symlinks, which Windows allows only with admin rights or Developer Mode. A junction test and a test that fakes a symlink on one path part cover the same logic.

`python verify.py` takes about 6 seconds. It compiles, runs the tests, starts the server over stdio on the toy vault and compares its `broken_links` output with `verify-features/expected_broken_links.json`, then builds the wheel and checks it carries the 21 toy-vault pages. It ends with `verify: PASS` or `verify: FAIL at <step>: <reason>`. `verify-features/` describes each check. GitHub Actions runs the tests and `verify.py` on every push, on Ubuntu (Python 3.11 and 3.13) and Windows (3.13).

The write checks: the tool list is exactly the four read tools, all read-only. Calls to `write_page`, `delete_page`, `create_page` and `edit_page` fail. Every file in the vault has the same SHA-256 hash before and after every tool call. The source contains no file-writing call.

## The Claude Code run

`eval/questions.md` holds 10 questions with known answers in the toy vault, plus a broken-link check and an escape attempt. I ran them once with Claude Code in print mode (`claude -p`, model `sonnet`, 2026-11-19), with only this server's four tools allowed and the built-in file tools blocked. Results table: [README](../README.md#results). The planted broken links are listed in `tests/test_vault.py` (`PLANTED`), and a test checks that `broken_links()` returns exactly that set.

## What failed or is weak

- Question 8 ("which pages link to District Heating?") was answered by text search. There is no backlinks tool, so a page that mentions the name without linking would count too.
- My first source check banned the word `symlink` and failed on the server's own docstring. It now bans `os.symlink` only.
- Deleting the `..` rule on purpose broke no test, because the second check (resolve the path, confirm it is inside the vault) still blocked every escape. Safe, but the `..` rule itself was untested. A test now asks for `lca/../index.md`, which stays inside the vault and must still be refused.

## More on limits

- Link matching is by file name or vault-relative path, case-insensitive, like Obsidian's default. Links to images and other attachments are reported as broken.
