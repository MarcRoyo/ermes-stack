# Ermes WebSocket Implementation

**Status:** Draft  
**Protocol version:** 1  
**Transport:** WebSocket  
**Scope:** `ermes-frontend` ↔ `ermes-backend` ↔ `ermes-orchestrator`

---

## 1. Purpose

This document describes the proposed implementation of the Ermes WebSocket protocol.

The protocol specification defines **what** commands and events exist. This document defines **how** they should be represented, validated, routed, published, relayed, and consumed by the Ermes components.

The main goals are:

- decouple client commands from server events;
- support interactions initiated outside the frontend, especially voice input;
- stream assistant output without tying it to a specific HTTP request;
- support future keyboard draft updates and speculative generation;
- provide deterministic ordering and correlation;
- support reconnect and event replay;
- keep orchestration logic inside `ermes-orchestrator`;
- keep public client connectivity, authentication, and API concerns inside `ermes-backend`.

Protocol V1 is intentionally small.

---

## 2. High-level architecture

```text
┌─────────────────────┐
│   ermes-frontend    │
│ React / Tauri       │
└──────────┬──────────┘
           │
           │ Public WebSocket
           │ /v1/ws
           ▼
┌─────────────────────┐
│    ermes-backend    │
│                     │
│ WebSocket gateway   │
│ Auth / sessions     │
└──────────┬──────────┘
           │
           │ Internal WebSocket
           │ /v1/ws
           ▼
┌─────────────────────────────────┐
│       ermes-orchestrator        │
│                                 │
│  CommandRouter                  │
│  Runtime                        │
│  EventBus                       │
│  SessionEventStore             │
│  Agents / LLM / voice logic    │
└─────────────────────────────────┘
```

The frontend never connects directly to the orchestrator.

The backend is the public gateway.

The orchestrator owns the real-time session semantics.

---

## 3. Main design rule

The WebSocket is bidirectional, but commands and events remain conceptually separate.

```text
CLIENT → SERVER    Commands
SERVER → CLIENT    Events
```

Examples:

```text
draft.update              command
message.commit            command
generation.cancel         command

voice.transcript.partial  event
message.committed         event
assistant.message.delta   event
generation.completed      event
```

A command expresses intent.

An event represents a fact that has already happened.

This distinction must remain visible in the implementation.

---

## 4. Proposed repository structure

### `ermes-orchestrator`

```text
ermes_orchestrator/
├── realtime/
│   ├── __init__.py
│   ├── protocol.py
│   ├── commands.py
│   ├── events.py
│   ├── event_bus.py
│   ├── event_store.py
│   ├── command_router.py
│   └── websocket.py
├── runtime.py
├── api.py
└── main.py
```

### `ermes-backend`

```text
ermes_backend/
├── realtime/
│   ├── __init__.py
│   ├── websocket.py
│   └── orchestrator_ws.py
├── api.py
├── orchestrator.py
└── main.py
```

### `ermes-frontend`

```text
src/
├── realtime/
│   ├── protocol.ts
│   ├── websocket.ts
│   └── reducer.ts
├── api/
└── components/
```

The exact filenames may change, but the responsibilities should remain separate.

---

## 5. Python protocol models

Pydantic should be the canonical validation layer inside the orchestrator.

The WebSocket endpoint should not manually inspect arbitrary dictionaries beyond the minimum required to select the correct model.

### 5.1 Command envelope

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CommandEnvelope(BaseModel):
    version: Literal[1]
    type: str
    id: str
    session_id: str
    timestamp: datetime
```

Commands do not contain a server sequence number.

### 5.2 Event envelope

```python
class EventEnvelope(BaseModel):
    version: Literal[1]
    type: str
    id: str
    session_id: str
    timestamp: datetime

    sequence: int
    correlation_id: str | None = None
```

Every event published for a session receives a monotonically increasing `sequence`.

---

## 6. Client commands

The initial V1 commands are:

```text
session.sync
draft.update
draft.cancel
message.commit
generation.cancel
```

### 6.1 `session.sync`

```python
class SessionSyncPayload(BaseModel):
    last_sequence: int | None = None


