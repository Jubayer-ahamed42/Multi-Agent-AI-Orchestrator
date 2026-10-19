import os
import logging
from typing import Optional
from google import genai
from google.genai import types
from config import get_api_key_for_model, get_api_keys_pool

logger = logging.getLogger(__name__)

def transcribe_audio_to_text(audio_bytes: bytes, mime_type: str = "audio/wav", api_key: Optional[str] = None) -> str:
    """Converts spoken audio (Bengali/English/mixed) to text using Gemini's native audio understanding.
    
    Args:
        audio_bytes: Raw bytes of the recorded voice.
        mime_type: MIME type of audio (e.g., 'audio/wav', 'audio/mp3', 'audio/webm', 'audio/ogg').
        api_key: Optional Gemini API key override.
        
    Returns:
        Accurate transcription text in the user's spoken language.
    """
    if api_key:
        keys_to_try = [api_key]
    else:
        keys_to_try = get_api_keys_pool("gemini")
        if not keys_to_try:
            fallback_k = os.getenv("GEMINI_API_KEY") or get_api_key_for_model("gemini")
            if fallback_k:
                keys_to_try = [fallback_k]

    if not keys_to_try:
        raise ValueError("Audio transcription requires a GEMINI_API_KEY. Please set it in .env or the sidebar.")

    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.5-flash"
    ]

    prompt = (
        "You are a native speech recognition expert specializing in Bengali and multilingual audio. "
        "Transcribe this audio recording exactly as spoken. "
        "Carefully capture native Bengali accents, colloquial expressions, dialect variations, and technical terms. "
        "Output ONLY the transcribed text without any prefixes, commentary, or markdown formatting."
    )

    last_error = None
    for key in keys_to_try:
        try:
            client = genai.Client(api_key=key)
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, audio_part]
                    )
                    text = response.text.strip() if response.text else ""
                    if text:
                        return text
                except Exception as model_err:
                    last_error = model_err
                    logger.debug(f"Audio transcription with model {model_name} failed: {model_err}")
                    continue
        except Exception as key_err:
            last_error = key_err
            logger.warning(f"Audio transcription key attempt error: {key_err}")
            continue

    logger.error(f"Voice transcription all fallbacks failed: {last_error}")
    raise RuntimeError(f"Voice Recognition Failed: {str(last_error)}")
