import json
import os
import re
import random
from sqlalchemy.orm import Session
from groq import Groq
from dotenv import load_dotenv
from db.models import LearnerProfile, LearningRoadmap, Subject
from rag.vector_store import get_vector_store

# Tải biến môi trường
load_dotenv()

class AdaptiveAgent:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = os.getenv("GROQ_KEY_ADAPTIVE")
        self.client = Groq(api_key=self.api_key) if self.api_key else None
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

    def summarize_material(self, subject: str, source_file: str, session_topic: str = "", allowed_filenames: list = None):
        query = f"Tóm tắt toàn bộ tài liệu {source_file} cho môn {subject}. {session_topic}".strip()

        search_filter = {"subject": {"$eq": subject}}
        if allowed_filenames:
            search_filter = {"$and": [{"subject": {"$eq": subject}}, {"source": {"$in": allowed_filenames}}]}
        if source_file:
            search_filter = {
                "$and": [
                    {"subject": {"$eq": subject}},
                    {"source": {"$eq": source_file}}
                ]
            }

        try:
            # Tăng k lên 60 để đảm bảo AI đọc toàn bộ nội dung tài liệu
            docs = self.vector_store.similarity_search(query, k=60, filter=search_filter)
            if not docs and source_file:
                # Fallback khi metadata source lưu dạng đường dẫn thay vì tên file thuần.
                docs_all = self.vector_store.similarity_search(query, k=100, filter={"subject": {"$eq": subject}})
                docs = [d for d in docs_all if os.path.basename(str(d.metadata.get("source", ""))) == source_file]
        except Exception:
            docs = []

        context_docs = "\n\n".join([d.page_content for d in docs if (d.page_content or "").strip()])[:18000]
        if not context_docs:
            return {
                "summary": f"Mình chưa đọc được nội dung chi tiết của tài liệu {source_file}. Bạn mở phần nội dung bên trái rồi gửi câu hỏi cụ thể, mình sẽ hỗ trợ từng phần.",
                "suggested_prompts": [
                    "Nêu mục tiêu chính của tài liệu này",
                    "Cho mình 3 ý quan trọng nhất cần nhớ",
                    "Đặt 3 câu trắc nghiệm tự kiểm tra từ tài liệu này",
                ],
            }

        fallback_sentences = [s.strip() for s in re.split(r"(?<=[\.!?;:])\s+", context_docs) if s.strip()]
        fallback_summary = " ".join(fallback_sentences[:6])[:700]
        fallback_prompts = [
            "Từ tài liệu này, phần nào dễ nhầm nhất?",
            "Hãy tóm tắt lại theo 5 ý chính ngắn gọn",
            "Tạo 5 câu trắc nghiệm bám sát nội dung tài liệu",
        ]

        if not self.client:
            return {"summary": fallback_summary, "suggested_prompts": fallback_prompts}

        prompt = f"""
Bạn là gia sư AI chuyên nghiệp. 

🔴 LỆNH TUYỆT ĐỐI: ĐỌC TOÀN BỘ NỘI DUNG TÀI LIỆU ĐƯỢC CUNG CẤP VÀ TÓM TẮT ĐẦY ĐỦ.

Hãy đọc toàn bộ nội dung tài liệu để cung cấp:
1. **summary**: Tóm tắt súc tích 8-12 câu, bao quát TOÀN BỘ nội dung tài liệu, có cấu trúc rõ ràng, gồm phần giới thiệu + nội dung chính + kết luận.
2. **suggested_prompts**: 4 câu hỏi học tập sâu sắc giúp người học đào sâu kiến thức tài liệu này.

Trả JSON hợp lệ:
{{
  "summary": "Tóm tắt toàn bộ nội dung...",
  "suggested_prompts": ["câu hỏi 1", "câu hỏi 2", "câu hỏi 3", "câu hỏi 4"]
}}

Ràng buộc KHÔNG ĐƯỢC VI PHẠM:
- summary phải dựa trên TOÀN BỘ nội dung tài liệu, không bịa, không bỏ sót phần quan trọng.
- suggested_prompts phải là câu hỏi học tập hữu ích giúp đào sâu từng mảng nội dung.
- Viết bằng tiếng Việt rõ ràng.

Môn: {subject}
Tên tài liệu: {source_file}
Ngữ cảnh buổi: {session_topic or 'Không xác định'}

NỘI DUNG TÀI LIỆU (HÃY ĐỌC TOÀN BỘ):
{context_docs}
"""

        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful tutor. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.2,
                max_tokens=1600,
                response_format={"type": "json_object"},
            )
            data = json.loads(completion.choices[0].message.content)
            summary = str(data.get("summary") or "").strip() or fallback_summary
            prompts = data.get("suggested_prompts") or fallback_prompts
            if not isinstance(prompts, list):
                prompts = fallback_prompts
            prompts = [str(p).strip() for p in prompts if str(p).strip()][:4] or fallback_prompts
            return {"summary": summary, "suggested_prompts": prompts}
        except Exception:
            return {"summary": fallback_summary, "suggested_prompts": fallback_prompts}

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
    def chat_with_tutor(self, subject: str, user_message: str, roadmap_context: str, allowed_filenames: list = None, session_topic: str = "", source_file: str = "", history: list = None):
        if history is None: history = []
        
        context_docs = ""
        search_filter = {"subject": {"$eq": subject}}
        if allowed_filenames:
            search_filter = {"$and": [{"subject": {"$eq": subject}}, {"source": {"$in": allowed_filenames}}]}
        if source_file:
            search_filter = {
                "$and": [
                    {"subject": {"$eq": subject}},
                    {"source": {"$eq": source_file}}
                ]
            }

        chapter_query = f"{session_topic}. {user_message}" if session_topic else user_message

        try:
            # Tăng k từ 5 lên 20 để AI có đủ context từ tài liệu khi trả lời câu hỏi
            docs = self.vector_store.similarity_search(chapter_query, k=20, filter=search_filter)
            if not docs and source_file:
                docs_all = self.vector_store.similarity_search(chapter_query, k=50, filter={"subject": {"$eq": subject}})
                docs = [d for d in docs_all if os.path.basename(str(d.metadata.get("source", ""))) == source_file]
            context_docs = "\n\n".join([doc.page_content for doc in docs])
        except Exception as e:
            context_docs = "Dữ liệu kiến thức đang được cập nhật."

        subject_obj = self.db.query(Subject).filter(Subject.name.ilike((subject or "").strip())).first()
        profile = None
        if subject_obj:
            profile = self.db.query(LearnerProfile).filter_by(subject_id=subject_obj.id).first()
        if not profile:
            profile = self.db.query(LearnerProfile).filter_by(subject=subject).first()
        current_level = profile.current_level if profile else "Beginner"

        system_prompt = f"""BẠN LÀ MỘT GIA SƯ AI TƯƠNG TÁC 1-1 CỰC KỲ XUẤT SẮC CỦA MÔN {subject}.
🔴 LỆNH TUYỆT ĐỐI: PHẢI LUÔN TRÍCH DẪN NỘI DUNG CỤ THỂ TỪ TÀI LIỆU KHI TRẢ LỜI, KHÔNG CHỈ GIẢI THÍCH CHUNG CHUNG.
TRÌNH ĐỘ HỌC VIÊN: {current_level}
[NỘI DUNG BUỔI HỌC HÔM NAY]: {roadmap_context}
[KIẾN THỨC TỪ TÀI LIỆU CỦA GIÁO VIÊN]: {context_docs[:5000]}

[NGUYÊN TẮC TỐI THƯỢNG]:
- TUYỆT ĐỐI KHÔNG giảng bài dài dòng. Mỗi tin nhắn chỉ đưa ra MỘT mẩu kiến thức nhỏ gắn liền với MỘT câu hỏi gợi mở.
- NẾU ĐÂY LÀ BÀI "KIỂM TRA TỔNG HỢP CUỐI KHÓA": Hãy nhắc nhở ôn tập, động viên học viên làm bài Test qua bài.

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
            return self._build_fallback_tutor_reply(subject, user_message, roadmap_context, context_docs)

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
                return self._build_fallback_tutor_reply(subject, user_message, roadmap_context, context_docs)
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