class SessionSyncCommand(CommandEnvelope):
    type: Literal["session.sync"]
    payload: SessionSyncPayload
```

### 6.2 `draft.update`

```python
class DraftUpdatePayload(BaseModel):
    draft_id: str
    revision: int
    source: Literal["keyboard"]
    text: str


class DraftUpdateCommand(CommandEnvelope):
    type: Literal["draft.update"]
    payload: DraftUpdatePayload
```

Voice transcription does not arrive from the frontend as `draft.update`.

Voice is generated internally by the Ermes runtime and published as server events.

### 6.3 `draft.cancel`

```python
class DraftCancelPayload(BaseModel):
    draft_id: str
    revision: int


class DraftCancelCommand(CommandEnvelope):
    type: Literal["draft.cancel"]
    payload: DraftCancelPayload
```

### 6.4 `message.commit`

```python
class MessageCommitPayload(BaseModel):
    draft_id: str | None = None
    revision: int | None = None
    source: Literal["keyboard"]
    text: str


class MessageCommitCommand(CommandEnvelope):
    type: Literal["message.commit"]
    payload: MessageCommitPayload
```

The complete text is included even if the server already knows the draft.

The committed message must not depend on reconstructing previous draft traffic.

### 6.5 `generation.cancel`

```python
class GenerationCancelPayload(BaseModel):
    generation_id: str


class GenerationCancelCommand(CommandEnvelope):
    type: Literal["generation.cancel"]
    payload: GenerationCancelPayload
```

---

## 7. Command discriminated union

Commands should be parsed through a Pydantic discriminated union.

```python
from typing import Annotated

from pydantic import Field, TypeAdapter


ClientCommand = Annotated[
    SessionSyncCommand
    | DraftUpdateCommand
    | DraftCancelCommand
    | MessageCommitCommand
    | GenerationCancelCommand,
    Field(discriminator="type"),
]


client_command_adapter = TypeAdapter(ClientCommand)
```

Incoming JSON can then be validated using:

```python
command = client_command_adapter.validate_python(data)
```

Invalid application messages should produce a protocol `error` event rather than crash the WebSocket handler.

---

## 8. Server events

The initial events are:

```text
session.synced

draft.updated
draft.cancelled

voice.transcript.partial
voice.transcript.final

message.committed

generation.started
generation.completed
generation.cancelled

assistant.message.started
assistant.message.delta
assistant.message.completed

error
```

### 8.1 `voice.transcript.partial`

```python
class VoiceTranscriptPartialPayload(BaseModel):
    utterance_id: str
    text: str
    activated: bool


class VoiceTranscriptPartialEvent(EventEnvelope):
    type: Literal["voice.transcript.partial"]
    payload: VoiceTranscriptPartialPayload
```

`text` is the complete current speech-recognition hypothesis.

The frontend replaces the previous text for the same `utterance_id`; it does not append partial transcripts.

### 8.2 `voice.transcript.final`

```python
class VoiceTranscriptFinalPayload(BaseModel):
    utterance_id: str
    text: str
    activated: bool


class VoiceTranscriptFinalEvent(EventEnvelope):
    type: Literal["voice.transcript.final"]
    payload: VoiceTranscriptFinalPayload
```

A final transcript is not automatically a committed chat message.

The orchestrator still decides whether the utterance is valid.

### 8.3 `message.committed`

```python
class MessageCommittedPayload(BaseModel):
    message_id: str
    source: Literal["keyboard", "voice"]
    text: str
    utterance_id: str | None = None


class MessageCommittedEvent(EventEnvelope):
    type: Literal["message.committed"]
    payload: MessageCommittedPayload
```

This event is the convergence point for keyboard and voice input.

```text
keyboard ─┐
          ├──► message.committed
voice ────┘
```

Downstream processing should normally not care how the message originated.

### 8.4 `generation.started`

```python
class GenerationStartedPayload(BaseModel):
    generation_id: str
    reply_to: str | None = None

    speculative: bool = False

    draft_id: str | None = None
    draft_revision: int | None = None


class GenerationStartedEvent(EventEnvelope):
    type: Literal["generation.started"]
    payload: GenerationStartedPayload
