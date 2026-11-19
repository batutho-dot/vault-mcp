# Path and write refusals

- **For the user:** the assistant cannot read outside the vault or change anything in it.
- **How to reach it:** any tool call with a bad path; any call to a write tool.
- **How verify drives it:** the pytest suite (35 vault tests, 14 client tests; unknown folders in
  `list_pages` and a missing vault root are refused too), plus a live
  `read_page("../README.md")` over stdio that must come back as an error.
- **End state that proves it worked:** error result; the toy vault hashes are unchanged.
- **Gotchas:** 3 tests create real symlinks and skip on Windows without admin rights or
  Developer Mode. Junction and fake-symlink tests cover the same check there.
