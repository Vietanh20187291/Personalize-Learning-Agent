from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import unicodedata 
import json
import io
import random
import copy
import re
from typing import List, Optional
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

from db.database import get_db
from db import models
from groq import Groq
import os

router = APIRouter()

class ExamRequest(BaseModel):
    class_id: int
    subject: str
    exam_type: str # "trắc nghiệm" hoặc "tự luận"
    num_questions: int
    num_versions: int # Số lượng mã đề
    level: str 


def _normalize_level(level: str) -> str:
    v = (level or "").strip().lower()
    if v in ["cơ bản", "co ban", "beginner", "dễ", "de"]:
        return "Beginner"
    if v in ["trung bình", "trung binh", "intermediate", "medium"]:
        return "Intermediate"
    return "Advanced"


def _collect_chunk_texts(db: Session, allowed_filenames: list, limit: int = 200) -> list:
    if not allowed_filenames:
        return []
    rows = db.query(models.Chunk).filter(models.Chunk.source_file.in_(allowed_filenames)).limit(limit).all()
    texts = []
    for r in rows:
        c = (r.content or "").strip()
        if c:
            texts.append(re.sub(r"\s+", " ", c))
    return texts


def _extract_json_text(raw_text: str) -> str:
    return re.sub(r"```json\s*|\s*```", "", raw_text or "", flags=re.IGNORECASE).strip()


def clean_text(raw_text: str) -> str:
    """Làm sạch trước khi sinh đề để giảm nhiễu đầu vào cho cả model mạnh/yếu."""
    if not raw_text:
        return ""

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines()]
    cleaned_lines = []
    noise_patterns = [
        r"^[\-\*•]+\s*$",
        r"^(mục lục|table of contents)\b",
        r"^(liên hệ|email|sđt|số điện thoại|hotline)\b",
        r"^(trường|khoa|bộ môn|giảng viên|thời khóa biểu|lịch học)\b",
        r"^slide\s*\d+\b",
        r"^chapter\s*\d+\b",
    ]

    for ln in lines:
        if not ln or len(ln) < 12:
            continue
        if re.match(r"^[\-\*•\d\)\.(\[]+\s*", ln) and len(ln.split()) < 5:
            continue
        if any(re.search(p, ln.lower()) for p in noise_patterns):
            continue
        if re.fullmatch(r"[A-ZÀ-Ỵ\s\d\-_:]{4,}", ln) and len(ln.split()) <= 10:
            continue
        cleaned_lines.append(ln)

    merged = " ".join(cleaned_lines)
    raw_sentences = re.split(r"(?<=[\.\!\?\;\:])\s+", merged)
    kept_sentences = []
    for s in raw_sentences:
        s = re.sub(r"\s+", " ", s).strip()
        if 35 <= len(s) <= 320 and re.search(r"[A-Za-zÀ-ỹ]", s):
            kept_sentences.append(s)
    return " ".join(kept_sentences)


def chunk_text(cleaned_text: str, min_words: int = 300, max_words: int = 800) -> List[str]:
    """Chia chunk vừa đủ để giữ ngữ cảnh nhưng không làm model sinh lan man."""
    words = cleaned_text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks = []
    i = 0
    while i < len(words):
        end = min(i + max_words, len(words))
        if end < len(words):
            probe = end
            while probe > i + min_words and not re.search(r"[\.\!\?]$", words[probe - 1]):
                probe -= 1
            if probe > i + min_words:
                end = probe
        chunks.append(" ".join(words[i:end]))
        i = end
    return chunks


def extract_knowledge(chunk: str, subject: str, client: Optional[Groq], level_instruction: str) -> List[str]:
    """Trích xuất statement học thuật trước khi đặt câu hỏi để tránh hỏi trực tiếp từ text thô."""
    if not chunk:
        return []

    if client:
        prompt = f"""
Bạn là trợ lý học thuật. Hãy TRÍCH XUẤT tri thức cốt lõi của môn {subject} từ đoạn sau.
{level_instruction}

Chỉ lấy statement có tính học thuật:
- định nghĩa
- nguyên lý
- kết luận kỹ thuật quan trọng

Loại bỏ:
- tiêu đề, ghi chú hành chính, thông tin liên hệ
- câu mơ hồ, câu chưa hoàn chỉnh

Trả về JSON đúng schema:
{{"items": ["statement 1", "statement 2", ...]}}
Giới hạn 4-8 statement, mỗi statement tự đầy đủ ngữ nghĩa.

Nội dung:
<<<
{chunk}
>>>
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            items = payload.get("items", [])
            return [re.sub(r"\s+", " ", str(x)).strip() for x in items if str(x).strip()]
        except Exception:
            pass

    # Fallback heuristic: dùng câu mang cấu trúc định nghĩa/nguyên lý để vẫn tạo được đề khi LLM yếu/lỗi.
    strong_markers = ["là", "gồm", "bao gồm", "được", "nguyên lý", "công thức", "thuật toán", "điều kiện", "mệnh đề"]
    raw_sentences = re.split(r"(?<=[\.\!\?\;\:])\s+", chunk)
    scored = []
    for s in raw_sentences:
        s = re.sub(r"\s+", " ", s).strip()
        if not (45 <= len(s) <= 260):
            continue
        low = s.lower()
        score = sum(2 for m in strong_markers if m in low) + (1 if re.search(r"\d", s) else 0)
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:8]]


def filter_knowledge(items: List[str]) -> List[str]:
    """Lọc tri thức để chỉ giữ statement rõ ràng, đủ ngữ nghĩa, giảm hallucination downstream."""
    out = []
    seen = set()
    for item in items:
        s = re.sub(r"\s+", " ", item or "").strip(" -:;,.\t\n")
        low = s.lower()
        if not s or len(s) < 40 or len(s) > 260:
            continue
        if s[-1] not in ".!?":
            continue
        if re.search(r"\b(ví dụ|tham khảo|xem thêm|liên hệ|email|hotline|mục lục)\b", low):
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(s)
    return out


def generate_question(knowledge: str, subject: str, client: Optional[Groq], level_instruction: str) -> str:
    """Sinh câu hỏi tách biệt khỏi câu nguồn để tăng tính hiểu bản chất thay vì sao chép."""
    if client:
        prompt = f"""
