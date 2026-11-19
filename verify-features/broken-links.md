# Broken wikilink report

- **For the user:** finds `[[links]]` to pages that do not exist.
- **How to reach it:** the `broken_links` tool.
- **How verify drives it:** calls it over stdio on `toy-vault/` and compares the result with
  `expected_broken_links.json` (the 7 links planted on purpose).
- **End state that proves it worked:** exact match, page, line and target.
- **Gotchas:** editing a toy note shifts line numbers; update the expected file in the same change.
