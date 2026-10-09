# MOM-Agent: local meeting minutes

Upload a meeting recording. It is transcribed locally (faster-whisper), analysed locally
(Ollama), and turned into structured minutes you can read in the browser or download as a
Word file. Nothing leaves your machine.

```
audio -> faster-whisper -> transcript -> Ollama (JSON schema) -> minutes -> web page + .docx
```

## Setup (Windows PowerShell)

```powershell
cd MOM-Agent
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

ollama pull gemma2:2b          # or a stronger model, see below
.\run.ps1                      # checks your setup, then starts the server
```

Open http://127.0.0.1:8000. Manual start: `uvicorn app.main:app --host 127.0.0.1 --port 8000`.

macOS/Linux: same steps, `source venv/bin/activate`, then `python scripts/check_setup.py && uvicorn app.main:app`.

## Using it

1. **New meeting**: choose a recording and the meeting date.
2. The page shows progress (transcribing, analysing) and updates itself.
3. When done you get summary, participants, decisions, action items, topics, next steps, the full
   transcript, and **Download .docx**.
4. If a step fails you see the reason and a **Retry** button. The transcript is saved, so a retry
   after an Ollama problem does not re-transcribe.

## Configuration (all optional)

Copy `.env.example` to `.env`. Common settings:

| Variable | Default | Notes |
|---|---|---|
| `MOM_OLLAMA_MODEL` | `gemma2:2b` | Use `qwen2.5:7b` or `llama3.1:8b` for better accuracy (fits a 16 GB GPU) |
| `MOM_OLLAMA_NUM_CTX` | `8192` | Longer transcripts are split into chunks automatically |
| `MOM_WHISPER_MODEL` | `base` | `small` / `medium` are more accurate; `large-v3` on GPU |
| `MOM_WHISPER_DEVICE` | `cpu` | `cuda` if you have an NVIDIA GPU with CUDA libraries installed |
| `MOM_WHISPER_LANGUAGE` | auto | e.g. `en`, `ur` |
| `MOM_DELETE_AUDIO_AFTER` | `true` | Delete the recording after successful processing |

The app deliberately ignores the `OLLAMA_HOST` environment variable and uses `MOM_OLLAMA_HOST`
(default `http://127.0.0.1:11434`). A server-style value like `0.0.0.0:11434` breaks Python
clients on Windows. Any `0.0.0.0` value is automatically mapped to `127.0.0.1`.

## Troubleshooting

* **"Cannot reach Ollama"**: start Ollama (tray app or `ollama serve`) and run `python scripts/check_setup.py`.
* **"Model is not installed"**: `ollama pull <model>`.
* **Poor or invalid minutes**: switch to a larger model; the app retries bad JSON automatically.
* **Slow transcription**: use a smaller Whisper model, or `MOM_WHISPER_DEVICE=cuda`.
* **Jobs stuck after a restart**: they are marked failed on startup; click Retry.

## Development

```
pytest                                  # unit + end-to-end tests (Whisper/Ollama are mocked)
python scripts/pipeline_test.py a.mp3   # run the real pipeline from the command line
```

Layout: `app/main.py` (routes + background job), `app/agent` (prompting, chunking, retries, merge),
`app/llm` (Ollama client), `app/transcription`, `app/documents` (docx), `app/database` (SQLite).

Security notes: the server binds to localhost and has no authentication. Do not expose it to a
network without adding auth. Uploads are stored under random names and size-limited.
