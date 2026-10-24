import ast
import os
import tempfile
import unittest
from pathlib import Path

from stocktrading import config, fundamentals, institutions, analysis_evidence
from stocktrading.intraday_engine import load_rules


class StructureTests(unittest.TestCase):
    def test_application_imports_use_package_namespace(self):
        source = config.PROJECT_ROOT / "stocktrading"
        names = {file.stem for file in source.glob("*.py")}
        for file in [config.PROJECT_ROOT / "dashboard.py", *source.glob("*.py")]:
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertNotIn(node.module, names, f"{file.name}:{node.lineno}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name, names, f"{file.name}:{node.lineno}")

    def test_paths_do_not_depend_on_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(load_rules()["version"], "3.0")
                self.assertTrue(analysis_evidence.GUIDE.is_file())
                self.assertTrue((config.DOCS_DIR / "MODEL_SETUP.md").is_file())
                self.assertTrue((config.RESOURCE_DIR / "research_catalog.json").is_file())
                expected_db = config.PROJECT_ROOT / "db"
                self.assertEqual(Path(config.DB_PATH).parent, expected_db)
                self.assertEqual(Path(config.TOKEN_FILE).parent, expected_db)
                self.assertEqual(fundamentals.DEFAULT_DB_PATH.parent, expected_db)
                self.assertEqual(institutions.DEFAULT_DB_PATH.parent, expected_db)
                self.assertEqual(analysis_evidence.AUDIT_DB.parent, expected_db)
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
