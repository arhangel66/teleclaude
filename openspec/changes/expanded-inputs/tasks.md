# Tasks: expanded-inputs

- [ ] Location / venue → text prompt with `lat, lon` and venue title/address
- [ ] Contact → text prompt with name + phone (+ vCard if present)
- [ ] Audio → download + optional transcription (env flag)
- [ ] Animation (GIF) → download as file, pass path
- [ ] Sticker → download (`.webp` / `.tgs` / `.webm`), pass path; decide on conversion later
- [ ] Album (`media_group_id`) → debounce ~1.5s, batch sibling messages, pass list of paths in one prompt
- [ ] Forwarded message → include `forward_from`/`forward_origin` info in prompt header
- [ ] Reply-to context → include quoted text/file in prompt header
- [ ] Tests for each new branch in `tests/test_file_handling.py`
- [ ] Update `CLAUDE.md` (project) with the new supported input list
