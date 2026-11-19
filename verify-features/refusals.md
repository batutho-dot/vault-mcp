# Path and write refusals

- **For the user:** the assistant cannot read outside the vault or change anything in it.
- **How to reach it:** any tool call with a bad path; any call to a write tool.
- **How verify drives it:** the pytest suite (32 vault tests, 10 client tests), plus a live
  `read_page("../README.md")` over stdio that must come back as an error.
- **End state that proves it worked:** error result; the toy vault hashes are unchanged.
- **Gotchas:** 3 tests create real symlinks and skip on Windows without admin rights or
  Developer Mode. Junction and fake-symlink tests cover the same check there.
