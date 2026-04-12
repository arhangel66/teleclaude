## ADDED Requirements

### Requirement: Typing indicator starts on message receipt
The system SHALL send a `typing` chat action to Telegram immediately when a user message is received and before Claude processing begins.

#### Scenario: User sends a message
- **WHEN** user sends a text message to the bot
- **THEN** the bot sends `typing` chat action to the same chat before spawning Claude

### Requirement: Typing indicator stays alive during processing
The system SHALL re-send the `typing` chat action every 4 seconds while Claude is processing, to prevent the indicator from expiring (Telegram expires it after 5 seconds).

#### Scenario: Claude processing takes longer than 5 seconds
- **WHEN** Claude has been processing for more than 5 seconds
- **THEN** the typing indicator is still visible because it was re-sent at the 4-second mark

#### Scenario: Claude processing takes 15 seconds
- **WHEN** Claude processes for 15 seconds
- **THEN** the typing action was sent at least 3 times (0s, 4s, 8s)

### Requirement: Typing indicator stops on completion
The system SHALL stop sending the `typing` chat action when Claude processing completes (either success or error).

#### Scenario: Claude returns a result
- **WHEN** Claude finishes processing and a result is sent to the user
- **THEN** no further `typing` chat actions are sent

#### Scenario: Processing fails with an error
- **WHEN** an exception occurs during Claude processing
- **THEN** the typing indicator is stopped and no further `typing` actions are sent
