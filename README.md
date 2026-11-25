# Ermes Stack

`ermes-stack` is the orchestration repository for the Ermes services.

It uses:

- Docker Compose
- Task
- Poetry
- Python tooling for configuration and Docker Compose execution
- Milvus standalone
- etcd
- MinIO

The goal of this repository is to provide a single entry point to build, configure, start, stop and inspect the complete Ermes stack.

[Project Tracking](docs/PROJECT_TRACKING.md)

## Table of contents

- [Repository structure](#repository-structure)
- [Requirements](#requirements)
- [Prerequisites](#prerequisites)
- [Install Python dependencies](#install-python-dependencies)
- [Configuration](#configuration)
- [Persistent data](#persistent-data)
- [Services](#services)
- [Common commands](#common-commands)
- [Docker Compose wrapper](#docker-compose-wrapper)
- [Milvus](#milvus)
- [Development workflow](#development-workflow)
  - [Use the web frontend](#use-the-web-frontend)
  - [Trace WebSocket traffic](#trace-websocket-traffic)
  - [Inspect live voice transcripts](#inspect-live-voice-transcripts)
  - [View logs and stop the stack](#view-logs-and-stop-the-stack)
- [Local files](#local-files)

## Repository structure

```text
ermes-stack/
├── compose.yaml
├── config.yaml
├── Taskfile.yml
├── pyproject.toml
├── poetry.lock
└── tools/
    ├── __init__.py
    └── compose.py
```

The application source code itself lives in separate repositories.

The Docker Compose file currently expects repositories such as:

```text
../ermes-frontend/
../ermes-backend/
../ermes-agents/
../ermes-mcp/
```

For example:

```text
github.com/MarcRoyo/
├── ermes-stack/
├── ermes-frontend/
├── ermes-backend/
├── ermes-agents/
└── ermes-mcp/
```

## Requirements

The following tools must be installed:

- Docker
- Docker Compose
- Poetry
- Task
- Python

The stack is currently intended to run under Linux / WSL2.

## Prerequisites
Install poetry

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
exec $SHELL
pipx install poetry

```

## Install Python dependencies

From the repository root:

```bash
poetry install
```

## Configuration

Local configuration is stored in:

```text
config.yaml
```

This file should not be committed to Git.

Example:

```yaml
env:
  ERMES_DATA_ROOT: /home/user/.local/share/ermes
  DOCKER_VOLUME_DIRECTORY: /home/user/.local/share/ermes/milvus
```

`tools/compose.py` reads this file and injects the configured values as environment variables when Docker Compose is executed.

This means that variables such as:

```yaml
${ERMES_DATA_ROOT}
${DOCKER_VOLUME_DIRECTORY}
```

can be used normally inside `compose.yaml` without requiring a `.env` file or permanently exported shell variables.

## Persistent data

Persistent application data is stored below `ERMES_DATA_ROOT`.

Example:

```text
~/.local/share/ermes/
├── music-agent/
│   └── data/
├── config-agent/
│   ├── data/
│   └── training/
├── mcp/
│   └── mcp-delta-data/
└── milvus/
    └── volumes/
        ├── etcd/
        ├── minio/
        └── milvus/
```

The required directories can be created with:

```bash
task init:data
```

They are also created automatically before starting the stack.

## Services

The stack currently contains the following services:

| Service | Description | Port |
|---|---|---:|
| `frontend` | Vite chat frontend | `5173` |
| `backend` | HTTP API and WebSocket gateway | `8091` |
| `music-agent` | Music agent | `9999` |
| `config-agent` | Configuration agent | `9998` |
| `financial-agent` | Sample accounting entries agent | `127.0.0.1:9997` |
| `mcp-server` | Ermes MCP server | `8182` |
| `etcd` | Milvus metadata storage | internal |
| `minio` | Milvus object storage | `9000`, `9001` |
| `standalone` | Milvus standalone server | `19530`, `9091` |

All services share the Docker network:

```text
ermes
```

This allows containers to communicate using their Compose service names.

Examples:

```text
standalone -> etcd:2379
standalone -> minio:9000
config-agent -> standalone:19530
```

## Common commands

### Build the stack

```bash
task build
```

This builds the local Docker images used by Ermes.

### Start the stack

```bash
task up
```

Before Docker Compose starts, the Python helper:

1. reads `config.yaml`
2. creates the required persistent directories
3. injects the configured environment variables
4. runs Docker Compose

### Stop the stack

```bash
task down
```

### Show logs

```bash
task logs
```

### Show service status

```bash
task status
```

This displays a simplified view of the complete stack.

Example:

```text
SERVICE       STATUS     DETAIL
------------  ---------  ------------------------
minio         ✓ HEALTHY  running
etcd          ✓ HEALTHY  running
standalone    ✓ HEALTHY  running
config-agent  ● RUNNING  no health check
mcp-server    ✗ STOPPED  exit code 1
music-agent   ● RUNNING  no health check

5/6 services are running correctly.
```

Possible states include:

```text
✓ HEALTHY
● RUNNING
… STARTING
✗ UNHEALTHY
✗ STOPPED
✗ MISSING
? UNKNOWN
```

`task status` is informational and does not fail even if one or more services are stopped.

## Docker Compose wrapper

Docker Compose should normally be executed through:

```text
tools/compose.py
```

For example:

```bash
poetry run python -m tools.compose up -d
```

Task provides the normal user-facing interface, so in most cases use:

```bash
task up
```

instead.

The wrapper is responsible for:

- loading `config.yaml`
- building the Docker Compose environment
- creating persistent data directories
- executing Docker Compose
- providing additional commands such as the simplified service status

## Milvus

The stack currently uses:

```text
Milvus: 2.6.24
etcd:   3.5.25
MinIO:  RELEASE.2024-12-18T13-15-44Z
```

Milvus runs in standalone mode using Woodpecker as its message queue.

The Milvus services use health checks so dependent Ermes services can wait until Milvus is ready.

For example:

```yaml
depends_on:
  standalone:
    condition: service_healthy
```

## Development workflow

A typical workflow is:

```bash
poetry install
task build
task up
task status
```

### Use the web frontend

After starting the stack with `task up`, open [Ermes Chat](http://localhost:5173/) in your browser. Enter a message and press **Enter** or click **Send**. Use **Shift+Enter** to add a line break. The reply appears as it streams from the backend.

Chat commands and events use the backend WebSocket at `ws://localhost:8091/v1/ws`.

On first startup, the frontend container installs its npm dependencies before serving the page. Check `task logs:frontend` for the Vite startup message. If the page loads but chat reports that the realtime connection is unavailable, check `task logs:backend` as well.

### Trace WebSocket traffic

1. Open [http://localhost:5173/?debugWs=1](http://localhost:5173/?debugWs=1) to enable WebSocket debugging.
2. In the browser's **Console**, make sure **Info** messages are visible and filter for `[Ermes WS]`.
3. Send a message. Look for `[Ermes WS] sent` with a `message.commit` payload and `[Ermes WS] received` with `assistant.message.delta` events. Expand each logged object to inspect its fields.

The trace includes message text and is available in the Vite development build. Remove `?debugWs=1` and reload to turn it off.

To check the backend WebSocket from a terminal, run the smoke test from `ermes-backend` with the stack up and the backend's Poetry dependencies installed.

```bash
cd ../ermes-backend
task test:ws-smoke
```

The test connects to `ws://localhost:8091/v1/ws`, synchronizes a session, sends a sample message, and prints events as they arrive.

### Inspect live voice transcripts

AudioServer sends microphone audio as RTP over UDP port `5004`. To direct the recognized speech to one browser session, open [Ermes Chat with tracing](http://localhost:5173/?debugWs=1) and copy the `session_id` from its outgoing `session.sync` event in the Console.

From `ermes-stack`, build and start the orchestrator with that session ID.

```bash
task build:orchestrator
ERMES_VOICE_SESSION_ID=ses_your_session_id task up:orchestrator
```

Keep AudioServer running. Compose publishes UDP port `5004` on `127.0.0.1` by default. In WSL NAT mode, Windows AudioServer sends to the Windows loopback interface. Recreate the orchestrator on the WSL interface and leave the Windows UDP relay running in a terminal.

```bash
export ERMES_VOICE_RTP_BIND="$(ip -4 -o addr show dev eth0 | awk '{split($4, address, "/"); print address[1]; exit}')"
ERMES_VOICE_SESSION_ID=ses_your_session_id task up:orchestrator
task voice:relay
```

Use `task logs:orchestrator` to check for `Listening for RTP audio` and `New RTP stream`. The first start may download the Whisper model and Silero voice activity detector. Once audio arrives, **Transcripción de voz** shows partial text and updates it when the utterance ends. The Console trace shows the corresponding `voice.transcript.partial` and `voice.transcript.final` events. Speech that appears in this panel does not submit a chat message.

To disable capture, stop the relay with **Ctrl+C** if you started it, then recreate the orchestrator with `ERMES_VOICE_SESSION_ID` unset.

### View logs and stop the stack

During development:

```bash
task logs
```
or filtered by service

```bash
task logs -- mcp-server
```

When finished:

```bash
task down
```

## Local files

The following local configuration or generated files should normally be ignored by Git:

```gitignore
config.yaml
```

Persistent service data should also live outside the repository, under `ERMES_DATA_ROOT`.

This keeps source code and runtime data separated.
