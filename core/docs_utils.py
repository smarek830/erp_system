"""
ERP Documents module – shared utilities.

Path safety
-----------
All paths in the database are stored with forward slashes (POSIX-like).
When accessing the filesystem we use pathlib.Path which works on both Windows
and Linux.  The two helper functions ``docs_root()`` / ``trash_root()`` /
``tmp_root()`` return pathlib.Path objects resolved to absolute paths.

Permission helper
-----------------
``is_docs_admin(user)`` returns True for superusers and members of the
group whose name is configured in ERP_DOCS_ADMIN_GROUP (default: 'docs_admin').
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from pathlib import Path, PurePosixPath

from django.conf import settings


# ---------------------------------------------------------------------------
# Blocked upload extensions (case-insensitive)
# ---------------------------------------------------------------------------
BLOCKED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.ps1', '.sh', '.vbs', '.js', '.jar',
    '.msi', '.dll', '.scr', '.com', '.pif', '.hta', '.wsf',
}


# ---------------------------------------------------------------------------
# Root helpers
# ---------------------------------------------------------------------------

def docs_root() -> Path:
    return Path(getattr(settings, 'ERP_DOCS_ROOT', r'C:\ERP_VAULT\docs'))


def trash_root() -> Path:
    return Path(getattr(settings, 'ERP_TRASH_ROOT', r'C:\ERP_VAULT\trash'))


def tmp_root() -> Path:
    return Path(getattr(settings, 'ERP_TMP_ROOT', r'C:\ERP_VAULT\tmp'))


def trash_retention_days() -> int:
    return int(getattr(settings, 'ERP_TRASH_RETENTION_DAYS', 30))


def docs_admin_group() -> str:
    return getattr(settings, 'ERP_DOCS_ADMIN_GROUP', 'docs_admin')


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

def _normalize_rel(rel_path: str) -> str:
    """Normalise an incoming relative path to forward slashes, strip leading
    slashes/dots so it can safely be joined with a root."""
    # Replace backslashes
    rel = rel_path.replace('\\', '/')
    # Strip leading / or ./
    rel = rel.lstrip('/')
    while rel.startswith('./'):
        rel = rel[2:]
    return rel


def safe_resolve(rel_path: str, root: Path) -> Path:
    """Resolve *rel_path* relative to *root* and raise ValueError if the
    result escapes *root* (path-traversal guard).

    ``rel_path`` may use either forward or backward slashes.  An empty
    ``rel_path`` returns ``root`` itself.
    """
    root = root.resolve()
    if not rel_path or rel_path in ('', '.', '/'):
        return root

    # Normalise slashes before any inspection
    normalized = rel_path.replace('\\', '/')

    # Block absolute paths (starts with '/' or Windows drive, e.g. 'C:/...')
    if normalized.startswith('/') or (len(normalized) >= 2 and normalized[1] == ':'):
        raise ValueError(f"Path traversal attempt blocked (absolute path): {rel_path!r}")

    rel = normalized.lstrip('/')
    while rel.startswith('./'):
        rel = rel[2:]
    if not rel:
        return root

    target = (root / rel).resolve()

    # Ensure target is strictly under root (or equals root).
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal attempt blocked: {rel_path!r}")

    return target


def to_rel(abs_path: Path, root: Path) -> str:
    """Return the forward-slash relative path of *abs_path* from *root*."""
    try:
        rel = abs_path.relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"{abs_path} is not under {root}")
    return rel.as_posix()


def is_extension_blocked(filename: str) -> bool:
    """Return True if the file's extension is in the blocked list."""
    suffix = Path(filename).suffix.lower()
    return suffix in BLOCKED_EXTENSIONS


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------

def is_docs_admin(user) -> bool:
    """Return True if *user* has docs-admin rights (superuser or member of
    the configured docs_admin group)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    group_name = docs_admin_group()
    return user.groups.filter(name=group_name).exists()


# ---------------------------------------------------------------------------
# Filename collision helpers
# ---------------------------------------------------------------------------

def resolve_collision(target_path: Path) -> Path:
    """If *target_path* already exists, return a new path with a numeric
    suffix, e.g. ``file (2).pdf``.  Tries up to 999 times."""
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent
    counter = 2
    while counter < 1000:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

    # Fallback: append a short tag to avoid collision (not used for security)
    import uuid
    tag = uuid.uuid4().hex[:6]
    return parent / f"{stem}_{tag}{suffix}"


def safe_filename(filename: str) -> str:
    """Sanitise a filename: strip path separators and control characters."""
    # Normalise unicode
    name = unicodedata.normalize('NFC', filename)
    # Remove path separators
    name = re.sub(r'[/\\]', '_', name)
    # Remove null bytes and other control chars
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # Collapse leading dots to avoid hidden files on Unix
    name = name.lstrip('.')
    return name or 'upload'