```

Draft-related fields are reserved for future speculative generation.

### 8.5 `assistant.message.started`

```python
class AssistantMessageStartedPayload(BaseModel):
    message_id: str
    generation_id: str
    reply_to: str | None = None


class AssistantMessageStartedEvent(EventEnvelope):
    type: Literal["assistant.message.started"]
    payload: AssistantMessageStartedPayload
```

### 8.6 `assistant.message.delta`

```python
class AssistantMessageDeltaPayload(BaseModel):
    message_id: str
    generation_id: str
    delta: str


class AssistantMessageDeltaEvent(EventEnvelope):
    type: Literal["assistant.message.delta"]
    payload: AssistantMessageDeltaPayload
```

Assistant deltas are incremental and are appended by the frontend.

```text
voice.transcript.partial
    → replace

assistant.message.delta
    → append
```

### 8.7 `assistant.message.completed`

```python
class AssistantMessageCompletedPayload(BaseModel):
    message_id: str
    generation_id: str


class AssistantMessageCompletedEvent(EventEnvelope):
    type: Literal["assistant.message.completed"]
    payload: AssistantMessageCompletedPayload
```

### 8.8 `generation.completed`

```python
class GenerationCompletedPayload(BaseModel):
    generation_id: str


class GenerationCompletedEvent(EventEnvelope):
    type: Literal["generation.completed"]
    payload: GenerationCompletedPayload
```

### 8.9 `generation.cancelled`

```python
class GenerationCancelledPayload(BaseModel):
    generation_id: str

    reason: Literal[
        "user_requested",
        "superseded",
        "session_closed",
        "internal_error",
    ]


class GenerationCancelledEvent(EventEnvelope):
    type: Literal["generation.cancelled"]
    payload: GenerationCancelledPayload
```

### 8.10 `error`

```python
class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] | None = None


class ErrorEvent(EventEnvelope):
    type: Literal["error"]
    payload: ErrorPayload
```

Initial error codes may include:

```text
INVALID_MESSAGE
INVALID_SESSION

DRAFT_NOT_FOUND
DRAFT_REVISION_CONFLICT

GENERATION_NOT_FOUND
GENERATION_ALREADY_COMPLETED

UNAUTHORIZED
RATE_LIMITED

INTERNAL_ERROR
```

---

## 9. Event discriminated union

The event side should use the same approach as commands.

```python
ServerEvent = Annotated[
    SessionSyncedEvent
    | DraftUpdatedEvent
    | DraftCancelledEvent
    | VoiceTranscriptPartialEvent
    | VoiceTranscriptFinalEvent
    | MessageCommittedEvent
    | GenerationStartedEvent
    | GenerationCompletedEvent
    | GenerationCancelledEvent
    | AssistantMessageStartedEvent
    | AssistantMessageDeltaEvent
    | AssistantMessageCompletedEvent
    | ErrorEvent,
    Field(discriminator="type"),
]
```

This provides one canonical Python contract for all server events.

---

## 10. EventBus

The runtime should not know anything about React, FastAPI WebSockets, or the public backend connection.

Runtime code publishes domain events through an internal abstraction.

Suggested interface:

```python
from collections.abc import AsyncIterator
from typing import Protocol


class EventBus(Protocol):

    async def publish(
        self,
        session_id: str,
        event: ServerEvent,
    ) -> None:
        ...

    async def subscribe(
        self,
        session_id: str,
    ) -> AsyncIterator[ServerEvent]:
        ...
```

The first implementation can be in-memory.

---

## 11. In-memory EventBus

A simple implementation can use one `asyncio.Queue` per subscriber.

```python
import asyncio
from collections import defaultdict


class InMemoryEventBus:

    def __init__(self) -> None:
        self._subscribers: dict[
            str,
            set[asyncio.Queue],
        ] = defaultdict(set)

    async def publish(
        self,
        session_id: str,
        event: ServerEvent,
    ) -> None:
        queues = list(
            self._subscribers.get(
                session_id,
                set(),
            )
        )

        for queue in queues:
            await queue.put(event)
