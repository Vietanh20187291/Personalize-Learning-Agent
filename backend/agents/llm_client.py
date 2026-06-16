"""
LLM Client với Gemini fallback.
Khi Groq chạm rate limit, tự động chuyển sang Gemini.

Cấu hình trong file .env:
  GROQ_KEY_EVALUATION=gsk_xxx       (bắt buộc - Groq primary)
  GEMINI_API_KEY=AIzaSyxxx           (tùy chọn - Gemini fallback)
"""
import os
import json
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------ #
#  Resolve API keys                                                   #
# ------------------------------------------------------------------ #

def _resolve_groq_key(extra_names: Optional[List[str]] = None) -> str:
    """Tìm Groq API key từ các biến môi trường."""
    candidates = list(extra_names or []) + [
        "GROQ_KEY_EVALUATION",
        "GROQ_KEY_ASSESSMENT",
        "GROQ_API_KEY",
        "GROQ_KEY_ADAPTIVE",
        "GROQ_KEY_DEBUG",
    ]
    blocked = ("dummy", "testing", "placeholder")
    for name in candidates:
        val = (os.getenv(name) or "").strip()
        if val and not any(t in val.lower() for t in blocked):
            return val
    return ""


def _resolve_gemini_key() -> str:
    """Tìm Gemini API key."""
    for name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        val = (os.getenv(name) or "").strip()
        if val and not any(t in val.lower() for t in ("dummy", "testing", "placeholder")):
            return val
    return ""


# ------------------------------------------------------------------ #
#  LLM Client với tự động fallback                                    #
# ------------------------------------------------------------------ #

class LLMClient:
    """
    LLM client tự động fallback: Groq → Gemini.

    Cách dùng:
        client = LLMClient()
        reply = client.chat(messages=[...], model="llama-3.3-70b-versatile")

    Nếu Groq lỗi (rate limit, 429, 500) → tự chuyển sang Gemini.
    """

    def __init__(self, groq_key: Optional[str] = None):
        self.groq_key = groq_key or _resolve_groq_key()
        self.gemini_key = _resolve_gemini_key()

        self._groq_client = None
        self._gemini_model = None

        if self.groq_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self.groq_key)
            except Exception as e:
                print(f"⚠️ Groq init failed: {e}")

        self._init_gemini()

    def _init_gemini(self):
        """Khởi tạo Gemini model nếu có key."""
        if not self.gemini_key:
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_key)
            self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            print(f"⚠️ Gemini init failed: {e}")

    @property
    def has_groq(self) -> bool:
        return self._groq_client is not None

    @property
    def has_gemini(self) -> bool:
        return self._gemini_model is not None

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.3,
        max_tokens: int = 900,
    ) -> str:
        """
        Gọi LLM với tự động fallback Groq → Gemini.
        Trả về text phản hồi.
        """
        # Thử Groq trước
        if self._groq_client:
            try:
                completion = self._groq_client.chat.completions.create(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return str(completion.choices[0].message.content or "").strip()
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = any(t in error_str for t in ["rate_limit", "429", "too many", "limit"])
                if is_rate_limit and self.has_gemini:
                    print(f"⚠️ Groq rate limit hit, falling back to Gemini: {e}")
                elif is_rate_limit:
                    print(f"⚠️ Groq rate limit và không có Gemini fallback: {e}")
                    raise
                else:
                    print(f"⚠️ Groq error: {e}")
                    if not self.has_gemini:
                        raise

        # Fallback sang Gemini
        if self._gemini_model:
            try:
                # Convert messages sang format Gemini
                system_prompt = ""
                user_parts = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "system":
                        system_prompt = content
                    elif role == "user":
                        user_parts.append(content)
                    elif role == "assistant":
                        user_parts.append(f"Assistant: {content}")

                full_prompt = "\n".join(user_parts)
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{full_prompt}"

                response = self._gemini_model.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                )
                return str(response.text or "").strip()
            except Exception as e:
                print(f"⚠️ Gemini fallback also failed: {e}")
                raise

        raise RuntimeError("Không có LLM client nào khả dụng (cần Groq hoặc Gemini API key)")
