"""File management helpers for A-semantika node attachments.

Provides copy/download/move/detect-mime operations for the ``--img``,
``--filmeto``, and ``--dosiero`` flags on ``nodo aldoni``.

All functions operate on ``pathlib.Path`` objects and return the final
storage path.  Network downloads delegate to ``A.core.http.fetch_binary``
for SSRF-protected, size-limited binary fetching.
"""
from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any, Literal

import typer

from A.core.paths import data_dir

# Subdirectory names inside data_dir()/A-semantika/files/
_ATTACHMENT_SUBDIRS: dict[str, str] = {
    "img": "img",
    "filmeto": "vid",
    "dosiero": "doc",
}


def _files_root() -> Path:
    """Return the root directory for all attachment files."""
    root = data_dir() / "A-semantika" / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_type_dir(attachment_type: str) -> Path:
    """Return (creating if needed) the subdirectory for *attachment_type*.

    Args:
        attachment_type: One of ``"img"``, ``"filmeto"``, ``"dosiero"``.

    Returns:
        Path to the subdirectory (e.g. ``.../files/img/``).
    """
    sub = _ATTACHMENT_SUBDIRS.get(attachment_type, "doc")
    d = _files_root() / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_stem(node_id: str, src: Path) -> str:
    """Return the filename stem for *node_id*, preserving source extension.

    If *src* has a detectable extension (e.g. ``.jpg``), it is appended.
    """
    suffix = src.suffix.lower() if src.suffix else ""
    return f"{node_id}{suffix}"


def detect_mime(path: Path) -> str:
    """Detect MIME type from file extension (fallback to ``application/octet-stream``).

    Args:
        path: Path to the file.

    Returns:
        MIME type string (e.g. ``"image/jpeg"``, ``"video/mp4"``).
    """
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def get_file_size(path: Path) -> int:
    """Return file size in bytes.

    Args:
        path: Path to the file.

    Returns:
        File size in bytes, or 0 if the path does not exist.
    """
    try:
        return path.stat().st_size
    except OSError:
        return 0


def copy_file(
    src: Path,
    node_id: str,
    attachment_type: Literal["img", "filmeto", "dosiero"] = "dosiero",
) -> Path:
    """Copy *src* into the A-semantika files directory.

    The destination filename is ``{node_id}{ext}`` where *ext* is taken
    from *src*.

    Args:
        src: Source file path on local filesystem.
        node_id: Node ID (used as destination filename stem).
        attachment_type: One of ``"img"``, ``"filmeto"``, ``"dosiero"``.

    Returns:
        Destination path that was written to.

    Raises:
        FileNotFoundError: If *src* does not exist.
        OSError: If the copy fails (permissions, disk full, etc.).
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    dest_dir = _ensure_type_dir(attachment_type)
    stem = _resolve_stem(node_id, src)
    dest = dest_dir / stem
    shutil.copy2(str(src), str(dest))
    return dest


def move_file(
    src: Path,
    node_id: str,
    attachment_type: Literal["img", "filmeto", "dosiero"] = "dosiero",
) -> Path:
    """Move *src* into the A-semantika files directory.

    Same naming convention as :func:`copy_file`.

    Args:
        src: Source file path on local filesystem.
        node_id: Node ID (used as destination filename stem).
        attachment_type: One of ``"img"``, ``"filmeto"``, ``"dosiero"``.

    Returns:
        Destination path after the move.

    Raises:
        FileNotFoundError: If *src* does not exist.
        OSError: If the move fails (permissions, cross-filesystem, etc.).
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    dest_dir = _ensure_type_dir(attachment_type)
    stem = _resolve_stem(node_id, src)
    dest = dest_dir / stem
    shutil.move(str(src), str(dest))
    return dest


def download_file(
    url: str,
    node_id: str,
    attachment_type: Literal["img", "filmeto", "dosiero"] = "dosiero",
) -> Path:
    """Download a URL into the A-semantika files directory.

    The filename is ``{node_id}`` without extension (extension unknown
    for URLs).  A best-effort MIME-based extension suffix MAY be added
    in a future version.

    Args:
        url: HTTP or HTTPS URL to download.
        node_id: Node ID (used as destination filename stem).
        attachment_type: One of ``"img"``, ``"filmeto"``, ``"dosiero"``.

    Returns:
        Destination path that was written to.

    Raises:
        ValueError: If the URL scheme is not http/https, or SSRF blocked.
        URLError: If the network request fails.
    """
    from A.core.http import fetch_binary

    data = fetch_binary(url)
    dest_dir = _ensure_type_dir(attachment_type)
    dest = dest_dir / node_id
    dest.write_bytes(data)
    return dest