```

Subscription should:

1. create a queue;
2. register it for the session;
3. yield events;
4. remove the queue in `finally`.

This prevents stale subscriptions after disconnect.

---

## 12. EventBus backpressure

Queues must not grow without a limit.

A first implementation can use a bounded queue, for example:

```python
asyncio.Queue(maxsize=256)
```

The exact value is an implementation detail.

The important rule is:

> A slow or dead client must not cause unlimited orchestrator memory growth.

Possible future policies include:

- disconnect the slow subscriber;
- drop obsolete replaceable events such as old voice partials;
- preserve important state-transition events;
- move to an external event transport.

Protocol V1 does not require distributed backpressure handling.

---

## 13. Event sequence allocation

The orchestrator is the authority for event ordering.

Each session maintains:

```text
next_sequence
```

When publishing an event:

```text
sequence = next_sequence
next_sequence += 1
```

Sequence allocation and event-store insertion should be atomic from the logical perspective of a session.

Two concurrently produced events must never receive the same sequence.

A per-session `asyncio.Lock` is sufficient for V1.

---

## 14. SessionEventStore

Reconnect requires a short history of recent events.

Suggested interface:

```python
class SessionEventStore(Protocol):

    async def append(
        self,
        session_id: str,
        event: ServerEvent,
    ) -> None:
        ...

    async def after(
        self,
        session_id: str,
        sequence: int,
    ) -> list[ServerEvent]:
        ...
```

The initial implementation may be memory-only.

For example:

```text
session A → deque(maxlen=1000)
session B → deque(maxlen=1000)
```

Persistent event storage is not required for V1.

---

## 15. Event publication pipeline

Events should be assigned a sequence and stored before live delivery.

Recommended flow:

```text
Runtime creates domain event
          │
          ▼
EventPublisher
          │
          ├── allocate sequence
          ├── assign timestamp / event id
          ├── append to SessionEventStore
          │
          ▼
       EventBus
          │
          ▼
     subscribers
```

This ordering matters.

If the WebSocket disconnects immediately after publication, the event is still available for replay.

---

## 16. CommandRouter

Incoming commands should not be implemented directly inside the WebSocket endpoint.

Use a dedicated command router.

```python
class CommandRouter:

    async def dispatch(
        self,
        command: ClientCommand,
    ) -> None:

        match command:
            case SessionSyncCommand():
                await self._handle_session_sync(command)

            case DraftUpdateCommand():
                await self._handle_draft_update(command)

            case DraftCancelCommand():
                await self._handle_draft_cancel(command)

            case MessageCommitCommand():
                await self._handle_message_commit(command)

            case GenerationCancelCommand():
                await self._handle_generation_cancel(command)
```

The WebSocket endpoint remains transport-oriented.

The router remains application-oriented.

---

## 17. Message commit flow

Keyboard example:

```text
Frontend
   │
   │ message.commit
   ▼
CommandRouter
   │
   ├── validate draft revision
   ├── create committed message
   │
   ▼
EventPublisher
   │
   └── message.committed
   │
   ▼
Runtime
   │
   ├── start generation
   ├── generation.started
   ├── assistant.message.started
   ├── assistant.message.delta × N
   ├── assistant.message.completed
   └── generation.completed
```

The command handler should not wait for the full assistant generation before returning control to the WebSocket receive loop.

Generation should run as an asynchronous task owned by the runtime/session.

---

## 18. Voice message flow

Voice originates inside the Ermes stack.

The frontend does not send a command to initiate it.

```text
AudioServer / speech recognition
            │
            ▼
       Orchestrator
            │
            ├── voice.transcript.partial
            ├── voice.transcript.partial
            ├── voice.transcript.final
            │
            ├── wake-word / silence /
            │   validation logic
            │
            ▼
       message.committed
            │
            ▼
        generation...
```

The UI is a subscriber.

It is not the authority that decides when voice becomes a chat message.

---

## 19. Orchestrator WebSocket endpoint

The orchestrator WebSocket is an internal endpoint.

Example:

```text
/v1/ws
```

The connection has two responsibilities:

1. receive and dispatch client commands;
2. stream subscribed server events.

These two responsibilities must run concurrently.

---

## 20. Separate receive and send loops

Do not combine command reception and event transmission into one sequential loop.

Use two concurrent tasks:

```text
receive_loop
send_loop
```

Conceptually:

```python
async def receive_loop(...):
    while True:
        data = await websocket.receive_json()
        command = parse_command(data)
        await command_router.dispatch(command)


