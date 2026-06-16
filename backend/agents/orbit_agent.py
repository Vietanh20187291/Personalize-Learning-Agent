"""
Orbit Agent — LLM-powered personalized coaching.

Thay vì trả lời bằng template string (if/else), Orbit sử dụng LLM
để coaching cá nhân hóa dựa trên hồ sơ học sinh thực tế.
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy.orm import Session

from db import models

load_dotenv()


class OrbitAgent:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = self._resolve_groq_api_key()
        self.model = "llama-3.3-70b-versatile"
        self.request_timeout_seconds = 18.0

        if self.api_key and not any(t in self.api_key.lower() for t in ("dummy", "testing", "placeholder")):
            try:
                self.client = Groq(api_key=self.api_key, timeout=self.request_timeout_seconds)
            except TypeError:
                self.client = Groq(api_key=self.api_key)
        else:
            self.client = None

    def _resolve_groq_api_key(self) -> str:
        for env_name in ["GROQ_KEY_ORBIT", "GROQ_KEY_ADAPTIVE", "GROQ_API_KEY", "GROQ_KEY_DEBUG"]:
            value = (os.getenv(env_name) or "").strip()
            if value and not any(t in value.lower() for t in ("dummy", "testing", "placeholder")):
                return value
        return (os.getenv("GROQ_KEY_ORBIT") or "").strip()

    # ==========================================
    # DATA HELPERS
    # ==========================================
    def _week_bounds(self, now: datetime) -> Tuple[datetime, datetime]:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end

    def _month_start(self, now: datetime) -> datetime:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _sum_study_minutes(self, user_id: int, since: Optional[datetime] = None) -> int:
        query = self.db.query(models.StudySession).filter(models.StudySession.user_id == user_id)
        if since is not None:
            query = query.filter(models.StudySession.start_time >= since)
        return int(sum(int(item.duration_minutes or 0) for item in query.all()))

    def _count_tests(self, user_id: int, since: Optional[datetime] = None) -> int:
        query = self.db.query(models.StudentDocumentScoreHistory).filter(
            models.StudentDocumentScoreHistory.user_id == user_id,
            models.StudentDocumentScoreHistory.test_type != "baseline",
        )
        if since is not None:
            query = query.filter(models.StudentDocumentScoreHistory.tested_at >= since)
        return int(query.count())

    def _count_passed_lessons(self, user_id: int, since: Optional[datetime] = None) -> int:
        query = self.db.query(models.StudentDocumentEvaluation).filter(
            models.StudentDocumentEvaluation.user_id == user_id,
            models.StudentDocumentEvaluation.is_completed == True,
        )
        if since is not None:
            attempts = self.db.query(models.StudentDocumentScoreHistory).filter(
                models.StudentDocumentScoreHistory.user_id == user_id,
                models.StudentDocumentScoreHistory.score >= 60,
                models.StudentDocumentScoreHistory.test_type != "baseline",
                models.StudentDocumentScoreHistory.tested_at >= since,
            ).all()
            return int(len({item.document_id for item in attempts}))
        return int(query.count())

    def _agent_chat_stats(self, user_id: int, since: Optional[datetime] = None) -> Tuple[int, int]:
        msg_query = self.db.query(models.OrbitChatMessage).filter(
            models.OrbitChatMessage.user_id == user_id,
            models.OrbitChatMessage.role == "user",
        )
        session_query = self.db.query(models.OrbitChatSession).filter(models.OrbitChatSession.user_id == user_id)
        if since is not None:
            msg_query = msg_query.filter(models.OrbitChatMessage.created_at >= since)
            session_query = session_query.filter(models.OrbitChatSession.started_at >= since)

        msg_count = int(msg_query.count())
        sessions = session_query.all()
        total_seconds = 0
        for item in sessions:
            if item.started_at and item.ended_at and item.ended_at >= item.started_at:
                total_seconds += int((item.ended_at - item.started_at).total_seconds())

        return msg_count, total_seconds

    def _last_activity_at(self, user_id: int) -> Optional[datetime]:
        candidates: List[Optional[datetime]] = []

        last_study = self.db.query(models.StudySession).filter(
            models.StudySession.user_id == user_id
        ).order_by(models.StudySession.start_time.desc()).first()
        if last_study:
            candidates.append(last_study.start_time)

        last_test = self.db.query(models.StudentDocumentScoreHistory).filter(
            models.StudentDocumentScoreHistory.user_id == user_id,
            models.StudentDocumentScoreHistory.test_type != "baseline",
        ).order_by(models.StudentDocumentScoreHistory.tested_at.desc()).first()
        if last_test:
            candidates.append(last_test.tested_at)

        last_chat = self.db.query(models.OrbitChatMessage).filter(
            models.OrbitChatMessage.user_id == user_id,
            models.OrbitChatMessage.role == "user",
        ).order_by(models.OrbitChatMessage.created_at.desc()).first()
        if last_chat:
            candidates.append(last_chat.created_at)

        valid = [item for item in candidates if item is not None]
        return max(valid) if valid else None

    def _get_active_directives(self, user_id: int, now: datetime) -> List[models.OrbitCoachDirective]:
        return self.db.query(models.OrbitCoachDirective).filter(
            models.OrbitCoachDirective.student_id == user_id,
            models.OrbitCoachDirective.is_active == True,
            models.OrbitCoachDirective.week_start <= now,
            models.OrbitCoachDirective.week_end >= now,
        ).order_by(models.OrbitCoachDirective.created_at.desc()).all()

    def _build_stats(self, user_id: int) -> Dict[str, int]:
        now = datetime.utcnow()
        week_start, _ = self._week_bounds(now)
        month_start = self._month_start(now)

        total_study = self._sum_study_minutes(user_id)
        week_study = self._sum_study_minutes(user_id, week_start)
        month_study = self._sum_study_minutes(user_id, month_start)

        total_tests = self._count_tests(user_id)
        week_tests = self._count_tests(user_id, week_start)
        month_tests = self._count_tests(user_id, month_start)

        total_lessons = self._count_passed_lessons(user_id)
        week_lessons = self._count_passed_lessons(user_id, week_start)
        month_lessons = self._count_passed_lessons(user_id, month_start)

        total_msgs, total_chat_sec = self._agent_chat_stats(user_id)
        week_msgs, week_chat_sec = self._agent_chat_stats(user_id, week_start)
        month_msgs, month_chat_sec = self._agent_chat_stats(user_id, month_start)

        return {
            "total_study": total_study,
            "week_study": week_study,
            "month_study": month_study,
            "total_tests": total_tests,
            "week_tests": week_tests,
            "month_tests": month_tests,
            "total_lessons": total_lessons,
            "week_lessons": week_lessons,
            "month_lessons": month_lessons,
            "total_msgs": total_msgs,
            "week_msgs": week_msgs,
            "month_msgs": month_msgs,
            "total_chat_sec": total_chat_sec,
            "week_chat_sec": week_chat_sec,
            "month_chat_sec": month_chat_sec,
        }

    def _build_weak_topics_summary(self, user_id: int, subject_name: str) -> str:
        """Lấy tóm tắt điểm yếu cho context LLM."""
        parts: List[str] = []

        subject = self.db.query(models.Subject).filter(models.Subject.name.ilike(subject_name)).first()
        if not subject:
            return ""
        subject_id = subject.id

        # Điểm yếu — tài liệu điểm thấp
        weak_docs = self.db.query(models.StudentDocumentEvaluation).filter(
            models.StudentDocumentEvaluation.user_id == user_id,
            models.StudentDocumentEvaluation.subject_id == subject_id,
            models.StudentDocumentEvaluation.latest_score < 50,
        ).order_by(models.StudentDocumentEvaluation.latest_score.asc()).limit(5).all()

        if weak_docs:
            names = []
            for ev in weak_docs:
                doc = self.db.query(models.Document).filter(models.Document.id == ev.document_id).first()
                name = (doc.title or doc.filename or f"Tài liệu {ev.document_id}").strip()
                names.append(f"{name} (điểm {ev.latest_score:.0f})")
            parts.append(f"Các phần đang yếu: {', '.join(names)}")

        # Câu sai gần đây
        recent_wrongs = self.db.query(models.WrongAnswerRecord).filter(
            models.WrongAnswerRecord.user_id == user_id,
            models.WrongAnswerRecord.subject_id == subject_id,
        ).order_by(models.WrongAnswerRecord.created_at.desc()).limit(5).all()

        if recent_wrongs:
            wrong_items = []
            for w in recent_wrongs[:3]:
                snippet = (w.question_text or "")[:60]
                if snippet:
                    wrong_items.append(f'"{snippet}" (chọn {w.student_choice}, đúng {w.correct_answer})')
            if wrong_items:
                parts.append(f"Hay sai các câu: {'; '.join(wrong_items)}")

        return "\n".join(parts)

    # ==========================================
    # LLM-POWERED RESPONSE
    # ==========================================
    def respond(
        self,
        user: models.User,
        subject_name: str,
        message: str,
        class_id: Optional[int] = None,
    ) -> str:
        """
        Orbit Agent — LLM-powered personalized coaching.
        Thay vì template if/else, dùng LLM với context cá nhân hóa.
        """
        now = datetime.utcnow()
        stats = self._build_stats(user.id)
        last_active = self._last_activity_at(user.id)
        days_inactive = None
        if last_active is not None:
            days_inactive = (now - last_active).days

        directives = self._get_active_directives(user.id, now)
        weak_summary = self._build_weak_topics_summary(user.id, subject_name)

        # Fallback nếu không có LLM
        if not self.client:
            return self._fallback_respond(subject_name, stats, days_inactive, directives)

        # Build system prompt cá nhân hóa
        student_name = (user.full_name or user.username or "bạn").strip()

        directive_lines: List[str] = []
        for item in directives:
            parts = []
            if int(item.target_tests or 0) > 0:
                parts.append(f"{int(item.target_tests)} bài kiểm tra")
            if int(item.target_chapters or 0) > 0:
                parts.append(f"{int(item.target_chapters)} chương")
            goal = " và ".join(parts) if parts else "mục tiêu học tập"
            note = f"; ghi chú: {item.note}" if item.note else ""
            directive_lines.append(f"- Chỉ tiêu tuần từ giảng viên: {goal}{note}")

        discipline = ""
        if days_inactive is not None and days_inactive >= 7:
            discipline = f"⚠️ NGHỈ QUÁ LÂU: đã {days_inactive} ngày không học. Phải cực kỳ nghiêm khắc, yêu cầu học NGAY."
        elif stats["week_tests"] == 0 and stats["week_lessons"] == 0:
            discipline = "TUẦN NÀY CHƯA CÓ HOẠT ĐỘNG: nhắc nhở nghiêm túc."
        elif stats["week_study"] < 60:
            discipline = "CƯỜNG ĐỘ HỌC THẤP: khuyên tăng thời lượng rõ rệt."
        elif stats["week_study"] >= 180 and stats["week_tests"] >= 2:
            discipline = "TÍN HIỆU TỐT: khen ngợi, khuyến khích giữ nhịp."

        system_prompt = f"""Bạn là Orbit — AI học tập cá nhân (coach) cho sinh viên {student_name}.

