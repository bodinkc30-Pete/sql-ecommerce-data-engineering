from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AIRFLOW_DOCKERFILE = PROJECT_ROOT / "Dockerfile.airflow"
AIRFLOW_COMPOSE = PROJECT_ROOT / "docker-compose.airflow.yml"
AIRFLOW_DAG = (
    PROJECT_ROOT
    / "airflow"
    / "dags"
    / "ecommerce_pipeline_dag.py"
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class AirflowFileContractTestCase(unittest.TestCase):
    def test_required_airflow_files_exist(self) -> None:
        missing = [
            str(path.relative_to(PROJECT_ROOT))
            for path in (
                AIRFLOW_DOCKERFILE,
                AIRFLOW_COMPOSE,
                AIRFLOW_DAG,
            )
            if not path.exists()
        ]

        self.assertEqual(
            [],
            missing,
            (
                "Airflow integration files are missing: "
                f"{missing}"
            ),
        )


@unittest.skipUnless(
    AIRFLOW_DOCKERFILE.exists()
    and AIRFLOW_COMPOSE.exists()
    and AIRFLOW_DAG.exists(),
    "Airflow integration files have not been implemented yet.",
)
class AirflowStaticContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dockerfile = read_text(AIRFLOW_DOCKERFILE)
        cls.compose = read_text(AIRFLOW_COMPOSE)
        cls.dag = read_text(AIRFLOW_DAG)

    def test_airflow_image_uses_python_312(self) -> None:
        self.assertRegex(
            self.dockerfile,
            r"(?im)^\s*FROM\s+apache/airflow:3\.3\.0-python3\.12\s*$",
        )

    def test_pipeline_dependency_is_installed_without_modifying_base_runtime(self) -> None:
        self.assertIn("requirements.txt", self.dockerfile)
        self.assertRegex(self.dockerfile, r"(?i)pip\s+install")

    def test_compose_has_required_services(self) -> None:
        required_services = {
            "postgres",
            "airflow-init",
            "airflow-api-server",
            "airflow-scheduler",
            "airflow-dag-processor",
        }

        missing = [
            service
            for service in sorted(required_services)
            if re.search(
                rf"(?m)^\s{{2}}{re.escape(service)}:\s*$",
                self.compose,
            )
            is None
        ]

        self.assertEqual(
            [],
            missing,
            f"Missing required Airflow services: {missing}",
        )

        self.assertIsNone(
            re.search(
                r"(?m)^\s{2}airflow-triggerer:\s*$",
                self.compose,
            ),
            (
                "Project 01 should not run a triggerer yet because "
                "the initial DAG does not use deferrable operators."
            ),
        )

    def test_api_server_uses_host_port_8081(self) -> None:
        self.assertRegex(
            self.compose,
            r'(?m)^\s*-\s*["\']?8081:8080["\']?\s*$',
        )

    def test_airflow_uses_local_executor_and_project_mount(self) -> None:
        self.assertIn(
            "AIRFLOW__CORE__EXECUTOR: LocalExecutor",
            self.compose,
        )
        self.assertRegex(
            self.compose,
            r"(?m)^\s*-\s+\./:/opt/project\s*$",
        )

    def test_dag_wraps_existing_pipeline_orchestrator(self) -> None:
        self.assertIn("05_run_pipeline.py", self.dag)
        self.assertIn("/opt/project", self.dag)

        forbidden_reimplementation_markers = [
            "02_load_raw_data.py",
            "03_run_transformations.py",
            "04_run_quality_checks.py",
        ]

        for marker in forbidden_reimplementation_markers:
            self.assertNotIn(
                marker,
                self.dag,
                (
                    "The Airflow DAG must wrap the existing orchestrator "
                    "instead of reimplementing pipeline steps directly."
                ),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