async def send_loop(...):
    async for event in event_bus.subscribe(
        session_id
    ):
        await websocket.send_json(
            event.model_dump(
                mode="json",
            )
        )
```

Run them together:

```python
async with asyncio.TaskGroup() as group:
    group.create_task(receive_loop(...))
    group.create_task(send_loop(...))
```

If either task fails or the connection closes, both tasks should be cancelled and cleaned up.

---

## 21. Session synchronization

The server should not consider the connection session-ready immediately after WebSocket `OPEN`.

Recommended lifecycle:

```text
WebSocket connected
        │
        ▼
waiting for session.sync
        │
        ▼
validate session
        │
        ├── replay missed events
        │
        └── subscribe live
        ▼
session active
```

Commands other than synchronization may be rejected until the session is synchronized.

This makes reconnect behavior deterministic.

---

## 22. Replay race condition

There is an important race between:

1. loading missed events;
2. subscribing to new events.

Naively doing:

```text
read store
then subscribe
```

can lose events published between those two operations.

The implementation must avoid that gap.

One simple V1 strategy is:

```text
acquire session event lock

register live subscription
read replay range

release session event lock
```

The client then receives:

```text
replayed events first
live events second
```

A cursor-based event log may replace this mechanism later.

---

## 23. Backend WebSocket gateway

`ermes-backend` exposes the public WebSocket endpoint.

Example:

```text
ws://localhost:8091/v1/ws
```

The backend responsibilities are:

- accept the public WebSocket;
- authenticate the client when authentication exists;
- authorize access to the requested session;
- establish an internal connection to the orchestrator;
- relay commands to the orchestrator;
- relay orchestrator events to the client;
- close both connections cleanly;
- expose observability and metrics.

The backend should not duplicate orchestration decisions.

---

## 24. Backend ↔ orchestrator transport

For V1, the simplest correct implementation is:

```text
Frontend WebSocket
       │
       ▼
Backend WebSocket gateway
       │
       ▼
Internal Orchestrator WebSocket
```

Initially, one public client connection may map to one internal orchestrator connection.

The same command/event protocol can be used across both hops.

This is intentionally simple.

Later, the internal transport may be replaced by:

- a shared multiplexed connection;
- Redis Pub/Sub;
- NATS;
- another message broker;
- gRPC streaming;
- another internal transport.

That change should not require a frontend protocol change.

---

## 25. Backend relay loops

The backend also needs two independent loops:

```text
client → backend → orchestrator
orchestrator → backend → client
```

Conceptually:

```python
async def client_to_orchestrator():
    while True:
        message = await client_ws.receive_text()
        await orchestrator_ws.send(message)


async def orchestrator_to_client():
    while True:
        message = await orchestrator_ws.recv()
        await client_ws.send_text(message)
```

The backend may parse commands when required for authentication or authorization, but it should avoid rewriting protocol semantics unnecessarily.

---

## 26. Domain-event ownership

The backend should not generate orchestrator-domain events such as:

```text
message.committed
generation.started
assistant.message.delta
```

Those are orchestrator facts.

The backend may report gateway/transport failures, but conversation state belongs to the orchestrator.

This prevents two competing sources of truth.

---

## 27. Frontend TypeScript models

The frontend should mirror the protocol using discriminated unions.

```typescript
interface BaseEvent {
  version: 1;
  id: string;
  session_id: string;
  timestamp: string;
  sequence: number;
  correlation_id?: string | null;
}
```

Example:

```typescript
interface AssistantMessageDeltaEvent
  extends BaseEvent {
  type: "assistant.message.delta";

  payload: {
    message_id: string;
    generation_id: string;
    delta: string;
  };
}
```

And:

```typescript
type ServerEvent =
  | SessionSyncedEvent
  | VoiceTranscriptPartialEvent
  | VoiceTranscriptFinalEvent
  | MessageCommittedEvent
  | GenerationStartedEvent
  | AssistantMessageStartedEvent
  | AssistantMessageDeltaEvent
  | AssistantMessageCompletedEvent
  | GenerationCompletedEvent
  | GenerationCancelledEvent
  | ErrorEvent;
