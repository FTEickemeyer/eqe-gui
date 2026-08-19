"""
Resolve the version string shown in the GUI's About dialog (see
mainwindow_qt.py's _on_about()).

For a normal `pip install` (including `pip install git+...`), the
installed dist-info's version is always fresh -- pip regenerates it on
every install/upgrade, so importlib.metadata.version() is correct and
that's all this needs.

For an *editable* dev install (`pip install -e .`), that metadata is only
written once, at install time, and does NOT auto-refresh on later
pyproject.toml version bumps or new commits -- even though the actual
code (an editable install just points back at the live source tree)
already reflects them immediately. This bit a real "About says 1.1.0
after already having pulled and installed 1.2.0" mix-up during
development, resolved at the time by manually rerunning
`pip install -e . --no-deps`. To make that automatic instead of a
manual chore every version bump, detect an editable install via its
direct_url.json (PEP 610 -- pip always writes this, with
dir_info.editable=true, for `-e` installs) and read `version` straight
out of that checkout's own pyproject.toml instead, bypassing the stale
cached metadata entirely.
"""

import json
import re
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

PACKAGE_NAME = "eqe-gui"

_VERSION_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')


def _editable_project_root(dist) -> Path | None:
    """
    Return the checkout root of an editable install of `dist`, or None if
    it isn't one (or that can't be determined) -- see module docstring.
    """
    try:
        raw = dist.read_text("direct_url.json")
    except Exception:
        return None

    if not raw:
        return None

    try:
        info = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not info.get("dir_info", {}).get("editable"):
        return None

    url = info.get("url", "")
    if not url.startswith("file://"):
        return None

    return Path(url2pathname(urlparse(url).path))


def _version_from_pyproject(project_root: Path) -> str | None:
    pyproject_path = project_root / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def get_app_version() -> str:
    """
    Best-effort current version of the running app -- prefers the live
    pyproject.toml for an editable install (see module docstring), falls
    back to the installed dist-info version, and finally to a plain
    "not installed as a package" message if neither is available (e.g.
    running straight from source with no install at all).
    """
    try:
        installed_version = version(PACKAGE_NAME)
    except PackageNotFoundError:
        installed_version = None

    try:
        dist = distribution(PACKAGE_NAME)
        project_root = _editable_project_root(dist)
        if project_root is not None:
            live_version = _version_from_pyproject(project_root)
            if live_version is not None:
                return live_version
    except PackageNotFoundError:
        pass

    return installed_version if installed_version is not None else "unknown (not installed as a package)"
