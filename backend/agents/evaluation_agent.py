import os
import json
import re
from datetime import datetime
from typing import Optional
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy import func
from db.models import AssessmentHistory, Document, QuestionBank, StudentDocumentEvaluation, StudentDocumentScoreHistory, StudentLearningPlanStep, UserLoginSession
from rag.vector_store import get_vector_store
from services.score_metrics import compute_subject_score_metrics

# Tải biến môi trường
load_dotenv()

class EvaluationAgent:
    def __init__(self, db_session=None):
        self.api_key = os.getenv("GROQ_KEY_EVALUATION")
        if not self.api_key:
            raise ValueError("Cần cấu hình GROQ_KEY_EVALUATION trong file .env")
            
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile" 
        self.db = db_session
        try:
            self.vector_store = get_vector_store()
        except Exception as exc:
            print(f"⚠️ EvaluationAgent fallback mode (vector store unavailable): {exc}")
            self.vector_store = None

    # --- HÀM ĐÁNH GIÁ HIỆU SUẤT TỔNG THỂ (CẤU TRÚC 1-10-1) ---
    def _compute_login_time_metrics(self, user_id: int):
        now = datetime.utcnow()
        sessions = self.db.query(UserLoginSession).filter(
            UserLoginSession.user_id == user_id,
        ).all()

        total_seconds = 0
        counted_sessions = 0
        for item in sessions:
            if not item.login_at:
                continue

            if item.duration_seconds and int(item.duration_seconds) > 0:
                total_seconds += int(item.duration_seconds)
                counted_sessions += 1
                continue

            if item.logout_at and item.logout_at >= item.login_at:
                total_seconds += int((item.logout_at - item.login_at).total_seconds())
                counted_sessions += 1
                continue

            # Phiên mở chưa logout: chỉ cộng phần thời gian đã trôi qua.
            if item.logout_at is None and now >= item.login_at:
                total_seconds += int((now - item.login_at).total_seconds())
                counted_sessions += 1

        total_minutes = total_seconds / 60.0
        return {
            "total_seconds": total_seconds,
            "total_minutes": total_minutes,
            "session_count": counted_sessions,
        }

    def chat_about_progress(self, user_id: int, message: str, subject: Optional[str] = None):
        clean_message = str(message or "").strip()
        clean_subject = str(subject or "").strip()
        if not clean_message:
            return "Hãy đặt câu hỏi cụ thể về thành tích học tập của bạn."

        history_query = self.db.query(AssessmentHistory).filter(AssessmentHistory.user_id == user_id)
        score_query = self.db.query(StudentDocumentScoreHistory).filter(StudentDocumentScoreHistory.user_id == user_id)
        eval_query = self.db.query(StudentDocumentEvaluation).filter(StudentDocumentEvaluation.user_id == user_id)
        doc_query = self.db.query(Document)

        if clean_subject:
            history_query = history_query.filter(AssessmentHistory.subject == clean_subject)
            doc_query = doc_query.filter(Document.subject == clean_subject)

        doc_rows = doc_query.all()
        doc_ids = [int(item.id) for item in doc_rows]
        if clean_subject:
            if doc_ids:
                score_query = score_query.filter(StudentDocumentScoreHistory.document_id.in_(doc_ids))
                eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_(doc_ids))
            else:
                score_query = score_query.filter(StudentDocumentScoreHistory.document_id.in_([-1]))
                eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_([-1]))

        history_rows = history_query.order_by(AssessmentHistory.timestamp.desc()).limit(20).all()
        score_rows = score_query.order_by(StudentDocumentScoreHistory.tested_at.desc()).limit(40).all()
        document_ids = sorted({int(item.document_id) for item in score_rows})
        if document_ids:
            eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_(document_ids))
        eval_rows = eval_query.order_by(StudentDocumentEvaluation.updated_at.desc()).all()
        plan_step_query = self.db.query(StudentLearningPlanStep).filter(StudentLearningPlanStep.user_id == user_id)
        if document_ids:
            plan_step_query = plan_step_query.filter(StudentLearningPlanStep.document_id.in_(document_ids))
        plan_rows = plan_step_query.order_by(
            StudentLearningPlanStep.updated_at.desc(),
            StudentLearningPlanStep.id.desc(),
        ).all()
        doc_name_map = {
            int(item.id): str(item.title or item.filename or f"Tai lieu {item.id}")
            for item in doc_rows
        }
        latest_plan_by_doc = {}
        for item in plan_rows:
            latest_plan_by_doc.setdefault(int(item.document_id), item)

        avg_score = 0.0
        best_score = 0.0
        if history_rows:
            avg_score = round(sum(float(item.score or 0.0) for item in history_rows) / len(history_rows), 2)
            best_score = round(max(float(item.score or 0.0) for item in history_rows), 2)

        recent_tests = [
            {
                "subject": str(item.subject or ""),
                "score": float(item.score or 0.0),
                "test_type": str(item.test_type or ""),
                "date": item.timestamp.isoformat() if item.timestamp else None,
            }
            for item in history_rows
        ]
        document_scores = [
            {
                "document_id": int(item.document_id),
                "document_title": doc_name_map.get(int(item.document_id), f"Tai lieu {item.document_id}"),
                "score": float(item.score or 0.0),
                "test_type": str(item.test_type or ""),
                "tested_at": item.tested_at.isoformat() if item.tested_at else None,
            }
            for item in score_rows
        ]
        document_status = [
            {
                "document_id": int(item.document_id),
                "document_title": doc_name_map.get(int(item.document_id), f"Tai lieu {item.document_id}"),
                "latest_score": float(item.latest_score or 0.0),
                "attempts": int(item.attempts or 0),
                "is_completed": bool(item.is_completed),
                "last_test_at": item.last_test_at.isoformat() if item.last_test_at else None,
                "planned_date": latest_plan_by_doc.get(int(item.document_id)).planned_date.isoformat()
                if latest_plan_by_doc.get(int(item.document_id)) and latest_plan_by_doc.get(int(item.document_id)).planned_date
                else None,
                "deadline_date": latest_plan_by_doc.get(int(item.document_id)).deadline_date.isoformat()
                if latest_plan_by_doc.get(int(item.document_id)) and latest_plan_by_doc.get(int(item.document_id)).deadline_date
                else None,
            }
            for item in eval_rows
        ]

        fallback = (
            f"Bạn đã có {len(recent_tests)} lần kiểm tra"
            f"{' cho môn ' + clean_subject if clean_subject else ''}. "
            f"Điểm trung bình hiện tại là {avg_score:.1f}, điểm cao nhất là {best_score:.1f}. "
            "Nếu bạn muốn, tôi có thể chỉ rõ môn hoặc tài liệu đang yếu nhất của bạn."
        )

        try:
            prompt = f"""
Ban la Evaluation Agent cho sinh vien.
Hay tra loi bang tieng Viet, ngan gon, dua tren du lieu, khong noi chung chung.
Neu co the, chi ro mon hoac tai lieu dang yeu va de xuat buoc tiep theo.
Tra loi toi da 6 cau.

Mon dang xem: {clean_subject or "Tat ca"}
Cau hoi cua sinh vien: {clean_message}

Tom tat nhanh:
- So bai kiem tra gan day: {len(recent_tests)}
- Diem trung binh: {avg_score}
- Diem cao nhat: {best_score}

Lich su bai kiem tra:
{json.dumps(recent_tests, ensure_ascii=False)}

Lich su diem theo tai lieu:
{json.dumps(document_scores, ensure_ascii=False)}

Trang thai tai lieu:
{json.dumps(document_status, ensure_ascii=False)}
""".strip()
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=500,
            )
            reply = str(completion.choices[0].message.content or "").strip()
            return reply or fallback
        except Exception:
            return fallback

    def evaluate_performance(self, user_id: int, subject: str, current_score: float, test_type: str):
        """
        Đánh giá điểm môn từ tất cả điểm kiểm tra theo từng tài liệu thuộc môn:
        - TEST SCORE: Trung bình điểm mới nhất của tất cả tài liệu trong môn.
        - EFFORT SCORE: Dựa trên tổng thời gian đăng nhập hệ thống.
        - PROGRESS SCORE: Dựa trên xu hướng tăng/giảm điểm qua các mốc thời gian.
        """

        # 1. TÍNH EFFORT SCORE (Tổng thời gian đăng nhập hệ thống)
        score_metrics = compute_subject_score_metrics(
            db=self.db,
            user_id=user_id,
            subject_name=subject,
        )

        login_metrics = self._compute_login_time_metrics(user_id)
        login_minutes = float(login_metrics.get("total_minutes", 0.0) or 0.0)
        effort_score = min(100.0, (login_minutes / 600.0) * 100.0)

        # 2. TEST SCORE + PROGRESS SCORE lấy từ lịch sử điểm theo tài liệu
        actual_test_score = float(score_metrics.get("test_score", current_score) or current_score)
        progress_score = float(score_metrics.get("progress_score", 0.0) or 0.0)
        improvement = float(score_metrics.get("improvement", 0.0) or 0.0)

        # 3. CHỐT FINAL SCORE
        final_score = (0.5 * actual_test_score) + (0.3 * effort_score) + (0.2 * progress_score)

        # 4. GỌI AI ĐỂ TẠO NHẬN XÉT CÁ NHÂN HÓA
        evaluation_msg = self._get_ai_feedback(actual_test_score, effort_score, improvement)
        
        return {
            "actual_test_score": round(actual_test_score, 2),
            "effort_score": round(effort_score, 2),
            "effort_total_login_minutes": round(login_minutes, 2),
            "effort_login_session_count": int(login_metrics.get("session_count", 0) or 0),
            "progress_score": round(progress_score, 2),
            "final_score": round(final_score, 2),
            "evaluation_msg": evaluation_msg
        }

    # --- 3. PROMPT AI VIẾT LỜI PHÊ ---
    def _get_ai_feedback(self, score, effort, improvement):
        # Logic này giúp định hướng AI viết đúng trọng tâm ngay lập tức
        directive = ""
        if score >= 80 and effort < 30:
            directive = "Cảnh báo nhẹ nhàng: Điểm tốt nhưng học với Gia sư AI quá ít, nhắc nhở tránh chủ quan hoặc học vẹt."
        elif score < 50 and effort > 70:
            directive = "Động viên mạnh mẽ: Điểm thi chưa tốt nhưng rất chăm học AI, khuyên không nên nản chí."
        elif score >= 80:
            directive = "Khen ngợi: Kết quả xuất sắc và thời gian tự học xứng đáng."
        elif score < 50:
            directive = "Nhắc nhở nghiêm túc: Cần tăng cường ôn tập và trao đổi với Gia sư AI nhiều hơn."
        else:
            directive = "Ghi nhận: Kết quả ở mức khá, cần bứt phá thêm ở phần tương tác AI."

        status_text = "tăng" if improvement >= 0 else "giảm"

        # Prompt "Thiết quân luật" - Ép AI vào khuôn khổ
        prompt = f"""
        Bạn là Giảng viên AI. Hãy viết nhận xét cho học viên dựa trên dữ liệu thật này:
        - Điểm kiểm tra tổng hợp: {score}/100
        - Nỗ lực tự học (Thời gian chat với AI): {effort}%
        - Tiến bộ so với đầu vào: {status_text} {abs(improvement)} điểm.

        MỆNH LỆNH CỦA BẠN (Follow this strictly): {directive}

        QUY TẮC BẮT BUỘC:
        1. Viết DUY NHẤT một đoạn văn ngắn (tối đa 40 từ).
        2. Tuyệt đối KHÔNG viết các câu giả định như "Nếu điểm cao thì...", "Hoặc nếu...".
        3. Chỉ nhận xét thẳng vào trường hợp cụ thể này.
        4. Giọng văn: Chân thành, ngắn gọn, súc tích.
        """

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3, # Giảm xuống thấp để AI bớt sáng tạo lung tung
                max_tokens=100,  # Giới hạn cứng số lượng từ trả về (Tiết kiệm token)
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Lỗi Evaluation Agent AI: {e}")
            # Fallback (Dự phòng) nếu AI lỗi
            if score >= 80: return "Kết quả rất tốt! Hãy tiếp tục duy trì phong độ này nhé."
            if score < 50: return "Kết quả chưa tốt lắm, hãy trao đổi thêm với Gia sư AI nhé."
            return "Bạn đã hoàn thành bài thi. Hãy cố gắng hơn ở lần sau!"

    # ==========================================
    # HÀM PHÂN TÍCH QUIZ THEO TỪNG CÂU
    # ==========================================
    def analyze_quiz_answers(self, subject: str, question_answer_pairs: list, source_file: str = ""):
        """
        Phân tích chi tiết từng câu trắc nghiệm sai.
        Input:
            subject: Môn học
            question_answer_pairs: [
                {
                    "question_id": 1,
                    "question_text": "Câu hỏi...",
                    "user_answer": "B",
                    "correct_answer": "C",
                    "is_correct": false,
                    "options": ["A...", "B...", "C...", "D..."]
                },
                ...
            ]
            source_file: Tên tài liệu để lấy context
        
        Output:
            [
                {
                    "question_id": 1,
                    "is_correct": false,
                    "analysis": "Chi tiết tại sao sai, lời giải thích AI."
                },
                ...
            ]
        """
        results = []
        
        for item in question_answer_pairs:
            # Nếu đúng, không cần phân tích
            if item.get("is_correct"):
                results.append({
                    "question_id": item.get("question_id"),
                    "is_correct": True,
                    "analysis": "✅ Câu trả lời chính xác!"
                })
                continue
            
            # Nếu sai → AI phân tích
            question_id = item.get("question_id")
            question_text = item.get("question_text", "")
            user_answer = item.get("user_answer", "")
            correct_answer = item.get("correct_answer", "")
            options = item.get("options", [])
            
            # Tìm nội dung option được chọn và option đúng
            user_answer_text = ""
            correct_answer_text = ""
            
            label_map = {0: "A", 1: "B", 2: "C", 3: "D"}
            for idx, opt in enumerate(options):
                label = label_map.get(idx, "?")
                if label == user_answer:
                    user_answer_text = opt
                if label == correct_answer:
                    correct_answer_text = opt
            
            # Lấy context từ tài liệu
            doc_context = ""
            if source_file and self.vector_store is not None:
                try:
                    docs = self.vector_store.similarity_search(
                        question_text,
                        k=5,
                        filter={"source": {"$regex": source_file}}
                    )
                    doc_context = "\n".join([d.page_content for d in docs[:3]])[:1000]
                except:
                    doc_context = ""
            
            # Gọi AI phân tích
            analysis = self._analyze_wrong_answer(
                question_text,
                user_answer_text,
                correct_answer_text,
                options,
                doc_context
            )
            
            results.append({
                "question_id": question_id,
                "is_correct": False,
                "analysis": analysis
            })
        
        return results

    def _analyze_wrong_answer(self, question: str, user_answer: str, correct_answer: str, options: list, doc_context: str):
        """AI phân tích tại sao học sinh trả lời sai."""
        
        context_text = f"\n\nTrích từ tài liệu:\n{doc_context}" if doc_context else ""
        
        prompt = f"""
        Bạn là một giáo viên chuyên phân tích lỗi học tập. 
        
        Câu hỏi: {question}
        
        Đáp án của học sinh: {user_answer}
        Đáp án đúng: {correct_answer}
        
        Các lựa chọn:
        {chr(10).join([f'- {opt}' for opt in options])}
        {context_text}
        
        NHIỆM VỤ:
        1. Giải thích tại sao đáp án của học sinh là SAIQA) (Phân tích logic sai, khái niệm nhầm, v.v.)
        2. Giải thích tại sao đáp án "{correct_answer}" là ĐÚNG (Dựa vào kiến thức)
        3. Nêu điểm nhầm lẫn chính
        
        VĂN PHONG: Ngắn gọn (tối đa 5-6 câu), chân thành, hướng dẫn cách sửa.
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.4,
                max_tokens=400
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Lỗi phân tích câu sai: {e}")
            return f"❌ Bạn chọn '{user_answer}' nhưng đáp án đúng là '{correct_answer}'. Hãy review lại phần này trong tài liệu."
