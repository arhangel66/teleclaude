## MODIFIED Requirements

### Requirement: Show progress via editable message
The system SHALL send a progress message on the first assistant event and edit it with subsequent updates. Edits SHALL be throttled to at most once per 2 seconds. The progress message SHALL include an inline "Cancel" button while the subprocess is active.

#### Scenario: First assistant text arrives
- **WHEN** the first assistant text event is received for a message
- **THEN** a new Telegram message is sent with the intermediate text and a "Cancel" inline button

#### Scenario: Subsequent assistant events arrive
- **WHEN** additional assistant text or tool_use events arrive
- **THEN** the progress message is edited with the latest content (throttled to 1 edit per 2s), keeping the "Cancel" button

#### Scenario: Subprocess completes
- **WHEN** the Claude subprocess finishes
- **THEN** the "Cancel" button is removed from the progress message