Bạn là giảng viên môn {subject}. Tạo 1 câu hỏi trắc nghiệm rõ ràng từ knowledge sau.
{level_instruction}

Yêu cầu:
- Câu hỏi tự hiểu được nếu đứng riêng
- Không copy nguyên văn knowledge
- Chỉ hỏi 1 ý chính

Trả về JSON: {{"question": "..."}}

Knowledge:
{knowledge}
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.35,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            q = re.sub(r"\s+", " ", str(payload.get("question", ""))).strip()
            if q:
                return q
        except Exception:
            pass

    anchor = knowledge[:110].strip(" .")
    return f"Trong môn {subject}, nhận định nào phản ánh đúng nhất ý sau: \"{anchor}\"?"


def _heuristic_distractors(correct_answer: str, knowledge: str) -> List[str]:
    numeric_bank = re.findall(r"\d+(?:[\.,]\d+)?", knowledge)
    token_bank = re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", knowledge)
    antonym_pairs = [("tăng", "giảm"), ("đúng", "sai"), ("lớn hơn", "nhỏ hơn"), ("cần", "không cần")]

    def mutate_number(text: str) -> str:
        nums = re.findall(r"\d+(?:[\.,]\d+)?", text)
        if not nums:
            return ""
        old = nums[0]
        replacement = None
        cands = [n for n in numeric_bank if n != old]
        if cands:
            replacement = random.choice(cands)
        if replacement is None:
            try:
                replacement = str(int(float(old.replace(",", "."))) + random.choice([-2, -1, 1, 2]))
            except Exception:
                replacement = old + "1"
        return re.sub(re.escape(old), replacement, text, count=1)

    def mutate_term(text: str) -> str:
        words = re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", text)
        if not words:
            return ""
        pick = words[min(1, len(words) - 1)]
        cands = [t for t in token_bank if t.lower() != pick.lower()]
        if not cands:
            return ""
        return re.sub(re.escape(pick), random.choice(cands), text, count=1)

    def mutate_relation(text: str) -> str:
        out = text
        for a, b in antonym_pairs:
            if re.search(re.escape(a), out, flags=re.IGNORECASE):
                return re.sub(re.escape(a), b, out, count=1, flags=re.IGNORECASE)
            if re.search(re.escape(b), out, flags=re.IGNORECASE):
                return re.sub(re.escape(b), a, out, count=1, flags=re.IGNORECASE)
        return ""

    pool = [mutate_number(correct_answer), mutate_term(correct_answer), mutate_relation(correct_answer)]
    result = []
    seen = {correct_answer.lower()}
    for p in pool:
        v = re.sub(r"\s+", " ", (p or "")).strip()[:220]
        if v and v.lower() not in seen:
            seen.add(v.lower())
            result.append(v)
    while len(result) < 3:
        result.append((correct_answer[:120] + " nhưng điều kiện áp dụng khác với nội dung tài liệu.")[:220])
    return result[:3]


