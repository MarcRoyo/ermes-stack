import json
import sys
from typing import Any

from tools.compose import (
    get_status_rows,
    load_config,
    print_status_rows,
)

from tools.windows_task import capture_windows_task


def get_audioserver_status() -> tuple[str, str, str]:
    result = capture_windows_task(
        "audioserver",
        ["status:json"],
    )

    if result.returncode != 0:
        return (
            "audioserver",
            "UNKNOWN",
            result.stderr.strip() or "status command failed",
        )

    try:
        data: dict[str, Any] = json.loads(
            result.stdout.strip()
        )

    except json.JSONDecodeError:
        return (
            "audioserver",
            "UNKNOWN",
            "invalid status response",
        )

    state = str(
        data.get("state", "unknown")
    ).lower()

    detail = str(
        data.get("detail", "")
    )

    if state == "running":
        status = "RUNNING"

    elif state == "stopped":
        status = "STOPPED"

    else:
        status = "UNKNOWN"

    return (
        "audioserver",
        status,
        detail,
    )


def main() -> int:
    try:
        config = load_config()

        rows = get_status_rows(config)

        rows.append(
            get_audioserver_status()
        )

        return print_status_rows(rows)

    except RuntimeError as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())