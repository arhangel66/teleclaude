## ADDED Requirements

### Requirement: Bot receives text messages from authorized users
The bot SHALL accept text messages from Telegram users whose chat_id is in the ALLOWED_CHAT_IDS configuration. Messages from unauthorized users SHALL be silently ignored.

#### Scenario: Authorized user sends a text message
- **WHEN** a user with chat_id in ALLOWED_CHAT_IDS sends a text message
- **THEN** the bot passes the message text to the Claude runner service

#### Scenario: Unauthorized user sends a message
- **WHEN** a user with chat_id NOT in ALLOWED_CHAT_IDS sends a message
- **THEN** the bot ignores the message and does not invoke Claude

### Requirement: Bot starts with long-polling
The bot SHALL use aiogram 3 long-polling mode to receive updates from Telegram. No webhook configuration is required.

#### Scenario: Bot startup
- **WHEN** the bot process starts
- **THEN** it begins polling Telegram for updates and is ready to receive messages

### Requirement: Configuration loaded from environment
The bot SHALL read configuration from `.env` file: TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, WORKING_DIRECTORY, CLAUDE_BINARY, SQLITE_DB.

#### Scenario: Valid configuration
- **WHEN** all required environment variables are set
- **THEN** the bot starts successfully

#### Scenario: Missing required configuration
- **WHEN** a required environment variable is missing
- **THEN** the bot exits with a clear error message