def generate_answers(question: str, knowledge: str, subject: str, client: Optional[Groq]) -> dict:
    """Tách riêng bước đáp án đúng và đáp án nhiễu để đảm bảo 4 lựa chọn cùng miền kiến thức."""
    if client:
        prompt = f"""
Bạn là giảng viên môn {subject}. Với question và knowledge bên dưới:
1) Sinh 1 đáp án đúng rõ ràng.
2) Sinh đúng 3 đáp án nhiễu, bắt buộc:
   - cùng chủ đề với đáp án đúng
   - văn phong tương tự
   - hợp lý nhưng sai
   - không lạc đề

Trả về JSON:
{{
  "correct_answer": "...",
  "distractors": ["...", "...", "..."]
}}

Question: {question}
Knowledge: {knowledge}
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=700,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            correct = re.sub(r"\s+", " ", str(payload.get("correct_answer", ""))).strip()
            distractors = [re.sub(r"\s+", " ", str(x)).strip() for x in payload.get("distractors", [])]
            distractors = [d for d in distractors if d]
            if correct and len(distractors) >= 3:
                return {"correct": correct, "distractors": distractors[:3]}
        except Exception:
            pass

    correct = re.sub(r"\s+", " ", knowledge).strip()[:220]
    return {"correct": correct, "distractors": _heuristic_distractors(correct, knowledge)}


def validate_question(question: str, options: List[str], correct_label: str, subject: str, knowledge: str) -> bool:
    """Validation gate chặn câu vô nghĩa/lạc chủ đề trước khi trả về cho người học."""
    if not question or len(question) < 18 or len(question) > 320:
        return False
    if len(options) != 4:
        return False
    if correct_label not in ["A", "B", "C", "D"]:
        return False

    q_low = question.lower()
    if "_____" in question or "chi tiết còn thiếu" in q_low:
        return False

    seen = set()
    for opt in options:
        clean = re.sub(r"^([A-D][\.:\-\)])\s*", "", str(opt)).strip()
        low = clean.lower()
        if not clean or len(clean) < 3:
            return False
        if low in ["a", "b", "c", "d"]:
            return False
        if low in seen:
            return False
        if re.search(r"[\uFFFD]", clean):
            return False
        seen.add(low)

    # Domain consistency: mỗi option cần có giao cắt từ khóa với knowledge để giảm đáp án lạc đề.
    knowledge_terms = set(
        t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", knowledge) if not t.isdigit()
    )
    if knowledge_terms:
        option_ok = 0
        for opt in options:
            opt_terms = set(t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", opt) if not t.isdigit())
            if knowledge_terms.intersection(opt_terms):
                option_ok += 1
        if option_ok < 3:
            return False

    return True


def _semantic_score(text: str) -> int:
    """Đánh điểm rất thô để nhận ra câu rác; mục tiêu là chặn prompt/LLM sinh câu vô nghĩa."""
    s = re.sub(r"\s+", " ", (text or "")).strip().lower()
    if not s:
        return 0

    score = 0
    if len(s) >= 18:
        score += 1
    if re.search(r"[a-zA-ZÀ-ỹ]", s):
        score += 1
    if len(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", s)) >= 4:
        score += 1

    meaningless_patterns = [
        r"\ba\b", r"\bb\b", r"\bc\b", r"\bd\b",
        r"\b(?:abc|xyz|lorem|ipsum|test|dummy)\b",
        r"\b(?:không rõ|vô nghĩa|random|foo|bar)\b",
    ]
    if any(re.search(p, s) for p in meaningless_patterns):
        score -= 2

    if re.search(r"(câu hỏi|đặc điểm|nguyên lý|vai trò|cấu trúc|ý nghĩa|phân biệt|so sánh)", s):
        score += 1
    if re.search(r"[\uFFFD]", s):
        score -= 2

    return score


def question_is_meaningful(question: str, subject: str, keyword: str) -> bool:
    q = re.sub(r"\s+", " ", (question or "")).strip()
    if _semantic_score(q) < 2:
        return False

    low = q.lower()
    if len(q) < 20 or len(q) > 320:
        return False
    if "____" in q or "chi tiết còn thiếu" in low or "điền" in low and len(q) < 40:
        return False

    subject_terms = set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", f"{subject} {keyword}".lower()))
    q_terms = set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", low))
    if subject_terms and not subject_terms.intersection(q_terms):
        return False

    return True


def answer_is_meaningful(answer: str, question: str, keyword: str) -> bool:
    a = re.sub(r"\s+", " ", (answer or "")).strip()
    if _semantic_score(a) < 2:
        return False
    if len(a) < 8 or len(a) > 260:
        return False

    low = a.lower()
    bad_tokens = ["a.", "b.", "c.", "d.", "option", "answer", "đáp án", "tbd", "n/a"]
    if any(tok in low for tok in bad_tokens):
        return False

    q_terms = set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", f"{question} {keyword}".lower()))
    a_terms = set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", low))
    if q_terms and not q_terms.intersection(a_terms):
        return False

    return True


def extract_topic_keywords(text: str, client: Optional[Groq], subject: str) -> List[str]:
    """Chỉ rút keyword/chủ đề để hiểu tài liệu nói về phần nào, không dùng nguyên văn để đặt câu hỏi."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    if client:
        prompt = f"""
Bạn là giảng viên đại học. Hãy đọc tài liệu và chỉ trích xuất keyword/chủ đề để nhận diện nội dung.

Yêu cầu:
- Không tạo câu hỏi từ tài liệu
- Không sao chép câu văn
- Chỉ trả về danh sách từ khóa/chủ đề ngắn gọn
- Ví dụ: lịch sử hệ điều hành, thế hệ máy tính 1945, kiến trúc von Neumann, CPU, bộ nhớ, tiến trình

Trả về JSON:
{{"keywords": ["keyword 1", "keyword 2", "keyword 3"]}}

Môn học: {subject}

Tài liệu:
<<<
{cleaned[:12000]}
>>>
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            keywords = [re.sub(r"\s+", " ", str(x)).strip() for x in payload.get("keywords", []) if str(x).strip()]
            if keywords:
                return list(dict.fromkeys(keywords))[:8]
        except Exception:
            pass

    # Fallback heuristic: suy ra topic từ cụm từ nổi bật, không dùng để sao chép làm câu hỏi.
    terms = re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", cleaned)
    terms = [t for t in terms if not t.isdigit()]
    return list(dict.fromkeys(terms))[:8]


def generate_concept_question(subject: str, keyword: str, client: Optional[Groq], level_instruction: str) -> str:
    """Sinh câu hỏi khái niệm dựa trên chủ đề, thay vì bám câu văn trong tài liệu."""
    keyword = re.sub(r"\s+", " ", (keyword or "")).strip()
    if not keyword:
        return f"Trong môn {subject}, khái niệm nào phản ánh đúng nội dung trọng tâm của chương học?"

    if client:
        prompt = f"""
