import os
import subprocess
import sys
from pathlib import Path
from typing import Any
import json
import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"

def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {CONFIG_FILE}\n"
            "Run 'task configure' first."
        )

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if not isinstance(config, dict):
        raise RuntimeError(
            "config.yaml must contain a YAML mapping."
        )

    return config


def get_config_env(config: dict[str, Any]) -> dict[str, str]:
    env_config = config.get("env", {})

    if not isinstance(env_config, dict):
        raise RuntimeError(
            "'env' in config.yaml must be a YAML mapping."
        )

    return {
        str(key): str(value)
        for key, value in env_config.items()
        if value is not None
    }


def build_environment(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()

    config_env = get_config_env(config)

    # Values from config.yaml override the current shell environment.
    env.update(config_env)

    return env


# def get_data_root(config: dict[str, Any]) -> Path:
#     config_env = get_config_env(config)

#     data_root = config_env.get("ERMES_DATA_ROOT")

#     if not data_root:
#         raise RuntimeError(
#             "ERMES_DATA_ROOT is not defined in config.yaml."
#         )

#     return Path(data_root).expanduser().resolve()


def init_data(config: dict[str, Any]) -> None:
    config_env = get_config_env(config)

    ermes_data_root = config_env.get("ERMES_DATA_ROOT")
    docker_volume_directory = config_env.get("DOCKER_VOLUME_DIRECTORY")

    if not ermes_data_root:
        raise RuntimeError(
            "ERMES_DATA_ROOT is not defined in config.yaml."
        )

    if not docker_volume_directory:
        raise RuntimeError(
            "DOCKER_VOLUME_DIRECTORY is not defined in config.yaml."
        )

    data_root = Path(ermes_data_root).expanduser().resolve()
    milvus_root = Path(docker_volume_directory).expanduser().resolve()

    directories = [
        data_root / "music-agent" / "data",
        data_root / "config-agent" / "data",
        data_root / "config-agent" / "training",
        data_root / "mcp" / "mcp-delta-data",
        data_root / "tts" / "data",
        data_root / "models",

        milvus_root / "volumes" / "etcd",
        milvus_root / "volumes" / "minio",
        milvus_root / "volumes" / "milvus",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    print(f"Ermes data root: {data_root}")
    print(f"Milvus volume root: {milvus_root}")


def run_compose(
    args: list[str],
    env: dict[str, str],
) -> int:
    command = [
        "docker",
        "compose",
        *args,
    ]

    print("+", " ".join(command))

    try:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            env=env,
            check=False,
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            "Docker command not found."
        ) from exc

    return result.returncode


def run_command(
    command: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Command not found: {command[0]}"
        ) from exc

def get_compose_services(
    env: dict[str, str],
) -> list[str]:
    result = run_command(
        [
            "docker",
            "compose",
            "config",
            "--services",
        ],
        env,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Unable to get Compose services:\n{result.stderr}"
        )

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

def get_compose_ps(
    env: dict[str, str],
) -> list[dict[str, Any]]:
    result = run_command(
        [
            "docker",
            "compose",
            "ps",
            "--all",
            "--format",
            "json",
        ],
        env,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Unable to get Compose status:\n{result.stderr}"
        )

    output = result.stdout.strip()

    if not output:
        return []

    try:
        data = json.loads(output)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return [data]

    except json.JSONDecodeError:
        pass

    # Compatibility with Compose versions that emit
    # one JSON object per line.
    containers = []

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            containers.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Unable to parse 'docker compose ps' output."
            ) from exc

    return containers