def delete_file(stored_path: Path) -> None:
    """Delete a previously stored attachment file.

    Silently succeeds if the file does not exist (idempotent).

    Args:
        stored_path: Path to the file (as returned by ``copy_file``,
            ``move_file``, or ``download_file``).
    """
    try:
        stored_path.unlink(missing_ok=True)
    except OSError:
        pass


def is_managed_file(path: Path) -> bool:
    """Check whether *path* lives under the A-semantika files directory.

    Args:
        path: Path to check.

    Returns:
        True if the file is inside ``data_dir()/A-semantika/files/``.
    """
    try:
        root = _files_root().resolve()
        return root in path.resolve().parents
    except OSError:
        return False


_HANDLE_FILE_ATTACHMENT_COLLISION_MAX = 99


def handle_file_attachment(
    img: str | None,
    filmeto: str | None,
    dosiero: str | None,
    en_loko: bool,
    movi: bool,
    node_id_val: str,
) -> list[dict[str, Any]]:
    """Process a file attachment flag and return file metadata triples.

    Args:
        img: Path or URL to image, or None.
        filmeto: Path or URL to video, or None.
        dosiero: Path or URL to arbitrary file, or None.
        en_loko: If True, store reference path instead of copying.
        movi: If True, move the file instead of copying.
        node_id_val: The node ID (used as filename stem in storage).

    Returns:
        List of triple dicts for file metadata, each with keys
        ``predicate``, ``object``, ``object_type``, and optionally
        ``object_datatype``.

    Raises:
        typer.Exit(1): On file operation failure.
    """
    from A import error, tr_multi, warning

    # Determine which flag was used
    attachment_type: str | None = None
    source: str | None = None
    if img:
        attachment_type = "img"
        source = img
    elif filmeto:
        attachment_type = "filmeto"
        source = filmeto
    elif dosiero:
        attachment_type = "dosiero"
        source = dosiero

    if not source:
        return []

    triples: list[dict[str, Any]] = []

    if en_loko:
        # Reference only — no file operation
        triples.append({
            "predicate": ":hasFilePath",
            "object": source,
            "object_type": "literal",
        })
        return triples

    # Determine if source is a URL or local path
    source_lower = source.strip().lower()
    is_url = source_lower.startswith("http://") or source_lower.startswith("https://")

    try:
        if is_url and movi:
            warning(tr_multi(
                "--movi ne efikas por URL; elŝutas anstataŭe.",
                "--movi has no effect on URLs; downloading instead.",
                "--movi n'a pas d'effet sur les URL ; téléchargement à la place.",
            ))

        if is_url:
            stored_path = download_file(source, node_id_val, attachment_type)  # type: ignore[arg-type]
            source_path = source  # Original URL
        elif movi:
            stored_path = move_file(Path(source), node_id_val, attachment_type)  # type: ignore[arg-type]
            source_path = None  # Original moved — no source to record
        else:
            stored_path = copy_file(Path(source), node_id_val, attachment_type)  # type: ignore[arg-type]
            source_path = source  # Original path
    except (FileNotFoundError, OSError, ValueError) as e:
        error(tr_multi(
            "Dosier-eraro: {e}",
            "File error: {e}",
            "Erreur de fichier : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e

    mime_type = detect_mime(stored_path)
    file_size = get_file_size(stored_path)

    triples.append({
        "predicate": ":hasFilePath",
        "object": str(stored_path),
        "object_type": "literal",
    })
    triples.append({
        "predicate": ":hasFileMime",
        "object": mime_type,
        "object_type": "literal",
    })
    triples.append({
        "predicate": ":hasFileSize",
        "object": str(file_size),
        "object_type": "literal",
        "object_datatype": "xsd:integer",
    })
    if source_path:
        triples.append({
            "predicate": ":hasFileSource",
            "object": source_path,
            "object_type": "literal",
        })

    return triples
