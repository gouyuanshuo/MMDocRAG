"""Portable input paths and restored artifact identity (no model/API calls)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expkit import paths
from expkit.artifacts import Registry, digest_path


class UbuntuMigrationTests(unittest.TestCase):
    def test_linux_defaults_and_explicit_source_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(paths.data_root(platform_name="posix", repo_root=tmp,
                                             environ={}), str(root / "data"))
            self.assertEqual(paths.pdf_zip(platform_name="posix", repo_root=tmp,
                                           environ={}), str(root / "data" / "doc_pdfs.zip"))
            self.assertEqual(paths.pdf_root(platform_name="posix", repo_root=tmp,
                                            environ={}), str(root / "data" / "doc_pdfs" / "doc_pdfs"))
            self.assertEqual(paths.image_root(platform_name="posix", repo_root=tmp,
                                              environ={}), str(root / "images"))
            env = {"MMDOCRAG_DATA_ROOT": str(root / "elsewhere"),
                   "MMDOCRAG_IMAGE_ROOT": str(root / "photos")}
            self.assertEqual(paths.pdf_root(platform_name="posix", repo_root=tmp,
                                            environ=env), str(root / "elsewhere" / "doc_pdfs" / "doc_pdfs"))
            self.assertEqual(paths.image_root(platform_name="posix", repo_root=tmp,
                                              environ=env), str(root / "photos"))

    def test_colpali_interpreter_uses_platform_venv_layout(self):
        self.assertEqual(paths.colpali_python(platform_name="posix"),
                         ".venv-colpali/bin/python")
        self.assertEqual(paths.colpali_python(platform_name="nt"),
                         ".venv-colpali/Scripts/python.exe")

    def test_restored_registry_uses_repo_relative_path_without_rewriting_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "canonical" / "mmdocrag.sqlite"
            target.parent.mkdir()
            target.write_bytes(b"restored input")
            record = {"path": "canonical/mmdocrag.sqlite",
                      "abs_path": r"D:\old-machine\MMDocRAG\canonical\mmdocrag.sqlite",
                      "content_hash": digest_path(target)}
            derived = root / "artifacts" / "derived"
            derived.mkdir(parents=True)
            registry_file = derived / "registry.json"
            registry_file.write_text(json.dumps({"artifacts": {"corpora/canonical-db": record}}),
                                     encoding="utf-8")
            before = registry_file.read_bytes()
            with patch.object(paths, "REPO_ROOT", tmp):
                registry = Registry(root=str(root / "artifacts"))
                self.assertEqual(registry.status("corpora/canonical-db"),
                                 ("present", str(target)))
                target.write_bytes(b"changed input")
                self.assertEqual(registry.status("corpora/canonical-db")[0], "stale")
            self.assertEqual(registry_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
