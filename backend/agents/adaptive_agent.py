import json
import os
import re
import random
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from pptx import Presentation
from sqlalchemy.orm import Session

from db.models import Document, LearnerProfile, LearningRoadmap, Subject
from rag.vector_store import get_vector_store

# Tải biến môi trường
load_dotenv()

MATERIAL_BRIEF_CACHE: Dict[str, dict] = {}

class AdaptiveAgent:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = (os.getenv("GROQ_KEY_ADAPTIVE") or "").strip()
        api_key_low = self.api_key.lower()
        if self.api_key and "dummy" not in api_key_low and "testing" not in api_key_low and "placeholder" not in api_key_low:
            self.client = Groq(api_key=self.api_key)
        else:
            self.client = None
        self.model = "llama-3.3-70b-versatile"
        
        # Kết nối tới Vector Database (ChromaDB)
        self.vector_store = get_vector_store()

    def _resolve_subject(self, subject: str) -> Subject:
        subject_name = (subject or "").strip()
        if not subject_name:
            raise ValueError("Subject không được rỗng")

        subject_obj = self.db.query(Subject).filter(Subject.name.ilike(subject_name)).first()
        if subject_obj:
            return subject_obj

        subject_obj = Subject(name=subject_name, description=f"Môn {subject_name}")
        self.db.add(subject_obj)
        self.db.flush()
        return subject_obj

    def _build_fallback_roadmap(self, subject_name: str, level: str):
        level_text = (level or "Beginner").upper()
        sessions = [
            {"session": 1, "topic": f"Nền tảng cốt lõi của {subject_name}", "description": "Làm quen mục tiêu học tập và khái niệm nền tảng quan trọng.", "focus_level": level_text},
            {"session": 2, "topic": "Thuật ngữ và mô hình cơ bản", "description": "Hiểu đúng thuật ngữ, mô hình tư duy và cách áp dụng trong bài tập.", "focus_level": level_text},
            {"session": 3, "topic": "Quy trình thực hành chuẩn", "description": "Rèn quy trình giải quyết bài toán theo từng bước rõ ràng.", "focus_level": level_text},
            {"session": 4, "topic": "Phân tích tình huống điển hình", "description": "Áp dụng kiến thức vào tình huống thực tế ở mức độ vừa phải.", "focus_level": level_text},
            {"session": 5, "topic": "Lỗi thường gặp và cách tránh", "description": "Nhận diện sai sót phổ biến và xây dựng chiến lược khắc phục.", "focus_level": level_text},
            {"session": 6, "topic": "Luyện tập theo nhóm kỹ năng", "description": "Củng cố năng lực qua bài tập phân nhóm từ dễ đến khó.", "focus_level": level_text},
            {"session": 7, "topic": "Vận dụng liên kết kiến thức", "description": "Kết nối các mảng kiến thức để giải bài toán tổng hợp.", "focus_level": level_text},
            {"session": 8, "topic": "Kịch bản ứng dụng thực tế", "description": "Mô phỏng bối cảnh thực tiễn và đưa ra phương án xử lý phù hợp.", "focus_level": level_text},
            {"session": 9, "topic": "Tối ưu cách giải", "description": "So sánh nhiều hướng tiếp cận và chọn cách làm hiệu quả hơn.", "focus_level": level_text},
            {"session": 10, "topic": "Ôn tập chiến lược", "description": "Hệ thống hóa toàn bộ nội dung trước khi kiểm tra cuối khóa.", "focus_level": level_text},
            {"session": 11, "topic": "KIỂM TRA TỔNG HỢP CUỐI KHÓA", "description": "Bài thi đánh giá toàn diện mức độ nắm vững kiến thức.", "focus_level": level_text},
        ]
        return sessions

    def _build_fallback_tutor_reply(self, subject: str, user_message: str, roadmap_context: str, context_docs: str) -> str:
        short_context = ""
        if context_docs:
            compact = " ".join(context_docs.split())
            short_context = compact[:260]

        return (
            f"Mình đang hỗ trợ bạn ở chế độ dự phòng cho môn {subject}. "
            f"Theo buổi học hiện tại: {roadmap_context[:140]}.\n\n"
            f"Gợi ý nhanh cho câu hỏi của bạn: \"{user_message[:180]}\"\n"
            f"1. Xác định đúng khái niệm/chủ điểm cần trả lời.\n"
            f"2. Liên hệ với ví dụ gần nhất trong bài học rồi so sánh điểm giống và khác.\n"
            f"3. Tự kiểm tra lại bằng 1 câu ngắn: vì sao cách hiểu này đúng trong ngữ cảnh hiện tại?\n\n"
            f"{('Trích từ học liệu: ' + short_context) if short_context else 'Học liệu đang được cập nhật, bạn có thể gửi câu hỏi cụ thể hơn để mình hướng dẫn từng bước.'}"
        )

    def _clean_text(self, text: str):
        return re.sub(r"\s+", " ", text or "").strip()

    def _looks_like_boilerplate(self, line: str):
        low = self._clean_text(line).lower()
        if not low or len(low) < 18:
            return True

        admin_patterns = [
            r"\bgiảng viên\b",
            r"\bgiáo viên\b",
            r"\bemail\b",
            r"\be-mail\b",
            r"\bsđt\b",
            r"\bsdt\b",
            r"\bđiện thoại\b",
            r"\bhotline\b",
            r"\bliên hệ\b",
            r"\bquy định\b",
            r"\bquy chế\b",
            r"\bđiểm danh\b",
            r"\bnộp bài\b",
            r"\bhọc phí\b",
            r"\blịch học\b",
            r"\bhọc phần\b",
        ]
        if any(re.search(pattern, low) for pattern in admin_patterns):
            return True

        if re.search(r"(?:email|e-mail|sđt|sdt|điện thoại)\s*[:：]", low):
            return True

        return False

    def _load_document_text(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            return ""

        ext = Path(file_path).suffix.lower()
        try:
            if ext == ".pdf":
                docs = PyPDFLoader(file_path).load()
                return "\n\n".join([doc.page_content for doc in docs if (doc.page_content or "").strip()])

            if ext == ".docx":
                docs = Docx2txtLoader(file_path).load()
                return "\n\n".join([doc.page_content for doc in docs if (doc.page_content or "").strip()])

            if ext == ".txt":
                docs = TextLoader(file_path, encoding="utf-8").load()
                return "\n\n".join([doc.page_content for doc in docs if (doc.page_content or "").strip()])

            if ext == ".pptx":
                prs = Presentation(file_path)
                full_text = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        try:
                            if hasattr(shape, "text") and isinstance(shape.text, str) and shape.text.strip():
                                full_text.append(shape.text)
                        except Exception:
                            continue
                return "\n\n".join(full_text)
        except Exception as exc:
            print(f"⚠️ Không đọc được file nguồn {file_path}: {exc}")

        return ""

    def _fetch_document(self, subject: str, source_file: str = "", document_id: Optional[int] = None):
        query = self.db.query(Document)
        subject_name = self._clean_text(subject)

        if document_id:
            doc = query.filter(Document.id == document_id).first()
            if doc:
                return doc

        if source_file:
            doc = query.filter(Document.filename == source_file).first()
            if doc:
                return doc

        if subject_name:
            doc = query.filter(Document.subject.ilike(subject_name)).order_by(Document.upload_time.desc()).first()
            if doc:
                return doc

        return None

    def _collect_rag_text(self, subject: str, source_file: str = "", allowed_filenames: list = None, document_id: Optional[int] = None):
        search_filter = {"subject": {"$eq": subject}}
        if allowed_filenames:
            search_filter = {"$and": [{"subject": {"$eq": subject}}, {"source": {"$in": allowed_filenames}}]}
        if source_file:
            search_filter = {"$and": [{"subject": {"$eq": subject}}, {"source": {"$eq": source_file}}]}

        if document_id:
            doc = self._fetch_document(subject, source_file=source_file, document_id=document_id)
            if doc and doc.filename:
                search_filter = {"$and": [{"subject": {"$eq": subject}}, {"source": {"$eq": doc.filename}}]}

        query = f"Toàn bộ nội dung tài liệu, bài học và ví dụ của môn {subject}. {source_file}".strip()
        try:
            docs = self.vector_store.similarity_search(query, k=60, filter=search_filter)
            if not docs and source_file:
                docs_all = self.vector_store.similarity_search(query, k=90, filter={"subject": {"$eq": subject}})
                docs = [d for d in docs_all if os.path.basename(str((d.metadata or {}).get("source", ""))) == source_file]
        except Exception:
            docs = []

        chunks = []
        seen = set()
        for doc in docs:
            text = self._clean_text(getattr(doc, "page_content", ""))
            if len(text) < 20:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            chunks.append(text)
        return "\n".join(chunks)

    def _normalize_material_text(self, raw_text: str):
        lines = []
        seen = set()
        for raw_line in (raw_text or "").splitlines():
            line = self._clean_text(raw_line)
            if not line or self._looks_like_boilerplate(line):
                continue
            if len(line) < 18:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)

        if not lines:
            return ""

        return "\n".join(lines)[:28000]

    def _extract_keywords(self, text: str, limit: int = 8):
        tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", (text or "").lower())
        stop = {
            "và", "của", "theo", "cho", "trong", "được", "này", "khi", "một", "các", "những",
            "that", "this", "with", "from", "have", "will", "about", "trên", "dưới",
        }
        freq: Dict[str, int] = {}
        for token in tokens:
            if token in stop or token.isdigit():
                continue
            freq[token] = freq.get(token, 0) + 1
        ranked = sorted(freq.items(), key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked[:limit]]

    def _build_rule_based_material_brief(self, subject: str, source_file: str, cleaned_text: str):
        sentences = [s.strip() for s in re.split(r"(?<=[\.\!\?;:])\s+", cleaned_text or "") if s.strip()]
        key_points = []
        for sentence in sentences:
            if len(sentence) < 24:
                continue
            if sentence not in key_points:
                key_points.append(sentence[:220])
            if len(key_points) == 6:
                break

        if not key_points:
            key_points = self._extract_keywords(cleaned_text, limit=6)

        important_notes = []
        note_patterns = [r"lưu ý", r"chú ý", r"quan trọng", r"cần nhớ", r"đặc biệt", r"không được", r"phải"]
        for sentence in sentences:
            low = sentence.lower()
            if any(pattern in low for pattern in note_patterns):
                candidate = sentence[:220]
                if candidate not in important_notes:
                    important_notes.append(candidate)
            if len(important_notes) == 5:
                break

        if not important_notes:
            important_notes = [
                "Bám vào khái niệm cốt lõi thay vì chỉ học thuộc từng dòng.",
                "Ưu tiên hiểu các ví dụ minh hoạ rồi mới chuyển sang bài tập.",
                "Ghi nhớ các công thức, điều kiện áp dụng và ngoại lệ nếu có.",
            ]

        keywords = self._extract_keywords(cleaned_text, limit=5)
        topic_label = ", ".join(keywords[:3]) if keywords else self._clean_text(source_file) or subject
        summary_seed = " ".join(sentences[:6])[:900]
        if not summary_seed:
            summary_seed = f"Tài liệu {source_file or subject} tập trung vào {topic_label}."

        key_points_text = "\n- ".join([item[:220] for item in key_points[:5]]) if key_points else "chưa trích được ý chính rõ ràng từ tài liệu"
        notes_text = "\n- ".join([item[:220] for item in important_notes[:5]])

        rewritten_material = "\n\n".join([
            f"Tài liệu đã được biên tập lại cho môn {subject}.",
            f"Trọng tâm chính: {topic_label}.",
            summary_seed,
            f"Các ý cần nhớ:\n- {key_points_text}",
            f"Lưu ý quan trọng:\n- {notes_text}",
        ])

        suggested_prompts = [
            f"Hãy giải thích lại phần cốt lõi của {subject} theo ngôn ngữ dễ hiểu.",
            f"Từ tài liệu này, đâu là 3 ý quan trọng nhất cần nhớ?",
            f"Đặt cho mình 3 câu hỏi kiểm tra nhanh từ tài liệu {source_file or subject}.",
            f"Phần nào trong tài liệu này dễ nhầm nhất và vì sao?",
        ]

        return {
            "subject": subject,
            "source_file": source_file,
            "rewritten_title": self._clean_text(source_file) or f"{subject} - Học liệu đã biên tập",
            "rewritten_material": rewritten_material[:5000],
            "summary": summary_seed[:1200],
            "key_points": key_points[:6],
            "important_notes": important_notes[:5],
            "suggested_prompts": suggested_prompts,
        }

    def _rewrite_material_brief(self, subject: str, source_file: str, cleaned_text: str):
        if not self.client:
            return self._build_rule_based_material_brief(subject, source_file, cleaned_text)

        prompt = f"""
Bạn là biên tập viên học liệu cho sinh viên.

NHIỆM VỤ:
- Viết lại tài liệu theo ngôn ngữ dễ hiểu, mạch lạc, ưu tiên góc nhìn học tập.
- Loại bỏ toàn bộ thông tin thừa: tên giảng viên, giới thiệu giảng viên, sđt, email, quy định môn học, số buổi, % điểm danh, nội quy hành chính, lịch học.
- Không bịa thêm kiến thức ngoài nội dung được cung cấp.
- Không nhắc rằng đây là bản tóm tắt hay bản trích xuất.

ĐẦU RA BẮT BUỘC JSON HỢP LỆ:
{{
  "rewritten_title": "...",
  "rewritten_material": "...",
  "summary": "...",
  "key_points": ["...", "...", "..."],
  "important_notes": ["...", "...", "..."],
  "suggested_prompts": ["...", "...", "...", "..."]
}}

QUY TẮC VIẾT:
- rewritten_material phải có cấu trúc ngắn gọn, rõ nghĩa, chia đoạn hoặc gạch đầu dòng.
- summary phải súc tích và bao quát nội dung chính.
- key_points và important_notes phải bám sát tài liệu, ưu tiên phần cần nhớ khi học.
- suggested_prompts là câu hỏi học tập để sinh viên hỏi tiếp gia sư AI.

MÔN: {subject}
TÀI LIỆU: {source_file}

NỘI DUNG ĐÃ LÀM SẠCH:
{cleaned_text[:22000]}
""".strip()

        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.2,
                max_tokens=2200,
                response_format={"type": "json_object"},
            )
            data = json.loads(completion.choices[0].message.content)

            summary = self._clean_text(str(data.get("summary", "")))
            rewritten_material = self._clean_text(str(data.get("rewritten_material", "")))
            rewritten_title = self._clean_text(str(data.get("rewritten_title", ""))) or self._clean_text(source_file) or f"{subject} - Học liệu đã biên tập"

            key_points = data.get("key_points") or []
            if not isinstance(key_points, list):
                key_points = []
            key_points = [self._clean_text(str(item)) for item in key_points if self._clean_text(str(item))][:6]

            important_notes = data.get("important_notes") or []
            if not isinstance(important_notes, list):
                important_notes = []
            important_notes = [self._clean_text(str(item)) for item in important_notes if self._clean_text(str(item))][:5]

            suggested_prompts = data.get("suggested_prompts") or []
            if not isinstance(suggested_prompts, list):
                suggested_prompts = []
            suggested_prompts = [self._clean_text(str(item)) for item in suggested_prompts if self._clean_text(str(item))][:4]

            if not summary or not rewritten_material:
                return self._build_rule_based_material_brief(subject, source_file, cleaned_text)

            return {
                "subject": subject,
                "source_file": source_file,
                "rewritten_title": rewritten_title,
                "rewritten_material": rewritten_material[:5000],
                "summary": summary[:1200],
                "key_points": key_points,
                "important_notes": important_notes,
                "suggested_prompts": suggested_prompts or self._build_rule_based_material_brief(subject, source_file, cleaned_text)["suggested_prompts"],
            }
        except Exception as exc:
            print(f"⚠️ Lỗi biên tập học liệu: {exc}")
            return self._build_rule_based_material_brief(subject, source_file, cleaned_text)

    def _get_material_brief(self, subject: str, source_file: str = "", allowed_filenames: list = None, session_topic: str = "", document_id: Optional[int] = None):
        cache_key = f"{(subject or '').strip().lower()}|{document_id or ''}|{(source_file or '').strip().lower()}|{','.join(sorted(allowed_filenames or []))}"
        cached = MATERIAL_BRIEF_CACHE.get(cache_key)
        if cached:
            return cached

        doc = self._fetch_document(subject, source_file=source_file, document_id=document_id)
        file_text = ""
        if doc and doc.file_path:
            file_text = self._load_document_text(doc.file_path)

        effective_source = doc.filename if doc and doc.filename else source_file
        rag_text = self._collect_rag_text(subject, source_file=effective_source, allowed_filenames=allowed_filenames, document_id=document_id)

        combined_parts = [part for part in [file_text, rag_text] if part.strip()]
        combined_text = "\n\n".join(combined_parts)
        cleaned_text = self._normalize_material_text(combined_text)
        if not cleaned_text:
            fallback = {
                "subject": subject,
                "source_file": source_file,
                "rewritten_title": self._clean_text(source_file) or f"{subject} - Học liệu đã biên tập",
                "rewritten_material": f"Mình chưa trích được đủ nội dung từ tài liệu {source_file or subject}. Hãy mở lại file hoặc chọn đúng tài liệu để mình tóm tắt tiếp.",
                "summary": f"Chưa đủ dữ liệu để biên tập tài liệu {source_file or subject}.",
                "key_points": [],
                "important_notes": ["Hãy thử tải lại tài liệu hoặc chọn đúng file đang học."],
                "suggested_prompts": [
                    "Tóm tắt ngắn tài liệu này",
                    "Nêu các ý cần nhớ trong tài liệu",
                    "Giải thích từng phần theo ngôn ngữ dễ hiểu",
                    "Đặt câu hỏi kiểm tra nhanh từ tài liệu",
                ],
            }
            MATERIAL_BRIEF_CACHE[cache_key] = fallback
            return fallback

        brief = self._rewrite_material_brief(subject, effective_source or source_file, cleaned_text)
        brief["session_topic"] = session_topic
        brief["document_id"] = document_id
        MATERIAL_BRIEF_CACHE[cache_key] = brief
        return brief

    def summarize_material(self, subject: str, source_file: str, session_topic: str = "", allowed_filenames: list = None):
        brief = self._get_material_brief(subject, source_file=source_file, allowed_filenames=allowed_filenames, session_topic=session_topic)
        result = dict(brief)
        result["suggested_prompts"] = brief.get("suggested_prompts") or [
            "Từ tài liệu này, phần nào dễ nhầm nhất?",
            "Hãy tóm tắt lại theo 5 ý chính ngắn gọn",
            "Tạo 5 câu trắc nghiệm bám sát nội dung tài liệu",
        ]
        return result

    # ==========================================
    # 1. HÀM SINH LỘ TRÌNH HỌC (ROADMAP)
    # ==========================================
    def generate_overall_roadmap(self, user_id: int, subject: str, allowed_filenames: list = None, force_level: str = None):
        subject_obj = self._resolve_subject(subject)
        subject_id = subject_obj.id
        subject_name = subject_obj.name

        current_level = force_level
        if not current_level:
            profile = self.db.query(LearnerProfile).filter_by(user_id=user_id, subject_id=subject_id).first()
            if not profile:
                profile = self.db.query(LearnerProfile).filter_by(user_id=user_id, subject=subject_name).first()
            current_level = profile.current_level if profile else "Beginner"

        context_summary = ""
        if allowed_filenames:
            try:
                if current_level == "Advanced":
                    search_query = f"Kiến thức nâng cao, chuyên sâu, thiết kế hệ thống, bảo mật, tối ưu hóa, giao thức phức tạp của môn {subject_name}"
                elif current_level == "Intermediate":
                    search_query = f"Kiến thức vận dụng, các mô hình thực tế, thuật toán, cấu trúc chi tiết của môn {subject_name}"
                else:
                    search_query = f"Mục lục, giới thiệu, các khái niệm cơ bản, tổng quan của môn {subject_name}"

                # Tăng k lên 40 để AI nhìn được bức tranh toàn cảnh toàn bộ cuốn giáo trình
                docs = self.vector_store.similarity_search(
                    search_query, 
                    k=40, 
                    filter={"source": {"$in": allowed_filenames}}
                )
                context_summary = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                print(f"⚠️ Lỗi trích xuất chủ đề: {e}")

        prompt = f"""
        BẠN LÀ CHUYÊN GIA THIẾT KẾ CHƯƠNG TRÌNH HỌC (CURRICULUM ARCHITECT).
        MÔN HỌC: {subject_name}
        TRÌNH ĐỘ HỌC VIÊN HIỆN TẠI: {current_level.upper()}
        
        TÀI LIỆU GIÁO VIÊN (NGUỒN THAM KHẢO):
        {context_summary[:12000] if context_summary else "Không có tài liệu."}

        [CHIẾN LƯỢC ÉP KIỂU THEO TRÌNH ĐỘ]:
        Học viên đang ở trình độ **{current_level.upper()}**. Bạn PHẢI thiết kế ĐÚNG 11 SESSIONS (10 học + 1 thi).

        QUY TẮC NỘI DUNG TỪ SESSION 1 ĐẾN 10 (Lệnh sống còn):
        - Bám sát hệ thống kiến thức trong tài liệu. 
        - Phân bổ kiến thức logic từ Session 1 đến 10, không được lặp lại chủ đề.
        - Mức Intermediate/Advanced: CẤM dạy lại "Giới thiệu/Tổng quan cơ bản". Đi thẳng vào kiến thức thực tế/chuyên sâu.

        QUY TẮC SESSION 11: 
        - Bắt buộc là: {{"session": 11, "topic": "KIỂM TRA TỔNG HỢP CUỐI KHÓA", "description": "Bài thi đánh giá toàn diện...", "focus_level": "{current_level.upper()}"}}

        [YÊU CẦU ĐẦU RA JSON]:
        {{
            "strategy": "Ghi rõ chiến lược thiết kế...",
            "roadmap": [
                {{
                    "session": 1,
                    "topic": "Tên bài học...",
                    "description": "Mô tả chi tiết (Tối đa 20 từ)...",
                    "focus_level": "{current_level.upper()}"
                }}
            ]
        }}
        """

        try:
            final_roadmap = []
            if self.client:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a strict curriculum architect. Output valid JSON containing exactly 11 sessions."},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.model,
                    temperature=0.2,
                    max_tokens=4000,
                    response_format={"type": "json_object"}
                )

                roadmap_data = json.loads(chat_completion.choices[0].message.content)
                final_roadmap = roadmap_data.get("roadmap", [])

            if len(final_roadmap) != 11:
                final_roadmap = self._build_fallback_roadmap(subject_name, current_level)

            self.db.query(LearningRoadmap).filter_by(user_id=user_id, subject_id=subject_id).delete()

            new_roadmap = LearningRoadmap(
                user_id=user_id,
                subject_id=subject_id,
                subject=subject_name,
                level_assigned=current_level,
                roadmap_data=final_roadmap,
                current_session=1
            )
            self.db.add(new_roadmap)
            self.db.commit()

            return final_roadmap
        except Exception as e:
            print(f"❌ Lỗi sinh lộ trình: {e}")
            self.db.rollback()
            try:
                fallback = self._build_fallback_roadmap(subject_name, current_level)
                self.db.query(LearningRoadmap).filter_by(user_id=user_id, subject_id=subject_id).delete()
                self.db.add(
                    LearningRoadmap(
                        user_id=user_id,
                        subject_id=subject_id,
                        subject=subject_name,
                        level_assigned=current_level,
                        roadmap_data=fallback,
                        current_session=1,
                    )
                )
                self.db.commit()
                return fallback
            except Exception as db_err:
                print(f"❌ Fallback roadmap cũng lỗi: {db_err}")
                self.db.rollback()
                return []

    # ==========================================
    # 2. HÀM GIA SƯ AI CHAT 
    # ==========================================
    def chat_with_tutor(self, subject: str, user_message: str, roadmap_context: str, allowed_filenames: list = None, session_topic: str = "", source_file: str = "", history: list = None, document_id: Optional[int] = None):
        if history is None:
            history = []

        material_brief = self._get_material_brief(
            subject,
            source_file=source_file,
            allowed_filenames=allowed_filenames,
            session_topic=session_topic,
            document_id=document_id,
        )
        rewritten_material = material_brief.get("rewritten_material", "")
        summary = material_brief.get("summary", "")
        key_points = material_brief.get("key_points", []) or []
        important_notes = material_brief.get("important_notes", []) or []

        key_points_text = "\n".join([f"- {item}" for item in key_points[:6]]) if key_points else "- Chưa trích được ý chính rõ ràng từ tài liệu."
        notes_text = "\n".join([f"- {item}" for item in important_notes[:5]]) if important_notes else "- Chưa trích được lưu ý quan trọng rõ ràng từ tài liệu."

        subject_obj = self.db.query(Subject).filter(Subject.name.ilike((subject or "").strip())).first()
        profile = None
        if subject_obj:
            profile = self.db.query(LearnerProfile).filter_by(subject_id=subject_obj.id).first()
        if not profile:
            profile = self.db.query(LearnerProfile).filter_by(subject=subject).first()
        current_level = profile.current_level if profile else "Beginner"

        system_prompt = f"""BẠN LÀ MỘT GIA SƯ AI TƯƠNG TÁC 1-1 CỰC KỲ XUẤT SẮC CỦA MÔN {subject}.
    TÀI LIỆU ĐÃ ĐƯỢC BIÊN TẬP LẠI THEO CÁCH DỄ HỌC, KHÔNG CÒN PHẦN THÔNG TIN HÀNH CHÍNH THỪA.
TRÌNH ĐỘ HỌC VIÊN: {current_level}
[NỘI DUNG BUỔI HỌC HÔM NAY]: {roadmap_context}
    [BẢN BIÊN TẬP TÀI LIỆU]: {rewritten_material[:5000]}
    [TÓM TẮT NGẮN]: {summary[:900]}
    [Ý CHÍNH]:
    {key_points_text}
    [LƯU Ý QUAN TRỌNG]:
    {notes_text}

[NGUYÊN TẮC TỐI THƯỢNG]:
    - Trả lời trực tiếp, không lặp lại nguyên văn bản biên tập.
    - Nếu người học chào mở bài, hãy tóm tắt mục tiêu buổi học, 2-3 ý quan trọng nhất và 1 câu hỏi gợi mở.
    - Nếu người học hỏi chi tiết, giải thích theo ngôn ngữ đơn giản, có ví dụ ngắn nếu phù hợp.
    - Chỉ dựa trên bản biên tập tài liệu và ngữ cảnh buổi học; không bịa thêm kiến thức ngoài tài liệu.

[PHONG CÁCH]: Ngắn gọn (tối đa 3-4 câu), thân thiện, năng động.
"""

        api_messages = [{"role": "system", "content": system_prompt}]
        # Lấy 8 tin nhắn gần nhất để AI có context tốt hơn về cuộc trò chuyện
        for msg in history[-8:]: 
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                api_messages.append({"role": role, "content": content})

        if not self.client:
            return self._build_fallback_tutor_reply(subject, user_message, roadmap_context, rewritten_material or summary)

        try:
            chat_completion = self.client.chat.completions.create(
                messages=api_messages,
                model=self.model,
                temperature=0.6 
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            error_text = str(e).lower()
            if "invalid_api_key" in error_text or "401" in error_text:
                return self._build_fallback_tutor_reply(subject, user_message, roadmap_context, rewritten_material or summary)
            return "Gia sư AI đang tạm gián đoạn kết nối. Bạn gửi lại câu hỏi ngắn hơn, mình sẽ hướng dẫn từng bước."

    # ==========================================
    # 3. HÀM SINH CÂU HỎI TRẮC NGHIỆM
    # ==========================================
    def _build_session_quiz_fallback(self, subject: str, session_topic: str, level: str, context_docs: str, num_questions: int):
        raw_sentences = re.split(r"(?<=[\.!\?;:])\s+", context_docs or "")
        sentences = []
        for s in raw_sentences:
            clean = re.sub(r"\s+", " ", s).strip()
            if 55 <= len(clean) <= 260:
                sentences.append(clean)

        if not sentences:
            sentences = [f"Buổi học {session_topic} của môn {subject} tập trung vào kiến thức cốt lõi và cách vận dụng trong bài tập."]

        token_bank = re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", context_docs or "")
        token_bank = [t for t in token_bank if not t.isdigit()]
        token_bank = list(dict.fromkeys(token_bank))
        numeric_bank = list(dict.fromkeys(re.findall(r"\d+(?:[\.,]\d+)?", context_docs or "")))

        antonym_pairs = [
            ("tăng", "giảm"),
            ("đúng", "sai"),
            ("lớn hơn", "nhỏ hơn"),
            ("trước", "sau"),
            ("hội tụ", "phân kỳ"),
            ("đồng biến", "nghịch biến"),
            ("liên tục", "gián đoạn"),
        ]

        def mutate_number(text: str) -> str:
            nums = re.findall(r"\d+(?:[\.,]\d+)?", text)
            if not nums:
                return ""
            old = nums[0]
            replacement = None
            cands = [n for n in numeric_bank if n != old]
            if cands:
                replacement = random.choice(cands)
            if not replacement:
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
            cands = [t for t in token_bank if t.lower() != pick.lower() and abs(len(t) - len(pick)) <= 6]
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

        templates = [
            "Theo học liệu buổi '{topic}', phát biểu nào đúng nhất về ý: \"{anchor}\"?",
            "Dựa trên tài liệu của buổi '{topic}', phương án nào phản ánh chính xác nội dung: \"{anchor}\"?",
            "Trong ngữ cảnh môn {subject}, nhận định nào đúng với nội dung đã học: \"{anchor}\"?",
        ]

        results = []
        for i in range(max(1, num_questions)):
            fact = sentences[i % len(sentences)]
            correct = fact[:210]
            near = sentences[(i + 1) % len(sentences)][:210]

            d1 = mutate_number(correct)
            d2 = mutate_term(correct)
            d3 = mutate_relation(correct)

            distractors = []
            for d in [d1, d2, d3, near]:
                d_clean = (d or "").strip()[:210]
                if d_clean and d_clean.lower() != correct.lower() and d_clean.lower() not in [x.lower() for x in distractors]:
                    distractors.append(d_clean)
                if len(distractors) == 3:
                    break

            while len(distractors) < 3:
                distractors.append((correct[:120] + " nhưng điều kiện áp dụng không khớp với tài liệu.")[:210])

            options_raw = [correct] + distractors[:3]
            order = [0, 1, 2, 3]
            random.shuffle(order)
            labels = ["A", "B", "C", "D"]
            final_options = []
            correct_label = "A"
            for pos, idx in enumerate(order):
                final_options.append(f"{labels[pos]}. {options_raw[idx]}")
                if idx == 0:
                    correct_label = labels[pos]

            q_template = templates[i % len(templates)]
            question_text = q_template.format(topic=session_topic, anchor=fact[:110], subject=subject)

            results.append(
                {
                    "id": i + 1,
                    "content": question_text,
                    "options": final_options,
                    "correct_label": correct_label,
                    "explanation": f"Câu fallback theo mức {str(level).upper()}, dựa trên nội dung tài liệu đã học; phương án nhiễu thay đổi thuật ngữ/số liệu/quan hệ.",
                }
            )

        return results

    def generate_session_quiz(self, subject: str, session_topic: str, level: str, allowed_filenames: list = None):
        context_docs = ""
        search_filter = {"subject": {"$eq": subject}}
        if allowed_filenames:
            search_filter = {
                "$and": [
                    {"subject": {"$eq": subject}},
                    {"source": {"$in": allowed_filenames}}
                ]
            }

        is_final_exam = "CUỐI KHÓA" in session_topic.upper() or "TỔNG HỢP" in session_topic.upper()

        # PHÂN LUỒNG TÌM KIẾM ĐỂ TRÁNH LẠC ĐỀ
        if is_final_exam:
            # Bốc diện rộng toàn bộ các chương
            search_query = f"Toàn bộ kiến thức trọng tâm, các khái niệm, bài tập, ứng dụng và tổng kết của môn {subject}"
            topic_instruction = f"- Chủ đề: TỔNG ÔN CUỐI KHÓA (Lệnh: Bốc ngẫu nhiên kiến thức rải rác ở TẤT CẢ CÁC CHƯƠNG để kiểm tra toàn diện)."
            num_questions = 20
            k_val = 30 # Lấy tận 30 mảnh kiến thức khác nhau
        else:
            # Focus cực mạnh vào đúng 1 keyword
            search_query = f"Kiến thức chuyên sâu, ví dụ thực tiễn, đoạn code, bài tập của chủ đề: {session_topic} trong môn {subject}"
            topic_instruction = f"- Chủ đề: {session_topic} (Lệnh Sống Còn: TUYỆT ĐỐI CHỈ HỎI XOAY QUANH CHỦ ĐỀ NÀY, không hỏi lan man chương khác)."
            num_questions = 10
            k_val = 20

        try:
            docs = self.vector_store.similarity_search(search_query, k=k_val, filter=search_filter)
            if not docs and allowed_filenames:
                docs_all = self.vector_store.similarity_search(search_query, k=max(k_val * 2, 40))
                docs = [d for d in docs_all if os.path.basename(d.metadata.get("source", "")) in allowed_filenames]
            # Ép dung lượng nạp lên mức 15.000 ký tự để AI thông minh nhất có thể
            context_docs = "\n\n".join([doc.page_content for doc in docs])[:15000] 
        except Exception as e:
            print(f"❌ Lỗi RAG lấy tài liệu: {e}")
            context_docs = "Dữ liệu kiến thức đang được cập nhật."

        prompt = f"""
        BẠN LÀ CHUYÊN GIA KHẢO THÍ ĐẠI HỌC CỰC KỲ KHẮT KHE. NHIỆM VỤ: Soạn ĐÚNG {num_questions} câu hỏi trắc nghiệm trình độ {level.upper()}.
        - Môn học: {subject}
        {topic_instruction}

        [TÀI LIỆU CỐT LÕI (BẮT BUỘC BÁM SÁT)]:
        {context_docs}

        [TIÊU CHUẨN CHẤT LƯỢNG ĐỀ THI (CHỐNG HỌC VẸT)]:
        1. KHÔNG hỏi lý thuyết suông (Vd: "Định nghĩa là gì?", "Cấu trúc gồm mấy phần?"). Sinh viên Đại học cần tư duy!
        2. BẮT BUỘC sử dụng Tình huống thực tiễn (Case study), Đoạn code/Công thức, hoặc Bài toán logic để sinh viên phân tích và giải quyết.
        3. Phân cấp độ:
           - BEGINNER: Nhận biết khái niệm thông qua ví dụ thực tế.
           - INTERMEDIATE: Phân tích đúng sai, dự đoán kết quả, tìm lỗi sai.
           - ADVANCED: Đánh giá, tối ưu hóa hệ thống, giải quyết tình huống hóc búa.
        4. TÍNH KHÁCH QUAN: 1 đáp án ĐÚNG CHÍNH XÁC, 3 đáp án SAI NHƯNG CÓ VẺ ĐÚNG (bẫy nhiễu).

        [YÊU CẦU ĐẦU RA JSON]:
        {{
            "questions": [
                {{
                    "id": 1,
                    "content": "Tình huống / Đoạn mã / Câu hỏi tư duy...",
                    "options": ["A. Đáp án 1", "B. Đáp án 2", "C. Đáp án 3", "D. Đáp án 4"],
                    "correct_label": "A", 
                    "explanation": "Giải thích chi tiết vì sao đúng và phân tích bẫy sai..."
                }}
            ]
        }}
        """

        if not self.client:
            return self._build_session_quiz_fallback(subject, session_topic, level, context_docs, num_questions)

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a top-tier examiner. You output strict and valid JSON containing the exact number of requested questions."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                max_tokens=6000, # Bơm token để viết đề dài
                temperature=0.3, # Tăng nhẹ độ sáng tạo để bớt rập khuôn
                response_format={"type": "json_object"}
            )
            
            result = json.loads(chat_completion.choices[0].message.content)
            questions = result.get("questions", [])
            if not questions:
                return self._build_session_quiz_fallback(subject, session_topic, level, context_docs, num_questions)
            return questions
        except Exception as e:
            print(f"❌ Lỗi sinh đề thi: {e}")
            return self._build_session_quiz_fallback(subject, session_topic, level, context_docs, num_questions)