Bạn là giảng viên đại học.

Nhiệm vụ:
- Dựa trên chủ đề sau, tự nghĩ ra 1 câu hỏi trắc nghiệm kiểm tra hiểu khái niệm.
- KHÔNG sao chép câu từ tài liệu.
- Câu hỏi phải rõ ràng, có nghĩa, đúng chủ đề.
- Ưu tiên hỏi về đặc điểm, vai trò, nguyên lý, cấu trúc, ý nghĩa.

Chủ đề: {keyword}
Môn học: {subject}
{level_instruction}

Trả về JSON:
{{"question": "..."}}
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.45,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            question = re.sub(r"\s+", " ", str(payload.get("question", ""))).strip()
            if question:
                return question
        except Exception:
            pass

    return f"Theo chủ đề {keyword}, đặc điểm hoặc vai trò nào mô tả đúng nhất nội dung này trong môn {subject}?"


def build_concept_correct_answer(subject: str, keyword: str, question: str, client: Optional[Groq]) -> str:
    """Sinh đáp án đúng từ chủ đề đã nhận diện, không phụ thuộc câu văn gốc."""
    keyword = re.sub(r"\s+", " ", (keyword or "")).strip()
    if client:
        prompt = f"""
Bạn là giảng viên đại học.

Hãy trả lời ngắn gọn, chính xác cho câu hỏi dưới đây dựa trên chủ đề đã cho.

Chủ đề: {keyword}
Môn học: {subject}

Câu hỏi: {question}

Yêu cầu:
- Chỉ đưa ra 1 đáp án đúng
- Câu trả lời phải đúng kiến thức, không dài dòng
- Không dùng lại nguyên văn câu hỏi

Trả về JSON:
{{"correct_answer": "..."}}
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.25,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            answer = re.sub(r"\s+", " ", str(payload.get("correct_answer", ""))).strip()
            if answer:
                return answer
        except Exception:
            pass

    return f"Nội dung cốt lõi liên quan đến {keyword} trong môn {subject}."


def build_keyword_distractors(subject: str, keyword: str, correct_answer: str, client: Optional[Groq]) -> List[str]:
    """Sinh 3 đáp án nhiễu cùng miền kiến thức để đánh lừa nhưng vẫn không lạc đề."""
    keyword = re.sub(r"\s+", " ", (keyword or "")).strip()
    if client:
        prompt = f"""
Bạn là giảng viên đại học.

Tạo đúng 3 đáp án sai cho câu hỏi khái niệm sau.

Chủ đề: {keyword}
Môn học: {subject}
Đáp án đúng: {correct_answer}

Yêu cầu:
- Cùng lĩnh vực với đáp án đúng
- Có vẻ hợp lý nhưng chắc chắn sai
- Không vô nghĩa
- Không lạc sang chủ đề khác
- Không trùng hoặc gần như trùng đáp án đúng

