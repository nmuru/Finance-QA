import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.main import download_analysis


class DownloadEndpointTests(unittest.TestCase):
    def test_returns_existing_download(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_root = Path(temporary_dir)
            work_dir = output_root / "run-id"
            work_dir.mkdir()
            zip_path = work_dir / "sdlc-documentation.zip"
            zip_path.write_bytes(b"zip")

            with patch("app.main.settings.analysis_results_dir", str(output_root)):
                response = download_analysis("run-id")

            self.assertEqual(Path(response.path), zip_path)
            self.assertEqual(response.filename, "sdlc-documentation.zip")


    def test_download_creates_package_when_missing(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_root = Path(temporary_dir)
            work_dir = output_root / "run-id"
            phase_dir = work_dir / "software-requirements"
            phase_dir.mkdir(parents=True)
            (phase_dir / "raw.md").write_text("# Software Requirements\n\nCompleted.", encoding="utf-8")

            with patch("app.main.settings.analysis_results_dir", str(output_root)):
                response = download_analysis("run-id")

            zip_path = work_dir / "sdlc-documentation.zip"
            self.assertEqual(Path(response.path), zip_path)
            self.assertTrue(zip_path.is_file())

    def test_missing_download_returns_404(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            with patch("app.main.settings.analysis_results_dir", temporary_dir):
                with self.assertRaises(HTTPException) as context:
                    download_analysis("missing")

            self.assertEqual(context.exception.status_code, 404)

    def test_path_traversal_returns_404(self):
        with self.assertRaises(HTTPException) as context:
            download_analysis("..\\other")

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
