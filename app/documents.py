from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from pypdf import PdfReader

from .config import settings
from .errors import AppError

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


def validate_text(text: str) -> str:
    text = text.strip()
    if not text or not any(char.isalnum() for char in text):
        raise AppError("No readable text found. Paste some text or choose a document containing text.")
    if len(text) > settings.max_input_chars:
        raise AppError(f"Text exceeds the {settings.max_input_chars:,}-character limit. Shorten it and try again.", 413)
    if len(text.encode("utf-8")) > settings.max_input_bytes:
        raise AppError(f"Text exceeds the {settings.max_input_bytes:,}-byte model input limit. Shorten it and try again.", 413)
    if "\x00" in text:
        raise AppError("The document contains invalid text characters. Export it as UTF-8 text and try again.")
    return text


def extract_document(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED:
        raise AppError("Unsupported file type. Choose a TXT, MD, PDF, or DOCX file.")
    if len(content) > settings.max_file_bytes:
        raise AppError("File is too large. Maximum upload size is 5 MB.", 413)
    if not content:
        raise AppError("This file is empty. Choose a document containing text.")
    try:
        if extension in {".txt", ".md"}:
            # BOM-marked UTF-16/32 and strict UTF-8 avoid silently losing source data.
            if content.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
                text = content.decode("utf-32")
            elif content.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = content.decode("utf-16")
            else:
                text = content.decode("utf-8-sig")
        elif extension == ".pdf":
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise AppError("Password-protected PDF files are not supported. Upload an unlocked copy.")
            parts = []
            size = 0
            for page in reader.pages:
                part = page.extract_text() or ""
                size += len(part) + 1
                if size > settings.max_input_chars:
                    raise AppError("PDF text exceeds the input limit. Upload a shorter document.", 413)
                parts.append(part)
            text = "\n".join(parts)
            if not text.strip():
                raise AppError("This PDF has no extractable text. Scanned or image-only PDFs need OCR, which is not supported.")
        else:
            # Bound decompressed XML before python-docx expands the archive.
            with ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                    raise AppError("The DOCX expands beyond the supported size. Upload a smaller document.", 413)
            document = Document(BytesIO(content))
            parts = []
            for block in document.iter_inner_content():
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.extend("\t".join(cell.text for cell in row.cells) for row in block.rows)
            text = "\n".join(parts)
    except AppError:
        raise
    except UnicodeError:
        raise AppError("Unable to decode this text file. Save it as UTF-8 and upload it again.") from None
    except Exception:
        raise AppError("Unable to read this document. It may be corrupted, encrypted, or incorrectly named.") from None
    return validate_text(text)
