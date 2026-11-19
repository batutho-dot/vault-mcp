"""Read-only access to a folder of Markdown notes.

Everything that touches the file system goes through `Vault.resolve`, which refuses any path
that could leave the vault root. Nothing in this module opens a file for writing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

WIKILINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
FENCE = re.compile(r"^(```|~~~)")
MAX_READ_BYTES = 200_000


class VaultError(ValueError):
    """Raised when a request is refused. The message is safe to show to the client."""


@dataclass(frozen=True)
class BrokenLink:
    source: str
    line: int
    target: str


def _is_link(path: Path) -> bool:
    """True for symlinks and, on Windows, junctions."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


class Vault:
    def __init__(self, root: str | os.PathLike[str]):
        root_path = Path(root)
        if not root_path.is_dir():
            raise VaultError(f"vault root is not a folder: {root}")
        if _is_link(root_path):
            raise VaultError("vault root must not be a symlink")
        self.root = root_path.resolve(strict=True)

    # ---- path safety -------------------------------------------------------------------

    def resolve(self, rel: str) -> Path:
        """Turn a vault-relative path into an absolute one, or refuse.

        Refused: empty paths, null bytes, absolute paths (POSIX or Windows, drive letters, UNC),
        any `..` part, any symlink or junction on the way, anything that resolves outside the
        root, and anything that is not an existing `.md` file.
        """
        if not isinstance(rel, str) or not rel.strip():
            raise VaultError("path is empty")
        if "\x00" in rel:
            raise VaultError("path contains a null byte")
        win, posix = PureWindowsPath(rel), PurePosixPath(rel.replace("\\", "/"))
        if win.drive or win.root or posix.is_absolute() or rel.startswith(("/", "\\", "~")):
            raise VaultError("absolute paths are refused; give a path relative to the vault")
        if ".." in posix.parts:
            raise VaultError("'..' is refused; paths must stay inside the vault")

        candidate = self.root
        for part in posix.parts:
            if part in ("", "."):
                continue
            candidate = candidate / part
            if _is_link(candidate):
                raise VaultError("symlinks are refused")

        try:
            real = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError):
            raise VaultError(f"no such page: {rel}") from None
        if not real.is_relative_to(self.root):
            raise VaultError("path resolves outside the vault")
        if not real.is_file() or real.suffix.lower() != ".md":
            raise VaultError("only existing .md files can be read")
        return real

    # ---- listing -----------------------------------------------------------------------

    def _walk(self) -> list[Path]:
        """All .md files under the root, never following symlinked folders or files."""
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            here = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames if not d.startswith(".") and not _is_link(here / d)
            )
            for name in sorted(filenames):
                p = here / name
                if name.lower().endswith(".md") and not _is_link(p):
                    found.append(p)
        return found

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def list_pages(self, folder: str = "") -> list[dict[str, str]]:
        pages = []
        prefix = folder.strip("/\\").replace("\\", "/")
        if prefix:
            if ".." in PurePosixPath(prefix).parts or PureWindowsPath(folder).drive or "\x00" in prefix:
                raise VaultError("folder must be a plain subfolder of the vault")
            sub = self.root / prefix
            if not sub.is_dir() or _is_link(sub):
                raise VaultError(f"no such folder in the vault: {prefix}")
        for p in self._walk():
            rel = self.rel(p)
            if prefix and not rel.startswith(prefix + "/"):
                continue
            pages.append({"path": rel, "title": self._title(p)})
        return pages

    def _title(self, path: Path) -> str:
        for line in self._text(path).splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return path.stem

    @staticmethod
    def _text(path: Path) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_READ_BYTES)

    # ---- reading and searching -----------------------------------------------------------

    def read_page(self, rel: str) -> str:
        return self._text(self.resolve(rel))

    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        terms = [t for t in query.lower().split() if t]
        if not terms:
            raise VaultError("query is empty")
        limit = max(1, min(int(limit), 50))
        hits = []
        for p in self._walk():
            text = self._text(p)
            low = text.lower()
            if not all(t in low for t in terms):
                continue
            score = sum(low.count(t) for t in terms)
            lines = [
                (n, line.strip())
                for n, line in enumerate(text.splitlines(), 1)
                if any(t in line.lower() for t in terms)
            ]
            hits.append(
                {
                    "path": self.rel(p),
                    "title": self._title(p),
                    "score": score,
                    "matches": [{"line": n, "text": t[:200]} for n, t in lines[:3]],
                }
            )
        hits.sort(key=lambda h: (-h["score"], h["path"]))
        return hits[:limit]

    # ---- links ---------------------------------------------------------------------------

    @staticmethod
    def links_in(text: str) -> list[tuple[int, str]]:
        """(line number, target) for every [[wikilink]] outside fenced code and inline code."""
        out = []
        in_fence = False
        for n, line in enumerate(text.splitlines(), 1):
            if FENCE.match(line.lstrip()):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            visible = re.sub(r"`[^`]*`", "", line)
            for m in WIKILINK.finditer(visible):
                target = m.group(1).split("|", 1)[0].split("#", 1)[0].strip()
                if target:
                    out.append((n, target))
        return out

    def broken_links(self) -> list[BrokenLink]:
        """Links whose target matches no page name (file stem) or relative path in the vault.

        Matching ignores case, like Obsidian does on most systems.
        """
        pages = self._walk()
        known = {p.stem.lower() for p in pages}
        known |= {self.rel(p)[:-3].lower() for p in pages}
        broken = []
        for p in pages:
            for line, target in self.links_in(self._text(p)):
                key = target.lower().removesuffix(".md")
                if key not in known:
                    broken.append(BrokenLink(self.rel(p), line, target))
        return broken
