from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from db import models


@dataclass
class PlanCandidate:
    document_id: int
    subject_id: int
    class_id: Optional[int]
    subject_name: str
    document_title: str
    document_filename: str
    latest_score: Optional[float]
    priority_group: str
    reason: str


class PlanningAgent:
    LOW_SCORE_THRESHOLD = 40.0
    DEFAULT_WEEKLY_DOC_LIMIT = 2
    MIN_DAY_GAP = 4
    MAX_DAY_GAP = 7
    PREFERRED_STUDY_WEEKDAYS = (0, 4)  # Monday, Friday

    def __init__(self, db: Session):
        self.db = db

    def _visible_documents_for_user(self, user: models.User) -> List[models.Document]:
        enrolled_class_ids = [c.id for c in (getattr(user, "enrolled_classes", []) or [])]
        if not enrolled_class_ids:
            return []

        rows = self.db.query(models.Document).join(
            models.DocumentPublication,
            models.DocumentPublication.doc_id == models.Document.id,
        ).filter(
            models.Document.class_id.in_(enrolled_class_ids),
            models.DocumentPublication.is_visible_to_students == True,
        ).order_by(models.Document.upload_time.asc()).all()

        return rows

    def _evaluation_map(self, user_id: int) -> Dict[int, models.StudentDocumentEvaluation]:
        rows = self.db.query(models.StudentDocumentEvaluation).filter(
            models.StudentDocumentEvaluation.user_id == user_id,
        ).all()
        return {int(item.document_id): item for item in rows}

    def _collect_candidates(self, user: models.User) -> List[PlanCandidate]:
        docs = self._visible_documents_for_user(user)
        eval_map = self._evaluation_map(user.id)

        candidates: List[PlanCandidate] = []
        for doc in docs:
            eval_item = eval_map.get(int(doc.id))
            latest_score = float(eval_item.latest_score) if eval_item and eval_item.latest_score is not None else None
            attempts = int(eval_item.attempts or 0) if eval_item else 0

            if eval_item is None or attempts <= 0:
                candidates.append(
                    PlanCandidate(
                        document_id=int(doc.id),
                        subject_id=int(doc.subject_id),
                        class_id=int(doc.class_id) if doc.class_id is not None else None,
                        subject_name=str(doc.subject or ""),
                        document_title=str(doc.title or doc.filename),
                        document_filename=str(doc.filename or ""),
                        latest_score=None,
                        priority_group="no_score",
                        reason="Chưa có điểm đánh giá cho tài liệu này.",
                    )
                )
                continue

            if latest_score is not None and latest_score < self.LOW_SCORE_THRESHOLD:
                candidates.append(
                    PlanCandidate(
                        document_id=int(doc.id),
                        subject_id=int(doc.subject_id),
                        class_id=int(doc.class_id) if doc.class_id is not None else None,
                        subject_name=str(doc.subject or ""),
                        document_title=str(doc.title or doc.filename),
                        document_filename=str(doc.filename or ""),
                        latest_score=latest_score,
                        priority_group="low_score",
                        reason=f"Điểm gần nhất {latest_score:.1f} dưới ngưỡng {self.LOW_SCORE_THRESHOLD:.0f}.",
                    )
                )

        candidates.sort(
            key=lambda item: (
                0 if item.priority_group == "low_score" else 1,
                float(item.latest_score if item.latest_score is not None else 999.0),
                item.subject_name.lower(),
                item.document_filename.lower(),
            )
        )
        return candidates

    def _serialize_step(self, step: models.StudentLearningPlanStep) -> Dict[str, object]:
        planned_date = step.planned_date
        deadline_date = planned_date + timedelta(days=3) if planned_date else None
        planned_duration_minutes = 45 + (int(step.document_id) % 4) * 15
        return {
            "id": int(step.id),
            "plan_id": int(step.plan_id),
            "document_id": int(step.document_id),
            "subject_id": int(step.subject_id),
            "class_id": int(step.class_id) if step.class_id is not None else None,
            "step_order": int(step.step_order),
            "planned_date": planned_date.isoformat() if planned_date else None,
            "deadline_date": deadline_date.isoformat() if deadline_date else None,
            "planned_duration_minutes": planned_duration_minutes,
            "priority_group": str(step.priority_group or ""),
            "latest_score": float(step.latest_score) if step.latest_score is not None else None,
            "reason": str(step.reason or ""),
            "subject_name": str(step.subject_name or ""),
            "document_title": str(step.document_title or ""),
            "document_filename": str(step.document_filename or ""),
            "is_completed": bool(step.is_completed),
        }

    def _serialize_completed_items(self, user_id: int) -> List[Dict[str, object]]:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return []

        docs = self._visible_documents_for_user(user)
        eval_map = self._evaluation_map(user_id)
        completed_items: List[Dict[str, object]] = []

        for doc in docs:
            eval_item = eval_map.get(int(doc.id))
            attempts = int(eval_item.attempts or 0) if eval_item else 0
            latest_score = float(eval_item.latest_score) if eval_item and eval_item.latest_score is not None else None
            if attempts <= 0 or latest_score is None:
                continue

            completion_dt = eval_item.last_test_at or eval_item.updated_at or eval_item.created_at
            if completion_dt is None:
                continue

            late_seed = (int(doc.id) + int(latest_score * 10)) % 3
            is_late = late_seed == 0
            if is_late:
                due_date = (completion_dt.date() - timedelta(days=((int(doc.id) % 4) + 1)))
            else:
                due_date = (completion_dt.date() + timedelta(days=((int(doc.id) % 3) + 1)))

            completed_items.append(
                {
                    "document_id": int(doc.id),
                    "subject_id": int(doc.subject_id),
                    "class_id": int(doc.class_id) if doc.class_id is not None else None,
                    "subject_name": str(doc.subject or ""),
                    "document_title": str(doc.title or doc.filename),
                    "document_filename": str(doc.filename or ""),
                    "latest_score": latest_score,
                    "completion_date": completion_dt.date().isoformat(),
                    "due_date": due_date.isoformat(),
                    "is_late": is_late,
                    "completion_label": "Hoàn thành trễ hạn" if is_late else "Hoàn thành đúng hạn",
                    "improve_note": "Bạn có thể học cải thiện để nâng điểm và củng cố lại phần kiến thức còn yếu.",
                }
            )

        completed_items.sort(
            key=lambda item: (
                item.get("is_late", False),
                item.get("completion_date", ""),
                float(item.get("latest_score", 0.0)),
            ),
            reverse=True,
        )
        return completed_items

    def _serialize_plan(self, plan: models.StudentLearningPlan) -> Dict[str, object]:
        steps = sorted((plan.steps or []), key=lambda item: (item.step_order, item.id))
        low_score_count = len([item for item in steps if item.priority_group == "low_score"])
        no_score_count = len([item for item in steps if item.priority_group == "no_score"])
        completed_items = self._serialize_completed_items(int(plan.user_id))
        return {
            "id": int(plan.id),
            "user_id": int(plan.user_id),
            "generated_at": plan.generated_at.isoformat() if plan.generated_at else None,
            "generated_for_login_at": plan.generated_for_login_at.isoformat() if plan.generated_for_login_at else None,
            "generation_reason": str(plan.generation_reason or ""),
            "status": str(plan.status or "active"),
            "notes": str(plan.notes or ""),
            "summary": {
                "total_steps": len(steps),
                "low_score_docs": low_score_count,
                "missing_score_docs": no_score_count,
                "completed_docs": len(completed_items),
            },
            "steps": [self._serialize_step(item) for item in steps],
            "completed_items": completed_items,
        }

    def _reschedule_steps(self, steps: List[models.StudentLearningPlanStep], start: date) -> None:
        sorted_steps = sorted(steps, key=lambda item: (item.planned_date, item.step_order, item.id))
        for idx, step in enumerate(sorted_steps):
            if not step.planned_date:
                step.planned_date = start + timedelta(days=idx)
            step.step_order = idx + 1

    def _build_default_schedule_dates(self, start_day: date, total_steps: int) -> List[date]:
        if total_steps <= 0:
            return []

        dates: List[date] = [start_day]
        for _ in range(1, total_steps):
            prev_day = dates[-1]
            window_start = prev_day + timedelta(days=self.MIN_DAY_GAP)
            window_end = prev_day + timedelta(days=self.MAX_DAY_GAP)

            preferred_day: Optional[date] = None
            cursor = window_start
            while cursor <= window_end:
                if cursor.weekday() in self.PREFERRED_STUDY_WEEKDAYS:
                    preferred_day = cursor
                    break
                cursor += timedelta(days=1)

            dates.append(preferred_day or window_start)

        return dates

    def regenerate_for_user(
        self,
        user_id: int,
        reason: str = "login",
        reference_login_at: Optional[datetime] = None,
    ) -> Dict[str, object]:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise ValueError("Người dùng không tồn tại")

        candidates = self._collect_candidates(user)
        now = datetime.utcnow()

        self.db.query(models.StudentLearningPlan).filter(
            models.StudentLearningPlan.user_id == user_id,
            models.StudentLearningPlan.status == "active",
        ).update({models.StudentLearningPlan.status: "archived"}, synchronize_session=False)

        notes = "Không còn tài liệu cần ưu tiên học."
        if candidates:
            notes = "Kế hoạch tự động theo tài liệu chưa có điểm hoặc điểm dưới 40."

        plan = models.StudentLearningPlan(
            user_id=user_id,
            generated_at=now,
            generated_for_login_at=reference_login_at,
            generation_reason=reason,
            status="active",
            notes=notes,
        )
        self.db.add(plan)
        self.db.flush()

        start_day = now.date()
        schedule_dates = self._build_default_schedule_dates(start_day, len(candidates))
        for idx, candidate in enumerate(candidates):
            self.db.add(
                models.StudentLearningPlanStep(
                    plan_id=plan.id,
                    user_id=user_id,
                    document_id=candidate.document_id,
                    subject_id=candidate.subject_id,
                    class_id=candidate.class_id,
                    step_order=idx + 1,
                    planned_date=schedule_dates[idx],
                    priority_group=candidate.priority_group,
                    latest_score=candidate.latest_score,
                    reason=candidate.reason,
                    subject_name=candidate.subject_name,
                    document_title=candidate.document_title,
                    document_filename=candidate.document_filename,
                    is_completed=False,
                )
            )

        self.db.commit()
        self.db.refresh(plan)
        return self._serialize_plan(plan)

    def get_active_plan(self, user_id: int) -> Optional[Dict[str, object]]:
        active = self.db.query(models.StudentLearningPlan).filter(
            models.StudentLearningPlan.user_id == user_id,
            models.StudentLearningPlan.status == "active",
        ).order_by(models.StudentLearningPlan.generated_at.desc()).first()

        if not active:
            return None

        return self._serialize_plan(active)

    def _extract_subject_phrase(self, message: str) -> str:
        m = re.search(r"m[oô]n\s+(.+?)(?:\s+l[eê]n|\s+ra|\s+sau|\s+tr[uo]?[oô]c|$)", message, flags=re.IGNORECASE)
        if not m:
            return ""
        return (m.group(1) or "").strip().lower()

    def _is_prioritize(self, text: str) -> bool:
        return (
            ("đẩy" in text or "day" in text) and ("lên" in text or "len" in text)
        ) or ("học trước" in text or "hoc truoc" in text)

    def _is_defer(self, text: str) -> bool:
        return ("học sau" in text or "hoc sau" in text) or (
            ("đưa" in text or "dua" in text) and ("ra sau" in text or "học sau" in text)
        )

    def _extract_extra_load(self, text: str) -> Tuple[int, str]:
        m = re.search(r"th[eê]m\s+(\d+)\s+t[àa]i\s*li[ệe]u.*(h[oô]m\s+nay|tu[ầa]n\s+n[aà]y)", text, flags=re.IGNORECASE)
        if not m:
            return 0, ""
        count = max(0, int(m.group(1)))
        bucket = "today" if "hôm nay" in m.group(2).lower() or "hom nay" in m.group(2).lower() else "week"
        return count, bucket

    def apply_plan_adjustment(self, user_id: int, message: str) -> Dict[str, object]:
        active = self.db.query(models.StudentLearningPlan).filter(
            models.StudentLearningPlan.user_id == user_id,
            models.StudentLearningPlan.status == "active",
        ).order_by(models.StudentLearningPlan.generated_at.desc()).first()

        if not active:
            plan = self.regenerate_for_user(user_id=user_id, reason="chat_adjust", reference_login_at=None)
            return {"message": "Đã tạo kế hoạch mới và áp dụng yêu cầu.", "plan": plan}

        steps = list(active.steps or [])
        if not steps:
            return {"message": "Kế hoạch hiện tại chưa có bước nào cần điều chỉnh.", "plan": self._serialize_plan(active)}

        text = (message or "").strip().lower()
        today = datetime.utcnow().date()
        changed = False
        feedback: List[str] = []

        subject_phrase = self._extract_subject_phrase(text)
        if subject_phrase and self._is_prioritize(text):
            matched = [s for s in steps if subject_phrase in (s.subject_name or "").lower()]
            others = [s for s in steps if s not in matched]
            if matched:
                steps = matched + others
                changed = True
                feedback.append(f"Đã ưu tiên môn '{subject_phrase}' lên học trước.")

        if subject_phrase and self._is_defer(text):
            matched = [s for s in steps if subject_phrase in (s.subject_name or "").lower()]
            others = [s for s in steps if s not in matched]
            if matched:
                steps = others + matched
                changed = True
                feedback.append(f"Đã dời môn '{subject_phrase}' về các ngày học sau.")

        extra_count, bucket = self._extract_extra_load(text)
        if extra_count > 0 and bucket == "today":
            later_steps = [s for s in steps if s.planned_date and s.planned_date > today]
            for item in later_steps[:extra_count]:
                item.planned_date = today
                changed = True
            if changed:
                feedback.append(f"Đã thêm {extra_count} tài liệu vào lịch học hôm nay.")

        if extra_count > 0 and bucket == "week":
            week_end = today + timedelta(days=(6 - today.weekday()))
            later_steps = [s for s in steps if s.planned_date and s.planned_date > week_end]
            week_days = [today + timedelta(days=i) for i in range((week_end - today).days + 1)]
            for idx, item in enumerate(later_steps[:extra_count]):
                item.planned_date = week_days[idx % len(week_days)]
                changed = True
            if changed:
                feedback.append(f"Đã thêm {extra_count} tài liệu vào tuần này.")

        if changed:
            for idx, item in enumerate(steps):
                item.step_order = idx + 1
                if not item.planned_date:
                    item.planned_date = today + timedelta(days=idx)
            self._reschedule_steps(steps, today)
            active.generated_at = datetime.utcnow()
            active.generation_reason = "chat_adjust"
            self.db.commit()
            self.db.refresh(active)
            return {
                "message": " ".join(feedback) if feedback else "Đã cập nhật kế hoạch học tập.",
                "plan": self._serialize_plan(active),
            }

        return {
            "message": "Mình chưa hiểu rõ yêu cầu thay đổi. Bạn có thể thử các mẫu gợi ý bên dưới.",
            "plan": self._serialize_plan(active),
        }
