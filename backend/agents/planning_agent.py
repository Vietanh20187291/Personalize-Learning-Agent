from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import models

load_dotenv()


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
    MIN_DAY_GAP = 4
    MAX_DAY_GAP = 7
    PREFERRED_STUDY_WEEKDAYS = (0, 4)  # Monday, Friday

    def __init__(self, db: Session):
        self.db = db
        self.api_key = self._resolve_groq_api_key()
        self.model = "llama-3.3-70b-versatile"
        self.client = Groq(api_key=self.api_key) if self.api_key else None

    def _resolve_groq_api_key(self) -> str:
        candidate_names = [
            "GROQ_KEY_PLANNING",
            "GROQ_API_KEY",
            "GROQ_KEY_ADAPTIVE",
            "GROQ_KEY_EVALUATION",
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

    def _priority_rank(self, value: str) -> int:
        normalized = str(value or "").lower()
        if normalized == "no_score":
            return 0
        if normalized == "low_score":
            return 1
        if normalized == "incomplete":
            return 2
        return 3

    def _default_deadline_date(self, planned_date: Optional[date], priority_group: str = "") -> Optional[date]:
        if not planned_date:
            return None
        extra_days = 4 if str(priority_group or "").lower() == "low_score" else 3
        return planned_date + timedelta(days=extra_days)

    def _visible_documents_for_user(self, user: models.User) -> List[models.Document]:
        enrolled_class_ids = [c.id for c in (getattr(user, "enrolled_classes", []) or [])]
        if not enrolled_class_ids:
            return []

        rows = (
            self.db.query(models.Document)
            .join(
                models.DocumentPublication,
                models.DocumentPublication.doc_id == models.Document.id,
            )
            .filter(
                models.Document.class_id.in_(enrolled_class_ids),
                models.DocumentPublication.is_visible_to_students == True,
            )
            .order_by(models.Document.upload_time.asc(), models.Document.id.asc())
            .all()
        )
        return rows

    def _evaluation_map(self, user_id: int) -> Dict[int, models.StudentDocumentEvaluation]:
        rows = (
            self.db.query(models.StudentDocumentEvaluation)
            .filter(models.StudentDocumentEvaluation.user_id == user_id)
            .all()
        )
        return {int(item.document_id): item for item in rows}

    def _collect_candidates(self, user: models.User) -> List[PlanCandidate]:
        docs = self._visible_documents_for_user(user)
        eval_map = self._evaluation_map(user.id)
        candidates: List[PlanCandidate] = []

        for doc in docs:
            eval_item = eval_map.get(int(doc.id))
            latest_score = float(eval_item.latest_score) if eval_item and eval_item.latest_score is not None else None
            attempts = int(eval_item.attempts or 0) if eval_item else 0
            is_completed = bool(eval_item.is_completed) if eval_item else False

            base_payload = dict(
                document_id=int(doc.id),
                subject_id=int(doc.subject_id),
                class_id=int(doc.class_id) if doc.class_id is not None else None,
                subject_name=str(doc.subject or ""),
                document_title=str(doc.title or doc.filename or f"Tai lieu {doc.id}"),
                document_filename=str(doc.filename or ""),
                latest_score=latest_score,
            )

            if eval_item is None or attempts <= 0:
                candidates.append(
                    PlanCandidate(
                        **base_payload,
                        priority_group="no_score",
                        reason="Tai lieu nay chua co lan kiem tra nao.",
                    )
                )
                continue

            if latest_score is not None and latest_score < self.LOW_SCORE_THRESHOLD:
                candidates.append(
                    PlanCandidate(
                        **base_payload,
                        priority_group="low_score",
                        reason=f"Diem gan nhat {latest_score:.1f} duoi nguong {self.LOW_SCORE_THRESHOLD:.0f}.",
                    )
                )
                continue

            if not is_completed:
                candidates.append(
                    PlanCandidate(
                        **base_payload,
                        priority_group="incomplete",
                        reason="Tai lieu da hoc nhung chua hoan thanh.",
                    )
                )

        candidates.sort(
            key=lambda item: (
                self._priority_rank(item.priority_group),
                float(item.latest_score if item.latest_score is not None else 999.0),
                item.subject_name.lower(),
                item.document_filename.lower(),
            )
        )
        return candidates

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

    def _build_fallback_schedule_map(
        self,
        candidates: List[PlanCandidate],
        start_day: date,
    ) -> Dict[int, Dict[str, object]]:
        schedule_dates = self._build_default_schedule_dates(start_day, len(candidates))
        schedule_map: Dict[int, Dict[str, object]] = {}
        for idx, candidate in enumerate(candidates):
            planned_date = schedule_dates[idx] if idx < len(schedule_dates) else start_day + timedelta(days=idx)
            schedule_map[int(candidate.document_id)] = {
                "planned_date": planned_date,
                "deadline_date": self._default_deadline_date(planned_date, candidate.priority_group),
                "reason": candidate.reason,
            }
        return schedule_map

    def _extract_json_payload(self, raw_text: str):
        text = str(raw_text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    def _plan_schedule_with_ai(
        self,
        candidates: List[PlanCandidate],
        start_day: date,
    ) -> Dict[int, Dict[str, object]]:
        if not self.client or not candidates:
            return {}

        payload = [
            {
                "document_id": item.document_id,
                "subject_name": item.subject_name,
                "document_title": item.document_title,
                "latest_score": item.latest_score,
                "priority_group": item.priority_group,
                "reason": item.reason,
            }
            for item in candidates
        ]
        prompt = f"""
You are Planning Agent for a student learning system.
Today is {start_day.isoformat()}.

Create a study plan for the unfinished documents below.
Rules:
- Schedule only these document_id values.
- planned_date must be from today onward.
- Keep workload around 1 or 2 documents per calendar week.
- Prioritize no_score first, then low_score, then incomplete.
- deadline_date should usually be 3 to 5 days after planned_date.
- Return ONLY valid JSON as an array.

JSON shape:
[
  {{
    "document_id": 123,
    "planned_date": "YYYY-MM-DD",
    "deadline_date": "YYYY-MM-DD",
    "reason": "short vietnamese explanation"
  }}
]

Documents:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = self._extract_json_payload(completion.choices[0].message.content)
            if not isinstance(parsed, list):
                return {}

            allowed_ids = {int(item.document_id) for item in candidates}
            result: Dict[int, Dict[str, object]] = {}
            for row in parsed:
                if not isinstance(row, dict):
                    continue
                try:
                    doc_id = int(row.get("document_id"))
                except Exception:
                    continue
                if doc_id not in allowed_ids:
                    continue

                planned_raw = str(row.get("planned_date") or "").strip()
                deadline_raw = str(row.get("deadline_date") or "").strip()
                try:
                    planned_date = datetime.strptime(planned_raw, "%Y-%m-%d").date()
                except Exception:
                    continue
                try:
                    deadline_date = datetime.strptime(deadline_raw, "%Y-%m-%d").date() if deadline_raw else None
                except Exception:
                    deadline_date = None

                result[doc_id] = {
                    "planned_date": planned_date,
                    "deadline_date": deadline_date,
                    "reason": str(row.get("reason") or "").strip(),
                }
            return result
        except Exception:
            return {}

    def _serialize_step(self, step: models.StudentLearningPlanStep) -> Dict[str, object]:
        planned_date = step.planned_date
        deadline_date = step.deadline_date or self._default_deadline_date(planned_date, str(step.priority_group or ""))
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
        latest_step_by_doc: Dict[int, models.StudentLearningPlanStep] = {}
        step_rows = (
            self.db.query(models.StudentLearningPlanStep)
            .filter(models.StudentLearningPlanStep.user_id == user_id)
            .order_by(
                models.StudentLearningPlanStep.updated_at.desc(),
                models.StudentLearningPlanStep.created_at.desc(),
                models.StudentLearningPlanStep.id.desc(),
            )
            .all()
        )
        for row in step_rows:
            latest_step_by_doc.setdefault(int(row.document_id), row)

        completed_items: List[Dict[str, object]] = []
        for doc in docs:
            eval_item = eval_map.get(int(doc.id))
            attempts = int(eval_item.attempts or 0) if eval_item else 0
            latest_score = float(eval_item.latest_score) if eval_item and eval_item.latest_score is not None else None
            is_completed = bool(eval_item.is_completed) if eval_item else False
            if attempts <= 0 or latest_score is None or not is_completed:
                continue

            completion_dt = eval_item.last_test_at or eval_item.updated_at or eval_item.created_at
            if completion_dt is None:
                continue

            step = latest_step_by_doc.get(int(doc.id))
            due_date = step.deadline_date if step and step.deadline_date else (step.planned_date if step else None)
            if due_date is None:
                due_date = completion_dt.date()

            is_late = bool(due_date and completion_dt.date() > due_date)
            completed_items.append(
                {
                    "document_id": int(doc.id),
                    "subject_id": int(doc.subject_id),
                    "class_id": int(doc.class_id) if doc.class_id is not None else None,
                    "subject_name": str(doc.subject or ""),
                    "document_title": str(doc.title or doc.filename or f"Tai lieu {doc.id}"),
                    "document_filename": str(doc.filename or ""),
                    "latest_score": latest_score,
                    "completion_date": completion_dt.date().isoformat(),
                    "due_date": due_date.isoformat(),
                    "is_late": is_late,
                    "completion_label": "Hoan thanh tre han" if is_late else "Hoan thanh dung han",
                    "improve_note": "Mo lai tai lieu nay trong tab Gia su de on tap va cai thien diem so.",
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

    def regenerate_for_user(
        self,
        user_id: int,
        reason: str = "login",
        reference_login_at: Optional[datetime] = None,
    ) -> Dict[str, object]:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise ValueError("Nguoi dung khong ton tai")

        candidates = self._collect_candidates(user)
        now = datetime.utcnow()

        (
            self.db.query(models.StudentLearningPlan)
            .filter(
                models.StudentLearningPlan.user_id == user_id,
                models.StudentLearningPlan.status == "active",
            )
            .update({models.StudentLearningPlan.status: "archived"}, synchronize_session=False)
        )

        notes = "Khong con tai lieu can uu tien hoc."
        if candidates:
            notes = "Ke hoach duoc tao cho cac tai lieu chua hoan thanh, chua co diem hoac diem thap."

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
        schedule_map = self._build_fallback_schedule_map(candidates, start_day)
        ai_schedule_map = self._plan_schedule_with_ai(candidates, start_day)
        for doc_id, payload in ai_schedule_map.items():
            fallback = schedule_map.get(int(doc_id), {})
            fallback["planned_date"] = payload.get("planned_date") or fallback.get("planned_date")
            fallback["deadline_date"] = payload.get("deadline_date") or fallback.get("deadline_date")
            if payload.get("reason"):
                fallback["reason"] = payload.get("reason")
            schedule_map[int(doc_id)] = fallback

        ordered_candidates = sorted(
            candidates,
            key=lambda item: (
                schedule_map[int(item.document_id)]["planned_date"],
                self._priority_rank(item.priority_group),
                item.subject_name.lower(),
                item.document_filename.lower(),
            ),
        )

        for idx, candidate in enumerate(ordered_candidates, start=1):
            schedule_item = schedule_map[int(candidate.document_id)]
            planned_date = schedule_item["planned_date"]
            deadline_date = schedule_item.get("deadline_date") or self._default_deadline_date(planned_date, candidate.priority_group)
            self.db.add(
                models.StudentLearningPlanStep(
                    plan_id=plan.id,
                    user_id=user_id,
                    document_id=candidate.document_id,
                    subject_id=candidate.subject_id,
                    class_id=candidate.class_id,
                    step_order=idx,
                    planned_date=planned_date,
                    deadline_date=deadline_date,
                    priority_group=candidate.priority_group,
                    latest_score=candidate.latest_score,
                    reason=str(schedule_item.get("reason") or candidate.reason),
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
        active = (
            self.db.query(models.StudentLearningPlan)
            .filter(
                models.StudentLearningPlan.user_id == user_id,
                models.StudentLearningPlan.status == "active",
            )
            .order_by(models.StudentLearningPlan.generated_at.desc())
            .first()
        )
        if not active:
            return None
        return self._serialize_plan(active)

    # ------------------------------------------------------------------ #
    #  Áp dụng chỉ thị của giảng viên (Nova → Orbit → Planning)           #
    # ------------------------------------------------------------------ #
    def apply_directive_documents(
        self,
        user_id: int,
        document_ids: List[int],
        reason: str = "Giáo viên yêu cầu học thêm",
    ) -> Dict[str, object]:
        """
        Thêm các tài liệu (do giảng viên yêu cầu qua OrbitCoachDirective) vào plan
        hoạt động của sinh viên. Nếu chưa có plan → tạo mới. Bỏ qua tài liệu đã có
        trong plan (unique constraint plan_id + document_id).
        """
        if not document_ids:
            return {"added_count": 0, "skipped_count": 0}

        plan_row = (
            self.db.query(models.StudentLearningPlan)
            .filter(
                models.StudentLearningPlan.user_id == user_id,
                models.StudentLearningPlan.status == "active",
            )
            .order_by(models.StudentLearningPlan.generated_at.desc())
            .first()
        )
        # Nếu chưa có plan active → tạo plan rỗng rồi thêm tài liệu chỉ thị vào.
        if plan_row is None:
            now = datetime.utcnow()
            plan_row = models.StudentLearningPlan(
                user_id=user_id,
                generated_at=now,
                generated_for_login_at=None,
                generation_reason="teacher_directive",
                status="active",
                notes="Kế hoạch khởi tạo từ chỉ thị của giảng viên.",
            )
            self.db.add(plan_row)
            self.db.flush()

        existing_steps = (
            self.db.query(models.StudentLearningPlanStep)
            .filter(models.StudentLearningPlanStep.plan_id == plan_row.id)
            .all()
        )
        existing_by_doc = {int(step.document_id): step for step in existing_steps}
        existing_doc_ids = set(existing_by_doc.keys())
        max_order = (
            self.db.query(func.max(models.StudentLearningPlanStep.step_order))
            .filter(models.StudentLearningPlanStep.plan_id == plan_row.id)
            .scalar()
            or 0
        )

        docs = self.db.query(models.Document).filter(
            models.Document.id.in_(document_ids),
        ).all()
        docs_by_id = {int(d.id): d for d in docs}

        now = datetime.utcnow()
        today = now.date()
        end_of_week = today + timedelta(days=(6 - today.weekday()))  # Chủ nhật cùng tuần

        added = 0
        skipped = 0
        promoted = 0
        for doc_id in document_ids:
            doc = docs_by_id.get(int(doc_id))
            if doc is None:
                skipped += 1
                continue
            # Nếu document đã có trong plan → nâng ưu tiên lên teacher_directive + dời lên tuần này.
            if int(doc_id) in existing_doc_ids:
                step = existing_by_doc.get(int(doc_id))
                if step is not None and step.priority_group != "teacher_directive":
                    step.priority_group = "teacher_directive"
                    step.planned_date = today
                    step.deadline_date = end_of_week
                    step.reason = reason
                    promoted += 1
                continue
            max_order += 1
            self.db.add(
                models.StudentLearningPlanStep(
                    plan_id=plan_row.id,
                    user_id=user_id,
                    document_id=doc.id,
                    subject_id=doc.subject_id,
                    class_id=doc.class_id,
                    step_order=max_order,
                    planned_date=today,
                    deadline_date=end_of_week,
                    priority_group="teacher_directive",
                    latest_score=None,
                    reason=reason,
                    subject_name=None,
                    document_title=doc.title or doc.filename,
                    document_filename=doc.filename,
                    is_completed=False,
                )
            )
            existing_doc_ids.add(int(doc_id))
            added += 1

        self.db.commit()
        return {"added_count": added, "promoted_count": promoted, "skipped_count": skipped}

    def apply_pending_directives(self, user_id: int) -> Dict[str, object]:
        """
        Tự động áp dụng các OrbitCoachDirective chưa xử lý (applied_at IS NULL) của sinh viên
        có chứa target_documents_json. Trả về tổng số tài liệu đã thêm.
        """
        pending = (
            self.db.query(models.OrbitCoachDirective)
            .filter(
                models.OrbitCoachDirective.student_id == user_id,
                models.OrbitCoachDirective.is_active == True,
                models.OrbitCoachDirective.applied_at.is_(None),
            )
            .all()
        )
        total_added = 0
        total_directives = 0
        for directive in pending:
            doc_ids = list(directive.target_documents_json or [])
            if not doc_ids:
                continue
            total_directives += 1
            result = self.apply_directive_documents(
                user_id=user_id,
                document_ids=doc_ids,
                reason="Giáo viên yêu cầu học thêm (chỉ thị tuần)",
            )
            total_added += int(result.get("added_count") or 0) + int(result.get("promoted_count") or 0)
            directive.applied_at = datetime.utcnow()
        if total_directives:
            self.db.commit()
        return {"directives_applied": total_directives, "documents_added": total_added}

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text or "")
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", ascii_text).strip().lower()

    def _extract_subject_phrase(self, message: str) -> str:
        normalized = self._normalize_text(message)
        patterns = [
            r"\bmon\s+(.+?)(?:\s+len\s+hoc\s+truoc|\s+hoc\s+truoc|\s+ra\s+sau|\s+hoc\s+sau|$)",
            r"\bday\s+(.+?)\s+len\s+hoc\s+truoc",
            r"\buu\s+tien\s+(.+?)(?:\s+trong|\s+truoc|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return (match.group(1) or "").strip().lower()
        return ""

    def _is_prioritize(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return (("day" in normalized) and ("len" in normalized)) or ("hoc truoc" in normalized) or ("uu tien" in normalized)

    def _is_defer(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return ("hoc sau" in normalized) or (("dua" in normalized) and ("ra sau" in normalized or "hoc sau" in normalized))

    def _extract_extra_load(self, text: str) -> Tuple[int, str]:
        normalized = self._normalize_text(text)
        match = re.search(
            r"them\s+(\d+)\s+(?:tai\s*lieu|bai\s+hoc|bai).*(hom\s+nay|tuan\s+nay)",
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            return 0, ""
        count = max(0, int(match.group(1)))
        bucket = "today" if "hom nay" in match.group(2).lower() else "week"
        return count, bucket

    def _adjust_schedule_with_ai(
        self,
        steps: List[models.StudentLearningPlanStep],
        message: str,
        today: date,
    ) -> Tuple[bool, str]:
        if not self.client or not steps:
            return False, ""

        steps_payload = [
            {
                "document_id": int(item.document_id),
                "subject_name": str(item.subject_name or ""),
                "document_title": str(item.document_title or item.document_filename or ""),
                "planned_date": item.planned_date.isoformat() if item.planned_date else None,
                "deadline_date": item.deadline_date.isoformat() if item.deadline_date else None,
                "latest_score": float(item.latest_score) if item.latest_score is not None else None,
                "priority_group": str(item.priority_group or ""),
                "reason": str(item.reason or ""),
            }
            for item in steps
        ]
        prompt = f"""
You are updating a student's study plan.
Today is {today.isoformat()}.
User request: {message}

Current unfinished plan:
{json.dumps(steps_payload, ensure_ascii=False)}

Return ONLY valid JSON as an array with the full reordered plan.
Rules:
- Keep exactly the same set of document_id values.
- You may change order, planned_date, deadline_date, and reason.
- planned_date must not be before today.
- Keep overall pacing around 1 or 2 documents per week when possible.
- deadline_date should be 3 to 5 days after planned_date.

JSON shape:
[
  {{
    "document_id": 123,
    "planned_date": "YYYY-MM-DD",
    "deadline_date": "YYYY-MM-DD",
    "reason": "short vietnamese explanation"
  }}
]
""".strip()

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = self._extract_json_payload(completion.choices[0].message.content)
            if not isinstance(parsed, list):
                return False, ""

            step_by_doc = {int(item.document_id): item for item in steps}
            updated_steps: List[models.StudentLearningPlanStep] = []
            seen: set[int] = set()

            for row in parsed:
                if not isinstance(row, dict):
                    continue
                try:
                    doc_id = int(row.get("document_id"))
                except Exception:
                    continue
                step = step_by_doc.get(doc_id)
                if not step or doc_id in seen:
                    continue

                planned_raw = str(row.get("planned_date") or "").strip()
                deadline_raw = str(row.get("deadline_date") or "").strip()
                try:
                    parsed_planned = datetime.strptime(planned_raw, "%Y-%m-%d").date()
                except Exception:
                    parsed_planned = step.planned_date or today
                try:
                    parsed_deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date() if deadline_raw else None
                except Exception:
                    parsed_deadline = None

                step.planned_date = max(parsed_planned, today)
                step.deadline_date = parsed_deadline or self._default_deadline_date(step.planned_date, str(step.priority_group or ""))
                reason = str(row.get("reason") or "").strip()
                if reason:
                    step.reason = reason
                updated_steps.append(step)
                seen.add(doc_id)

            if len(updated_steps) != len(steps):
                return False, ""

            for idx, step in enumerate(updated_steps, start=1):
                step.step_order = idx
                if not step.deadline_date:
                    step.deadline_date = self._default_deadline_date(step.planned_date, str(step.priority_group or ""))
                steps[idx - 1] = step
            return True, "Da cap nhat ke hoach theo yeu cau moi."
        except Exception:
            return False, ""

    def apply_plan_adjustment(self, user_id: int, message: str) -> Dict[str, object]:
        active = (
            self.db.query(models.StudentLearningPlan)
            .filter(
                models.StudentLearningPlan.user_id == user_id,
                models.StudentLearningPlan.status == "active",
            )
            .order_by(models.StudentLearningPlan.generated_at.desc())
            .first()
        )
        if not active:
            plan = self.regenerate_for_user(user_id=user_id, reason="chat_adjust", reference_login_at=None)
            return {"message": "Da tao ke hoach moi va ap dung yeu cau.", "plan": plan}

        steps = sorted(list(active.steps or []), key=lambda item: (item.step_order, item.id))
        if not steps:
            return {"message": "Ke hoach hien tai chua co buoc nao can dieu chinh.", "plan": self._serialize_plan(active)}

        today = datetime.utcnow().date()
        ai_changed, ai_feedback = self._adjust_schedule_with_ai(steps, message, today)
        if ai_changed:
            active.generated_at = datetime.utcnow()
            active.generation_reason = "chat_adjust_ai"
            self.db.commit()
            self.db.refresh(active)
            return {"message": ai_feedback, "plan": self._serialize_plan(active)}

        text = (message or "").strip()
        normalized = self._normalize_text(text)
        changed = False
        feedback: List[str] = []

        subject_phrase = self._extract_subject_phrase(text)
        if subject_phrase and self._is_prioritize(text):
            matched = [s for s in steps if subject_phrase in self._normalize_text(s.subject_name or "")]
            others = [s for s in steps if s not in matched]
            if matched:
                steps = matched + others
                changed = True
                feedback.append(f"Da uu tien mon '{subject_phrase}' len hoc truoc.")

        if subject_phrase and self._is_defer(text):
            matched = [s for s in steps if subject_phrase in self._normalize_text(s.subject_name or "")]
            others = [s for s in steps if s not in matched]
            if matched:
                steps = others + matched
                changed = True
                feedback.append(f"Da doi mon '{subject_phrase}' ve cac ngay hoc sau.")

        extra_count, bucket = self._extract_extra_load(text)
        if extra_count > 0 and bucket == "today":
            later_steps = [s for s in steps if s.planned_date and s.planned_date > today]
            for item in later_steps[:extra_count]:
                item.planned_date = today
                item.deadline_date = self._default_deadline_date(item.planned_date, str(item.priority_group or ""))
                changed = True
            if changed:
                feedback.append(f"Da them {extra_count} tai lieu vao lich hoc hom nay.")

        if extra_count > 0 and bucket == "week":
            week_end = today + timedelta(days=(6 - today.weekday()))
            later_steps = [s for s in steps if s.planned_date and s.planned_date > week_end]
            week_days = [today + timedelta(days=i) for i in range((week_end - today).days + 1)]
            for idx, item in enumerate(later_steps[:extra_count]):
                item.planned_date = week_days[idx % len(week_days)]
                item.deadline_date = self._default_deadline_date(item.planned_date, str(item.priority_group or ""))
                changed = True
            if changed:
                feedback.append(f"Da them {extra_count} tai lieu vao tuan nay.")

        if changed:
            for idx, item in enumerate(steps, start=1):
                item.step_order = idx
                if not item.planned_date:
                    item.planned_date = today + timedelta(days=idx - 1)
                if not item.deadline_date:
                    item.deadline_date = self._default_deadline_date(item.planned_date, str(item.priority_group or ""))

            active.generated_at = datetime.utcnow()
            active.generation_reason = "chat_adjust_rule"
            self.db.commit()
            self.db.refresh(active)
            return {
                "message": " ".join(feedback) if feedback else "Da cap nhat ke hoach hoc tap.",
                "plan": self._serialize_plan(active),
            }

        if "lam moi" in normalized or "tao lai" in normalized:
            refreshed = self.regenerate_for_user(user_id=user_id, reason="chat_refresh", reference_login_at=None)
            return {
                "message": "Da tao lai ke hoach hoc tap moi.",
                "plan": refreshed,
            }

        return {
            "message": "Minh chua hieu ro yeu cau thay doi. Ban co the thu mot yeu cau cu the hon ve mon hoc, thu tu uu tien hoac tai lieu can hoc som.",
            "plan": self._serialize_plan(active),
        }
