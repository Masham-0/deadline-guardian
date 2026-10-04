import os
from dotenv import load_dotenv

# Load environment variables from .env if available
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

    # Provide a placeholder key if none set (e.g. for Ollama which ignores keys)
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
            temperature=0.2
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
