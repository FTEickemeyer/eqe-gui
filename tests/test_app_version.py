"""
Tests for utils/app_version.py's get_app_version() -- the version shown
in the GUI's About dialog (see mainwindow_qt.py's _on_about()).

Uses a fake importlib.metadata Distribution rather than the real
installed one, so these tests don't depend on (or get thrown off by)
whatever state this specific dev checkout's own install happens to be
in.
"""

import json
import sys
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.utils import app_version


class FakeDistribution:
    def __init__(self, direct_url_json=None):
        self._direct_url_json = direct_url_json

    def read_text(self, filename):
        if filename == "direct_url.json":
            return self._direct_url_json
        return None


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


class EditableProjectRootTests(unittest.TestCase):
    def test_returns_none_when_no_direct_url_json(self):
        dist = FakeDistribution(direct_url_json=None)
        self.assertIsNone(app_version._editable_project_root(dist))

    def test_returns_none_when_not_editable(self):
        payload = json.dumps({"url": "file:///C:/somewhere"})
        dist = FakeDistribution(direct_url_json=payload)
        self.assertIsNone(app_version._editable_project_root(dist))

    def test_returns_none_for_non_file_url(self):
        payload = json.dumps(
            {"dir_info": {"editable": True}, "url": "https://example.com/eqe-gui"}
        )
        dist = FakeDistribution(direct_url_json=payload)
        self.assertIsNone(app_version._editable_project_root(dist))

    def test_returns_none_on_malformed_json(self):
        dist = FakeDistribution(direct_url_json="{not json")
        self.assertIsNone(app_version._editable_project_root(dist))

    def test_returns_path_for_editable_file_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = json.dumps(
                {"dir_info": {"editable": True}, "url": _file_url(root)}
            )
            dist = FakeDistribution(direct_url_json=payload)
            resolved = app_version._editable_project_root(dist)
            self.assertEqual(Path(resolved).resolve(), root.resolve())


class VersionFromPyprojectTests(unittest.TestCase):
    def test_reads_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "eqe-gui"\nversion = "3.4.5"\n', encoding="utf-8"
            )
            self.assertEqual(app_version._version_from_pyproject(root), "3.4.5")

    def test_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(app_version._version_from_pyproject(Path(tmp)))

    def test_returns_none_when_version_key_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "eqe-gui"\n', encoding="utf-8"
            )
            self.assertIsNone(app_version._version_from_pyproject(root))


class GetAppVersionTests(unittest.TestCase):
    def test_prefers_live_pyproject_for_editable_install(self):
        # The core bug this exists to fix: an editable install's cached
        # dist-info metadata (version()) can go stale after a version
        # bump/new commit, even though the checkout's pyproject.toml (and
        # the actual running code) already reflect it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "9.9.9"\n', encoding="utf-8"
            )
            payload = json.dumps(
                {"dir_info": {"editable": True}, "url": _file_url(root)}
            )
            dist = FakeDistribution(direct_url_json=payload)

            with mock.patch.object(app_version, "version", return_value="1.0.0"), \
                 mock.patch.object(app_version, "distribution", return_value=dist):
                self.assertEqual(app_version.get_app_version(), "9.9.9")

    def test_falls_back_to_installed_metadata_when_not_editable(self):
        dist = FakeDistribution(direct_url_json=None)
        with mock.patch.object(app_version, "version", return_value="2.0.0"), \
             mock.patch.object(app_version, "distribution", return_value=dist):
            self.assertEqual(app_version.get_app_version(), "2.0.0")

    def test_falls_back_to_installed_metadata_when_pyproject_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no pyproject.toml written here
            payload = json.dumps(
                {"dir_info": {"editable": True}, "url": _file_url(root)}
            )
            dist = FakeDistribution(direct_url_json=payload)
            with mock.patch.object(app_version, "version", return_value="2.0.0"), \
                 mock.patch.object(app_version, "distribution", return_value=dist):
                self.assertEqual(app_version.get_app_version(), "2.0.0")

    def test_unknown_when_package_not_found_at_all(self):
        with mock.patch.object(
            app_version, "version", side_effect=PackageNotFoundError
        ), mock.patch.object(
            app_version, "distribution", side_effect=PackageNotFoundError
        ):
            self.assertEqual(
                app_version.get_app_version(),
                "unknown (not installed as a package)",
            )


if __name__ == "__main__":
    unittest.main()
