from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.airflow.yml"
EXPECTED_EXECUTION_API_URL = "http://airflow-api-server:8080/execution/"


class AirflowExecutionApiRoutingTestCase(unittest.TestCase):
    def test_scheduler_workers_use_api_server_service_for_execution_api(self) -> None:
        compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

        match = re.search(
            r'AIRFLOW__CORE__EXECUTION_API_SERVER_URL:\s*["\']?([^"\'\s]+)',
            compose_text,
        )

        self.assertIsNotNone(
            match,
            "Airflow Execution API URL must be configured explicitly in Compose.",
        )
        self.assertEqual(
            match.group(1),
            EXPECTED_EXECUTION_API_URL,
            "LocalExecutor workers must reach the API Server by Docker service DNS, "
            "not localhost or the Windows host port.",
        )


if __name__ == "__main__":
    unittest.main()