```

The UI should use exhaustive switching on `event.type`.

---

## 28. Frontend WebSocket client

The WebSocket client should be isolated from React components.

Suggested interface:

```typescript
interface ErmesRealtimeClient {
  connect(): Promise<void>;
  disconnect(): void;

  send(command: ClientCommand): void;

  subscribe(
    listener: (event: ServerEvent) => void,
  ): () => void;
}
```

React components should not instantiate `WebSocket` directly.

---

## 29. WebSocket URL

Development:

```text
ws://localhost:8091/v1/ws
```

Production:

```text
wss://api.example.com/v1/ws
```

For same-origin deployments, derive the WebSocket scheme from the browser location:

```typescript
const protocol =
  window.location.protocol === "https:"
    ? "wss:"
    : "ws:";
```

This fits a future deployment where the backend serves the frontend static assets or where a reverse proxy exposes both under one origin.

---

## 30. Frontend connection state

Connection state should be separate from chat/application state.

Suggested states:

```text
disconnected
connecting
syncing
connected
reconnecting
failed
```

Do not treat:

```text
WebSocket OPEN
```

as equivalent to:

```text
Ermes session synchronized
```

The session is ready only after `session.synced`.

---

## 31. Frontend event reducer

React should process server events through a reducer or equivalent state machine.

```typescript
function applyEvent(
  state: ChatState,
  event: ServerEvent,
): ChatState {
  switch (event.type) {
    case "voice.transcript.partial":
      return updateVoiceDraft(state, event);

    case "message.committed":
      return addUserMessage(state, event);

    case "assistant.message.started":
      return startAssistantMessage(
        state,
        event,
      );

    case "assistant.message.delta":
      return appendAssistantDelta(
        state,
        event,
      );

    case "assistant.message.completed":
      return completeAssistantMessage(
        state,
        event,
      );

    default:
      return state;
  }
}
```

This keeps protocol handling out of presentational components.

---

## 32. Voice UI state

Voice transcription should be separate from the manual text input.

```typescript
interface VoiceDraft {
  utteranceId: string;
  text: string;
  activated: boolean;
  final: boolean;
}
```

The UI may display:

```text
🎙 Ermes play music by Pink Floyd
```

while the keyboard input remains untouched.

When `message.committed` arrives for that utterance, the temporary voice draft is removed and the committed user message is inserted into conversation history.

---

## 33. Keyboard draft updates

Keyboard partial input should not be sent on every keystroke.

The frontend should debounce updates.

A possible initial range is:

```text
300–500 ms
```

The exact value is not part of the protocol.

Each update increments:

```text
revision
```

Example:

```text
draft_17 rev 4
draft_17 rev 5
draft_17 rev 6
```

A stale revision must never overwrite a newer revision.

---

## 34. Future speculative generation

Protocol V1 reserves fields needed for future speculative work.

A future orchestrator may use:

```text
draft.update
     │
     ▼
speculative generation
```

but speculative output should initially remain invisible.

On commit:

```text
if draft revision still matches
and context is still valid
    → promote/reuse generation

otherwise
    → cancel speculative generation
      and start a normal generation
```

This policy belongs to the orchestrator, not the frontend.

---

## 35. Generation ownership

The runtime should track active generation tasks by generation ID.

Conceptually:

```python
active_generations: dict[
    str,
    asyncio.Task,
]
```

Cancellation:

```python
task = active_generations.get(
    generation_id
)

if task:
    task.cancel()
```

The cancellation path must publish `generation.cancelled` once the final generation state is known.

---

## 36. Runtime streaming integration

The existing LLM streaming pipeline should publish deltas through the EventBus rather than tying them directly to an HTTP `StreamingResponse`.

Conceptually:

```python
await events.publish(
    session_id,
    AssistantMessageStartedEvent(...),
)

