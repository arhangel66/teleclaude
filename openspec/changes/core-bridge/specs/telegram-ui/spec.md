## ADDED Requirements

### Requirement: Show progress via editable message
The system SHALL send a progress message on the first assistant event and edit it with subsequent updates. Edits SHALL be throttled to at most once per 2 seconds to avoid Telegram rate limits.

#### Scenario: First assistant text arrives
- **WHEN** the first assistant text event is received for a message
- **THEN** a new Telegram message is sent with the intermediate text (this becomes the progress message)

#### Scenario: Subsequent assistant events arrive
- **WHEN** additional assistant text or tool_use events arrive
- **THEN** the progress message is edited with the latest content (throttled to 1 edit per 2s)

#### Scenario: Tool use event displayed
- **WHEN** a tool_use event is received
- **THEN** the progress message shows a status line like "Bash: git status..."

### Requirement: Send final response as new message
The system SHALL send the final Claude response as a new Telegram message (not an edit) so that it triggers a push notification on the user's device.

#### Scenario: Result event received
- **WHEN** the result event is parsed from the NDJSON stream
- **THEN** a new Telegram message is sent with the final response text

### Requirement: Display context size in footer
The system SHALL append context size information to the final message footer (e.g. `15k`). The size SHALL be extracted from the result event's token/cost data, or estimated from message length if unavailable.

#### Scenario: Final message with context size
- **WHEN** the final response is sent
- **THEN** the message ends with a footer line showing context size (e.g. `· 15k`)

### Requirement: Handle long messages
The system SHALL split messages that exceed Telegram's 4096 character limit into multiple messages.

#### Scenario: Response exceeds 4096 characters
- **WHEN** the final response text is longer than 4096 characters
- **THEN** it is split into multiple consecutive messages
