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
../ermes-agents/
../ermes-mcp/
```

For example:

```text
github.com/MarcRoyo/
├── ermes-stack/
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
sudo apt install python3-poetry
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
| `music-agent` | Music agent | `9999` |
| `config-agent` | Configuration agent | `9998` |
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