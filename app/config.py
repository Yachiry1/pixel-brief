import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("GROQ_API_KEY", "")
    model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", "5242880"))
    max_input_chars: int = int(os.getenv("MAX_INPUT_CHARS", "20000"))
    # UTF-8 bytes conservatively bound token count, including multilingual input.
    max_input_bytes: int = int(os.getenv("MAX_INPUT_BYTES", "24000"))
    timeout: float = float(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))


settings = Settings()
