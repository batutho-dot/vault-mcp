# Read-only tools over stdio

- **For the user:** an MCP client (Claude Code, Claude Desktop) can list, read and search the notes.
- **How to reach it:** `vault-mcp --vault <folder>` (stdio transport).
- **How verify drives it:** starts the server as a real subprocess over stdio on `toy-vault/`,
  calls `list_pages`, `read_page("ptx/Electrolysis.md")` and `search("coefficient performance")`.
- **End state that proves it worked:** 21 pages; the page text contains "Alkaline"; search
  returns exactly `energy/Heat Pumps.md`.
- **Gotchas:** nothing may print to stdout in the server, or the stdio stream breaks.
