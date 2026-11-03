from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from .config import settings
from .documents import extract_document, validate_text
from .errors import AppError
from .summarizer import LENGTHS, summarize

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="PIXEL//BRIEF", docs_url=None, redoc_url=None)


class RequestLimitMiddleware:
    """Bound the complete request, including streamed/chunked multipart uploads."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        received = 0
        limit = settings.max_file_bytes + 64 * 1024

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "Request is too large. Maximum file size is 5 MB.")
            return message

        await self.app(scope, bounded_receive, send)


app.add_middleware(RequestLimitMiddleware)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AppError)
async def app_error(request: Request, error: AppError):
    return JSONResponse({"error": error.message}, status_code=error.status)


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    return JSONResponse({"error": str(error.detail)}, status_code=error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    return JSONResponse({"error": "Invalid request. Check your input and try again."}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    return JSONResponse({"error": "An unexpected error occurred. Please try again."}, status_code=500)


@app.get("/api/health")
async def health():
    return {"status": "online", "server_key_configured": bool(settings.api_key),
            "max_file_bytes": settings.max_file_bytes, "max_input_chars": settings.max_input_chars,
            "max_input_bytes": settings.max_input_bytes}


@app.post("/api/summarize")
async def create_summary(request: Request):
    async with request.form(max_files=1, max_fields=3, max_part_size=65536) as form:
        text = form.get("text", "")
        length = form.get("length", "standard")
        api_key = form.get("api_key", "")
        file = form.get("file")
        if not all(isinstance(value, str) for value in (text, length, api_key)):
            raise AppError("Invalid input fields.")
        if length not in LENGTHS:
            raise AppError("Choose Short or Standard summary length.")
        if file is not None and not isinstance(file, UploadFile):
            raise AppError("Choose a valid document.")
        if file and text.strip():
            raise AppError("Submit either pasted text or a document, not both.")
        if file:
            content = await file.read(settings.max_file_bytes + 1)
            source = await run_in_threadpool(extract_document, file.filename or "", content)
        else:
            source = validate_text(text)
        key = api_key.strip() or settings.api_key.strip()
        summary = await summarize(source, length, key)
        return {"summary": summary, "source_characters": len(source), "length": length}


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
