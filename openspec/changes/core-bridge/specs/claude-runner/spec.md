## ADDED Requirements

### Requirement: Spawn Claude CLI subprocess per message
The system SHALL spawn `claude -p "{message}" --resume {session_id} --output-format stream-json --dangerously-skip-permissions` as an async subprocess for each incoming user message. The working directory SHALL be the configured WORKING_DIRECTORY.

#### Scenario: User sends a text message
- **WHEN** a text message is received from an authorized user
- **THEN** the system spawns a Claude CLI subprocess with the message as prompt and the user's session_id

### Requirement: Parse NDJSON stream events
The system SHALL read the subprocess stdout line by line and parse each line as JSON. It SHALL handle the following event types: `system`, `assistant` (with `text` or `tool_use` content), and `result`.

#### Scenario: System event received
- **WHEN** a `system` event is parsed from the stream
- **THEN** the session_id is extracted and stored for future use

#### Scenario: Assistant text event received
- **WHEN** an `assistant` event with text content is parsed
- **THEN** the text is forwarded to the Telegram UI service for progress display

#### Scenario: Assistant tool_use event received
- **WHEN** an `assistant` event with `tool_use` content is parsed
- **THEN** the tool name is forwarded to the Telegram UI service as a status line

#### Scenario: Result event received
- **WHEN** a `result` event is parsed
- **THEN** the final text and cost/token information are forwarded to the Telegram UI service for the final message

### Requirement: Subprocess timeout
The system SHALL enforce a 10-minute timeout on each Claude subprocess. If the timeout is exceeded, the subprocess SHALL be terminated with SIGTERM.

#### Scenario: Subprocess exceeds timeout
- **WHEN** a Claude subprocess runs for more than 10 minutes
- **THEN** the subprocess receives SIGTERM and the user is notified of the timeout

### Requirement: One subprocess per user at a time
The system SHALL allow only one active Claude subprocess per chat_id. If a new message arrives while a subprocess is running, the system SHALL queue it or notify the user that Claude is busy.

#### Scenario: Message received while Claude is busy
- **WHEN** a user sends a message while their previous Claude subprocess is still running
- **THEN** the user receives a notification that Claude is still processing
