import os
import json
import random
import re
import urllib.request
import urllib.error
from sqlalchemy.orm import Session
from groq import Groq
from dotenv import load_dotenv
from db.models import QuestionBank, LearnerProfile, Subject
from rag.vector_store import get_vector_store

load_dotenv()

class AssessmentAgent:
    def __init__(self, db: Session):
        self.db = db
        self.provider = os.getenv("ASSESSMENT_LLM_PROVIDER", "ollama").strip().lower()
        self.model = os.getenv(
            "ASSESSMENT_LLM_MODEL",
            "qwen2.5:14b" if self.provider == "ollama" else "deepseek-r1-distill-llama-70b",
        )

        self.client = None
        self.api_key = os.getenv("GROQ_KEY_ASSESSMENT")
        self.ollama_host = os.getenv("ASSESSMENT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        if self.provider == "groq":
            if not self.api_key:
                raise ValueError("Thiếu GROQ_KEY_ASSESSMENT cho provider=groq")
            self.client = Groq(api_key=self.api_key)

        self.vector_store = get_vector_store()

    def _chat_json(self, prompt: str, system_prompt: str, temperature: float, max_tokens: int):
        if self.provider == "groq":
            res = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = res.choices[0].message.content
            clean = re.sub(r'```json|```', '', raw).strip()
            return json.loads(clean)

        # Ollama (free local): gọi REST API, ép output JSON qua prompt.
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        req = urllib.request.Request(
            f"{self.ollama_host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            clean = re.sub(r'```json|```', '', content).strip()
            return json.loads(clean)

    # ========================
    # SUBJECT HELPER
    # ========================
    def _resolve_subject_id(self, subject: str):
        sub = self.db.query(Subject).filter(Subject.name == subject).first()
        if sub:
            return sub.id

        sub = Subject(name=subject, description=f"Môn {subject}")
        self.db.add(sub)
        self.db.flush()
        return sub.id

    def _clean_text(self, text: str):
        return re.sub(r"\s+", " ", text or "").strip()

    def _is_meaningful_text(self, text: str, min_len: int = 10):
        t = self._clean_text(text)
        if len(t) < min_len:
            return False
        if not re.search(r"[A-Za-zÀ-ỹ]", t):
            return False
        if re.search(r"^(a|b|c|d)$", t.lower()):
            return False
        if re.search(r"[\uFFFD]", t):
            return False
        return True

    def _is_valid_question(self, q: str, concept: str):
        q_clean = self._clean_text(q).lower()
        c_clean = self._clean_text(concept).lower()

        if len(q_clean) < 18 or len(q_clean) > 260:
            return False
        if "_____" in q_clean or "chi tiết còn thiếu" in q_clean:
            return False
        if c_clean and c_clean not in q_clean and len(set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", q_clean)).intersection(set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", c_clean)))) == 0:
            return False
        return True

    def _is_valid_options(self, options):
        if len(options) != 4:
            return False

        seen = set()
        for opt in options:
            clean = re.sub(r'^[A-D][\.\)]\s*', '', str(opt)).strip()
            low = clean.lower()
            if not self._is_meaningful_text(clean, min_len=8):
                return False
            if low in seen:
                return False
            seen.add(low)
        return True

    def _build_rag_context(self, subject: str):
        # Dùng toàn bộ retrieval cho môn để trích xuất phạm vi khái niệm trước khi tạo câu hỏi.
        docs = self.vector_store.similarity_search(
            f"Tổng hợp tất cả khái niệm cốt lõi và chương mục của môn {subject}",
            k=80,
        )

        if not docs:
            return ""

        lines = []
        seen = set()
        for d in docs:
            for raw_ln in (d.page_content or "").splitlines():
                ln = self._clean_text(raw_ln)
                if len(ln) < 20:
                    continue
                key = ln.lower()
                if key in seen:
                    continue
                seen.add(key)
                lines.append(ln)

        return "\n".join(lines)[:30000]

    def _extract_concepts_from_rag(self, subject: str, rag_context: str):
        if not rag_context:
            return []

        prompt = f"""
Bạn là giảng viên đại học môn "{subject}".

Nhiệm vụ:
1. Đọc toàn bộ ngữ cảnh RAG.
2. Trích xuất TẤT CẢ khái niệm liên quan trực tiếp đến môn học.
3. Chỉ trả về danh sách khái niệm ngắn gọn, ví dụ:
   - Lập lịch tiến trình
   - Thao tác với tiến trình
   - Truyền thông giữa các tiến trình

Yêu cầu:
- Không trả câu giải thích dài.
- Không trả dữ liệu rác.
- Không trả trùng lặp.

Output JSON:
{{"concepts": ["..."]}}

Ngữ cảnh RAG:
<<<
{rag_context}
>>>
"""

        try:
            data = self._chat_json(
                prompt=prompt,
                system_prompt="Chỉ trả JSON hợp lệ.",
                temperature=0.2,
                max_tokens=2500,
            )

            concepts = []
            for c in data.get("concepts", []):
                text = self._clean_text(str(c))
                if len(text) < 4 or len(text) > 120:
                    continue
                concepts.append(text)

            # de-dup theo lowercase
            unique = []
            seen = set()
            for c in concepts:
                key = c.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(c)

            return unique
        except Exception as e:
            print(f"❌ Lỗi trích xuất concepts từ RAG: {e}")
            return []

    def _generate_question_for_concept(self, subject: str, concept: str):
        prompt = f"""
Bạn là giảng viên đại học.

Hãy tạo 1 câu hỏi kiểm tra kiến thức cho khái niệm sau trong môn "{subject}":
{concept}

Yêu cầu:
- Câu hỏi rõ nghĩa, trực tiếp, tự nhiên.
- Ưu tiên kiểu: "{concept} là gì?" hoặc hỏi vai trò/đặc điểm cốt lõi.
- Không dài dòng.

Output JSON:
{{"question": "..."}}
"""

        try:
            data = self._chat_json(
                prompt=prompt,
                system_prompt="Chỉ trả JSON hợp lệ.",
                temperature=0.3,
                max_tokens=300,
            )
            return self._clean_text(data.get("question", ""))
        except Exception as e:
            print(f"❌ Lỗi tạo câu hỏi cho concept '{concept}': {e}")
            return ""

    def _generate_answers_for_question(self, subject: str, concept: str, question: str):
        # Theo yêu cầu: AI tự tạo đáp án, không dùng hoặc phụ thuộc trực tiếp câu văn tài liệu.
        prompt = f"""
Bạn là giảng viên đại học.

Môn: {subject}
Khái niệm: {concept}
Câu hỏi: {question}

Nhiệm vụ:
1. Tạo 1 đáp án đúng.
2. Tạo 3 đáp án sai nhưng cùng domain, rất giống phong cách diễn đạt, và chắc chắn sai.

Yêu cầu:
- Không trả nhãn A/B/C/D trong nội dung đáp án.
- Không trả câu vô nghĩa.
- Không lặp lại đáp án.
- Không dùng nội dung tài liệu nguồn; chỉ dựa vào hiểu biết chuyên môn của AI.

Output JSON:
{{
  "correct_answer": "...",
  "wrong_answers": ["...", "...", "..."]
}}
"""

        try:
            data = self._chat_json(
                prompt=prompt,
                system_prompt="Chỉ trả JSON hợp lệ.",
                temperature=0.4,
                max_tokens=700,
            )

            correct = self._clean_text(str(data.get("correct_answer", "")))
            wrongs = [self._clean_text(str(x)) for x in data.get("wrong_answers", [])]
            wrongs = [w for w in wrongs if w]

            return correct, wrongs
        except Exception as e:
            print(f"❌ Lỗi tạo đáp án cho concept '{concept}': {e}")
            return "", []

    def _create_mcq_from_concept(self, subject: str, concept: str, max_retries: int = 3):
        # Validation + regenerate: nếu câu hỏi/đáp án rác thì sinh lại.
        for _ in range(max_retries):
            question = self._generate_question_for_concept(subject, concept)
            if not self._is_valid_question(question, concept):
                continue

            correct, wrongs = self._generate_answers_for_question(subject, concept, question)
            if not self._is_meaningful_text(correct, min_len=8):
                continue
            if len(wrongs) < 3:
                continue

            options_raw = [correct] + wrongs[:3]
            if not self._is_valid_options(options_raw):
                continue

            order = [0, 1, 2, 3]
            random.shuffle(order)
            labels = ["A", "B", "C", "D"]
            final_options = []
            correct_label = "A"
            for pos, idx in enumerate(order):
                final_options.append(f"{labels[pos]}. {options_raw[idx]}")
                if idx == 0:
                    correct_label = labels[pos]

            return {
                "question": question,
                "options": final_options,
                "correct_answer": correct_label,
                "explanation": f"Câu hỏi sinh theo khái niệm '{concept}'.",
            }

        return None

    # ========================
    # MAIN API
    # ========================
    def get_or_create_quiz(self, subject: str, user_id: int, num_questions: int = 20):
        self._resolve_subject_id(subject)

        # Nếu đã có thì lấy random
        existing = self.db.query(QuestionBank).filter(
            QuestionBank.subject == subject
        ).all()

        if len(existing) >= num_questions:
            random.shuffle(existing)
            return self._format(existing[:num_questions])

        # Nếu chưa đủ → generate mới
        needed = num_questions - len(existing)
        print(f"🚀 Generating {needed} questions for subject: {subject}")

        self._generate_from_rag_concepts(subject, needed)

        questions = self.db.query(QuestionBank).filter(
            QuestionBank.subject == subject
        ).all()

        random.shuffle(questions)
        return self._format(questions[:num_questions])

    # ========================
    # FORMAT OUTPUT
    # ========================
    def _format(self, questions):
        result = []
        for q in questions:
            try:
                options = json.loads(q.options)
            except:
                options = []

            result.append({
                "id": q.id,
                "content": q.content,
                "options": options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation
            })
        return result

    # ========================
    # CORE GENERATION (RAG CONCEPT -> MCQ)
    # ========================
    def _generate_from_rag_concepts(self, subject: str, count: int):
        try:
            subject_id = self._resolve_subject_id(subject)
            rag_context = self._build_rag_context(subject)
            concepts = self._extract_concepts_from_rag(subject, rag_context)

            if not concepts:
                print("⚠️ Không trích xuất được concept từ RAG.")
                return

            inserted = 0
            attempts = 0
            max_attempts = max(count * 6, 24)
            used_questions = set()

            while inserted < count and attempts < max_attempts:
                concept = concepts[attempts % len(concepts)]
                attempts += 1

                mcq = self._create_mcq_from_concept(subject, concept, max_retries=3)
                if not mcq:
                    continue

                q = mcq["question"]
                final_opts = mcq["options"]
                ans = mcq["correct_answer"]
                exp = mcq["explanation"]

                q_key = q.lower()
                if q_key in used_questions:
                    continue
                if self.db.query(QuestionBank).filter(QuestionBank.subject == subject, QuestionBank.content == q).first():
                    continue
                used_questions.add(q_key)

                # Insert DB
                db_q = QuestionBank(
                    subject_id=subject_id,
                    subject=subject,
                    difficulty="Basic",
                    content=q,
                    options=json.dumps(final_opts, ensure_ascii=False),
                    correct_answer=ans,
                    explanation=exp,
                    is_used=False,
                    source_file="AI_GENERATED"
                )

                self.db.add(db_q)
                inserted += 1

            self.db.commit()
            print(f"✅ Generated {inserted} questions from {len(concepts)} concepts")

        except Exception as e:
            self.db.rollback()
            print(f"❌ Error: {e}")