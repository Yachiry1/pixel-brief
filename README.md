---
title: PIXEL BRIEF
emoji: 🟩
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Retro pixel interface for single-request AI document summaries
---

# PIXEL//BRIEF

**Less text. More meaning.** A complete, responsive AI summarizer with a charcoal and lime pixel interface. Paste text or upload TXT, MD, PDF, and DOCX files, choose a short (1–2 sentences) or standard (3–4 sentences) summary, and copy the result.

FastAPI serves the vanilla HTML/CSS/JavaScript frontend and handles extraction and Groq chat completions. No database, authentication, agent framework, chunking, or browser-to-Groq requests.

## Run locally

Use Python 3.12 or newer.

```sh
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env to set GROQ_API_KEY (optional when supplying a key in the UI).
uvicorn app.main:app --host 0.0.0.0 --port 7860 --no-access-log
```

Open **http://localhost:7860**. Create a Groq key at [Groq Console](https://console.groq.com/keys). The optional password input overrides the server key for that request. User keys remain in the current page's memory and are never written to localStorage or sent back in responses. Closing the page clears them. Use HTTPS when hosting remotely. Never commit `.env`.

Alternatively, with [uv](https://docs.astral.sh/uv/):

```sh
uv run --no-project --with-requirements requirements.txt uvicorn app.main:app --host 0.0.0.0 --port 7860 --no-access-log
```

## Exactly one LLM request

`app/summarizer.py` contains one `client.chat.completions.create()` invocation. The official Groq SDK is configured with **`max_retries=0`**, so rate limits, connection failures, and timeouts never trigger a hidden second request. Invalid input makes zero LLM requests. Health checks and parsing make zero LLM requests. Clicking again after an error is a separate user-initiated request.

The complete validated source is sent in one user message, with a system prompt that preserves language, facts, and requested length; treats source text as untrusted data; and forbids conversational introductions. Short mode explicitly limits output to two sentences and prioritizes the central idea over secondary details; Standard limits it to four. The prompt asks the model to silently check and condense its draft before responding, within the same API request. The application returns `message.content` with only outer whitespace removed. It never rewrites the output or makes a repair call. Sentence counts, factual accuracy, and injection resistance are model instructions, not absolute guarantees; review important results. Very short sources may produce fewer sentences to avoid padding. Empty and truncated completions produce a useful error.

The default model, [`openai/gpt-oss-20b`](https://console.groq.com/docs/model/openai/gpt-oss-20b), was verified against [Groq's supported models](https://console.groq.com/docs/models) during implementation. For GPT-OSS, `include_reasoning=False` keeps reasoning out of the result, and low reasoning effort limits latency. Temperature is 0.2. Account quotas and model availability may change; free-tier access and token limits depend on your Groq account.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | Server key; optional if the visitor supplies a key |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq chat-completion model |
| `MAX_FILE_BYTES` | `5242880` | Maximum upload, 5 MiB |
| `MAX_INPUT_CHARS` | `20000` | Maximum full extracted/pasted text length |
| `MAX_INPUT_BYTES` | `24000` | Conservative UTF-8 input budget |
| `GROQ_TIMEOUT_SECONDS` | `60` | Upstream request timeout |

Both character and UTF-8 byte limits apply. UTF-8 bytes conservatively bound source tokens without a tokenizer dependency, with output and prompt headroom for the default 131,072-token context. This is deliberately below that context window; Groq's free-tier rate budgets can be lower and can still cause 429 errors. If selecting a smaller-context model, lower input limits and verify that its API supports `temperature` and `max_completion_tokens`. No text is silently truncated. The UI obtains limits from the backend. The total multipart request is bounded to the file limit plus 64 KiB, including streamed uploads.

TXT/MD support strict UTF-8 (with optional BOM) and BOM-marked UTF-16/32; other encodings prompt the user to export UTF-8. PDF extraction uses pypdf and rejects encrypted and image-only PDFs. No OCR is performed. DOCX uses python-docx, preserving body paragraph/table order, with a 25 MiB uncompressed archive limit. It summarizes main-body text, not embedded images, comments, text boxes, or page headers/footers. Corrupted and empty documents receive clear errors. Uploaded documents aren't persistently stored; multipart handling may spool large uploads to temporary storage, closed after each request. Content is sent to Groq under its data policies.

## Free deployment on Render

[Deploy to Render](https://render.com/deploy?repo=https://github.com/Yachiry1/pixel-brief)

The included `render.yaml` creates one Python Web Service on the **Free** plan. `.python-version` selects Python 3.12. No Docker build or separate frontend service is needed.

1. Open the deploy link above, sign in to Render, and connect/authorize this GitHub repository if prompted.
2. Review the Blueprint: one service named `pixel-brief`, plan **Free**.
3. Enter your `GROQ_API_KEY` in the prompted secret field. It is stored in Render, not Git. Alternatively, create the service manually without this variable and supply a key through the app UI.
4. Deploy and wait for **Live**. Open the actual URL Render provides and test a summary.

For manual setup, select **New → Web Service**, connect `Yachiry1/pixel-brief`, choose **Python 3** as the runtime (even though a Dockerfile also exists), and set:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`
- Health check: `/api/health`
- Instance type: **Free**
- Environment secret: `GROQ_API_KEY`

Render's free web services sleep after 15 minutes without inbound traffic, so the next visit can take longer to load. See [Render free service limits](https://render.com/docs/free) and [FastAPI deployment](https://render.com/docs/deploy-fastapi). Uploading this repository does not itself deploy the app; create the service in your Render account.

## Hugging Face Spaces deployment

Creating Docker Spaces currently requires an eligible paid Hugging Face plan. See [current Spaces requirements](https://huggingface.co/docs/hub/spaces-overview). For a free university demo, use Render above.

The repository includes Docker Spaces YAML metadata above and a non-root Docker image binding to `0.0.0.0:7860`.

1. Create a Space at [Hugging Face](https://huggingface.co/new-space). Select **Docker → Blank** and CPU Basic.
2. Upload this project's `app/`, `static/`, `requirements.txt`, `Dockerfile`, `.dockerignore`, and this `README.md` to the Space repository. Or push the project with Git using the commands shown on your Space's Files tab.
3. In **Settings → Variables and secrets → New secret**, set `GROQ_API_KEY` to your key. Do not put it in a Dockerfile, README, or ordinary public variable.
4. Optionally set `GROQ_MODEL` and limit settings as Space variables. Rebuild/restart the Space after changing configuration.
5. Wait for the Docker build to finish. Open the actual URL provided by Hugging Face and test a summary. Without a server secret, visitors can supply their own keys.

See [official Docker Spaces documentation](https://huggingface.co/docs/hub/spaces-sdks-docker). This project is prepared for deployment; no hosted deployment URL is claimed. A public Space with a server key lets visitors consume that key's quota; choose Space visibility and account limits accordingly.

Local Docker:

```sh
docker build -t pixel-brief .
docker run --rm -p 7860:7860 --env-file .env pixel-brief
```

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest tests/test_app.py -q
# Browser tests (requires installed Chromium):
python -m playwright install chromium
python -m pytest tests/test_browser.py -q
```

Or run either command with `uv run --no-project --with-requirements requirements-dev.txt` preceding `python`.

Verified during implementation: **49 tests passed** (40 backend tests and 9 Chromium checks), including viewport widths of 360, 390, 768, 1024, and 1440 pixels. Live Groq generation was not tested because no API key was supplied. The Docker build was not verified because this environment denied access to the local Docker daemon.

Backend tests use the **real Groq SDK with an httpx mock transport** to verify exact outgoing request counts and request payloads. They cover English and Ukrainian, both summary lengths, supported formats, empty/corrupt/encrypted/image-only documents, input and upload limits, key precedence, missing/incorrect keys, 429 responses, network/timeouts, and empty/truncated responses. Browser tests check successful output, duplicate-submit protection, copy, validation, upload, keyboard tabs, and desktop/mobile overflow using mocked summary responses. Mocked summaries don't establish live model quality. No live Groq test is required or implied by these checks.

## Structure

```text
app/main.py          FastAPI routes, request limits, friendly errors
app/config.py        Environment configuration
app/documents.py     File extraction and complete-source validation
app/summarizer.py    Prompt and single-request Groq integration
app/errors.py        Safe application errors
static/              Responsive frontend and original SVG/pixel art
tests/              Backend and browser verification
docs/project-uk.md  Ukrainian university submission description
```

Google Fonts supplies Press Start 2P and IBM Plex Mono; readable local monospace fallbacks keep the app usable if the font service is unavailable. All content uses `textContent`, and a Content Security Policy restricts scripts to this app. There is no document or key logging in application code. The UI supports keyboard controls, status announcements, reduced motion, and mobile layouts.
