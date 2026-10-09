# Windows launcher: python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt first.
# Clears a bad OLLAMA_HOST for this session (the app doesn't use it, but the CLI/tools may).
if ($env:OLLAMA_HOST -match "0\.0\.0\.0") { $env:OLLAMA_HOST = "127.0.0.1:11434" }
python scripts/check_setup.py
if ($LASTEXITCODE -ne 0) { Write-Host "Fix the items above, then re-run." -ForegroundColor Yellow; exit 1 }
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
