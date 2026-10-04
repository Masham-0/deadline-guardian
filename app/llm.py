import os
import base64
from dotenv import load_dotenv

load_dotenv()

try:
    import openai
    from openai import OpenAI
except ImportError:
    openai = None
    OpenAI = None


def get_llm_config() -> tuple[str, str, str]:
    """Retrieve LLM parameters from environment variables."""
    base_url = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gemma-2-9b-it").strip()
    return base_url, api_key, model


def chat(system_prompt: str, user_prompt: str, timeout: float = 60.0) -> str:
    """
    Send chat prompts to OpenAI-compatible LLM endpoint.
    Handles timeouts and formats readable error messages.
    """
    if OpenAI is None:
        raise ImportError("openai package is required. Run `pip install openai`.")

    base_url, api_key, model = get_llm_config()
    effective_api_key = api_key if api_key else "ollama-or-local"

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=effective_api_key,
            timeout=timeout
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2048
        )

        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content or ""
        return "No response generated from LLM."

    except openai.AuthenticationError as e:
        return f"[LLM Error] Authentication failed (401). Please verify your LLM_API_KEY in environment or .env: {e}"
    except openai.RateLimitError as e:
        return f"[LLM Error] Rate limit exceeded (429). Please try again in a few seconds: {e}"
    except openai.APITimeoutError as e:
        return f"[LLM Error] Request timed out ({timeout}s). The LLM provider took too long to respond: {e}"
    except openai.APIConnectionError as e:
        return f"[LLM Error] Could not connect to LLM server at '{base_url}'. Ensure the server is online: {e}"
    except openai.APIError as e:
        return f"[LLM Error] API Error ({e.code}): {e.message}"
    except Exception as e:
        return f"[LLM Error] Unexpected error while calling LLM: {str(e)}"


def chat_stream(system_prompt: str, user_prompt: str, timeout: float = 60.0):
    """
    Stream response text tokens from OpenAI-compatible LLM endpoint.
    Yields chunks of text as strings.
    """
    if OpenAI is None:
        raise ImportError("openai package is required. Run `pip install openai`.")

    base_url, api_key, model = get_llm_config()
    effective_api_key = api_key if api_key else "ollama-or-local"

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=effective_api_key,
            timeout=timeout
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
            stream=True
        )

        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    except Exception as e:
        yield f"\n\n[LLM Stream Error]: {str(e)}"


def describe_image(image_bytes: bytes, mime_type: str = "image/jpeg", mode: str = "FULL", timeout: float = 60.0) -> str:
    """
    Send image bytes to vision-capable LLM model via OpenAI-compatible image_url format.
    """
    if OpenAI is None:
        raise ImportError("openai package is required. Run `pip install openai`.")

    base_url, api_key, model = get_llm_config()
    effective_api_key = api_key if api_key else "ollama-or-local"

    if mode.upper() == "FIGURES":
        prompt_text = (
            "Describe each diagram, chart, table or figure and transcribe any text inside it. "
            "Do not repeat ordinary body text."
        )
    else:
        prompt_text = (
            "Transcribe all text in this image exactly, preserving structure "
            "(headings, bullets, equations, tables). Mark unreadable parts as [illegible]. "
            "Do not summarize or add anything."
        )

    b64_str = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64_str}"

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=effective_api_key,
            timeout=timeout
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=2048
        )

        if response.choices and len(response.choices) > 0:
            res_text = (response.choices[0].message.content or "").strip()
            if res_text.startswith("[Vision Error]") or res_text.startswith("[LLM Error]") or "may not support vision" in res_text:
                return ""
            return res_text
        return ""

    except Exception as e:
        print(f"[Vision Warning] Vision processing skipped: {e}")
        return ""