async for delta in app.process_message_stream(
    message
):
    await events.publish(
        session_id,
        AssistantMessageDeltaEvent(
            ...,
            payload={
                "message_id": message_id,
                "generation_id": generation_id,
                "delta": delta,
            },
        ),
    )

await events.publish(
    session_id,
    AssistantMessageCompletedEvent(...),
)
```

The runtime remains independent of the WebSocket transport.

---

## 37. Migration from HTTP/SSE

The existing endpoint:

```text
POST /v1/messages/stream
```

should not be removed immediately.

Recommended migration:

### Phase 1

Keep the existing HTTP/SSE path.

Add:

```text
EventBus
SessionEventStore
/v1/ws
```

### Phase 2

Move assistant-generation events to the EventBus/WebSocket path.

Keep SSE as compatibility mode.

### Phase 3

Add voice events:

```text
voice.transcript.partial
voice.transcript.final
message.committed
```

### Phase 4

Update React to use WebSocket for all real-time interaction.

### Phase 5

Add keyboard drafts.

### Phase 6

Deprecate `/v1/messages/stream` when remaining clients have migrated or no longer need it.

This avoids breaking the current working system during migration.

---

## 38. Error handling

Malformed application messages should not automatically close the WebSocket.

Example:

```text
invalid draft command
      │
      ▼
error event
      │
      ▼
connection remains open
```

Fatal transport/session errors may close the connection.

Examples include:

- authentication failure;
- unsupported protocol version;
- forbidden session access;
- unrecoverable session state.

Use WebSocket close codes for transport-level failures.

Use `error` events for normal protocol/application failures.

---

## 39. Duplicate commands

Clients may retry commands after reconnect.

Command IDs should therefore be globally unique enough for short-term deduplication.

Example:

```text
cmd_123 received
cmd_123 processed

cmd_123 received again
→ do not commit the same message twice
```

A bounded cache of recently processed command IDs is sufficient for V1 if needed.

This is particularly important for `message.commit`.

---

## 40. Reconnect strategy

The frontend should reconnect automatically after temporary connection loss.

```text
connection lost
      │
      ▼
short backoff
      │
      ▼
reconnect
      │
      ▼
session.sync(last_sequence)
      │
      ▼
replay missing events
      │
      ▼
live stream resumes
```

Use bounded exponential backoff with jitter.

For example:

```text
0.5 s
1 s
2 s
4 s
8 s
...
```

with a sensible maximum.

The exact retry timing is an implementation detail.

---

## 41. Client sequence tracking

The client stores the highest fully processed event sequence.

```typescript
let lastSequence = 205;
```

After event `206` is successfully applied:

```typescript
lastSequence = 206;
```

If an event arrives with:

```text
sequence <= lastSequence
```

it may be a replay duplicate and can be ignored.

If an unexpected gap appears:

```text
lastSequence = 206
received = 209
```

the client should treat the session as out of sync and resynchronize rather than guessing the missing state.

---

## 42. Security boundary

The public WebSocket terminates at `ermes-backend`.

Future authentication and authorization belong there.

```text
Frontend
   │
   │ authenticated WS
   ▼
Backend
   │
   ├── authenticate user
   ├── authorize session
   │
   ▼
