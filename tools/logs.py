import sys

from tools.compose import (
    build_environment,
    load_config,
    run_compose,
)

from tools.windows_task import run_windows_task


AUDIO_SERVICE = "audioserver"


def run_logs(
    follow: bool,
    args: list[str],
) -> int:

    #
    # AudioServer is a native Windows service.
    #
    if args and args[0] == AUDIO_SERVICE:
        task_name = "follow" if follow else "logs"

        return run_windows_task(
            AUDIO_SERVICE,
            [
                task_name,
                *args[1:],
            ],
        )

    #
    # Everything else is handled by Docker Compose.
    #
    config = load_config()
    env = build_environment(config)

    compose_args = ["logs"]

    if follow:
        compose_args.append("-f")

    compose_args.extend(args)

    return run_compose(
        args=compose_args,
        env=env,
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  logs.py logs [service]\n"
            "  logs.py follow [service]",
            file=sys.stderr,
        )
        return 2

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "logs":
        return run_logs(
            follow=False,
            args=args,
        )

    if command == "follow":
        return run_logs(
            follow=True,
            args=args,
        )

    print(
        f"Unknown command: {command}",
        file=sys.stderr,
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())