Trả về JSON:
{{"distractors": ["...", "...", "..."]}}
"""
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_json_text(chat_completion.choices[0].message.content))
            distractors = [re.sub(r"\s+", " ", str(x)).strip() for x in payload.get("distractors", []) if str(x).strip()]
            cleaned = []
            seen = {correct_answer.lower()}
            for item in distractors:
                if item.lower() not in seen:
                    cleaned.append(item)
                    seen.add(item.lower())
                if len(cleaned) == 3:
                    break
            if len(cleaned) == 3:
                return cleaned
        except Exception:
            pass

    return _heuristic_distractors(correct_answer, keyword or subject)


def _build_fallback_exam_questions(req: ExamRequest, context_summary: str, chunk_texts: list):
    level_tag = _normalize_level(req.level)
    needed = max(1, req.num_questions)
    source_text = "\n".join(chunk_texts[:120]) if chunk_texts else context_summary
    source_text = (source_text or "").strip()

    raw_sentences = re.split(r"(?<=[\.!\?;:])\s+", source_text)
    sentences = []
    for s in raw_sentences:
        clean = re.sub(r"\s+", " ", s).strip()
        if 55 <= len(clean) <= 260:
            sentences.append(clean)
    if not sentences:
        sentences = [f"Trong môn {req.subject}, học viên cần nắm rõ các khái niệm cốt lõi theo từng chủ điểm trước khi làm bài tổng hợp."]

    # Ưu tiên câu mang tính facts: có thuật ngữ, số liệu, hoặc quan hệ logic.
    strong_markers = ["là", "gồm", "bao gồm", "được", "sử dụng", "điều kiện", "công thức", "hàm", "thuật toán", "đạo hàm", "tích phân", "ma trận", "vector", "mệnh đề", "chứng minh"]
    candidate_facts = []
    for s in sentences:
        low = s.lower()
        marker_score = sum(1 for m in strong_markers if m in low)
        number_score = 1 if re.search(r"\d", s) else 0
        token_score = len(re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", s))
        score = marker_score * 3 + number_score * 2 + min(token_score, 12)
        candidate_facts.append((score, s))
    candidate_facts.sort(key=lambda x: x[0], reverse=True)
    facts = [s for _, s in candidate_facts[: max(needed * 3, 20)]]
    if not facts:
        facts = sentences

    questions = []

    if req.exam_type == "trắc nghiệm":
        token_bank = re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", source_text)
        token_bank = [t for t in token_bank if not t.isdigit()]
        token_bank = list(dict.fromkeys(token_bank))

        numeric_bank = re.findall(r"\d+(?:[\.,]\d+)?", source_text)
        numeric_bank = list(dict.fromkeys(numeric_bank))

        antonym_pairs = [
            ("tăng", "giảm"),
            ("đúng", "sai"),
            ("lớn hơn", "nhỏ hơn"),
            ("trước", "sau"),
            ("cần", "không cần"),
            ("hội tụ", "phân kỳ"),
            ("liên tục", "gián đoạn"),
            ("đồng biến", "nghịch biến"),
            ("tối đa", "tối thiểu"),
        ]

        q_templates = [
            "Theo học liệu môn {subject}, nhận định nào phản ánh chính xác nhất nội dung sau: \"{anchor}\"?",
            "Dựa vào tài liệu lớp học môn {subject}, phương án nào đúng với bối cảnh: \"{anchor}\"?",
            "Từ nội dung học liệu môn {subject}, phát biểu nào KHỚP nhất với ý: \"{anchor}\"?",
            "Xét theo tài liệu đã học của môn {subject}, đâu là kết luận phù hợp nhất cho ý: \"{anchor}\"?",
        ]

        def _mutate_with_number(text: str) -> str:
            nums = re.findall(r"\d+(?:[\.,]\d+)?", text)
            if not nums:
                return ""
            old = nums[0]
            replacement = None
            if numeric_bank:
                cands = [n for n in numeric_bank if n != old]
                if cands:
                    replacement = random.choice(cands)
            if replacement is None:
                try:
                    replacement = str(int(float(old.replace(",", "."))) + random.choice([-2, -1, 1, 2]))
                except Exception:
                    replacement = old + "1"
            return re.sub(re.escape(old), replacement, text, count=1)

        def _mutate_with_term(text: str) -> str:
            words = re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", text)
            if not words:
                return ""
            pick = words[min(1, len(words) - 1)]
            cands = [t for t in token_bank if t.lower() != pick.lower() and abs(len(t) - len(pick)) <= 6]
            if not cands:
                return ""
            return re.sub(re.escape(pick), random.choice(cands), text, count=1)

        def _mutate_with_relation(text: str) -> str:
            out = text
            changed = False
            for a, b in antonym_pairs:
                if re.search(re.escape(a), out, flags=re.IGNORECASE):
                    out = re.sub(re.escape(a), b, out, count=1, flags=re.IGNORECASE)
                    changed = True
                    break
                if re.search(re.escape(b), out, flags=re.IGNORECASE):
                    out = re.sub(re.escape(b), a, out, count=1, flags=re.IGNORECASE)
                    changed = True
                    break
            return out if changed else ""

        def _build_distractors(correct: str, ref_idx: int):
            pool = []
            m1 = _mutate_with_number(correct)
            if m1 and m1 != correct:
                pool.append(m1)
            m2 = _mutate_with_term(correct)
            if m2 and m2 != correct:
                pool.append(m2)
            m3 = _mutate_with_relation(correct)
            if m3 and m3 != correct:
                pool.append(m3)

            # Nhiễu gần nghĩa từ fact kế cận để tạo độ nhầm lẫn.
            near = facts[(ref_idx + 1) % len(facts)]
            if near != correct:
                pool.append(near)

            uniq = []
            seen = set()
            for item in pool:
                clean = item.strip()[:210]
                key = clean.lower()
                if not clean or key in seen or key == correct.lower():
                    continue
                seen.add(key)
                uniq.append(clean)
                if len(uniq) == 3:
                    break

            while len(uniq) < 3:
                fallback_near = facts[(ref_idx + len(uniq) + 2) % len(facts)]
                if fallback_near.lower() != correct.lower() and fallback_near.lower() not in seen:
                    uniq.append(fallback_near[:210])
                    seen.add(fallback_near.lower())
                else:
                    uniq.append((correct[:120] + " nhưng điều kiện áp dụng khác với nội dung tài liệu.")[:210])
            return uniq

        for i in range(needed):
            fact = facts[i % len(facts)]
            anchor = fact[:110]
            q = q_templates[i % len(q_templates)].format(subject=req.subject, anchor=anchor)

            correct = fact[:210]
            distractors = _build_distractors(correct, i % len(facts))
            opts = [correct] + distractors

            labels = ["A", "B", "C", "D"]
            order = [0, 1, 2, 3]
            random.shuffle(order)
            shuffled = []
            correct_label = "A"
            for pos, idx in enumerate(order):
                shuffled.append(opts[idx])
                if idx == 0:
                    correct_label = labels[pos]

            questions.append(
                {
                    "q": q,
                    "options": shuffled,
                    "ans": correct_label,
                    "exp": f"Đáp án đúng bám sát học liệu gốc; các phương án nhiễu thay đổi số liệu/thuật ngữ/quan hệ để tăng độ phân biệt ({level_tag}).",
                }
            )
    else:
        for i in range(needed):
            s = sentences[i % len(sentences)]
            questions.append(
                {
                    "q": f"Phân tích và trình bày hướng giải quyết cho nội dung sau trong môn {req.subject}: {s[:150]}",
                    "ans": "Trình bày đủ bối cảnh, khái niệm chính, quy trình xử lý và kết luận.",
                    "exp": f"Ưu tiên lập luận rõ ràng theo mức {level_tag}.",
                }
            )

    return questions

def create_exam_header(doc, subject, exam_type, exam_code):
    """Hàm tạo Header chuẩn form Trường Đại học Xây Dựng Hà Nội"""
    table = doc.add_table(rows=1, cols=2)
    table.autofit = True
    
    cell_left = table.cell(0, 0)
    p_left1 = cell_left.paragraphs[0]
    p_left1.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_left1 = p_left1.add_run("BỘ GIÁO DỤC VÀ ĐÀO TẠO\nTRƯỜNG ĐẠI HỌC XÂY DỰNG HÀ NỘI")
    run_left1.font.size = Pt(11)
    
    p_left2 = cell_left.add_paragraph()
    p_left2.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_left2 = p_left2.add_run("KHOA CÔNG NGHỆ THÔNG TIN")
    run_left2.font.size = Pt(12)
    run_left2.bold = True
    
    p_left3 = cell_left.add_paragraph()
    p_left3.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p_left3.add_run("-----------------------").bold = True

    cell_right = table.cell(0, 1)
    p_right1 = cell_right.paragraphs[0]
    p_right1.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_right1 = p_right1.add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    run_right1.font.size = Pt(11)
    run_right1.bold = True
    
    p_right2 = cell_right.add_paragraph()
    p_right2.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_right2 = p_right2.add_run("Độc lập - Tự do - Hạnh phúc")
    run_right2.font.size = Pt(12)
    run_right2.bold = True
    
    p_right3 = cell_right.add_paragraph()
    p_right3.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p_right3.add_run("-----------------------").bold = True

    doc.add_paragraph() 
    
    p_title = doc.add_paragraph()
    p_title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_title = p_title.add_run("ĐỀ THI KẾT THÚC HỌC PHẦN")
    run_title.font.size = Pt(16)
    run_title.bold = True

    p_info = doc.add_paragraph()
    p_info.add_run(f"Môn thi: ").bold = True
    p_info.add_run(f"{subject}\n")
    p_info.add_run(f"Hình thức thi: ").bold = True
    p_info.add_run(f"{exam_type.title()}\n")
    p_info.add_run(f"Mã đề thi: ").bold = True
    p_info.add_run(f"{exam_code}\n")
    p_info.add_run("Họ và tên sinh viên: ..................................................... MSSV: ............................... Lớp: ..................")
    
    doc.add_paragraph("--------------------------------------------------------------------------------------------------------------------------")

def remove_accents(input_str):
    s = input_str.replace('đ', 'd').replace('Đ', 'D')
    nfkd_form = unicodedata.normalize('NFKD', s)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

@router.post("/generate-word")
def generate_exam_word(req: ExamRequest, db: Session = Depends(get_db)):
    # 1. LẤY SUBJECT_ID TỪ CLASSROOM ĐỂ TÌM DOCUMENTS MỘT CÁCH ĐÁNG TIN CẬY
    target_class = db.query(models.Classroom).filter_by(id=req.class_id).first()
    if not target_class:
        raise HTTPException(status_code=404, detail="Lớp học không tồn tại.")
    
    # 2. RAG - Lấy tài liệu gốc cực lớn - DÙNG SUBJECT_ID FK THAY VÌ SUBJECT STRING
    docs = db.query(models.Document).filter(
        models.Document.class_id == req.class_id,
        models.Document.subject_id == target_class.subject_id
    ).all()
    allowed_filenames = [doc.filename for doc in docs]
    
    context_summary = "Sử dụng kiến thức chuyên ngành chuẩn xác."
    chunk_texts = _collect_chunk_texts(db, allowed_filenames)
    if allowed_filenames:
        try:
            from rag.vector_store import get_vector_store
            vector_store = get_vector_store()
            # Tăng lượng tài liệu nạp vào để AI không bị bí ý tưởng
            search_results = vector_store.similarity_search(
                f"Toàn bộ tài liệu, slide bài giảng, code mẫu môn {req.subject}", k=40, filter={"source": {"$in": allowed_filenames}}
            )
            context_summary = "\n".join([d.page_content for d in search_results])[:25000]
        except Exception as e:
            print("Lỗi RAG:", e)
            if chunk_texts:
                context_summary = "\n".join(chunk_texts[:80])[:25000]

    # 2. KHỞI TẠO CLIENT AI
    api_key = os.getenv("GROQ_KEY_ADAPTIVE") or os.getenv("GROQ_KEY_ASSESSMENT")
    client = Groq(api_key=api_key) if api_key else None
    
    # Ép AI sinh dư thêm vài câu để buffer lọc lỗi
    ask_count = req.num_questions + 3 

    # --- KHỐI LỆNH ĐỘ KHÓ ---
    level_instruction = ""
    normalized_level = _normalize_level(req.level)
    if normalized_level == "Beginner":
        level_instruction = "[MỨC ĐỘ DỄ - BEGINNER]: Tập trung vào nhận biết cú pháp, lý thuyết cơ bản, đọc hiểu."
    elif normalized_level == "Intermediate":
        level_instruction = "[MỨC ĐỘ TRUNG BÌNH]: Yêu cầu phân tích luồng chạy, tìm lỗi sai logic, vận dụng."
    else:
        level_instruction = "[MỨC ĐỘ KHÓ - ADVANCED]: Tập trung vào thiết kế hệ thống, tối ưu hóa, bẫy phức tạp."

    if req.exam_type != "trắc nghiệm":
        prompt = f"""Soạn {req.num_questions} câu hỏi TỰ LUẬN môn {req.subject}. 
        {level_instruction}
        Tài liệu: {context_summary}
        Đầu ra JSON: {{"questions": [{{"q": "Câu hỏi tự luận tình huống/bài tập sâu sắc?", "ans": "Đáp án/Bareme", "exp": "Gợi ý"}}]}}"""

    # 3. GỌI AI / PIPELINE
    base_questions = []
    ai_error = None
    if req.exam_type == "trắc nghiệm":
        try:
            source_text = "\n".join(chunk_texts[:120]) if chunk_texts else context_summary
            source_text = (source_text or "").strip()

            # Bước 1: chỉ nhận diện keyword/chủ đề để biết tài liệu đang nói về phần nào.
            keywords = extract_topic_keywords(source_text, client, req.subject)
            if not keywords:
                keywords = [req.subject]

            # Bước 2: từ keyword, model tự tạo câu hỏi khái niệm thay vì bám câu văn gốc.
            chosen_keywords = keywords[: max(1, min(len(keywords), req.num_questions))]
            if len(chosen_keywords) < req.num_questions:
                for fallback_term in re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", source_text):
                    if fallback_term.lower() not in [k.lower() for k in chosen_keywords]:
                        chosen_keywords.append(fallback_term)
                    if len(chosen_keywords) >= req.num_questions:
                        break

            max_attempts = max(12, req.num_questions * 6)
            attempt = 0
            keyword_index = 0

            while len(base_questions) < req.num_questions and attempt < max_attempts:
                attempt += 1
                keyword = chosen_keywords[keyword_index % len(chosen_keywords)]
                keyword_index += 1

                q_text = generate_concept_question(req.subject, keyword, client, level_instruction)
                if not question_is_meaningful(q_text, req.subject, keyword):
                    continue

                correct_answer = build_concept_correct_answer(req.subject, keyword, q_text, client)
                if not answer_is_meaningful(correct_answer, q_text, keyword):
                    # Nếu đáp án rác, đổi keyword và sinh lại.
                    continue

                distractors = build_keyword_distractors(req.subject, keyword, correct_answer, client)
                if len(distractors) < 3:
                    continue

                cleaned_distractors = []
                for d in distractors:
                    d_clean = re.sub(r"^([A-D][\.:\-\)])\s*", "", str(d)).strip()
                    if answer_is_meaningful(d_clean, q_text, keyword) and d_clean.lower() != correct_answer.lower():
                        cleaned_distractors.append(d_clean)

                if len(cleaned_distractors) < 3:
                    continue

                options_raw = [correct_answer] + cleaned_distractors[:3]
                cleaned_options = []
                for op in options_raw:
                    cleaned_op = re.sub(r"^([A-D][\.:\-\)])\s*", "", str(op)).strip()
                    if cleaned_op:
                        cleaned_options.append(cleaned_op)

                if len(cleaned_options) < 4:
                    continue

                order = [0, 1, 2, 3]
                random.shuffle(order)
                labels = ["A", "B", "C", "D"]
                shuffled_options = []
                correct_label = "A"
                for pos, raw_idx in enumerate(order):
                    shuffled_options.append(cleaned_options[raw_idx])
                    if raw_idx == 0:
                        correct_label = labels[pos]

                if not validate_question(q_text, shuffled_options, correct_label, req.subject, keyword):
                    continue

                base_questions.append(
                    {
                        "q": q_text,
                        "options": shuffled_options,
                        "ans": correct_label,
                        "exp": f"Câu hỏi bám keyword/chủ đề '{keyword}' đã rút từ tài liệu.",
                    }
                )
        except Exception as e:
            ai_error = str(e)
            print(f"Lỗi AI sinh đề theo keyword/topic, chuyển fallback: {ai_error}")
    elif client:
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": f"Output valid JSON only. Generate exactly {req.num_questions} questions."}, {"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
                max_tokens=8000,
                response_format={"type": "json_object"}
            )

            raw_content = chat_completion.choices[0].message.content
            ai_data = json.loads(_extract_json_text(raw_content))
            raw_questions = ai_data.get("questions", [])
            base_questions = raw_questions[:req.num_questions]
        except Exception as e:
            ai_error = str(e)
            print(f"Lỗi AI sinh đề, chuyển fallback: {ai_error}")

    if len(base_questions) < req.num_questions:
        fallback_questions = _build_fallback_exam_questions(req, context_summary, chunk_texts)
        if fallback_questions:
            base_questions = fallback_questions[:req.num_questions]

    if not base_questions:
        reason = ai_error or "Không đủ dữ liệu học liệu để sinh đề."
        raise HTTPException(status_code=500, detail=f"Không thể sinh đề thi: {reason}")

    doc = Document()
    exam_versions = []

    # =========================================================
    # 4. THUẬT TOÁN TRỘN ĐỀ VÀ TẠO FILE WORD
    # =========================================================
    for v in range(req.num_versions):
        exam_code = str(random.randint(101, 999))
        
        shuffled_qs = copy.deepcopy(base_questions)
        random.shuffle(shuffled_qs) 
        
        exam_versions.append({"code": exam_code, "questions": shuffled_qs})
        
        create_exam_header(doc, req.subject, req.exam_type, exam_code)

        for i, q in enumerate(shuffled_qs):
            p = doc.add_paragraph()
            p.add_run(f'Câu {i+1}: ').bold = True
            p.add_run(q.get('q', ''))
            
            if req.exam_type == "trắc nghiệm":
                options = q.get('options', [])
                correct_opt_idx = ord(q.get('ans', 'A').upper()) - 65
                if 0 <= correct_opt_idx < len(options):
                    correct_opt_text = options[correct_opt_idx]
                else:
                    correct_opt_text = options[0]
                
                random.shuffle(options) 
                
                labels = ['A', 'B', 'C', 'D']
                new_correct_label = "A"
                for idx, opt in enumerate(options):
                    if opt == correct_opt_text:
                        new_correct_label = labels[idx]
                        
                    doc.add_paragraph(f"{labels[idx]}. {opt}", style='List Bullet')
                
                q['new_ans'] = new_correct_label
            else:
                for _ in range(4): doc.add_paragraph("................................................................................................................................")
            doc.add_paragraph()
            
        doc.add_page_break() 

    # =========================================================
    # 5. VẼ ĐÁP ÁN CHO GIÁO VIÊN
    # =========================================================
    ans_heading = doc.add_heading('HƯỚNG DẪN CHẤM & ĐÁP ÁN CHI TIẾT', 1)
    ans_heading.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    doc.add_paragraph()

    for version in exam_versions:
        doc.add_paragraph(f"MÃ ĐỀ: {version['code']}").bold = True
        
        if req.exam_type == "trắc nghiệm":
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            for i in range(6): hdr_cells[i].text = 'Câu - Đáp án'
            
            row_cells = table.add_row().cells
            col_idx = 0
            for i, q in enumerate(version['questions']):
                if col_idx > 5:
                    row_cells = table.add_row().cells
                    col_idx = 0
                row_cells[col_idx].text = f"Câu {i+1}: {q.get('new_ans', q.get('ans'))}"
                col_idx += 1
            doc.add_paragraph()
        else:
            for i, q in enumerate(version['questions']):
                p = doc.add_paragraph()
                p.add_run(f'Câu {i+1}: ').bold = True
                doc.add_paragraph(q.get('ans', ''))
                doc.add_paragraph(f"Gợi ý chấm: {q.get('exp', '')}").italic = True
        doc.add_paragraph("----------------------------------------------------------------")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    clean_subject = remove_accents(req.subject).replace(' ', '')
    clean_exam_type = remove_accents(req.exam_type).replace(' ', '')
    filename = f"DeThi_{clean_subject}_{clean_exam_type}.docx"
    
    return StreamingResponse(
        file_stream, 
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )