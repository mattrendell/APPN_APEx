"""Resolve ``DataLocation.yaml`` pointer files (multi-root data trees).

A directory whose data lives outside this repository holds a git-tracked
``DataLocation.yaml`` pointer instead of data. The pointer re-roots the
subtree beneath it: a path under the pointer's directory maps to the same
relative path under ``data_root``. Pointers are host-keyed because they
are git-tracked — the same bytes land on every machine the repo reaches,
and the external mount point differs on each.

Host identity is ``$APEX_DATA_HOST`` when set, else the short (lowercased,
cut at the first dot) ``socket.gethostname()``, matched case-insensitively
against each root's ``host`` and ``aliases``.

Three outcomes, three behaviours (workspace plan, step 8):

- matched host + existing ``data_root``  -> the re-rooted path;
- matched host + ``data_root`` missing on disk -> ``FileNotFoundError``;
- no entry for this host -> :class:`DataLocationUnavailable`, a distinct
  "not reachable from here" signal that sweeps log-and-skip while explicit
  single-target runs treat as fatal. There is deliberately no ``default``
  root: an unlisted host must not guess.

``read_only`` is dataset-wide with an optional per-root override; the
resolver refuses to return a read-only root as a *write* target, which
protects the inviolate master copy at the code level.
"""

import os
import socket
import pathlib
from typing import Any, Dict, List, Optional, Tuple

import yaml

POINTER_NAME = "DataLocation.yaml"
POINTER_SCHEMA = "DataLocation/1"


# ==================================================================================
class DataLocationUnavailable(Exception):
    """The pointed-at data is not reachable from this host.

    Raised when a ``DataLocation.yaml`` has no root entry matching the
    current host identity. Sweeps should catch this, log the subtree,
    and skip it; scripts pointed explicitly at the subtree should let
    it propagate.
    """


# ==================================================================================
def host_identity() -> str:
    """Return the host identity used to key ``DataLocation.yaml`` roots.

    Returns
    -------
    str
        ``$APEX_DATA_HOST`` (stripped, lowercased) when set — the escape
        hatch for hosts whose name is unstable or duplicated — else the
        short hostname: ``socket.gethostname()`` lowercased and cut at
        the first dot.
    """
    env = os.environ.get("APEX_DATA_HOST")
    if env and env.strip():
        return env.strip().lower()
    return socket.gethostname().lower().split(".", 1)[0]


# ==================================================================================
def load_pointer(pointer_file: pathlib.Path) -> Dict[str, Any]:
    """Load and validate a ``DataLocation.yaml`` pointer file.

    Parameters
    ----------
    pointer_file : pathlib.Path
        Path to the pointer file.

    Returns
    -------
    dict
        The parsed document.

    Raises
    ------
    ValueError
        If the schema marker is missing/unknown or ``roots`` is not a
        list of mappings with ``host`` and ``data_root``.
    """
    with open(pointer_file, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict) or doc.get("schema") != POINTER_SCHEMA:
        raise ValueError(
            f"{pointer_file}: expected 'schema: {POINTER_SCHEMA}', "
            f"got {doc.get('schema') if isinstance(doc, dict) else doc!r}")
    roots = doc.get("roots")
    if not isinstance(roots, list) or not all(
            isinstance(r, dict) and r.get("host") and r.get("data_root")
            for r in roots):
        raise ValueError(
            f"{pointer_file}: 'roots' must be a list of mappings with "
            "'host' and 'data_root'")
    return doc


