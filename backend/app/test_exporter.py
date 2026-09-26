import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from app.exporter import TEMPLATE_PATH, create_download_package


class ExporterTests(unittest.TestCase):
    def test_creates_valid_package_with_expected_files(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            work_dir = Path(temporary_dir)
            (work_dir / "business-purpose").mkdir()
            (work_dir / "business-purpose" / "raw.md").write_text("# Purpose")
            (work_dir / "features").mkdir()
            (work_dir / "features" / "raw.md").write_text("# Features")
            (work_dir / "notes.txt").write_text("exclude")

            zip_path = create_download_package(work_dir)

            self.assertEqual(zip_path, work_dir / "sdlc-documentation.zip")
            self.assertEqual((work_dir / "index.html").read_bytes(), TEMPLATE_PATH.read_bytes())
            self.assertTrue(zip_path.is_file())
            with ZipFile(zip_path) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "index.html",
                        "business-purpose.md",
                        "business-purpose.html",
                        "features.md",
                        "features.html",
                    },
                )
                self.assertEqual(archive.read("business-purpose.md"), b"# Purpose")
                self.assertIn(b"<h1>Purpose</h1>", archive.read("business-purpose.html"))

    def test_excludes_existing_zip_and_unrelated_markdown_location(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            work_dir = Path(temporary_dir)
            (work_dir / "existing.zip").write_bytes(b"ignore")
            (work_dir / "nested").mkdir()
            (work_dir / "nested" / "unrelated.md").write_text("ignore")
            (work_dir / "direct.md").write_text("include")

            zip_path = create_download_package(work_dir)
            create_download_package(work_dir)

            with ZipFile(zip_path) as archive:
                self.assertEqual(
                    set(archive.namelist()), {"index.html", "direct.md"}
                )

    def test_missing_work_directory_raises(self):
        with self.assertRaises(FileNotFoundError):
            create_download_package(Path("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
