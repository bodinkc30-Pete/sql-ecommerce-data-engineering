from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "pipeline_config.json"
)

SCRIPTS_DIRECTORY = (
    PROJECT_ROOT
    / "scripts"
)

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

LOG_DIRECTORY = (
    PROJECT_ROOT
    / "logs"
)

PIPELINE_LOG_PATH = (
    LOG_DIRECTORY
    / "pipeline.log"
)


PIPELINE_STEPS = [
    {
        "step_number": 1,
        "step_name": "SETUP_DATABASE",
        "script_name": "01_setup_database.py",
        "description": (
            "สร้างตาราง Index และ View "
            "ในฐานข้อมูล SQLite"
        ),
    },
    {
        "step_number": 2,
        "step_name": "LOAD_RAW_DATA",
        "script_name": "02_load_raw_data.py",
        "description": (
            "โหลดข้อมูลต้นทางเข้าสู่ Staging "
            "ตาม Pipeline Mode"
        ),
    },
    {
        "step_number": 3,
        "step_name": "RUN_TRANSFORMATIONS",
        "script_name": "03_run_transformations.py",
        "description": (
            "ทำความสะอาด ตรวจสอบ "
            "และโหลดข้อมูลเข้าสู่ Core Tables"
        ),
    },
    {
        "step_number": 4,
        "step_name": "RUN_QUALITY_CHECKS",
        "script_name": "04_run_quality_checks.py",
        "description": (
            "ตรวจ Null, Duplicate, Foreign Key, "
            "Reconciliation และ Business Rules"
        ),
    },
]


def current_utc_time() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")


def read_pipeline_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"ไม่พบไฟล์ Config: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        mode="r",
        encoding="utf-8",
    ) as config_file:
        return json.load(config_file)


def get_pipeline_mode(
    config: dict[str, Any],
) -> str:
    pipeline_config = config.get(
        "pipeline",
        {},
    )

    pipeline_mode = str(
        pipeline_config.get(
            "mode",
            "hybrid",
        )
    ).strip().lower()

    allowed_modes = {
        "demo",
        "hybrid",
    }

    if pipeline_mode not in allowed_modes:
        allowed_mode_text = ", ".join(
            sorted(allowed_modes)
        )

        raise ValueError(
            "ค่า pipeline.mode ไม่ถูกต้อง: "
            f"{pipeline_mode}. "
            "ค่าที่รองรับคือ: "
            f"{allowed_mode_text}"
        )

    return pipeline_mode


def ensure_required_directories() -> None:
    required_directories = [
        PROJECT_ROOT / "database",
        PROJECT_ROOT / "logs",
        PROJECT_ROOT / "data" / "staging",
        PROJECT_ROOT / "data" / "processed",
    ]

    for directory_path in required_directories:
        directory_path.mkdir(
            parents=True,
            exist_ok=True,
        )


def write_log(
    message: str,
) -> None:
    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_message = (
        f"{current_utc_time()} | "
        f"{message}\n"
    )

    with PIPELINE_LOG_PATH.open(
        mode="a",
        encoding="utf-8",
    ) as log_file:
        log_file.write(
            log_message
        )


def print_separator() -> None:
    print("=" * 70)


def validate_script_exists(
    script_path: Path,
) -> None:
    if not script_path.exists():
        raise FileNotFoundError(
            f"ไม่พบ Script: {script_path}"
        )


def create_child_environment() -> dict[str, str]:
    child_environment = os.environ.copy()

    child_environment["PYTHONIOENCODING"] = (
        "utf-8"
    )

    child_environment["PYTHONUTF8"] = "1"

    return child_environment


def run_script(
    step_number: int,
    step_name: str,
    script_name: str,
    description: str,
) -> float:
    script_path = (
        SCRIPTS_DIRECTORY
        / script_name
    )

    validate_script_exists(
        script_path
    )

    print_separator()

    print(
        f"[STEP {step_number}] "
        f"{step_name}"
    )

    print(
        f"[INFO] {description}"
    )

    print(
        f"[INFO] กำลังรัน: "
        f"{script_name}"
    )

    write_log(
        f"START | {step_name} | "
        f"{script_name}"
    )

    started_at = time.perf_counter()

    child_environment = (
        create_child_environment()
    )

    process = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        cwd=PROJECT_ROOT,
        env=child_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )

    elapsed_seconds = (
        time.perf_counter()
        - started_at
    )

    if process.stdout:
        standard_output = (
            process.stdout.rstrip()
        )

        print(
            standard_output
        )

        write_log(
            f"STDOUT | {step_name}\n"
            f"{standard_output}"
        )

    if process.stderr:
        standard_error = (
            process.stderr.rstrip()
        )

        print(
            standard_error,
            file=sys.stderr,
        )

        write_log(
            f"STDERR | {step_name}\n"
            f"{standard_error}"
        )

    if process.returncode != 0:
        error_message = (
            f"ขั้นตอน {step_name} ล้มเหลว "
            f"ด้วย Exit Code "
            f"{process.returncode}"
        )

        write_log(
            f"FAILED | {step_name} | "
            f"{elapsed_seconds:.2f} seconds | "
            f"exit_code={process.returncode}"
        )

        raise RuntimeError(
            error_message
        )

    print(
        f"[SUCCESS] {step_name} สำเร็จ "
        f"ใช้เวลา {elapsed_seconds:.2f} วินาที"
    )

    write_log(
        f"SUCCESS | {step_name} | "
        f"{elapsed_seconds:.2f} seconds"
    )

    return elapsed_seconds