### THÔNG TIN HỌC SINH:
- Tên: {student_name}
- Môn đang theo dõi: {subject_name}
- Tổng đã học: {stats['total_study']} phút, {stats['total_lessons']} bài/chương đạt, {stats['total_tests']} bài kiểm tra
- Tuần này: {stats['week_study']} phút, {stats['week_tests']} bài kiểm tra, {stats['week_lessons']} bài đạt
- Tháng này: {stats['month_study']} phút, {stats['month_tests']} bài kiểm tra
- Tương tác Orbit: {stats['total_msgs']} câu hỏi, {stats['total_chat_sec'] // 60} phút chat
- Số ngày không hoạt động: {days_inactive or 0}
{"- " + weak_summary if weak_summary else ""}
{"- " + discipline if discipline else ""}

{"### CHỈ TIÊU TUẦN TỪ GIẢNG VIÊN:" + chr(10) + chr(10).join(directive_lines) if directive_lines else ""}

### NHIỆM VỤ:
- Bạn là COACH, không phải chatbot. Phản hồi phải mang tính cá nhân, như một người hướng dẫn tận tâm.
- Gọi tên học sinh ({student_name}) ít nhất 1 lần để tạo cảm giác cá nhân hóa.
- Phân tích dữ liệu, đưa ra nhận xét CỤ THỂ (không nói chung chung).
- Nếu học sinh yếu phần gì → đề xuất ôn lại phần đó, không chỉ nói "ôn thêm".
- Nếu học sinh tốt → khen ngợi và đề xuất thử thách nâng cao.
- Nếu nghỉ lâu → nghiêm khắc nhưng động viên, đưa ra kế hoạch cụ thể cho hôm nay.
- Đề xuất cụ thể: "ôm lại chương X", "làm thêm 2 bài kiểm tra về Y".
- Trả lời bằng tiếng Việt, ngắn gọn (3-8 câu), thân thiện nhưng thẳng thắn.
- KHÔNG lặp lại toàn bộ số liệu — chọn số liệu quan trọng nhất để nói.
"""

        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                model=self.model,
                temperature=0.5,
                max_tokens=800,
            )
            response_text = str(completion.choices[0].message.content or "").strip()
            return response_text or self._fallback_respond(subject_name, stats, days_inactive, directives)
        except Exception as exc:
            print(f"⚠️ Orbit LLM fallback: {exc}")
            return self._fallback_respond(subject_name, stats, days_inactive, directives)

    def _fallback_respond(self, subject_name: str, stats: Dict[str, int], days_inactive, directives) -> str:
        """Fallback khi LLM không khả dụng — trả về template cơ bản."""
        parts = [
            f"Orbit đang theo dõi tiến độ môn {subject_name}.",
            f"- Tuần này: {stats['week_study']} phút học, {stats['week_tests']} bài kiểm tra, {stats['week_lessons']} bài đạt.",
        ]
        if days_inactive is not None and days_inactive >= 7:
            parts.append(f"- ⚠️ Bạn đã {days_inactive} ngày chưa hoạt động. Cần vào học ngay.")
        if stats["week_study"] < 60:
            parts.append("- Cường độ học tuần này thấp. Hãy cố gắng học thêm.")
        return "\n".join(parts)
