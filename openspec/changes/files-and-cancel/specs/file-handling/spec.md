## ADDED Requirements

### Requirement: Download and store Telegram attachments
The system SHALL download photo, voice, video, and document attachments from Telegram and store them at `files/{chat_id}/{timestamp}_{filename}`.

#### Scenario: User sends a photo
- **WHEN** a user sends a photo
- **THEN** the bot downloads the largest resolution and stores it as `files/{chat_id}/{ts}_{file_id}.jpg`

#### Scenario: User sends a voice message
- **WHEN** a user sends a voice message
- **THEN** the bot downloads it as `files/{chat_id}/{ts}_voice.ogg`

#### Scenario: User sends a document
- **WHEN** a user sends a document
- **THEN** the bot downloads it preserving the original filename

#### Scenario: User sends a video
- **WHEN** a user sends a video
- **THEN** the bot downloads it as `files/{chat_id}/{ts}_video.mp4`

### Requirement: Pass file path in Claude prompt
The system SHALL include the absolute file path in the prompt sent to Claude: `"User sent a file: /abs/path/to/file\n\n{caption or empty}"`.

#### Scenario: File with caption
- **WHEN** a user sends a file with caption text
- **THEN** the prompt includes the file path and caption

#### Scenario: File without caption
- **WHEN** a user sends a file without caption
- **THEN** the prompt includes only the file path
