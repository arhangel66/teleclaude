## MODIFIED Requirements

### Requirement: Spawn Claude CLI subprocess per message
The system SHALL spawn `claude -p "{message}" --resume {session_id} --output-format stream-json --dangerously-skip-permissions` as an async subprocess for each incoming user message. The working directory SHALL be the configured WORKING_DIRECTORY. When a file path is provided, the prompt SHALL be formatted as `"User sent a file: {path}\n\n{caption}"`.

#### Scenario: User sends a text message
- **WHEN** a text message is received from an authorized user
- **THEN** the system spawns a Claude CLI subprocess with the message as prompt and the user's session_id

#### Scenario: User sends a file
- **WHEN** a file message is received with a local path
- **THEN** the system spawns a Claude CLI subprocess with the file path injected into the prompt

### Requirement: Subprocess can be cancelled externally
The system SHALL expose a method to terminate a running subprocess by chat_id via SIGTERM.

#### Scenario: Cancel requested for active subprocess
- **WHEN** cancel is called for a chat_id with an active subprocess
- **THEN** the subprocess receives SIGTERM and resources are cleaned up

#### Scenario: Cancel requested for no active subprocess
- **WHEN** cancel is called for a chat_id with no active subprocess
- **THEN** nothing happens (no error)
