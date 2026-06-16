"""
ReviewAgent – Sinh tài liệu ôn tập từ các câu sai của sinh viên.
Gửi danh sách câu sai cho Groq, yêu cầu hệ thống hoá thành tài liệu ôn tập.
"""
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class ReviewAgent:
    def __init__(self):
        self.api_key = self._resolve_groq_api_key()
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self.model = "llama-3.3-70b-versatile"

    # ------------------------------------------------------------------ #
    #  Groq API key resolution (giống pattern của EvaluationAgent)       #
    # ------------------------------------------------------------------ #
    def _resolve_groq_api_key(self) -> str:
        candidate_names = [
            "GROQ_KEY_EVALUATION",
            "GROQ_API_KEY",
            "GROQ_KEY_DEBUG",
            "GROQ_KEY_ADAPTIVE",
        ]
        blocked_tokens = ("dummy", "testing", "placeholder")

        for env_name in candidate_names:
            value = (os.getenv(env_name) or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if any(token in lowered for token in blocked_tokens):
                continue
            return value
        return ""

    # ------------------------------------------------------------------ #
    #  Sinh tài liệu ôn tập từ câu sai                                   #
    # ------------------------------------------------------------------ #
    def generate_review(self, wrong_answers: list[dict]) -> str:
        """
        Nhận danh sách câu sai → gửi Groq → trả về tài liệu Markdown
        được hệ thống hoá theo chủ đề để sinh viên ôn tập.

        Mỗi dict trong wrong_answers có:
            question_text, options, student_choice, correct_answer, explanation
        """
        if not self.client:
            return self._build_fallback_review(wrong_answers)

        qa_text = ""
        for i, wa in enumerate(wrong_answers, 1):
            qa_text += f"\nCâu {i}: {wa.get('question_text', '')}\n"
            options = wa.get("options") or []
            if isinstance(options, list):
                for opt in options:
                    qa_text += f"  {opt}\n"
            qa_text += f"  Bạn chọn: {wa.get('student_choice', '')}\n"
            qa_text += f"  Đáp án đúng: {wa.get('correct_answer', '')}\n"
            explanation = wa.get("explanation", "")
            if explanation:
                qa_text += f"  Giải thích: {explanation}\n"

        prompt = f"""Bạn là một gia sư AI xuất sắc. Một sinh viên vừa làm bài kiểm tra và sai các câu hỏi sau:

{qa_text}

Hãy tổ chức lại các câu sai này thành một tài liệu ôn tập có cấu trúc theo đúng format sau:
1. Phân loại các câu hỏi theo chủ đề/kiến thức (dùng heading ##).
2. Với mỗi chủ đề:
   - Tóm tắt ngắn gọn kiến thức cốt lõi cần nhớ.
   - Giải thích chi tiết tại sao câu trả lời của sinh viên sai.
   - Giải thích vì sao đáp án đúng là đúng.
   - Đưa ra 1-2 câu hỏi ví dụ tương tự kèm đáp án để sinh viên luyện tập thêm.
3. Cuối cùng, tóm tắt những điểm sinh viên cần chú ý ôn tập lại.

Viết bằng tiếng Việt. Dùng định dạng Markdown. Viết chi tiết, dễ hiểu."""

        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Bạn là một gia sư AI chuyên tạo tài liệu ôn tập có cấu trúc. Luôn viết bằng tiếng Việt, chi tiết và dễ hiểu.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.4,
                max_tokens=2500,
            )
            reply = str(completion.choices[0].message.content or "").strip()
            return reply or self._build_fallback_review(wrong_answers)
        except Exception as exc:
            print(f"⚠️ ReviewAgent Groq error: {exc}")
            return self._build_fallback_review(wrong_answers)

    # ------------------------------------------------------------------ #
    #  Fallback khi Groq không khả dụng                                  #
    # ------------------------------------------------------------------ #
    def _build_fallback_review(self, wrong_answers: list[dict]) -> str:
        """Tạo tài liệu ôn tập đơn giản không cần LLM."""
        lines = ["# Tài liệu ôn tập từ câu sai", ""]
        for i, wa in enumerate(wrong_answers, 1):
            lines.append(f"## Câu {i}")
            lines.append(f"**Câu hỏi:** {wa.get('question_text', '')}")
            options = wa.get("options") or []
            if isinstance(options, list) and options:
                lines.append("**Các lựa chọn:**")
                for opt in options:
                    lines.append(f"- {opt}")
            lines.append(f"**Bạn chọn:** {wa.get('student_choice', '')}")
            lines.append(f"**Đáp án đúng:** {wa.get('correct_answer', '')}")
            if wa.get("explanation"):
                lines.append(f"**Giải thích:** {wa.get('explanation')}")
            lines.append("")
        return "\n".join(lines)
