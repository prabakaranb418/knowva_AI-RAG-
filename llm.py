"""Single place that talks to Gemini, shared by question answering and summaries."""
import logging
import os
import time

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash-lite"
_RETRYABLE = ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "timed out")


class LLMError(RuntimeError):
    """Raised with a message that is safe to show to the user."""


def generate(prompt, system=None, max_tokens=None, temperature=0.2, attempts=3):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise LLMError("GEMINI_API_KEY is not configured. Add it to your .env file.")

    try:
        from google import genai
    except ImportError as exc:
        raise LLMError("The google-genai package is not installed. Run: pip install -r requirements.txt") from exc

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    limit = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "900"))
    client = genai.Client(api_key=api_key)
    config = {"temperature": temperature, "max_output_tokens": limit}
    if system:
        config["system_instruction"] = system

    last_error = None
    for attempt in range(attempts):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            text = (response.text or "").strip()
            if not text:
                raise LLMError("Gemini returned an empty response. Try again or rephrase.")
            return text
        except LLMError:
            raise
        except Exception as exc:  # network, quota, model name, safety block...
            last_error = exc
            retryable = any(token in str(exc) for token in _RETRYABLE)
            logger.warning("Gemini call failed (attempt %s/%s): %s", attempt + 1, attempts, type(exc).__name__)
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(2 ** attempt)

    raise LLMError(
        "Gemini could not generate a response. Check the model name, API key, quota and network connection."
    ) from last_error
