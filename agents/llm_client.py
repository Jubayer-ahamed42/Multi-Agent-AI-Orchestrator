import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
import litellm
from config import get_active_model, get_api_key_for_model, get_api_keys_pool, sanitize_model_name

litellm.suppress_debug_info = True
logger = logging.getLogger(__name__)

def call_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    response_format: Optional[Dict[str, Any]] = None,
    max_tokens: int = 4000,
    max_retries: int = 4
) -> str:
    """Invokes the configured LLM through litellm with automatic key failover and rate-limit retry."""
    raw_model = model or get_active_model()
    active_model = sanitize_model_name(raw_model)
    available_keys = get_api_keys_pool(active_model)
    if not available_keys:
        single_key = get_api_key_for_model(active_model)
        if single_key:
            available_keys = [single_key]

    last_exception = None

    # Try each available API key (primary fresh key, then auto-failover to backup key)
    for key_idx, current_key in enumerate(available_keys or [None]):
        kwargs = {
            "model": active_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        if current_key:
            kwargs["api_key"] = current_key
        if response_format:
            kwargs["response_format"] = response_format

        key_label = "primary" if key_idx == 0 else f"backup #{key_idx}"

        for attempt in range(1, max_retries + 1):
            try:
                response = litellm.completion(**kwargs)
                content = response.choices[0].message.content
                return content or ""
            except Exception as e:
                err_str = str(e).lower()
                last_exception = e
                # If daily quota is exhausted on this key, failover to next key immediately without waiting
                if "quota" in err_str or "resource_exhausted" in err_str or "exceeded your current quota" in err_str:
                    logger.warning(
                        f"[{key_label.upper()} KEY] Model {active_model} quota exhausted. "
                        f"Immediately switching to next available key in pool..."
                    )
                    break
                # Handle transient high demand (503) or rate limit (429 concurrency)
                elif "503" in err_str or "unavailable" in err_str or "429" in err_str:
                    sleep_time = attempt * 1.5
                    logger.warning(f"LLM 503/429 transient error on attempt {attempt}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                elif "api_key" in err_str or "authentication" in err_str:
                    logger.warning(f"[{key_label.upper()} KEY] Auth/Key error. Trying next key...")
                    break
                else:
                    time.sleep(1)

    # Automatic fallback cascade for Gemini models across fallback models
    if "gemini" in active_model:
        fallback_candidates = [
            "gemini/gemini-3.5-flash-lite",
            "gemini/gemini-flash-latest",
            "gemini/gemini-3.6-flash"
        ]
        for fb_model in fallback_candidates:
            if fb_model == active_model:
                continue
            for fb_key in available_keys or [None]:
                try:
                    logger.info(f"Attempting automatic fallback to {fb_model}...")
                    fb_kwargs = {
                        "model": fb_model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    }
                    if fb_key:
                        fb_kwargs["api_key"] = fb_key
                    resp = litellm.completion(**fb_kwargs)
                    if resp and resp.choices and resp.choices[0].message.content:
                        return resp.choices[0].message.content
                except Exception as fb_err:
                    logger.debug(f"Fallback model {fb_model} failed: {fb_err}")
                    continue

    logger.error(f"All keys and fallback attempts failed for model {active_model}: {last_exception}")
    raise last_exception
