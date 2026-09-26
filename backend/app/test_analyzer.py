import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from app.analyzer import _run_single_phase
from app.analyzer import analyze_repository


class AnalyzerResultHandoffTests(unittest.TestCase):
    def test_phase_result_is_plain_markdown(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            workspace = Path(temporary_dir) / "workspace"
            output_dir = Path(temporary_dir) / "results"
            with patch("app.analyzer.run_phase_agent", return_value="# Markdown"):
                result = _run_single_phase(
                    "business-purpose",
                    "Business Purpose",
                    workspace,
                    "https://example.test/repository.git",
                    output_dir,
                    "run-id",
                )

            self.assertEqual(result["raw_analysis"], "# Markdown")
            self.assertEqual(
                (output_dir / "business-purpose" / "raw.md").read_text(),
                "# Markdown",
            )

    def test_export_runs_once_after_final_configured_phase(self):
        with patch("app.analyzer.run_phase_agent", return_value="# Markdown"):
            with patch("app.analyzer.create_download_package") as create_package:
                with patch.object(
                    __import__("app.analyzer", fromlist=["settings"]).settings,
                    "analysis_results_dir",
                    tempfile.mkdtemp(),
                ):
                    result = analyze_repository(
                        "https://example.test/repository.git",
                        phases_per_batch=1,
                        number_of_batches=1,
                        batch_mode="sequence",
                    )

        create_package.assert_called_once()
        self.assertEqual(create_package.call_args.args[0].name, result["run_id"])

    def test_export_runs_after_parallel_phases(self):
        with patch("app.analyzer.run_phase_agent", return_value="# Markdown"):
            with patch("app.analyzer.create_download_package") as create_package:
                with patch.object(
                    __import__("app.analyzer", fromlist=["settings"]).settings,
                    "analysis_results_dir",
                    tempfile.mkdtemp(),
                ):
                    analyze_repository(
                        "https://example.test/repository.git",
                        phases_per_batch=1,
                        number_of_batches=2,
                        batch_mode="parallel",
                    )

        create_package.assert_called_once()

    def test_selected_phases_are_chunked_by_configured_capacity(self):
        calls = []

        def fake_run_phase(phase, phase_name, workspace, repo_url):
            calls.append(phase)
            return f"# {phase_name}"

        with patch("app.analyzer.run_phase_agent", side_effect=fake_run_phase):
            with patch("app.analyzer.create_download_package"):
                with patch.object(
                    __import__("app.analyzer", fromlist=["settings"]).settings,
                    "analysis_results_dir",
                    tempfile.mkdtemp(),
                ):
                    result = analyze_repository(
                        "https://example.test/repository.git",
                        phases_per_batch=2,
                        batch_mode="sequence",
                        selected_phases=[
                            "features",
                            "business-purpose",
                            "requirements",
                            "future-directions",
                            "testing-harness",
                        ],
                    )

        self.assertEqual(len(result["results"]), 5)
        self.assertEqual(set(calls), set(result["results"]))

    def test_selected_phases_must_be_valid_and_nonempty(self):
        for selected_phases in ([], ["features", "features"], ["unknown"]):
            with self.subTest(selected_phases=selected_phases):
                with self.assertRaises(ValueError):
                    analyze_repository(
                        "https://example.test/repository.git",
                        phases_per_batch=2,
                        selected_phases=selected_phases,
                    )

    def test_repeated_run_reuses_work_id_and_rejects_completed_phase(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            with patch("app.analyzer.run_phase_agent", return_value="# Markdown"):
                with patch("app.analyzer.create_download_package"):
                    with patch.object(
                        __import__("app.analyzer", fromlist=["settings"]).settings,
                        "analysis_results_dir",
                        temporary_dir,
                    ):
                        first = analyze_repository(
                            "https://example.test/repository.git",
                            selected_phases=["business-purpose"],
                            work_id="stableworkid",
                        )
                        with self.assertRaisesRegex(ValueError, "already completed"):
                            analyze_repository(
                                "https://example.test/repository.git",
                                selected_phases=["business-purpose"],
                                work_id=first["run_id"],
                            )

        self.assertEqual(first["run_id"], "stableworkid")

    def test_repeated_run_regenerates_cumulative_zip(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            with patch("app.analyzer.run_phase_agent", return_value="# Markdown"):
                with patch.object(
                    __import__("app.analyzer", fromlist=["settings"]).settings,
                    "analysis_results_dir",
                    temporary_dir,
                ):
                    first = analyze_repository(
                        "https://example.test/repository.git",
                        selected_phases=["business-purpose"],
                        work_id="cumulativework",
                    )
                    second = analyze_repository(
                        "https://example.test/repository.git",
                        selected_phases=["features"],
                        work_id=first["run_id"],
                    )

            self.assertEqual(second["run_id"], "cumulativework")
            with ZipFile(
                Path(temporary_dir) / "cumulativework" / "sdlc-documentation.zip"
            ) as archive:
                self.assertIn("business-purpose.md", archive.namelist())
                self.assertIn("features.md", archive.namelist())


if __name__ == "__main__":
    unittest.main()