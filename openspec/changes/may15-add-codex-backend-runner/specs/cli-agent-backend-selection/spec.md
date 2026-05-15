## ADDED Requirements

### Requirement: Backend selection from environment
The system SHALL select the CLI prompt execution backend from configuration, defaulting to the existing Claude CLI backend when no backend is configured.

#### Scenario: Default backend remains Claude
- **WHEN** the application starts without an explicit agent backend setting
- **THEN** prompts are executed through the Claude CLI backend using the existing Claude-compatible behavior

#### Scenario: Codex backend is selected
- **WHEN** the application starts with the agent backend configured as Codex
- **THEN** prompts are executed through the Codex CLI backend

#### Scenario: Unknown backend is rejected
- **WHEN** the application starts with an unsupported backend value
- **THEN** startup fails with a clear configuration error

### Requirement: Normalized prompt execution events
The system SHALL expose the same internal prompt execution event types to `run_prompt` and Telegram renderers regardless of the selected CLI backend.

#### Scenario: Claude events are normalized
- **WHEN** the Claude CLI emits stream JSON events for session id, text, tool use, thinking, and final result
- **THEN** the runner emits the corresponding normalized internal events

#### Scenario: Codex events are normalized
- **WHEN** the Codex CLI emits JSONL events for thread start, completed agent messages, completed tool calls, reasoning, and turn usage
- **THEN** the runner emits the corresponding normalized internal events

#### Scenario: Unknown raw events are ignored
- **WHEN** the selected CLI emits an unknown or unsupported JSON event
- **THEN** the runner ignores that event without failing the prompt execution

### Requirement: Backend-aware sessions
The system SHALL persist and resume CLI sessions per Telegram chat and backend, without mixing session identifiers from different backends.

#### Scenario: Claude and Codex sessions are isolated
- **WHEN** the same chat uses both Claude and Codex at different times
- **THEN** each backend resumes only its own stored session identifier

#### Scenario: New session resets selected backend
- **WHEN** a user requests a new session while one backend is selected
- **THEN** the stored session for that chat and selected backend is cleared

#### Scenario: Existing sessions migrate to Claude
- **WHEN** an existing database created before backend-aware sessions is opened
- **THEN** existing chat session rows remain available as Claude backend sessions

### Requirement: Existing Telegram behavior is preserved
The system SHALL preserve current Telegram prompt handling, streaming renderers, cancellation, attachment prompt assembly, and final-answer delivery while adding backend selection.

#### Scenario: Prompt flow stays renderer-compatible
- **WHEN** `run_prompt` receives normalized events from any supported backend
- **THEN** the configured Telegram renderer receives the same event callbacks it uses today

#### Scenario: Cancellation terminates active subprocess
- **WHEN** a user presses the cancel button during a running prompt
- **THEN** the active CLI subprocess for that chat is terminated

#### Scenario: Attachments remain path-injected
- **WHEN** a user sends a supported file attachment
- **THEN** the prompt still includes the downloaded absolute file path for the selected backend to inspect

### Requirement: Codex command contract
The system SHALL run Codex through its non-interactive JSONL CLI contract.

#### Scenario: Fresh Codex prompt starts a thread
- **WHEN** a chat has no stored Codex session
- **THEN** the runner invokes `codex exec --json` with the configured working directory and prompt

#### Scenario: Existing Codex prompt resumes a thread
- **WHEN** a chat has a stored Codex session
- **THEN** the runner invokes `codex exec resume --json` with the stored thread id and prompt

#### Scenario: Codex usage is reported
- **WHEN** Codex emits turn usage information
- **THEN** the final normalized result includes input context token information for the Telegram footer