Orchestrator
```

The orchestrator may trust identity/session metadata supplied through the internal trusted connection.

Authentication should not be duplicated as arbitrary fields inside every protocol payload.

---

## 43. Observability

Real-time logs should include identifiers where available:

```text
session_id
command_id
event_id
correlation_id
message_id
generation_id
draft_id
utterance_id
```

Example:

```text
session=ses_1
command=cmd_54
type=message.commit
message=msg_31
```

This becomes critical once voice, cancellation, speculative generation, and multiple clients are active simultaneously.

---

## 44. Testing strategy

The real-time layer should be tested at several levels.

### Model tests

Validate:

- valid commands;
- malformed commands;
- unknown `type`;
- invalid revisions;
- invalid enum values.

### EventBus tests

Validate:

- one subscriber;
- multiple subscribers;
- unsubscribe cleanup;
- ordering;
- bounded queues.

### Event-store tests

Validate:

- sequence ordering;
- replay after a sequence;
- bounded history;
- duplicate handling.

### Command-router tests

Validate behavior such as:

```text
message.commit
→ message.committed
→ generation started
```

without requiring a real WebSocket.

### WebSocket integration tests

Validate:

```text
connect
session.sync
message.commit
receive message.committed
receive assistant deltas
receive completion
```

### Reconnect tests

Validate:

```text
receive sequence 1..5
disconnect
server produces 6..8
reconnect(last_sequence=5)
receive 6..8
continue live with 9
```

---

## 45. Recommended implementation order

### Step 1 — Protocol models

Create:

```text
commands.py
events.py
protocol.py
```

with Pydantic validation and tests.

No WebSocket is required yet.

### Step 2 — EventPublisher and sequence allocation

Implement:

```text
EventPublisher
SessionEventStore
```

and test sequence ordering.

### Step 3 — EventBus

Implement in-memory pub/sub and cleanup.

### Step 4 — Integrate current assistant streaming

Publish:

```text
generation.started
assistant.message.started
assistant.message.delta
assistant.message.completed
generation.completed
```

from the current runtime.

### Step 5 — Orchestrator WebSocket

Implement:

```text
/v1/ws
session.sync
message.commit
generation.cancel
```

### Step 6 — Backend WebSocket gateway

Expose the public:

```text
/v1/ws
```

and relay to the orchestrator.

### Step 7 — Frontend WebSocket client

Implement:

```text
protocol.ts
websocket.ts
reducer.ts
```

and migrate assistant streaming from SSE to WebSocket.

### Step 8 — Voice events

Publish:

```text
voice.transcript.partial
voice.transcript.final
message.committed
```

from the existing voice/orchestrator logic.

### Step 9 — Keyboard drafts

Add:

```text
draft.update
draft.cancel
```

with debounce.

### Step 10 — Reconnect replay

Add:

```text
last_sequence
replay
duplicate protection
```

after the basic live path is stable.

---

## 46. V1 non-goals

Do not implement these in the first iteration:

```text
raw audio over WebSocket
binary protocol frames
distributed EventBus
Redis / NATS / Kafka
persistent event sourcing
visible speculative output
multi-user rooms
tool-specific rich UI events
presence
typing indicators
file transfer
```

The architecture should allow these later without requiring them now.

---

## 47. Core implementation principles

### The frontend sends intent

```text
draft.update
message.commit
generation.cancel
```

### The orchestrator publishes facts

```text
message.committed
generation.started
assistant.message.delta
```

### The backend is the public gateway

It owns public connectivity and future authentication, not reasoning.

### The runtime does not depend on WebSocket

It publishes events through `EventBus`.

### Voice and keyboard converge at committed messages

```text
voice ────┐
          ├──► message.committed
keyboard ─┘
```

### Partial voice text replaces previous hypotheses

```text
voice.transcript.partial → replace
```

### LLM deltas are incremental

```text
assistant.message.delta → append
```

### Session event ordering is authoritative

Use server `sequence`.

### Reconnect is part of the protocol

It is not an afterthought.

### Protocol V1 stays deliberately small

New message types should represent real domain concepts, not implementation details.

---

## 48. Target result

After the first complete implementation, Ermes should support this architecture:

```text
                FRONTEND
                    │
                    │ WebSocket
                    ▼
                 BACKEND
                    │
                    │ Internal WebSocket
                    ▼
              ORCHESTRATOR
                    │
             ┌──────┴──────┐
             │             │
          commands       EventBus
             │             ▲
             ▼             │
          Runtime ──────────┘
             │
         Agents / LLM
```

A voice interaction can then happen without any frontend request:

```text
voice.transcript.partial
        ↓
voice.transcript.final
        ↓
message.committed
        ↓
generation.started
        ↓
assistant.message.started
        ↓
assistant.message.delta × N
        ↓
assistant.message.completed
        ↓
generation.completed
```

A keyboard interaction uses the same event pipeline after commit:

```text
draft.update × N
        ↓
message.commit
        ↓
message.committed
        ↓
generation...
```

This provides the foundation for Ermes as a real-time multimodal assistant rather than a request/response chatbot.
