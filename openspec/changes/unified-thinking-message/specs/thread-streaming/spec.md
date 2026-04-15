## ADDED Requirements

### Requirement: At most two Telegram messages per prompt

The bot SHALL produce no more than two Telegram messages per user prompt when `streaming_mode="thread"`: one persistent log message (containing thinking, tool-use, and intermediate assistant text) and one final-answer message.

#### Scenario: Typical interaction with thinking and tools

- **WHEN** a user sends a prompt that causes Claude to emit several thinking steps, tool calls, and a final answer
- **THEN** the chat contains exactly two bot messages: (1) a single log message holding every thinking/tool/intermediate line, and (2) the final-answer message

#### Scenario: Interaction with only a final answer

- **WHEN** Claude produces no thinking or tool events and returns only a final answer
- **THEN** the chat contains the log message (possibly empty or near-empty) and the final-answer message, and still never more than two messages

### Requirement: Log message is edited in place and preserved

The log message SHALL be created on the first streaming event and edited in place as new events arrive. It MUST remain in the chat after the final answer is sent (not deleted).

#### Scenario: Subsequent events edit rather than send

- **WHEN** new `TextEvent`, `ToolUseEvent`, or `ThinkingEvent` arrive after the log message already exists
- **THEN** the renderer edits the existing log message and does not send a new message

#### Scenario: Log is kept after final

- **WHEN** the final answer is sent
- **THEN** the log message stays in the chat as a record of intermediate activity

### Requirement: Log content is rendered as a MarkdownV2 blockquote

Intermediate content in the log SHALL be rendered as a Telegram MarkdownV2 blockquote so the client renders it compactly. Dynamic text (tool arguments, thinking snippets, assistant intermediate text) MUST be escaped per MarkdownV2 rules before being embedded.

#### Scenario: Lines are prefixed with blockquote marker

- **WHEN** the renderer edits the log with two events
- **THEN** the emitted text is sent with `parse_mode="MarkdownV2"` and every line starts with `> ` (after escape)

#### Scenario: Expandable blockquote for long logs

- **WHEN** the log has more than the expandable threshold of lines (default 4)
- **THEN** the renderer emits the block using Telegram's expandable-blockquote syntax so clients that support it render it collapsed by default

#### Scenario: MarkdownV2 escaping

- **WHEN** a tool call contains characters like `_`, `*`, `(`, `)`, `.`, or `!`
- **THEN** those characters are escaped with a leading `\` before being inserted into the blockquote

#### Scenario: Parse failure fallback

- **WHEN** Telegram rejects an edit with MarkdownV2 due to unescaped content
- **THEN** the renderer retries the same edit without `parse_mode` so the log never goes dark, and logs the failure at `DEBUG`

### Requirement: Final answer is a separate message

The final answer (from `ResultEvent`) SHALL be sent as a new Telegram message, not by editing the log message. The context-token footer (e.g. `(12k)`) MUST be appended to the final answer as it is today.

#### Scenario: Final answer sent as new message

- **WHEN** a `ResultEvent` arrives
- **THEN** the renderer sends `ResultEvent.text` as a new message with the token footer, then removes the inline cancel keyboard from the log message

#### Scenario: Intermediate text is not promoted to final

- **WHEN** Claude emitted intermediate `TextEvent`s before the `ResultEvent`
- **THEN** those intermediate texts are appended to the log (not sent as final), and the final message content equals `ResultEvent.text` only

### Requirement: Cancel button lifecycle

The log message SHALL carry the cancel inline button while Claude is running. The button MUST be removed when the final answer is sent or when the renderer's cleanup path runs.

#### Scenario: Cancel button on log during run

- **WHEN** the log message is created or edited while Claude is still running
- **THEN** it is accompanied by an inline keyboard with a "Cancel" button tied to the chat

#### Scenario: Cancel button removed on completion

- **WHEN** the final answer is about to be sent (or the run ends via cleanup)
- **THEN** the log message's inline keyboard is removed before the final answer message is sent

### Requirement: Log respects Telegram message length limit

If the rendered blockquote would exceed Telegram's 4096-character limit, the renderer SHALL tail-trim older lines and prepend a single `> …` truncation marker. It MUST NOT spawn additional log messages.

#### Scenario: Overflow tail-trim

- **WHEN** the accumulated log exceeds 4096 characters
- **THEN** the renderer drops oldest lines until it fits, prepends a truncation marker, and still sends a single edit to the single log message

### Requirement: Edits are throttled

The renderer SHALL throttle edits to the log message to at most once every 2 seconds, with a final flush on completion and on cancellation, to avoid Telegram rate limits and redundant edits.

#### Scenario: Burst of events coalesces

- **WHEN** five events arrive within one second
- **THEN** Telegram sees at most one edit during that second, and the final state is flushed before the final answer is sent

### Requirement: `thread` is the default streaming mode

`Settings.streaming_mode` SHALL accept the value `"thread"` and default to it. The existing values `"verbose"`, `"compact"`, and `"quiet"` MUST remain valid and selectable via `.env`.

#### Scenario: Default mode

- **WHEN** `.env` does not specify `streaming_mode`
- **THEN** `Settings.streaming_mode` equals `"thread"` and `build_renderer` returns a `ThreadRenderer`

#### Scenario: Opt-out to legacy modes

- **WHEN** `.env` specifies `streaming_mode=verbose` (or `compact`, or `quiet`)
- **THEN** the previous per-mode behavior is used unchanged