def get_status_rows(config: dict[str, Any]) -> list[tuple[str, str, str]]:

    env = build_environment(config)

    services = get_compose_services(env)
    containers = get_compose_ps(env)

    containers_by_service = {
        container.get("Service"): container
        for container in containers
        if container.get("Service")
    }

    rows = []

    for service in services:
        container = containers_by_service.get(service)

        if container is None:
            status = "MISSING"
            detail = "container not created"

        else:
            state = str(container.get("State", "")).lower()
            health = str(container.get("Health", "")).lower()
            compose_status = str(container.get("Status", "")).lower()

            if not health:
                if "(healthy)" in compose_status:
                    health = "healthy"
                elif "(unhealthy)" in compose_status:
                    health = "unhealthy"
                elif "(health: starting)" in compose_status:
                    health = "starting"

            if state == "running":
                if health == "healthy":
                    status = "HEALTHY"
                    detail = "running"

                elif health == "starting":
                    status = "STARTING"
                    detail = "health check pending"

                elif health == "unhealthy":
                    status = "UNHEALTHY"
                    detail = "health check failed"

                else:
                    status = "RUNNING"
                    detail = "no health check"

            elif state in {
                "exited",
                "dead",
                "removing",
            }:
                status = "STOPPED"

                exit_code = container.get("ExitCode")

                if exit_code is not None:
                    detail = f"exit code {exit_code}"
                else:
                    detail = state

            elif state:
                status = state.upper()
                detail = ""

            else:
                status = "UNKNOWN"
                detail = ""

        rows.append(
            (
                service,
                status,
                detail,
            )
        )
    
    return rows

def print_status_rows(rows: list[tuple[str, str, str]]) -> int:

    service_width = max(
        len("SERVICE"),
        *(len(row[0]) for row in rows),
    )

    status_width = max(
        len("STATUS"),
        *(len(row[1]) for row in rows),
    )

    symbols = {
        "HEALTHY": "✓",
        "RUNNING": "●",
        "STARTING": "…",
        "UNHEALTHY": "✗",
        "STOPPED": "✗",
        "MISSING": "✗",
        "UNKNOWN": "?",
    }

    colors = {
        "HEALTHY": "\033[32m",    # green
        "RUNNING": "\033[36m",    # cyan
        "STARTING": "\033[33m",   # yellow
        "UNHEALTHY": "\033[31m",  # red
        "STOPPED": "\033[31m",    # red
        "MISSING": "\033[31m",    # red
        "UNKNOWN": "\033[35m",    # magenta
    }

    reset = "\033[0m"

    print()
    print(
        f"{'SERVICE':<{service_width}}  "
        f"{'STATUS':<{status_width + 2}}  "
        f"DETAIL"
    )

    print(
        f"{'-' * service_width}  "
        f"{'-' * (status_width + 2)}  "
        f"{'-' * 24}"
    )

    for service, status, detail in rows:
        symbol = symbols.get(status, "!")
        color = colors.get(status, "")

        status_text = f"{symbol} {status}"

        print(
            f"{service:<{service_width}}  "
            f"{color}{status_text:<{status_width + 2}}{reset}  "
            f"{detail}"
        )

    print()

    running_ok = sum(
        1
        for _, status, _ in rows
        if status in {"HEALTHY", "RUNNING"}
    )

    total = len(rows)

    if running_ok == total:
        print(
            f"\033[32mAll {total} services are running correctly."
            f"{reset}"
        )
    else:
        print(
            f"\033[33m{running_ok}/{total} services are running correctly."
            f"{reset}"
        )

    # Informational command: never fail Task.
    return 0

def show_status(config: dict[str, Any]) -> int:
    rows = get_status_rows(config)
    return print_status_rows(rows)

def main() -> int:
    try:
        config = load_config()

        if len(sys.argv) < 2:
            print(
                "Usage:\n"
                "  ermes-compose init\n"
                "  ermes-compose up -d\n"
                "  ermes-compose build\n"
                "  ermes-compose down\n"
                "  ermes-compose logs -f\n"
                "  ermes-compose ps\n"
                "  ermes-compose config",
                file=sys.stderr,
            )

            return 2

        args = sys.argv[1:]
        command = args[0]

        if command == "init":
            init_data(config)
            return 0

        if command == "status":
            return show_status(config)

        # Commands that may require persistent directories.
        if command in {
            "up",
            "build",
            "create",
            "run",
            "start",
        }:
            init_data(config)

        env = build_environment(config)

        return run_compose(
            args=args,
            env=env,
        )

    except RuntimeError as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )

        return 1

    except KeyboardInterrupt:
        print(
            "\nInterrupted.",
            file=sys.stderr,
        )

        return 130


if __name__ == "__main__":
    raise SystemExit(main())