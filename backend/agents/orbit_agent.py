from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from db import models


class OrbitAgent:
    def __init__(self, db: Session):
        self.db = db

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
        query = self.db.query(models.AssessmentHistory).filter(models.AssessmentHistory.user_id == user_id)
        if since is not None:
            query = query.filter(models.AssessmentHistory.timestamp >= since)
        return int(query.count())

    def _count_passed_lessons(self, user_id: int, since: Optional[datetime] = None) -> int:
        query = self.db.query(models.AssessmentHistory).filter(
            models.AssessmentHistory.user_id == user_id,
            models.AssessmentHistory.test_type.in_(["chapter", "session"]),
            models.AssessmentHistory.score >= 60,
        )
        if since is not None:
            query = query.filter(models.AssessmentHistory.timestamp >= since)
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

        last_test = self.db.query(models.AssessmentHistory).filter(
            models.AssessmentHistory.user_id == user_id
        ).order_by(models.AssessmentHistory.timestamp.desc()).first()
        if last_test:
            candidates.append(last_test.timestamp)

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

    def _discipline_judgement(self, stats: Dict[str, int], days_inactive: Optional[int]) -> str:
        if days_inactive is not None and days_inactive >= 7:
            return "Cảnh báo nghiêm trọng: bạn đã mất nhịp học hơn 1 tuần."
        if stats["week_tests"] == 0 and stats["week_lessons"] == 0:
            return "Đang học thiếu kỷ luật tuần này: chưa hoàn thành bài kiểm tra/chương nào."
        if stats["week_study"] < 60:
            return "Cường độ học tuần này thấp, cần tăng thời lượng học rõ rệt."
        if stats["week_study"] >= 180 and stats["week_tests"] >= 2:
            return "Tín hiệu rất tốt: bạn đang học đều và có kiểm tra định kỳ."
        return "Nhịp học ở mức tạm ổn, nhưng vẫn có thể tăng tốc thêm."

    def respond(
        self,
        user: models.User,
        subject_name: str,
        message: str,
        class_id: Optional[int] = None,
    ) -> str:
        now = datetime.utcnow()
        stats = self._build_stats(user.id)
        last_active = self._last_activity_at(user.id)
        days_inactive = None
        if last_active is not None:
            days_inactive = (now - last_active).days

        directives = self._get_active_directives(user.id, now)
        judgement = self._discipline_judgement(stats, days_inactive)

        msg_lower = (message or "").lower()
        asks_progress = any(token in msg_lower for token in ["bao nhiêu bài", "bao nhieu bai", "học bao lâu", "hoc bao lau", "bao nhiêu câu", "bao nhieu cau"]) 
        asks_plan = any(token in msg_lower for token in ["kế hoạch", "ke hoach", "nên học gì", "nen hoc gi", "quên học gì", "quen hoc gi"])

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

        praise_line = ""
        if stats["week_study"] >= 120 and stats["week_tests"] >= 1:
            praise_line = "Bạn có cải thiện trong tuần này, tôi ghi nhận nỗ lực đó. Tiếp tục giữ nhịp."

        if asks_progress:
            response = [
                f"Orbit Agent báo cáo học tập môn {subject_name} cho bạn:",
                f"- Tổng số bài/chương đã hoàn thành: {stats['total_lessons']} (tuần này: {stats['week_lessons']}, tháng này: {stats['month_lessons']})",
                f"- Thời gian học: tổng {stats['total_study']} phút, tuần này {stats['week_study']} phút, tháng này {stats['month_study']} phút",
                f"- Bài kiểm tra đã làm: tổng {stats['total_tests']}, tuần này {stats['week_tests']}, tháng này {stats['month_tests']}",
                f"- Tương tác với Orbit: tổng {stats['total_msgs']} câu hỏi, {stats['total_chat_sec'] // 60} phút chat; tuần này {stats['week_msgs']} câu, {stats['week_chat_sec'] // 60} phút",
                f"- Đánh giá kỷ luật học tập: {judgement}",
            ]
            if days_inactive is not None and days_inactive >= 7:
                response.append(f"- Cảnh báo: bạn đã {days_inactive} ngày chưa có hoạt động học tập đáng kể.")
            if directive_lines:
                response.append("- Chỉ tiêu giảng viên giao tuần này:")
                response.extend(directive_lines)
            if praise_line:
                response.append(f"- {praise_line}")
            return "\n".join(response)

        if asks_plan:
            plan = [
                "Kế hoạch học tập tôi giao cho bạn (Orbit - chế độ nghiêm):",
                "- Mỗi ngày tối thiểu 30 phút đọc lại bài + 15 phút luyện câu hỏi.",
                "- Tuần này hoàn thành ít nhất 2 phiên học có kiểm tra cuối buổi.",
                "- Mỗi phiên học phải có ghi chú 3 ý chính bạn đã nắm được.",
                "- Nếu làm sai >40% câu hỏi, bắt buộc học lại phần sai trong ngày.",
                f"- Đánh giá hiện tại của bạn: {judgement}",
            ]
            if days_inactive is not None and days_inactive >= 7:
                plan.append("- Bạn đã bỏ học quá lâu. Ưu tiên hôm nay: vào học ngay 1 chương và làm 1 bài test.")
            if directive_lines:
                plan.append("- Mục tiêu bắt buộc từ giảng viên:")
                plan.extend(directive_lines)
            if praise_line:
                plan.append(f"- {praise_line}")
            return "\n".join(plan)

        base = [
            f"Orbit đang theo dõi tiến độ môn {subject_name} của bạn.",
            f"- Tuần này bạn đã học {stats['week_study']} phút, làm {stats['week_tests']} bài kiểm tra, hoàn thành {stats['week_lessons']} bài/chương.",
            f"- Nhận xét: {judgement}",
            "Bạn có thể hỏi tôi: 'Tôi đã học bao nhiêu bài?', 'Tôi có quên học gì không?', hoặc 'Lập kế hoạch học tuần này cho tôi'.",
        ]
        if days_inactive is not None and days_inactive >= 7:
            base.append("Cảnh báo: hơn 1 tuần bạn chưa học đều. Tôi yêu cầu bạn bắt đầu lại ngay hôm nay.")
        if directive_lines:
            base.append("Yêu cầu tuần này từ giảng viên:")
            base.extend(directive_lines)
        if praise_line:
            base.append(praise_line)
        return "\n".join(base)
