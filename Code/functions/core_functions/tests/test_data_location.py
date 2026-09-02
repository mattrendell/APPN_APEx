"""Tests for the DataLocation.yaml resolver (data_location.py).

Pointer files and data roots are built in tmp_path; host identity is
controlled through the $APEX_DATA_HOST escape hatch so the suite runs
identically on any machine.

Run with:
    pytest Code/functions/core_functions/tests/test_data_location.py -v
"""

import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is importable
# ---------------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Code.functions.core_functions import data_location as dl  # type: ignore # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def host(monkeypatch):
    """Pin the host identity to 'testhost' via the env escape hatch."""
    monkeypatch.setenv("APEX_DATA_HOST", "TestHost")  # case-insensitive
    return "testhost"


def _write_pointer(project_dir: pathlib.Path, data_root: pathlib.Path,
                   host: str = "testhost", read_only: bool = True,
                   aliases=None, root_read_only=None) -> pathlib.Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    root_entry = {"host": host, "data_root": str(data_root)}
    if aliases:
        root_entry["aliases"] = aliases
    if root_read_only is not None:
        root_entry["read_only"] = root_read_only
    import yaml
    doc = {"schema": "DataLocation/1", "read_only": read_only,
           "reason": "test", "roots": [root_entry]}
    pointer = project_dir / dl.POINTER_NAME
    pointer.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return pointer


@pytest.fixture
def tree(tmp_path, host):
    """A repo-like tree with one redirected project and a real data root."""
    repo = tmp_path / "repo"
    estate = tmp_path / "estate" / "2026_APEx"
    run = estate / "2026Site" / "GOBI" / "20260101" / "run_00"
    run.mkdir(parents=True)
    (run / "data.txt").write_text("x")
    project = repo / "USYD" / "2026_APEx"
    pointer = _write_pointer(project, estate)
    # a normal, non-redirected project too
    (repo / "AU" / "2026_APEx").mkdir(parents=True)
    return {"repo": repo, "estate": estate, "project": project,
            "pointer": pointer}


# ===========================================================================
# host_identity
# ===========================================================================
def test_host_identity_env_wins(monkeypatch):
    monkeypatch.setenv("APEX_DATA_HOST", "  Mint ")
    assert dl.host_identity() == "mint"


def test_host_identity_short_hostname(monkeypatch):
    monkeypatch.delenv("APEX_DATA_HOST", raising=False)
    monkeypatch.setattr(dl.socket, "gethostname",
                        lambda: "ArdenAPPN.local.domain")
    assert dl.host_identity() == "ardenappn"


# ===========================================================================
# load_pointer validation
# ===========================================================================
def test_load_pointer_bad_schema(tmp_path, host):
    p = tmp_path / dl.POINTER_NAME
    p.write_text("schema: DataLocation/99\nroots: []\n")
    with pytest.raises(ValueError, match="schema"):
        dl.load_pointer(p)


def test_load_pointer_bad_roots(tmp_path, host):
    p = tmp_path / dl.POINTER_NAME
    p.write_text("schema: DataLocation/1\nroots:\n  - host: x\n")
    with pytest.raises(ValueError, match="roots"):
        dl.load_pointer(p)


# ===========================================================================
# resolve_root: the three outcomes + write refusal
# ===========================================================================
def test_resolve_root_matched(tree):
    assert dl.resolve_root(tree["pointer"]) == tree["estate"]


def test_resolve_root_alias_case_insensitive(tmp_path, host):
    estate = tmp_path / "estate"
    estate.mkdir()
    pointer = _write_pointer(tmp_path / "proj", estate, host="other",
                             aliases=["TESTHOST", "spare"])
    assert dl.resolve_root(pointer) == estate


def test_resolve_root_unlisted_host_distinct_signal(tmp_path, host):
    estate = tmp_path / "estate"
    estate.mkdir()
    pointer = _write_pointer(tmp_path / "proj", estate, host="someoneelse")
    with pytest.raises(dl.DataLocationUnavailable):
        dl.resolve_root(pointer)


def test_resolve_root_listed_but_missing_is_hard_error(tmp_path, host):
    pointer = _write_pointer(tmp_path / "proj", tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        dl.resolve_root(pointer)


def test_resolve_root_refuses_readonly_write(tree):
    with pytest.raises(PermissionError):
        dl.resolve_root(tree["pointer"], write=True)


def test_resolve_root_per_root_readonly_override(tmp_path, host):
    estate = tmp_path / "estate"
    estate.mkdir()
    pointer = _write_pointer(tmp_path / "proj", estate,
                             read_only=True, root_read_only=False)
    assert dl.resolve_root(pointer, write=True) == estate


# ===========================================================================
# find_pointer / resolve_path
# ===========================================================================
def test_find_pointer_walks_up(tree):
    deep = tree["project"] / "2026Site" / "GOBI"
    assert dl.find_pointer(deep) == tree["pointer"]


def test_find_pointer_none(tree):
    assert dl.find_pointer(tree["repo"] / "AU" / "2026_APEx") is None


def test_resolve_path_reroots(tree):
    virt = tree["project"] / "2026Site" / "GOBI" / "20260101" / "run_00"
    assert dl.resolve_path(virt) == (
        tree["estate"] / "2026Site" / "GOBI" / "20260101" / "run_00")


def test_resolve_path_no_pointer_unchanged(tree):
    p = tree["repo"] / "AU" / "2026_APEx"
    assert dl.resolve_path(p) == p


def test_resolve_path_unavailable_is_fatal(tmp_path, monkeypatch, host):
    estate = tmp_path / "estate"
    estate.mkdir()
    proj = tmp_path / "proj"
    _write_pointer(proj, estate, host="someoneelse")
    with pytest.raises(dl.DataLocationUnavailable):
        dl.resolve_path(proj / "2026Site")


# ===========================================================================
# sweep_roots
# ===========================================================================
def test_sweep_roots_direct_plus_pointer(tree):
    pairs, skipped = dl.sweep_roots(tree["repo"])
    assert skipped == []
    assert pairs[0] == (tree["repo"], tree["repo"])
    assert (tree["estate"], tree["project"]) in pairs


def test_sweep_roots_unavailable_logged_not_raised(tmp_path, host):
    repo = tmp_path / "repo"
    estate = tmp_path / "estate"
    estate.mkdir()
    _write_pointer(repo / "USYD" / "2026_APEx", estate, host="someoneelse")
    pairs, skipped = dl.sweep_roots(repo)
    assert pairs == [(repo, repo)]
    assert len(skipped) == 1 and "someoneelse" not in skipped[0]


def test_sweep_roots_inside_redirected_project(tree):
    """Crawling below the pointer re-roots the primary pair itself."""
    site = tree["project"] / "2026Site"
    pairs, skipped = dl.sweep_roots(site)
    assert pairs == [(tree["estate"] / "2026Site", site)]
    assert skipped == []
