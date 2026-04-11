## ADDED Requirements

### Requirement: Persist session mapping in SQLite
The system SHALL store the mapping of chat_id to Claude session_id in a SQLite database. The session_id SHALL be updated when a `system` event provides a new one.

#### Scenario: First message from a user
- **WHEN** a user sends their first message (no existing session)
- **THEN** a new session is created and stored after the `system` event provides a session_id

#### Scenario: Returning user sends a message
- **WHEN** a user with an existing session sends a message
- **THEN** the stored session_id is used with `--resume` flag

### Requirement: Reset session with /new command
The system SHALL provide a `/new` command that discards the current session_id for the chat and generates a new one on the next message.

#### Scenario: User resets session
- **WHEN** a user sends `/new`
- **THEN** the stored session_id is cleared and the bot confirms "New session started."

#### Scenario: Next message after reset
- **WHEN** a user sends a message after `/new`
- **THEN** Claude is invoked without `--resume`, starting a fresh session
