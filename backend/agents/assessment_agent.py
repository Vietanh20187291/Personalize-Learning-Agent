import os
import json
import random
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from groq import Groq
from dotenv import load_dotenv
from rag.vector_store import get_vector_store
from db.models import QuestionBank, LearnerProfile, Subject

load_dotenv()

class AssessmentAgent:
    def __init__(self, db: Session):
        self.db = db
        self.vector_store = get_vector_store()
        self.api_key = os.getenv("GROQ_KEY_ASSESSMENT")
        if not self.api_key:
            raise ValueError("Cần cấu hình GROQ_KEY_ASSESSMENT trong file .env")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile" 

    def force_reset_subject(self, subject: str):
        try:
            self.db.query(QuestionBank).filter_by(subject=subject).delete()
            self.db.commit()
            print(f"🧹 Đã xóa sạch dữ liệu cũ của môn {subject}.")
        except Exception as e:
            self.db.rollback()
            print(f"Lỗi reset data: {e}")

    def _resolve_subject_id(self, subject: str):
        sub = self.db.query(Subject).filter(Subject.name == subject).first()
        if sub:
            return sub.id
        # Backward compat: nếu chưa có subject record thì tạo mới.
        sub = Subject(name=subject, description=f"Môn {subject}")
        self.db.add(sub)
        self.db.flush()
        return sub.id

    def _build_fallback_questions(self, subject: str, level: str, count: int, docs: list, source_file: str):
        """Sinh câu hỏi dự phòng khi LLM lỗi (ví dụ invalid API key).
        Mục tiêu: hệ thống luôn có bài để sinh viên làm, tránh dead-end UX.
        """
        if count <= 0 or not docs:
            return 0

        subject_id = self._resolve_subject_id(subject)
        corpus_parts = []
        for d in docs[:60]:
            text = re.sub(r"\s+", " ", (d.page_content or "").strip())
            if text:
                corpus_parts.append(text)

        corpus = " ".join(corpus_parts)
        raw_sentences = re.split(r"(?<=[\.!\?;:])\s+", corpus)
        base_sentences = []
        for s in raw_sentences:
            clean = re.sub(r"\s+", " ", s).strip()
            if 40 <= len(clean) <= 220:
                base_sentences.append(clean)

        base_sentences = list(dict.fromkeys(base_sentences))
        if not base_sentences:
            return 0

        stopwords = {
            "trong", "được", "không", "những", "các", "với", "cho", "của", "một", "này", "khi", "và", "hoặc",
            "the", "and", "for", "with", "that", "from", "this", "there", "have", "into", "about"
        }

        tokens = re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", corpus)
        term_bank = []
        for t in tokens:
            low = t.lower()
            if low not in stopwords and not low.isdigit():
                term_bank.append(t)
        term_bank = list(dict.fromkeys(term_bank))

        def make_similar_wrong(sentence: str):
            words = re.findall(r"[A-Za-zÀ-ỹ0-9_]{5,}", sentence)
            candidate = sentence
            if words and term_bank:
                original = words[min(len(words) - 1, 1)]
                alternatives = [t for t in term_bank if t.lower() != original.lower()]
                if alternatives:
                    candidate = re.sub(re.escape(original), random.choice(alternatives), candidate, count=1)
            if " không " not in f" {candidate.lower()} ":
                candidate = candidate.replace(" là ", " không phải là ", 1) if " là " in candidate else "Không " + candidate[0].lower() + candidate[1:]
            return candidate

        inserted_count = 0
        max_attempts = max(count * 5, 40)
        attempt = 0

        while inserted_count < count and attempt < max_attempts:
            attempt += 1
            idx = (attempt - 1) % len(base_sentences)
            correct_fact = base_sentences[idx]
            alt_fact = base_sentences[(idx + 1) % len(base_sentences)]

            question_anchor = correct_fact[:90]
            q_text = (
                f"Dựa trên học liệu môn '{subject}', phương án nào phản ánh CHÍNH XÁC nhất nội dung đã học về ý: \"{question_anchor}\"?"
            )

            options_raw = [
                correct_fact,
                make_similar_wrong(correct_fact),
                make_similar_wrong(alt_fact),
                alt_fact[: min(len(alt_fact), 180)],
            ]

            # Cắt độ dài đáp án để tránh quá dài gây khó đọc.
            options_raw = [re.sub(r"\s+", " ", o).strip()[:200] for o in options_raw]

            # Trộn đáp án để tránh luôn đúng ở A.
            labels = ["A", "B", "C", "D"]
            idxs = [0, 1, 2, 3]
            random.shuffle(idxs)
            final_options = []
            correct_label = "A"
            for pos, raw_idx in enumerate(idxs):
                final_options.append(f"{labels[pos]}. {options_raw[raw_idx]}")
                if raw_idx == 0:
                    correct_label = labels[pos]

            if self.db.query(QuestionBank).filter(QuestionBank.content == q_text).first():
                continue

            db_q = QuestionBank(
                subject_id=subject_id,
                subject=subject,
                difficulty=level,
                content=q_text,
                options=json.dumps(final_options, ensure_ascii=False),
                correct_answer=correct_label,
                explanation="Câu hỏi dự phòng được sinh từ chính học liệu đã upload, ưu tiên phương án đúng bám sát nội dung tài liệu.",
                is_used=False,
                source_file=source_file,
            )
            self.db.add(db_q)
            inserted_count += 1

        return inserted_count

    def get_or_create_quiz(self, subject: str, user_id: int, num_questions: int = 20, allowed_files: list = None):
        if not allowed_files:
            return None

        # ---QUÉT SẠCH CÂU HỎI RÁC DO LỖI CŨ ĐỂ LẠI ---
        existing_qs = self.db.query(QuestionBank).filter(
            QuestionBank.subject == subject,
            QuestionBank.source_file.in_(allowed_files)
        ).all()
        
        if existing_qs:
            count_A = sum(1 for q in existing_qs if q.correct_answer == 'A')
            is_looping_garbage = sum(1 for q in existing_qs if "phương thức nào" in str(q.content).lower() or "đoạn mã sau" in str(q.content).lower()) > (len(existing_qs) * 0.4)
            
            has_garbage_options = False
            for q in existing_qs:
                if len(str(q.options)) < 40 or "A. A\"" in str(q.options) or "B. B\"" in str(q.options):
                    has_garbage_options = True
                    break
            
            if has_garbage_options or is_looping_garbage or (len(existing_qs) > 5 and (count_A / len(existing_qs) > 0.8)):
                print(f"⚠️ Phát hiện bộ đề cũ bị lỗi (Lặp từ / Đáp án rỗng). Đang TIÊU DIỆT TỰ ĐỘNG...")
                self.db.query(QuestionBank).filter(
                    QuestionBank.subject == subject,
                    QuestionBank.source_file.in_(allowed_files)
                ).delete(synchronize_session=False)
                self.db.commit()
                self.db.expire_all()

        profile = self.db.query(LearnerProfile).filter_by(subject=subject, user_id=user_id).first()
        current_level = profile.current_level if profile else "Beginner"

        questions = self.db.query(QuestionBank).filter(
            QuestionBank.subject == subject,
            QuestionBank.source_file.in_(allowed_files)
        ).limit(num_questions).all()

        if len(questions) < num_questions:
            needed = num_questions - len(questions)
            print(f"🚀 AI 70B đang tạo {needed} câu hỏi CHUYÊN NGHIỆP CHO GIÁO VIÊN...")
            
            success = self._generate_batch_safe(subject, current_level, needed, allowed_files)
            if not success:
                print("⚠️ Thử tạo lại với số lượng nhỏ hơn để tránh nổ Token API...")
                self._generate_batch_safe(subject, current_level, min(10, needed), allowed_files)
            
            questions = self.db.query(QuestionBank).filter(
                QuestionBank.subject == subject,
                QuestionBank.source_file.in_(allowed_files)
            ).order_by(func.random()).limit(num_questions).all()

        if not questions: return None 

        random.shuffle(questions)
        final_result = []
        for q in questions[:num_questions]:
            try:
                parsed_options = json.loads(q.options) if isinstance(q.options, str) else q.options
            except:
                parsed_options = []
            final_result.append({
                "id": q.id,
                "content": q.content,
                "options": parsed_options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation
            })

        return final_result

    def _generate_batch_safe(self, subject: str, level: str, count: int, allowed_files: list = None):
        if count <= 0: return True
        try:
            subject_id = self._resolve_subject_id(subject)
            docs = self.vector_store.similarity_search(
                f"Kiến thức trọng tâm, bài toán thực tế, code mẫu và ứng dụng môn {subject}", 
                k=40, 
                filter={"subject": {"$eq": subject}}
            )

            if allowed_files:
                filtered_docs = [d for d in docs if os.path.basename(d.metadata.get("source", "")) in allowed_files]
            else:
                filtered_docs = docs

            # Backward-compat: dữ liệu cũ có thể bị gắn subject sai (ví dụ "Khác").
            # Fallback theo filename để vẫn truy xuất đúng tri thức của lớp.
            if not filtered_docs and allowed_files:
                docs_no_subject_filter = self.vector_store.similarity_search(
                    f"Kiến thức trọng tâm, bài toán thực tế, code mẫu và ứng dụng môn {subject}",
                    k=80,
                )
                filtered_docs = [
                    d for d in docs_no_subject_filter
                    if os.path.basename(d.metadata.get("source", "")) in allowed_files
                ]

            if not filtered_docs:
                return False
            random.shuffle(filtered_docs)
            primary_source_file = os.path.basename(filtered_docs[0].metadata.get("source", "")) if filtered_docs[0].metadata.get("source", "") else "Unknown"
            
            context = "\n".join([d.page_content for d in filtered_docs[:30]])[:20000]

            # BỘ ĐỆM AN TOÀN: Chỉ xin dư 3 câu để KHÔNG BAO GIỜ bị quá tải Token làm đứt gãy JSON
            ask_count = count + 3 

            prompt = f"""
            BẠN LÀ HỘI ĐỒNG RA ĐỀ THI XUẤT BẢN CẤP QUỐC GIA CHO MÔN: "{subject}" (Trình độ: {level.upper()}).
            
            [TÀI LIỆU CỐT LÕI MÔN HỌC]:
            {context}

            [🔴 CÁC LỆNH CẤM TUYỆT ĐỐI (HỦY DIỆT SỰ LẶP LẠI VÀ ẢO GIÁC)]:
            1. CHỐNG LẶP LẠI (ANTI-LOOP): TẤT CẢ {ask_count} câu hỏi phải khai thác {ask_count} VẤN ĐỀ HOÀN TOÀN KHÁC NHAU. TUYỆT ĐỐI KHÔNG ĐƯỢC lặp lại bất kỳ câu hỏi hay đoạn code nào đã viết trước đó!
            2. CẤM ĐÁP ÁN RỖNG: Mảng "options" PHẢI CHỨA TEXT ĐÁP ÁN THẬT SỰ (Ví dụ: "Lỗi biên dịch do...", "Kết quả là 55"). CẤM TUYỆT ĐỐI việc chỉ trả về ["A", "B", "C", "D"].
            3. CHẤT LƯỢNG GIẢI THÍCH: Phần 'explanation' BẮT BUỘC phải giải thích chi tiết tại sao đúng/sai (ít nhất 2-3 câu). TUYỆT ĐỐI KHÔNG trả về từ khóa cộc lốc.
            4. VĂN PHONG ĐA DẠNG: Đừng mãi dùng chữ "Đoạn mã sau...". Hãy dùng: "Xét hàm...", "Trong mô hình...", "Khi hệ thống...".

            [KPI ĐAN XEN TƯ DUY - PHẢI TẠO ĐÚNG {ask_count} CÂU]:
            1. THỰC HÀNH/BÀI TẬP (35%):
               - Lập trình/CNTT: Bắt buộc có mã code (dùng \\n). Hỏi về output, tìm lỗi, hoặc điền vào chỗ trống.
               - Toán/Kinh tế: Đưa ra thông số, bắt tính toán.
            2. TÌNH HUỐNG/CASE STUDY (35%): Xây dựng bối cảnh dự án, phần mềm thực tế. Yêu cầu chọn phương án thiết kế tốt nhất.
            3. LÝ THUYẾT NÂNG CAO (30%): So sánh sự khác biệt bản chất. Phân tích ưu/nhược điểm. 

            [CẤU TRÚC JSON BẮT BUỘC]:
            {{
                "questions": [
                    {{
                        "concept_tested": "Tên vấn đề cốt lõi (Không trùng lặp)",
                        "question_type": "Thực hành / Bài tập" HOẶC "Tình huống (Case study)" HOẶC "Lý thuyết nâng cao",
                        "is_code_included": true/false,
                        "question": "Nội dung câu hỏi sâu sắc, dùng \\n để xuống dòng trình bày code/đoạn văn...",
                        "options": [
                            "Nội dung đáp án 1 (Phải là text thực tế)", 
                            "Nội dung đáp án 2 (Phải là text thực tế)", 
                            "Nội dung đáp án 3 (Phải là text thực tế)", 
                            "Nội dung đáp án 4 (Phải là text thực tế)"
                        ],
                        "correct_answer": "C",
                        "explanation": "Giải thích chi tiết lý do chọn đáp án này, phân tích tối thiểu 2 câu."
                    }}
                ]
            }}
            Chỉ xuất ra chuỗi JSON. KHÔNG CHÈN TEXT BÊN NGOÀI.
            """

            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": f"You are a strict national-level examiner. Output valid JSON ONLY. Generate exactly {ask_count} highly diverse questions. NEVER output empty 'A,B,C,D' arrays in options. ZERO tolerance for repeating the same question."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.8, # Tăng lên 0.8 để bắt nó phải bung sự sáng tạo
                max_tokens=8000, 
                response_format={"type": "json_object"}
            )
            
            raw_content = chat_completion.choices[0].message.content
            clean_content = re.sub(r'```json\s*|\s*```', '', raw_content, flags=re.IGNORECASE).strip()
            
            data = json.loads(clean_content)
            questions_list = data.get("questions", [])

            inserted_count = 0
            for item in questions_list:
                if inserted_count >= count:
                    break
                    
                q_text = str(item.get('question', '')).strip()
                raw_options = item.get('options', [])
                correct_ans = str(item.get('correct_answer', 'A')).strip().upper()
                
                if not q_text or len(raw_options) < 4: continue 

                # LỚP KHIÊN THÉP: Chặn đứng đáp án rỗng hoặc chỉ chứa chữ A,B,C,D
                is_garbage = False
                for opt in raw_options:
                    clean_opt = re.sub(r'^[A-D][\.\:\-\)]\s*', '', str(opt)).strip()
                    if clean_opt in ["A", "B", "C", "D", ""] or len(clean_opt) <= 1:
                        is_garbage = True
                        break
                
                if is_garbage:
                    continue

                match = re.search(r'([A-D])', correct_ans)
                final_key = match.group(1) if match else "A"

                labels = ["A", "B", "C", "D"]
                final_options = []
                for i in range(4):
                    clean_text = re.sub(r'^[A-D][\.\:\-\)]\s*', '', str(raw_options[i])).strip()
                    final_options.append(f"{labels[i]}. {clean_text}")

                if not self.db.query(QuestionBank).filter(QuestionBank.content == q_text).first():
                    db_q = QuestionBank(
                        subject_id=subject_id,
                        subject=subject, 
                        difficulty=level, 
                        content=q_text,
                        options=json.dumps(final_options, ensure_ascii=False), 
                        correct_answer=final_key,
                        explanation=f"[{item.get('question_type', 'Tư duy')}] {item.get('explanation', '')}",
                        is_used=False,
                        source_file=primary_source_file
                    )
                    self.db.add(db_q)
                    inserted_count += 1

            # Nếu LLM trả về không dùng được, tự sinh fallback để không bị kẹt luồng tạo đề.
            if inserted_count == 0:
                inserted_count = self._build_fallback_questions(subject, level, count, filtered_docs, primary_source_file)

            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"❌ Lỗi sinh batch câu hỏi (Nổ Token hoặc đứt gãy JSON): {e}")

            # Fallback cuối: nếu dịch vụ AI lỗi (401/timeout), vẫn tạo bộ câu hỏi dự phòng từ học liệu.
            try:
                docs_for_fallback = self.vector_store.similarity_search(
                    f"Nội dung học liệu môn {subject}",
                    k=60,
                )
                if allowed_files:
                    docs_for_fallback = [
                        d for d in docs_for_fallback
                        if os.path.basename(d.metadata.get("source", "")) in allowed_files
                    ]

                if docs_for_fallback:
                    primary_source_file = os.path.basename(docs_for_fallback[0].metadata.get("source", "")) if docs_for_fallback[0].metadata.get("source", "") else "Unknown"
                    inserted = self._build_fallback_questions(subject, level, count, docs_for_fallback, primary_source_file)
                    if inserted > 0:
                        self.db.commit()
                        print(f"✅ Đã kích hoạt fallback và tạo {inserted} câu hỏi dự phòng cho môn {subject}.")
                        return True
            except Exception as fallback_err:
                self.db.rollback()
                print(f"❌ Fallback cũng thất bại: {fallback_err}")

            return False

    