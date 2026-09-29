from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.templating import Jinja2Templates

from app.transcription.whisper import Transcriber


BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


ALLOWED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4"
}


app = FastAPI(
    title="Local Meeting AI Agent"
)


templates = Jinja2Templates(
    directory=str(BASE_DIR / "app" / "templates")
)


@app.get("/")
async def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/upload")
async def upload_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={}
    )


@app.post("/upload")
async def upload_meeting(
    request: Request,
    file: UploadFile = File(...)
):

    # Check file extension
    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:

        return templates.TemplateResponse(
            request=request,
            name="upload.html",
            context={
                "error": "Unsupported file format."
            }
        )

    # Create safe file path
    file_path = UPLOAD_DIR / Path(file.filename).name

    # Save uploaded file
    with open(file_path, "wb") as buffer:

        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    # Transcribe meeting
    transcriber = Transcriber()

    transcript = transcriber.transcribe(
        str(file_path)
    )

    # Show transcript on dashboard
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={
            "success": f"Meeting uploaded successfully: {file.filename}",
            "transcript": transcript
        }
    )
