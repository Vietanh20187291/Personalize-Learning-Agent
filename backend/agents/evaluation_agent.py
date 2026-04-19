import os
import json
import re
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy import func
from db.models import QuestionBank, UserLoginSession
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
        self.vector_store = get_vector_store()

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
            if source_file:
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