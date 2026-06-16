import os
import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Optional
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy import func
from db.models import AssessmentHistory, Document, QuestionBank, StudentDocumentEvaluation, StudentDocumentScoreHistory, StudentLearningPlanStep, Subject, UserLoginSession
from rag.vector_store import get_vector_store
from services.score_metrics import compute_subject_score_metrics

# Tải biến môi trường
load_dotenv()

class EvaluationAgent:
    def __init__(self, db_session=None):
        self.api_key = self._resolve_groq_api_key()
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self.model = "llama-3.3-70b-versatile" 
        self.db = db_session
        try:
            self.vector_store = get_vector_store()
        except Exception as exc:
            print(f"⚠️ EvaluationAgent fallback mode (vector store unavailable): {exc}")
            self.vector_store = None

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

    def _to_iso(self, value):
        if not value:
            return None
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    def _build_progress_fallback_reply(
        self,
        message: str,
        subject: str,
        recent_tests: list,
        subject_summaries: list,
        document_status: list,
        overdue_documents: list,
        completed_late_documents: list,
        avg_score: float,
        best_score: float,
    ) -> str:
        clean_message = (message or "").strip().lower()
        if not recent_tests and not document_status:
            return "Bạn chưa có đủ dữ liệu kiểm tra hoặc kế hoạch học tập để Evaluation Agent phân tích."

        weakest_subject = subject_summaries[0] if subject_summaries else None
        weakest_documents = sorted(
            document_status,
            key=lambda item: (
                0 if item.get("is_pending_overdue") else 1,
                0 if item.get("is_completed_late") else 1,
                float(item.get("latest_score", 0.0)),
                item.get("document_title", ""),
            ),
        )[:3]

        latest_scores = [float(item.get("score") or 0.0) for item in recent_tests[:5]]
        previous_scores = [float(item.get("score") or 0.0) for item in recent_tests[5:10]]
        trend_text = "chưa đủ dữ liệu để kết luận xu hướng"
        if latest_scores and previous_scores:
            latest_avg = sum(latest_scores) / len(latest_scores)
            previous_avg = sum(previous_scores) / len(previous_scores)
            delta = round(latest_avg - previous_avg, 1)
            if delta > 0:
                trend_text = f"điểm gần đây đang tăng khoảng {delta} điểm"
            elif delta < 0:
                trend_text = f"điểm gần đây đang giảm khoảng {abs(delta)} điểm"
            else:
                trend_text = "điểm gần đây gần như đi ngang"

        if any(token in clean_message for token in ["trễ", "quá hạn", "đúng hạn", "hạn"]):
            if overdue_documents:
                names = ", ".join(str(item.get("document_title") or "") for item in overdue_documents[:3])
                return f"Bạn đang có {len(overdue_documents)} tài liệu quá hạn chưa hoàn thành. Cần ưu tiên xử lý ngay: {names}."
            if completed_late_documents:
                names = ", ".join(str(item.get("document_title") or "") for item in completed_late_documents[:3])
                return f"Hiện không còn tài liệu treo quá hạn, nhưng có {len(completed_late_documents)} tài liệu đã hoàn thành trễ hạn: {names}."
            return "Hiện chưa thấy tài liệu nào bị trễ hoặc quá hạn trong dữ liệu kế hoạch học tập."

        if any(token in clean_message for token in ["môn", "yếu", "kém", "đuối"]):
            if weakest_subject:
                return (
                    f"Môn yếu nhất hiện tại là {weakest_subject['subject']}: "
                    f"điểm trung bình khoảng {weakest_subject['avg_score']}, "
                    f"điểm gần nhất {weakest_subject['latest_score']}. "
                    f"{'Bạn cũng đang có tài liệu trễ hạn ở môn này.' if any((item.get('subject') or '') == weakest_subject['subject'] and item.get('is_pending_overdue') for item in document_status) else 'Bạn nên ưu tiên ôn lại các tài liệu có điểm thấp của môn này.'}"
                )
            return "Chưa đủ dữ liệu để xác định môn yếu nhất của bạn."

        if any(token in clean_message for token in ["tài liệu", "ôn", "ôn lại", "học lại", "nên học"]):
            if weakest_documents:
                lines = []
                for item in weakest_documents:
                    status = str(item.get("status") or "đang học")
                    score = float(item.get("latest_score") or 0.0)
                    lines.append(f"{item.get('document_title')} ({score:.1f} điểm, {status})")
                return "Các tài liệu nên ưu tiên tiếp theo là: " + "; ".join(lines) + "."
            return "Hiện chưa có tài liệu nào đủ dữ liệu để đề xuất ưu tiên ôn tập."

        if any(token in clean_message for token in ["tiến bộ", "xu hướng", "cải thiện"]):
            return f"Xu hướng hiện tại: {trend_text}. Điểm trung bình đang là {avg_score:.1f} và điểm cao nhất là {best_score:.1f}."

        summary_parts = [
            f"Tổng số lượt kiểm tra hiện có là {len(recent_tests)}{' trong môn ' + subject if subject else ''}.",
            f"Mức điểm trung bình đang ở {avg_score:.1f}, còn điểm cao nhất đạt {best_score:.1f}.",
        ]
        if weakest_subject:
            summary_parts.append(
                f"Môn cần chú ý nhất là {weakest_subject['subject']} với mức trung bình khoảng {weakest_subject['avg_score']}."
            )
        if overdue_documents:
            summary_parts.append(f"Bạn đang có {len(overdue_documents)} tài liệu quá hạn chưa hoàn thành.")
        elif completed_late_documents:
            summary_parts.append(f"Có {len(completed_late_documents)} tài liệu đã hoàn thành nhưng bị trễ hạn.")
        summary_parts.append(f"Xu hướng chung: {trend_text}.")
        return " ".join(summary_parts)

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
        subject_doc_ids = []

        if clean_subject:
            history_query = history_query.filter(AssessmentHistory.subject == clean_subject)
            subject_obj = self.db.query(Subject).filter(func.lower(Subject.name) == clean_subject.lower()).first()
            subject_filter = self.db.query(Document)
            if subject_obj:
                subject_filter = subject_filter.filter(Document.subject_id == int(subject_obj.id))
            else:
                subject_filter = subject_filter.filter(Document.subject == clean_subject)
            subject_doc_ids = [
                int(item.id)
                for item in subject_filter
                .all()
            ]
            if subject_doc_ids:
                score_query = score_query.filter(StudentDocumentScoreHistory.document_id.in_(subject_doc_ids))
                eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_(subject_doc_ids))
            else:
                score_query = score_query.filter(StudentDocumentScoreHistory.document_id.in_([-1]))
                eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_([-1]))

        history_rows = history_query.order_by(AssessmentHistory.timestamp.desc()).limit(120).all()
        score_rows = score_query.order_by(StudentDocumentScoreHistory.tested_at.desc()).limit(180).all()
        plan_step_query = self.db.query(StudentLearningPlanStep).filter(StudentLearningPlanStep.user_id == user_id)
        if clean_subject:
            plan_step_query = plan_step_query.filter(StudentLearningPlanStep.subject_name == clean_subject)
            if subject_doc_ids:
                plan_step_query = plan_step_query.filter(StudentLearningPlanStep.document_id.in_(subject_doc_ids))
        plan_rows = plan_step_query.order_by(
            StudentLearningPlanStep.updated_at.desc(),
            StudentLearningPlanStep.id.desc(),
        ).all()

        candidate_document_ids = sorted(
            {
                *[int(item.document_id) for item in score_rows],
                *[int(item.document_id) for item in plan_rows],
            }
        )
        if candidate_document_ids:
            eval_query = eval_query.filter(StudentDocumentEvaluation.document_id.in_(candidate_document_ids))
        eval_rows = eval_query.order_by(StudentDocumentEvaluation.updated_at.desc()).all()

        all_document_ids = sorted(
            {
                *candidate_document_ids,
                *[int(item.document_id) for item in eval_rows],
            }
        )
        doc_query = self.db.query(Document)
        if all_document_ids:
            doc_query = doc_query.filter(Document.id.in_(all_document_ids))
        elif clean_subject:
            doc_query = doc_query.filter(Document.subject == clean_subject)
        else:
            doc_query = doc_query.filter(Document.id.in_([-1]))
        doc_rows = doc_query.all()
        login_metrics = self._compute_login_time_metrics(user_id)
        doc_name_map = {
            int(item.id): str(item.title or item.filename or f"Tai lieu {item.id}")
            for item in doc_rows
        }
        doc_subject_map = {
            int(item.id): str(getattr(getattr(item, "subject_obj", None), "name", None) or item.subject or "").strip()
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
                "date": self._to_iso(item.timestamp),
                "duration_seconds": int(item.duration_seconds or 0),
                "level": str(item.level_at_time or ""),
                "total_questions": int(item.total_questions or 0),
                "correct_count": int(item.correct_count or 0),
            }
            for item in history_rows
        ]
        document_scores = [
            {
                "document_id": int(item.document_id),
                "document_title": doc_name_map.get(int(item.document_id), f"Tai lieu {item.document_id}"),
                "subject": doc_subject_map.get(int(item.document_id), clean_subject),
                "score": float(item.score or 0.0),
                "test_type": str(item.test_type or ""),
                "tested_at": self._to_iso(item.tested_at),
                "total_questions": int(item.total_questions or 0),
                "correct_count": int(item.correct_count or 0),
            }
            for item in score_rows
        ]
        document_status = []
        overdue_documents = []
        completed_late_documents = []
        today = datetime.utcnow().date()
        for item in eval_rows:
            plan_item = latest_plan_by_doc.get(int(item.document_id))
            planned_date = plan_item.planned_date if plan_item and plan_item.planned_date else None
            deadline_date = plan_item.deadline_date if plan_item and plan_item.deadline_date else None
            last_test_at = item.last_test_at
            completed_on_time = bool(item.is_completed and deadline_date and last_test_at and last_test_at.date() <= deadline_date)
            completed_late = bool(item.is_completed and deadline_date and last_test_at and last_test_at.date() > deadline_date)
            pending_overdue = bool((not item.is_completed) and deadline_date and deadline_date < today)

            status_label = "đang học"
            if completed_on_time:
                status_label = "hoàn thành đúng hạn"
            elif completed_late:
                status_label = "hoàn thành trễ hạn"
            elif pending_overdue:
                status_label = "quá hạn chưa hoàn thành"
            elif item.is_completed:
                status_label = "đã hoàn thành"

            payload = {
                "document_id": int(item.document_id),
                "document_title": doc_name_map.get(int(item.document_id), f"Tai lieu {item.document_id}"),
                "subject": doc_subject_map.get(int(item.document_id), clean_subject),
                "latest_score": float(item.latest_score or 0.0),
                "attempts": int(item.attempts or 0),
                "is_completed": bool(item.is_completed),
                "last_test_at": self._to_iso(last_test_at),
                "planned_date": planned_date.isoformat() if planned_date else None,
                "deadline_date": deadline_date.isoformat() if deadline_date else None,
                "status": status_label,
                "is_pending_overdue": pending_overdue,
                "is_completed_late": completed_late,
            }
            document_status.append(payload)
            if pending_overdue:
                overdue_documents.append(payload)
            if completed_late:
                completed_late_documents.append(payload)

        subject_summary_map = defaultdict(lambda: {"scores": [], "attempts": 0, "best": 0.0, "latest": None})
        for item in recent_tests:
            subject_name = str(item.get("subject") or "Chưa rõ môn")
            subject_summary_map[subject_name]["scores"].append(float(item.get("score") or 0.0))
            subject_summary_map[subject_name]["attempts"] += 1
            subject_summary_map[subject_name]["best"] = max(
                float(subject_summary_map[subject_name]["best"] or 0.0),
                float(item.get("score") or 0.0),
            )
            if subject_summary_map[subject_name]["latest"] is None:
                subject_summary_map[subject_name]["latest"] = float(item.get("score") or 0.0)

        subject_summaries = []
        for subject_name, summary in subject_summary_map.items():
            scores = summary["scores"]
            avg_subject_score = round(sum(scores) / len(scores), 2) if scores else 0.0
            subject_summaries.append(
                {
                    "subject": subject_name,
                    "attempts": int(summary["attempts"] or 0),
                    "avg_score": avg_subject_score,
                    "best_score": round(float(summary["best"] or 0.0), 2),
                    "latest_score": round(float(summary["latest"] or 0.0), 2) if summary["latest"] is not None else None,
                }
            )
        subject_summaries.sort(key=lambda item: (float(item["avg_score"]), item["subject"]))

        weakest_subject = subject_summaries[0]["subject"] if subject_summaries else None
        overdue_count = len(overdue_documents)
        late_count = len(completed_late_documents)

        fallback = self._build_progress_fallback_reply(
            message=clean_message,
            subject=clean_subject,
            recent_tests=recent_tests,
            subject_summaries=subject_summaries,
            document_status=document_status,
            overdue_documents=overdue_documents,
            completed_late_documents=completed_late_documents,
            avg_score=avg_score,
            best_score=best_score,
        )

        try:
            prompt = f"""
Bạn là Evaluation Agent cho sinh viên.
Hãy trả lời bằng tiếng Việt, bám sát dữ liệu thật của người dùng, không dùng câu mẫu lặp lại.
Khi trả lời:
- Phải trả lời đúng trọng tâm câu hỏi của người dùng.
- Nếu người dùng hỏi điểm yếu, chỉ rõ môn yếu, tài liệu yếu hoặc các tài liệu bị trễ hạn.
- Nếu người dùng hỏi thành tích tổng quát, hãy nêu xu hướng, điểm trung bình, điểm tốt nhất, và điểm đáng lo.
- Nếu dữ liệu cho thấy học trễ hạn, phải nói rõ tài liệu nào trễ hoặc đã hoàn thành muộn.
- Nếu phù hợp, kết thúc bằng 1 đến 3 hành động cụ thể nên làm tiếp theo.
- Không bịa dữ liệu ngoài phần được cung cấp.

Người dùng đang hỏi: {clean_message}
Phạm vi môn đang chọn trên giao diện: {clean_subject or "Tất cả các môn"}
Thời điểm hiện tại: {datetime.utcnow().isoformat()}

Tóm tắt nhanh:
{json.dumps({
    "recent_test_count": len(recent_tests),
    "average_score": avg_score,
    "best_score": best_score,
    "weakest_subject": weakest_subject,
    "pending_overdue_documents": overdue_count,
    "completed_late_documents": late_count,
    "total_login_minutes": round(float(login_metrics.get("total_minutes", 0.0) or 0.0), 2),
    "login_session_count": int(login_metrics.get("session_count", 0) or 0),
}, ensure_ascii=False)}

Tổng hợp theo môn:
{json.dumps(subject_summaries, ensure_ascii=False)}

Lịch sử kiểm tra:
{json.dumps(recent_tests, ensure_ascii=False)}

Lịch sử điểm theo tài liệu:
{json.dumps(document_scores, ensure_ascii=False)}

Trạng thái tài liệu và kế hoạch:
{json.dumps(document_status, ensure_ascii=False)}
""".strip()
            if not self.client:
                return fallback
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý phân tích học tập chính xác, súc tích và bám dữ liệu."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=900,
            )
            reply = str(completion.choices[0].message.content or "").strip()
            lowered = reply.lower()
            if (
                not reply
                or "nếu bạn muốn" in lowered
                or "tôi có thể chỉ rõ" in lowered
                or ("bạn đã có" in lowered and "điểm trung bình" in lowered and len(reply) < 220)
            ):
                return fallback
            return reply
        except Exception as exc:
            print(f"❌ Evaluation Agent chat error: {exc}")
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
