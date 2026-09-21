import importlib.metadata
import tomllib
import unittest
from pathlib import Path

import lvren_jev


class VersionTests(unittest.TestCase):
    def test_runtime_version_matches_installed_distribution_version(self):
        self.assertEqual(
            lvren_jev.__version__,
            importlib.metadata.version("lvren-jev"),
        )

    def test_build_metadata_uses_runtime_version_as_single_source(self):
        project_file = Path(__file__).parents[1] / "pyproject.toml"
        with project_file.open("rb") as stream:
            project = tomllib.load(stream)

        metadata = project["project"]
        self.assertNotIn("version", metadata)
        self.assertIn("version", metadata["dynamic"])
        self.assertEqual(
            project["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "lvren_jev._version.__version__",
        )


if __name__ == "__main__":
    unittest.main()
