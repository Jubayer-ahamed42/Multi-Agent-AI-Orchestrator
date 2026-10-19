import re
import io
import logging
from typing import Optional
from gtts import gTTS

logger = logging.getLogger(__name__)

def text_to_speech_bengali(text: str, max_chars: int = 400) -> Optional[bytes]:
    """Converts response text to natural Bengali spoken audio (MP3).
    
    Args:
        text: Response string (may contain markdown).
        max_chars: Character limit for snappy voice playback.
        
    Returns:
        MP3 audio bytes or None if conversion fails.
    """
    if not text or not text.strip():
        return None

    try:
        # 1. Clean markdown formatting, code blocks, tables, and URLs for speech
        clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        clean = re.sub(r"\[.*?\]\(.*?\)", "", clean)
        clean = re.sub(r"[\*\_#`>\$]", "", clean)
        clean = re.sub(r"\|.*?\|", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        if not clean:
            return None

        # Take first few meaningful sentences
        speech_text = clean[:max_chars].strip()
        if len(clean) > max_chars:
            # Cut at last period/danda
            last_punct = max(speech_text.rfind("।"), speech_text.rfind("."))
            if last_punct > 50:
                speech_text = speech_text[:last_punct + 1]

        # Detect if text contains Bengali characters (\u0980-\u09FF)
        has_bengali = bool(re.search(r"[\u0980-\u09FF]", speech_text))
        tts_lang = "bn" if has_bengali else "en"

        tts = gTTS(text=speech_text, lang=tts_lang, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.getvalue()
    except Exception as e:
        logger.warning(f"TTS conversion skipped: {e}")
        return None
