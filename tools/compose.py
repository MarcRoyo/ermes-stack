import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def get_data_root(config: dict[str, Any]) -> Path:
    config_env = get_config_env(config)

    data_root = config_env.get("ERMES_DATA_ROOT")

    if not data_root:
        raise RuntimeError(
            "ERMES_DATA_ROOT is not defined in config.yaml."
        )

    return Path(data_root).expanduser().resolve()


def init_data(config: dict[str, Any]) -> None:
    data_root = get_data_root(config)

    directories = [
        data_root / "music-agent" / "data",
        data_root / "config-agent" / "data",
        data_root / "config-agent" / "training",
        data_root / "mcp" / "mcp-delta-data",
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    print(f"Ermes data root: {data_root}")


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