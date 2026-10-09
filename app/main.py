import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent.meeting_agent import MeetingAgent
from app.config import Settings
from app.database.database import Database
from app.documents.docx_generator import generate_docx
from app.llm.ollama import OllamaClient, OllamaError
from app.schemas import MeetingMinutes
from app.transcription.whisper import Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mom")

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def create_app(settings: Settings | None = None, transcriber=None, agent=None) -> FastAPI:
    """App factory. `transcriber` / `agent` can be injected (used by the tests)."""
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = Database(settings.db_path)
        app.state.db.reset_stuck()
        app.state.transcriber = transcriber or Transcriber(
            settings.whisper_model, settings.whisper_device,
            settings.whisper_compute_type, settings.whisper_language,
        )
        app.state.llm = None if agent else OllamaClient(settings)
        app.state.agent = agent or MeetingAgent(app.state.llm)
        app.state.preflight = _preflight
        app.state.executor = ThreadPoolExecutor(max_workers=1)  # one heavy job at a time
        try:
            _preflight(app)
            log.info("Ollama OK (model %s)", settings.ollama_model)
        except OllamaError as e:
            log.warning("Ollama preflight failed: %s", e)
        yield
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Local Meeting AI Agent", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    def render(request: Request, name: str, status_code: int = 200, **ctx):
        return templates.TemplateResponse(request=request, name=name, context=ctx,
                                          status_code=status_code)

    # ------------------------------------------------------------------ pages
    @app.get("/")
    async def home(request: Request):
        return render(request, "index.html", meetings=request.app.state.db.list())

    @app.get("/upload")
    async def upload_page(request: Request):
        return render(request, "upload.html", today=date.today().isoformat(),
                      max_mb=settings.max_upload_mb)

    @app.post("/upload")
    async def upload_meeting(request: Request, file: UploadFile = File(...),
                             meeting_date: str = Form("")):
        def fail(msg: str, code: int = 400):
            return render(request, "upload.html", status_code=code, error=msg,
                          today=date.today().isoformat(), max_mb=settings.max_upload_mb)

        name = Path(file.filename or "").name
        ext = Path(name).suffix.lower()
        if not name or ext not in settings.allowed_extensions:
            return fail("Unsupported file format. Allowed: "
                        + ", ".join(settings.allowed_extensions))

        # Check Ollama BEFORE spending minutes transcribing.
        try:
            await _run_blocking(_preflight, request.app)
        except OllamaError as e:
            return fail(str(e), 503)

        meeting_id = uuid.uuid4().hex
        path = settings.upload_dir / f"{meeting_id}{ext}"
        limit = settings.max_upload_mb * 1024 * 1024
        size = 0
        with open(path, "wb") as buf:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    buf.close()
                    path.unlink(missing_ok=True)
                    return fail(f"File is larger than {settings.max_upload_mb} MB.", 413)
                buf.write(chunk)

        request.app.state.db.create(meeting_id, name, meeting_date or date.today().isoformat(),
                                    str(path))
        request.app.state.executor.submit(process, request.app, meeting_id)
        return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)

    @app.get("/meetings/{meeting_id}")
    async def meeting_page(request: Request, meeting_id: str):
        m = request.app.state.db.get(meeting_id)
        if not m:
            return render(request, "index.html", status_code=404,
                          meetings=request.app.state.db.list(), error="Meeting not found.")
        return render(request, "meeting.html", m=m, model=settings.ollama_model)

    @app.get("/meetings/{meeting_id}/status")
    async def meeting_status(request: Request, meeting_id: str):
        m = request.app.state.db.get(meeting_id)
        if not m:
            return JSONResponse({"status": "missing"}, status_code=404)
        return {"status": m["status"], "stage": m["stage"], "error": m["error"]}

    @app.get("/meetings/{meeting_id}/download")
    async def download(request: Request, meeting_id: str):
        m = request.app.state.db.get(meeting_id)
        if not m or not m["minutes"]:
            return JSONResponse({"error": "Minutes not available"}, status_code=404)
        minutes = MeetingMinutes.model_validate(m["minutes"])
        out = generate_docx(minutes, settings.output_dir / f"{meeting_id}.docx", m["filename"])
        stem = Path(m["filename"]).stem or "meeting"
        return FileResponse(
            out, filename=f"Minutes - {stem}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @app.post("/meetings/{meeting_id}/retry")
    async def retry(request: Request, meeting_id: str):
        db = request.app.state.db
        m = db.get(meeting_id)
        if m and m["status"] == "failed":
            db.update(meeting_id, status="queued", stage="Queued", error="")
            request.app.state.executor.submit(process, request.app, meeting_id)
        return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)

    @app.post("/meetings/{meeting_id}/delete")
    async def delete(request: Request, meeting_id: str):
        db = request.app.state.db
        m = db.get(meeting_id)
        if m:
            if m["audio_path"]:
                Path(m["audio_path"]).unlink(missing_ok=True)
            (settings.output_dir / f"{meeting_id}.docx").unlink(missing_ok=True)
            db.delete(meeting_id)
        return RedirectResponse("/", status_code=303)

    return app


# ---------------------------------------------------------------- helpers
async def _run_blocking(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *args)


def _preflight(app: FastAPI) -> None:
    llm = app.state.llm
    if llm is not None:  # None when a test agent is injected
        llm.check()


def process(app: FastAPI, meeting_id: str) -> None:
    """Background job: transcribe -> analyze -> save. Resumes from a saved transcript."""
    db, settings = app.state.db, app.state.settings
    try:
        m = db.get(meeting_id)
        if not m:
            return
        db.update(meeting_id, status="processing", error="")

        transcript = m["transcript"]
        if not transcript:
            db.update(meeting_id, stage="Transcribing audio")
            transcript = app.state.transcriber.transcribe(m["audio_path"])
            db.update(meeting_id, transcript=transcript)  # saved so a retry skips this step

        db.update(meeting_id, stage=f"Analyzing with {settings.ollama_model}")
        minutes = app.state.agent.analyze(transcript, m["meeting_date"])
        if not minutes.date:
            minutes.date = m["meeting_date"]

        db.update(meeting_id, status="done", stage="Done", minutes=minutes)
        if settings.delete_audio_after and m["audio_path"]:
            Path(m["audio_path"]).unlink(missing_ok=True)
    except Exception as e:
        log.exception("Job %s failed", meeting_id)
        db.update(meeting_id, status="failed", stage="Failed", error=str(e))


app = create_app()