# ==================================================================================
def resolve_root(
        pointer_file: pathlib.Path,
        write: bool = False,
    ) -> pathlib.Path:
    """Resolve a pointer file to this host's ``data_root``.

    Parameters
    ----------
    pointer_file : pathlib.Path
        The ``DataLocation.yaml`` to resolve.
    write : bool, optional
        The caller intends to write under the root. Default False.

    Returns
    -------
    pathlib.Path
        The ``data_root`` of the entry matching this host.

    Raises
    ------
    DataLocationUnavailable
        No root entry matches this host (data not reachable from here).
    FileNotFoundError
        This host is listed but its ``data_root`` does not exist on disk.
    PermissionError
        ``write=True`` and the matched root is read-only.
    """
    doc = load_pointer(pointer_file)
    ident = host_identity()
    for root in doc["roots"]:
        names = {str(root["host"]).lower()}
        names.update(str(a).lower() for a in root.get("aliases") or [])
        if ident not in names:
            continue
        if write and root.get("read_only", doc.get("read_only", False)):
            raise PermissionError(
                f"{pointer_file}: root for host '{ident}' is read-only "
                f"({doc.get('reason', 'no reason recorded')}); refusing "
                "to return it as a write target")
        data_root = pathlib.Path(root["data_root"])
        if not data_root.is_dir():
            raise FileNotFoundError(
                f"{pointer_file}: host '{ident}' is listed but its "
                f"data_root does not exist on disk: {data_root}")
        return data_root
    raise DataLocationUnavailable(
        f"{pointer_file}: no root for host '{ident}' - this data is not "
        "reachable from this machine (add a host entry to the pointer "
        "file, or set $APEX_DATA_HOST to a listed identity)")


# ==================================================================================
def find_pointer(path: pathlib.Path) -> Optional[pathlib.Path]:
    """Find the nearest ``DataLocation.yaml`` at or above ``path``.

    Parameters
    ----------
    path : pathlib.Path
        Any path inside the tree (need not exist).

    Returns
    -------
    pathlib.Path or None
        The nearest pointer file walking upward, or None.
    """
    p = pathlib.Path(path)
    for d in (p, *p.parents):
        cand = d / POINTER_NAME
        if cand.is_file():
            return cand
    return None


# ==================================================================================
def resolve_path(path: pathlib.Path, write: bool = False) -> pathlib.Path:
    """Re-root ``path`` through the nearest pointer above it.

    Parameters
    ----------
    path : pathlib.Path
        Any path inside the tree.
    write : bool, optional
        The caller intends to write at the resolved location.

    Returns
    -------
    pathlib.Path
        ``data_root / <path relative to the pointer's directory>`` when a
        pointer governs ``path``; ``path`` unchanged when none does.

    Raises
    ------
    DataLocationUnavailable, FileNotFoundError, PermissionError
        Propagated from :func:`resolve_root` (an explicit target that is
        unavailable here is fatal by design).
    """
    p = pathlib.Path(path)
    pointer = find_pointer(p)
    if pointer is None:
        return p
    root = resolve_root(pointer, write=write)
    rel = p.absolute().relative_to(pointer.parent.absolute())
    return root / rel


# ==================================================================================
def sweep_roots(
        path: pathlib.Path,
    ) -> Tuple[List[Tuple[pathlib.Path, pathlib.Path]], List[str]]:
    """Crawl roots for a sweep of ``path``, following pointers (read side).

    The first pair covers ``path`` itself (re-rooted when a pointer above
    it governs it — unavailable there is fatal, the caller asked for that
    subtree explicitly). One further pair is added per pointer strictly
    below ``path`` that resolves on this host; pointers whose data is not
    reachable from here are skipped and reported, not raised.

    Parameters
    ----------
    path : pathlib.Path
        The sweep/crawl root as given (repo-side path).

    Returns
    -------
    tuple[list[tuple[pathlib.Path, pathlib.Path]], list[str]]
        ``(pairs, skipped)`` where each pair is ``(real_root,
        virtual_root)`` — crawl ``real_root`` on disk, and map each hit
        ``f`` to its repo-side identity ``virtual_root /
        f.relative_to(real_root)`` — and ``skipped`` holds one message
        per unavailable pointer.
    """
    p = pathlib.Path(path)
    pairs = [(resolve_path(p), p)]
    skipped: List[str] = []
    for pointer in sorted(p.rglob(POINTER_NAME)):
        try:
            data_root = resolve_root(pointer)
        except DataLocationUnavailable as err:
            skipped.append(str(err))
            continue
        pairs.append((data_root, pointer.parent))
    return pairs, skipped
