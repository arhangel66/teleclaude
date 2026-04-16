## Why

Today the bot accepts only text, photos, voice, video, video_note, and documents. Users sometimes send other Telegram message types — locations, contacts, audio files, GIFs (animations), albums (media groups). They are silently dropped. The agent should be able to react to all reasonable inputs.

## What Changes

Extend `_build_prompt` / `_download_file` in `handlers.py` to recognize and forward:

- `location` / `venue` — pass `lat, lon` (and venue title/address if present) as text
- `contact` — pass name + phone (+ vCard text if present)
- `audio` — download like voice; optionally transcribe (configurable)
- `animation` (GIF) — download like video, pass file path
- `sticker` — download as `.webp` / `.tgs` / `.webm`, pass file path
- `media_group` (album) — collect all parts in a short window, pass list of paths in one prompt
- forwarded messages — include forward origin (`forward_from`, `forward_origin.chat`) in prompt header
- `reply_to_message` — include the quoted message text/file as context

## Capabilities

### Modified Capabilities

- `file-handling`: support new attachment kinds and album batching
- `telegram-handlers`: build richer prompts from location/contact/forward/reply metadata

## Impact

- Modified: `src/bot/handlers.py` (new branches in `_download_file` / `_build_prompt`, album buffering)
- Modified: `src/bot/services/transcriber.py` (optional: audio transcription toggle)
- New tests: per new input kind in `tests/test_file_handling.py`

## Open Questions

- Album batching: simplest is a small per-chat debounce (e.g. 1.5s) to collect `media_group_id` siblings before invoking Claude.
- Sticker formats (.tgs / .webm) Claude can't read directly — convert to png? Or just pass the raw file path and let Claude decline?
- Audio transcription default: on or off?
