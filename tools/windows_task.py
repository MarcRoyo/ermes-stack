import subprocess
import sys
from typing import Any

from tools.compose import load_config


def get_windows_config() -> dict[str, Any]:
    config = load_config()

    windows = config.get("windows", {})

    if not isinstance(windows, dict):
        raise RuntimeError(
            "'windows' in config.yaml must be a YAML mapping."
        )

    return windows


def windows_to_wsl_path(path: str) -> str:
    result = subprocess.run(
        [
            "wslpath",
            "-u",
            path,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Unable to convert Windows path '{path}':\n"
            f"{result.stderr}"
        )

    return result.stdout.strip()


def get_task_executable() -> str:
    windows = get_windows_config()

    executable = windows.get("task_executable")

    if not executable:
        raise RuntimeError(
            "windows.task_executable is not defined in config.yaml."
        )

    return windows_to_wsl_path(str(executable))


def get_service_task_dir(service: str) -> str:
    windows = get_windows_config()

    services = windows.get("services", {})

    if not isinstance(services, dict):
        raise RuntimeError(
            "'windows.services' must be a YAML mapping."
        )

    service_config = services.get(service)

    if not isinstance(service_config, dict):
        raise RuntimeError(
            f"Windows service '{service}' is not configured."
        )

    task_dir = service_config.get("task_dir")

    if not task_dir:
        raise RuntimeError(
            f"windows.services.{service}.task_dir "
            "is not defined in config.yaml."
        )

    return str(task_dir)


def run_windows_task(
    service: str,
    args: list[str],
) -> int:

    task_executable = get_task_executable()
    task_dir = get_service_task_dir(service)

    command = [
        task_executable,
        "--dir",
        task_dir,
        *args,
    ]

    print("+", " ".join(command))

    result = subprocess.run(
        command,
        check=False,
        cwd="/mnt/c",
    )

    return result.returncode


def capture_windows_task(
    service: str,
    args: list[str],
) -> subprocess.CompletedProcess[str]:

    task_executable = get_task_executable()
    task_dir = get_service_task_dir(service)

    command = [
        task_executable,
        "--silent",
        "--dir",
        task_dir,
        *args,
    ]

    return subprocess.run(
        command,
        check=False,
        cwd="/mnt/c",
        capture_output=True,
        text=True,
    )

def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  windows-task <service> [task arguments...]\n"
            "\n"
            "Example:\n"
            "  windows-task audioserver build",
            file=sys.stderr,
        )
        return 2

    service = sys.argv[1]
    args = sys.argv[2:]

    try:
        return run_windows_task(
            service=service,
            args=args,
        )

    except RuntimeError as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())