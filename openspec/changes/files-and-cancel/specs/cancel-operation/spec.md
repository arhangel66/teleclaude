## ADDED Requirements

### Requirement: Cancel button on progress messages
The system SHALL add an inline "Cancel" button to the progress message while Claude is processing.

#### Scenario: User presses Cancel
- **WHEN** the user presses the "Cancel" inline button
- **THEN** the Claude subprocess receives SIGTERM and the bot confirms "Operation cancelled."

#### Scenario: Cancel after subprocess already finished
- **WHEN** the user presses "Cancel" but the subprocess has already completed
- **THEN** the button is silently removed, no error shown

### Requirement: Remove cancel button on completion
The system SHALL remove the inline "Cancel" button from the progress message when the Claude subprocess finishes.

#### Scenario: Subprocess completes normally
- **WHEN** the Claude subprocess finishes and the final response is sent
- **THEN** the cancel button is removed from the progress message
