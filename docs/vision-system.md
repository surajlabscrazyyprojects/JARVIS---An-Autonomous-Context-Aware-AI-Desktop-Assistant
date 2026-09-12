# JARVIS screen-vision controls

The existing `VisionAnalyzer` is the single observation facade. It prefers
UI Automation, then local Gemma/Ollama visual interpretation, and finally
returns a degraded result instead of guessing. `MotorPlanner` and the motor
controllers remain the only action path.

## Privacy and modes

`VISION_CONTROL` supports `ON`, `OFF`, `ON_DEMAND`, `TASK_AWARE`, and
`CONTINUOUS_LOW_RATE`. When OFF, the analyzer returns
`SCREEN_VISION_DISABLED` before querying window metadata or capturing pixels.
OCR and remote/local visual inference are therefore blocked too. Raw frames
are not retained by the vision memory; only hashes, structured elements, and
short-lived target metadata are kept.

## Tools

- `screen_observe`: adaptive metadata/UI-tree/region/full-screen observation.
- `screen_question`: concise screen summary.
- `screen_ocr`: local OCR with UIA text fallback when Tesseract is unavailable.
- `find_element`, `click_element`, `double_click_element`, `drag_and_drop`.
- `verify_state`: before/after verification and bounded stale-target handling.
- `vision_control`: explicit privacy mode control.

All physical actions pass through the process-wide `CursorControlManager` so
concurrent tasks cannot move the cursor or type simultaneously.

The system still reports degraded/unavailable when a live UIA, OCR, Gemma, or
Windows-display capability is not present. It does not claim a click or visual
answer succeeded without an observation-based result.
