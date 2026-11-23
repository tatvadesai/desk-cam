# desk-cam

Zero-dependency CLI tool that turns any webcam, document camera, or iPhone (Continuity Camera) into editable Markdown + LaTeX in ~1.7 seconds.

## Features

- **Live camera + freeze on capture**: Auto-pauses the camera after capture, on tab switch, or after 2 minutes idle to save battery.
- **Rotate anywhere**: Rotate 90° while live or after capturing a sideways page.
- **Streaming OCR to Markdown + LaTeX**: Streams verbatim transcription into a split **Editor** and live **KaTeX Preview**. Marks crossed-out text (`~~...~~`) and unclear symbols (`[?]`) without silently "fixing" your mistakes.
- **Multi-provider (`auto`, zero dependencies)**: Uses `GEMINI_API_KEY`, `OPENAI_API_KEY` (supports `OPENAI_BASE_URL`), `ANTHROPIC_API_KEY`, or local `ollama`.
- **Save & copy (`Cmd+Enter` / `Ctrl+Enter`)**: Writes clean Markdown to disk, copies to your clipboard (`pbcopy`, `wl-copy`, or `xclip`), and removes the temporary JPEG.

## Install

Run directly with Python 3.10+, or install globally:

```sh
uv tool install --editable .
# or: pipx install -e .
```

Set one API key (or run Ollama locally):

```sh
export GEMINI_API_KEY="..."      # fastest (~1.7s with gemini-3.5-flash-lite)
# export OPENAI_API_KEY="..."    # or any OpenAI-compatible server via OPENAI_BASE_URL
# export ANTHROPIC_API_KEY="..."
# export OLLAMA_HOST="http://127.0.0.1:11434"
```

## Usage

```sh
desk-cam
```

Options:

| Flag | Default | Purpose |
|---|---|---|
| `--out DIR` | `~/desk-cam` (or `DESK_CAM_OUT`) | Output folder |
| `--file NAME` | `work.md` (or `DESK_CAM_FILE`) | Output Markdown filename |
| `--port PORT` | `8765` (or `DESK_CAM_PORT`) | Local HTTP port |
| `--provider` | `auto` (`gemini`, `openai`, `anthropic`, `ollama`) | Vision backend |
| `--model ID` | Provider default (or `DESK_CAM_MODEL`) | Override model ID |
| `--frontmatter` | off | Add YAML frontmatter (`status`, `captured_at`) |
| `--no-open` | off | Do not open a browser tab automatically |

## Shortcuts

- `Space`: Capture photo (auto-starts camera if paused)
- `Cmd+Enter` / `Ctrl+Enter`: Save Markdown, copy to clipboard, and delete temporary photo

## Privacy

- Binds only to `127.0.0.1` and blocks cross-origin `POST` requests (`403`).
- Live video never leaves your browser. Only captured/uploaded JPEGs are sent to your chosen provider.
- Do not capture passwords, IDs, or private documents on free-tier cloud APIs.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