def validate_pipeline_inputs(
    config: dict[str, Any],
    pipeline_mode: str,
) -> None:
    directories = config["directories"]
    synthetic_files = config["synthetic_files"]
    pawchoice_files = config["pawchoice_files"]

    synthetic_directory = (
        PROJECT_ROOT
        / directories["synthetic_raw_data"]
    )

    pawchoice_directory = (
        PROJECT_ROOT
        / directories["pawchoice_raw_data"]
    )

    required_paths = [
        CONFIG_PATH,
        synthetic_directory
        / synthetic_files["customers"],
        synthetic_directory
        / synthetic_files["products"],
        synthetic_directory
        / synthetic_files["orders"],
        synthetic_directory
        / synthetic_files["order_items"],
        synthetic_directory
        / synthetic_files["payments"],
    ]

    if pipeline_mode == "hybrid":
        required_paths.append(
            pawchoice_directory
            / pawchoice_files[
                "influencer_payments"
            ]
        )

    missing_paths = [
        path
        for path in required_paths
        if not path.exists()
    ]

    if missing_paths:
        missing_path_text = "\n".join(
            f"- {path}"
            for path in missing_paths
        )

        raise FileNotFoundError(
            "ไฟล์ที่ Pipeline ต้องใช้ไม่ครบ:\n"
            f"{missing_path_text}"
        )


def print_pipeline_sources(
    pipeline_mode: str,
) -> None:
    print(
        f"[INFO] Pipeline mode: "
        f"{pipeline_mode.upper()}"
    )

    print(
        "[INFO] แหล่งข้อมูล:"
    )

    print(
        "  1. Synthetic CSV"
    )

    if pipeline_mode == "hybrid":
        print(
            "  2. Pawchoice Excel"
        )
    else:
        print(
            "  2. Pawchoice Excel "
            "(ข้ามใน Demo Mode)"
        )


def run_pipeline() -> None:
    ensure_required_directories()

    config = read_pipeline_config()

    pipeline_mode = get_pipeline_mode(
        config
    )

    validate_pipeline_inputs(
        config=config,
        pipeline_mode=pipeline_mode,
    )

    pipeline_started_at = (
        time.perf_counter()
    )

    pipeline_start_time = (
        current_utc_time()
    )

    print_separator()

    print(
        "[START] E-COMMERCE "
        "DATA PIPELINE"
    )

    print_pipeline_sources(
        pipeline_mode
    )

    print(
        f"[INFO] เริ่มทำงานเวลา UTC: "
        f"{pipeline_start_time}"
    )

    write_log(
        "PIPELINE START | "
        f"mode={pipeline_mode} | "
        "ecommerce_data_pipeline"
    )

    step_durations: dict[str, float] = {}

    for pipeline_step in PIPELINE_STEPS:
        elapsed_seconds = run_script(
            step_number=pipeline_step[
                "step_number"
            ],
            step_name=pipeline_step[
                "step_name"
            ],
            script_name=pipeline_step[
                "script_name"
            ],
            description=pipeline_step[
                "description"
            ],
        )

        step_durations[
            pipeline_step["step_name"]
        ] = elapsed_seconds

    total_elapsed_seconds = (
        time.perf_counter()
        - pipeline_started_at
    )

    print_separator()

    print(
        "[SUCCESS] PIPELINE "
        "ทำงานครบทุกขั้นตอน"
    )

    print(
        f"[INFO] Pipeline mode: "
        f"{pipeline_mode.upper()}"
    )

    print(
        f"[INFO] ฐานข้อมูล: "
        f"{DATABASE_PATH}"
    )

    print(
        f"[INFO] Log: "
        f"{PIPELINE_LOG_PATH}"
    )

    print(
        "[INFO] ระยะเวลาของแต่ละขั้นตอน:"
    )

    for step_name, duration in (
        step_durations.items()
    ):
        print(
            f"  - {step_name}: "
            f"{duration:.2f} วินาที"
        )

    print(
        f"[INFO] เวลารวม: "
        f"{total_elapsed_seconds:.2f} วินาที"
    )

    print_separator()

    write_log(
        "PIPELINE SUCCESS | "
        f"mode={pipeline_mode} | "
        f"duration={total_elapsed_seconds:.2f} seconds"
    )


def main() -> None:
    try:
        run_pipeline()

    except FileNotFoundError as error:
        print_separator()

        print(
            f"[FILE ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"FILE ERROR | {error}"
        )

        sys.exit(1)

    except json.JSONDecodeError as error:
        print_separator()

        print(
            f"[CONFIG JSON ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"CONFIG JSON ERROR | {error}"
        )

        sys.exit(1)

    except ValueError as error:
        print_separator()

        print(
            f"[CONFIG ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"CONFIG ERROR | {error}"
        )

        sys.exit(1)

    except UnicodeError as error:
        print_separator()

        print(
            f"[ENCODING ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"ENCODING ERROR | {error}"
        )

        sys.exit(1)

    except RuntimeError as error:
        print_separator()

        print(
            f"[PIPELINE ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"RUNTIME ERROR | {error}"
        )

        sys.exit(1)

    except KeyboardInterrupt:
        print_separator()

        print(
            "[CANCELLED] ผู้ใช้หยุด Pipeline"
        )

        write_log(
            "PIPELINE CANCELLED BY USER"
        )

        sys.exit(1)

    except Exception as error:
        print_separator()

        print(
            f"[UNEXPECTED ERROR] {error}"
        )

        write_log(
            f"PIPELINE FAILED | "
            f"UNEXPECTED ERROR | {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
