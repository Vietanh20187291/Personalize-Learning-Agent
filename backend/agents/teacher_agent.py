import json
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from db.models import AssessmentHistory, Classroom, Document, OrbitCoachDirective, QuestionBank, Subject, User
from memory import ActionRouter, IntentClassifier, get_conversation_memory


class TeacherAgent:
    def __init__(self, db: Session):
        self.db = db
        self.classifier = IntentClassifier()
        self.router = ActionRouter()

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _normalize(self, text: str) -> str:
        return self._clean_text(text).lower()

    def _subject_candidates(self) -> List[Subject]:
        return self.db.query(Subject).order_by(Subject.name.asc()).all()

    def _classroom_candidates(self) -> List[Classroom]:
        return self.db.query(Classroom).order_by(Classroom.id.asc()).all()

    def _student_candidates(self) -> List[User]:
        return self.db.query(User).filter(User.role == "student").order_by(User.full_name.asc()).all()

    def _strip_target_suffix(self, text: str) -> str:
        cleaned = self._clean_text(text)
        cleaned = re.sub(r"^(?:học|hoc)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+môn\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+lớp\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+class\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.split(r"\b(?:thuộc|thuoc)\s+đề tài\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+ngành\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        return self._clean_text(cleaned).strip(" .,:;-\"")

    def _has_crud_signal(self, message: str) -> bool:
        normalized = self._normalize(message)
        return any(token in normalized for token in [
            "thêm", "them", "tạo", "tao", "xóa", "xoá", "xoa", "sửa", "sua", "cập nhật", "cap nhat", "update", "delete", "create", "add", "upload", "nạp", "nap"
        ])

    def _crud_clarification_response(self) -> Dict[str, Any]:
        reply = (
            "Mình chưa đủ thông tin để xử lý CRUD chính xác. Bạn muốn thao tác với môn học, lớp học hay tài liệu? "
            "Bạn có thể nói theo mẫu: 'Thêm môn học <tên môn>', 'Sửa lớp <tên lớp>', hoặc 'Xóa tài liệu <tên tài liệu> của lớp <tên lớp>'."
        )
        return {
            "reply": reply,
            "suggested_actions": [
                "Thêm môn học <tên môn>",
                "Sửa lớp <tên lớp>",
                "Xóa tài liệu <tên tài liệu> của lớp <tên lớp>",
            ],
            "intent_type": "crud_clarification",
            "confidence": 0.9,
            "needs_more_info": True,
            "missing_fields": ["entity_type_or_target_name"],
            "action_metadata": {
                "action_type": "none",
                "target": "teacher",
                "tab_name": "subjects",
                "should_auto_execute": False,
            },
        }

    def _extract_management_target(self, message: str, entity_type: str) -> str:
        patterns = {
            "subject": [
                r"(?:thêm|tạo|sửa|chỉnh sửa|cập nhật|xóa|xoá|delete|create|update|add)\s+(?:môn học|môn|subject|course)\s+(.+)",
                r"(?:môn học|môn|subject|course)\s+(.+)",
            ],
            "class": [
                r"(?:thêm|tạo|sửa|chỉnh sửa|cập nhật|xóa|xoá|delete|create|update|add)\s+(?:lớp học|lớp|class)\s+(.+)",
                r"(?:lớp học|lớp|class)\s+(.+)",
            ],
            "document": [
                r"(?:thêm|tạo|sửa|chỉnh sửa|cập nhật|xóa|xoá|upload|nạp|delete|create|update|add)\s+(?:tài liệu|học liệu|document|file)\s+(.+)",
                r"(?:tài liệu|học liệu|document|file)\s+(.+)",
            ],
        }

        for pattern in patterns.get(entity_type, []):
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = self._strip_target_suffix(match.group(1))
                if candidate:
                    return candidate

        if entity_type == "subject":
            subject = self._find_subject_in_message(message)
            if subject:
                return subject.name
        if entity_type == "class":
            classroom = self._find_classroom_in_message(message)
            if classroom:
                return classroom.name
        return ""

    def _detect_management_action(self, message: str, entities: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        normalized = self._normalize(message)
        if not normalized:
            return None

        if "thiếu tài liệu" in normalized or "thieu tai lieu" in normalized:
            return None

        operation = None
        if any(token in normalized for token in ["xóa", "xoá", "xoa", "delete", "remove", "hủy", "huy"]):
            operation = "delete"
        elif any(token in normalized for token in ["cập nhật", "cap nhat", "chỉnh sửa", "chinh sua", "sửa", "sua", "update", "đổi tên", "doi ten", "rename"]):
            operation = "update"
        elif any(token in normalized for token in ["thêm", "them", "tạo", "tao", "mới", "moi", "add", "create", "upload", "nạp", "nap"]):
            operation = "create"

        if not operation:
            return None

        entity_type = None
        if any(token in normalized for token in ["tài liệu", "tai lieu", "học liệu", "hoc lieu", "document", "file"]):
            entity_type = "document"
        elif any(token in normalized for token in ["lớp", "lop", "class"]):
            entity_type = "class"
        elif any(token in normalized for token in ["môn học", "mon hoc", "môn", "mon", "subject", "course"]):
            entity_type = "subject"

        if entity_type is None:
            return None

        subject_name = entities.get("subject_name") or ""
        class_name = entities.get("class_name") or ""
        document_name = entities.get("document_name") or ""
        subject_obj = self._find_subject_in_message(message)
        classroom_obj = self._find_classroom_in_message(message, subject_obj)

        extracted_subject = self._extract_management_target(message, "subject")
        extracted_class = self._extract_management_target(message, "class")
        extracted_document = self._extract_management_target(message, "document")

        if extracted_subject:
            subject_name = extracted_subject
        if extracted_class:
            class_name = extracted_class
        if extracted_document:
            document_name = extracted_document

        if class_name and not classroom_obj:
            classroom_obj = self._resolve_classroom({"class_name": class_name}, context, subject_obj)

        if classroom_obj:
            class_name = class_name or classroom_obj.name
            if not subject_obj and getattr(classroom_obj, "subject_obj", None):
                subject_obj = classroom_obj.subject_obj
            if subject_obj:
                subject_name = subject_obj.name

        if entity_type == "subject":
            if not subject_name:
                return None
            if not subject_obj:
                subject_obj = self._find_subject_in_message(subject_name)
        elif entity_type == "class":
            if not class_name:
                return None
            if not subject_name:
                if subject_obj:
                    subject_name = subject_obj.name
        elif entity_type == "document":
            if not document_name and operation == "create":
                document_name = self._clean_text(message)
            if not subject_name:
                if subject_obj:
                    subject_name = subject_obj.name
            if not class_name:
                if classroom_obj:
                    class_name = classroom_obj.name

        if entity_type == "document" and not (class_name or subject_name):
            return None

        action_mode = f"{operation}_{entity_type}"
        params = {
            "mode": action_mode,
            "operation": operation,
            "entity_type": entity_type,
        }

        if subject_name:
            params["subject_name"] = subject_name
        if subject_obj:
            params["subject_id"] = subject_obj.id
        if class_name:
            params["class_name"] = class_name
        if classroom_obj:
            params["classroom_id"] = classroom_obj.id
        if document_name:
            params["document_name"] = document_name

        if entity_type == "subject":
            verb = "thêm" if operation == "create" else "cập nhật" if operation == "update" else "xóa"
            reply = f"Tôi đã mở Quản lý môn học và điền sẵn tên môn {subject_name}. Bạn có thể bấm Lưu để {verb} môn này."
            actions = [
                "Xác nhận lại tên môn học",
                "Lưu thay đổi trong form Quản lý môn học",
                "Nếu muốn, tôi có thể mở sang phần lớp của môn này",
            ]
        elif entity_type == "class":
            reply = (
                f"Tôi đã mở Quản lý môn học và chọn sẵn lớp {class_name}. "
                f"Nếu là tạo mới, bạn có thể nhập lại tên lớp rồi bấm Lưu; nếu là chỉnh sửa/xóa, hãy kiểm tra lớp đã chọn."
            )
            actions = [
                "Kiểm tra môn đang chọn",
                "Lưu thay đổi của lớp trong form Quản lý môn học",
                "Xem danh sách sinh viên của lớp sau khi cập nhật",
            ]
        else:
            reply = (
                f"Tôi đã mở khu quản lý học liệu và giữ sẵn ngữ cảnh cho {class_name or subject_name}. "
                f"Bạn có thể upload hoặc chỉnh sửa tài liệu ngay trong màn hình quản lý môn học."
            )
            actions = [
                "Nạp tài liệu mới cho lớp đã chọn",
                "Kiểm tra tài liệu đang hiển thị cho sinh viên",
                "Quay lại danh sách tài liệu của lớp",
            ]

        return {
            "reply": reply,
            "suggested_actions": actions,
            "intent_type": f"crud_{entity_type}",
            "confidence": 1.0,
            "class_name": class_name,
            "subject": subject_name,
            "action_metadata": {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "subjects",
                "params": params,
                "message": reply,
                "should_auto_execute": True,
            },
        }

    def _find_subject_in_message(self, message: str) -> Optional[Subject]:
        normalized_message = self._normalize(message)
        subjects = sorted(self._subject_candidates(), key=lambda item: len(self._normalize(item.name or "")), reverse=True)
        for subject in subjects:
            candidate = self._normalize(subject.name or "")
            if candidate and candidate in normalized_message:
                return subject
        return None

    def _find_classroom_in_message(self, message: str, subject: Optional[Subject] = None) -> Optional[Classroom]:
        normalized_message = self._normalize(message)
        classrooms = self._classroom_candidates()
        if subject is not None:
            classrooms = [
                item
                for item in classrooms
                if item.subject_id == subject.id or self._normalize(item.subject or "") == self._normalize(subject.name)
            ]

        # Prefer longer/more specific class names first.
        classrooms = sorted(classrooms, key=lambda item: len(self._normalize(item.name or "")), reverse=True)

        for classroom in classrooms:
            for raw_candidate in [classroom.name, classroom.class_code or ""]:
                candidate = self._normalize(raw_candidate)
                if not candidate:
                    continue
                # Boundary-aware match to avoid IT1 matching IT10.
                if re.search(rf"(^|[^a-z0-9]){re.escape(candidate)}([^a-z0-9]|$)", normalized_message):
                    return classroom
        return None

    def _subject_display(self, subject: Optional[Subject], context: Dict[str, Any]) -> str:
        if subject:
            return subject.name
        return self._clean_text(context.get("last_subject_name") or context.get("last_subject") or "")

    def _resolve_subject(self, entities: Dict[str, Any], context: Dict[str, Any], classroom: Optional[Classroom] = None) -> Optional[Subject]:
        subject_name = self._clean_text(entities.get("subject_name") or "")
        if not subject_name and classroom:
            subject_name = self._clean_text(getattr(classroom.subject_obj, "name", "") or classroom.subject or "")

        if not subject_name:
            subject_name = self._clean_text(context.get("last_subject_name") or context.get("last_subject") or "")

        if not subject_name:
            return None

        normalized = self._normalize(subject_name)
        exact = self.db.query(Subject).filter(func.lower(Subject.name) == normalized).first()
        if exact:
            return exact

        for subject in self._subject_candidates():
            candidate = self._normalize(subject.name)
            if candidate == normalized or normalized in candidate or candidate in normalized:
                return subject
        return None

    def _resolve_classroom(self, entities: Dict[str, Any], context: Dict[str, Any], subject: Optional[Subject] = None) -> Optional[Classroom]:
        class_name = self._clean_text(entities.get("class_name") or "")
        if not class_name:
            class_name = self._clean_text(context.get("last_class_name") or "")

        if not class_name:
            return None

        normalized = self._normalize(class_name)
        classrooms = self._classroom_candidates()
        if subject:
            classrooms = [item for item in classrooms if item.subject_id == subject.id or self._normalize(item.subject or "") == self._normalize(subject.name)]

        for classroom in classrooms:
            candidate_names = [self._normalize(classroom.name), self._normalize(classroom.class_code or "")]
            if normalized in candidate_names or any(normalized == candidate or normalized in candidate or candidate in normalized for candidate in candidate_names):
                return classroom

        # Try exact prefix/substring fallback across all classrooms.
        for classroom in self._classroom_candidates():
            candidate = self._normalize(classroom.name)
            if normalized in candidate or candidate in normalized:
                return classroom
        return None

    def _resolve_student(self, entities: Dict[str, Any], context: Dict[str, Any], classroom: Optional[Classroom] = None) -> Optional[User]:
        student_name = self._clean_text(entities.get("student_name") or entities.get("student_identifier") or "")
        if not student_name:
            student_name = self._clean_text(
                (context.get("last_student_name") or "")
                or (context.get("last_student_asked") or {}).get("name", "")
            )

        if not student_name:
            return None

        normalized = self._normalize(student_name)
        candidates = []
        if classroom is not None:
            for student in classroom.students:
                if getattr(student, "role", "student") != "student":
                    continue
                candidates.append(student)
        else:
            candidates = self._student_candidates()

        for student in candidates:
            fields = [
                self._normalize(getattr(student, "full_name", "") or ""),
                self._normalize(getattr(student, "student_id", "") or ""),
                self._normalize(getattr(student, "username", "") or ""),
            ]
            if any(normalized == field or normalized in field or field in normalized for field in fields if field):
                return student
        return None

    def _latest_scores_for_students(self, histories: List[AssessmentHistory]) -> Dict[int, float]:
        latest_scores: Dict[int, float] = {}
        for item in histories:
            if item.user_id is None or item.user_id in latest_scores:
                continue
            latest_scores[item.user_id] = float(item.score or 0)
        return latest_scores

    def _class_score_summary(self, classroom: Classroom, subject: Optional[Subject] = None) -> Dict[str, Any]:
        subject_id = subject.id if subject else classroom.subject_id
        histories = (
            self.db.query(AssessmentHistory)
            .filter(
                AssessmentHistory.user_id.in_([student.id for student in classroom.students if getattr(student, "role", "student") == "student"]),
                AssessmentHistory.subject_id == subject_id,
            )
            .order_by(desc(AssessmentHistory.timestamp))
            .all()
        )

        latest_scores = self._latest_scores_for_students(histories)
        scores = list(latest_scores.values())
        student_count = len([student for student in classroom.students if getattr(student, "role", "student") == "student"])
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        pass_count = len([score for score in scores if score >= 50])
        fail_count = len([score for score in scores if score < 50])
        distribution = {
            "Yếu (<40)": len([score for score in scores if score < 40]),
            "Trung bình (40-60)": len([score for score in scores if 40 <= score < 60]),
            "Khá (60-80)": len([score for score in scores if 60 <= score < 80]),
            "Giỏi (>=80)": len([score for score in scores if score >= 80]),
        }
        weak_students = []
        low_score_students = []
        strong_students = []
        for student in sorted(classroom.students, key=lambda item: item.id):
            if getattr(student, "role", "student") != "student":
                continue
            score = latest_scores.get(student.id)
            if score is not None:
                student_info = {
                    "id": student.id,
                    "name": self._clean_text(getattr(student, "full_name", "") or getattr(student, "username", "") or f"SV {student.id}"),
                    "score": round(score, 1),
                }
                if score < 40:
                    low_score_students.append(student_info)
                elif 40 <= score < 60:
                    weak_students.append(student_info)
                elif score >= 80:
                    strong_students.append(student_info)

        return {
            "student_count": student_count,
            "avg_score": avg_score,
            "pass_rate": round((pass_count / len(scores)) * 100, 1) if scores else 0.0,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "distribution": distribution,
            "weak_students": weak_students[:5],
            "low_score_students": low_score_students[:5],
            "strong_students": strong_students[:5],
            "histories_count": len(histories),
            "scores": scores,
        }

    def _class_overview_reply(self, classroom: Classroom, subject: Optional[Subject], context: Dict[str, Any]) -> Dict[str, Any]:
        summary = self._class_score_summary(classroom, subject)
        
        # Format thông tin thống kê lớp thành bullet points
        student_count_text = f"Số sinh viên: {summary['student_count']}"
        avg_score_text = f"Điểm trung bình: {summary['avg_score']:.1f}"
        pass_rate_text = f"Tỷ lệ đỗ (>=50): {summary['pass_rate']:.1f}% ({summary['pass_count']}/{summary['student_count']} sinh viên)"
        distribution_text = (
            f"Phân bố điểm: {summary['distribution']['Giỏi (>=80)']} giỏi, "
            f"{summary['distribution']['Khá (60-80)']} khá, {summary['distribution']['Trung bình (40-60)']} trung bình, "
            f"{summary['distribution']['Yếu (<40)']} yếu"
        )
        
        # Thêm thông tin sinh viên điểm cao
        strong_text = "Chưa có sinh viên đạt điểm cao"
        if summary["strong_students"]:
            strong_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["strong_students"]])
        strong_students_text = f"Sinh viên xuất sắc (>=80): {strong_text}"
        
        # Thêm thông tin sinh viên cần cải thiện (40-60)
        weak_text = "Không có"
        if summary["weak_students"]:
            weak_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["weak_students"]])
        weak_students_text = f"Sinh viên cần cải thiện (40-60): {weak_text}"
        
        # Thêm thông tin sinh viên điểm thấp (<40)
        low_text = "Không có"
        if summary["low_score_students"]:
            low_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["low_score_students"]])
        low_students_text = f"Sinh viên không đạt (<40): {low_text}"
        
        # Ghép thành bullet points
        reply = (
            f"📊 **Tình hình học tập lớp {classroom.name}**\n"
            f"• {student_count_text}\n"
            f"• {avg_score_text}\n"
            f"• {pass_rate_text}\n"
            f"• {distribution_text}\n"
            f"• {strong_students_text}\n"
            f"• {weak_students_text}\n"
            f"• {low_students_text}"
        )
        
        actions = [
            "Xem chi tiết phân bố điểm của lớp",
            "Lọc danh sách sinh viên dưới 60 điểm",
            "Đề xuất kế hoạch củng cố 1 buổi cho lớp",
        ]
        return {"reply": reply, "suggested_actions": actions}

    def _course_info_reply(self, subject: Subject) -> Dict[str, Any]:
        classes = (
            self.db.query(Classroom)
            .filter(Classroom.subject_id == subject.id)
            .order_by(Classroom.name.asc())
            .all()
        )
        class_names = [classroom.name for classroom in classes]
        student_total = sum(len([student for student in classroom.students if getattr(student, "role", "student") == "student"]) for classroom in classes)
        reply = (
            f"Môn {subject.name} hiện có {len(classes)} lớp: {', '.join(class_names) if class_names else 'chưa có lớp nào'}. "
            f"Tổng số sinh viên đang theo học các lớp của môn này là {student_total}."
        )
        actions = [
            f"Mở danh sách lớp của môn {subject.name}",
            "Xem thống kê điểm trung bình từng lớp",
            "Kiểm tra môn này đang thiếu bao nhiêu tài liệu",
        ]
        return {"reply": reply, "suggested_actions": actions}

    def _class_analytics_reply(self, classroom: Optional[Classroom], subject: Optional[Subject]) -> Dict[str, Any]:
        if classroom is not None:
            summary = self._class_score_summary(classroom, subject)
            
            # Format thông tin phân tích thành bullet points
            avg_score_text = f"Điểm trung bình: {summary['avg_score']:.1f}"
            pass_rate_text = f"Tỷ lệ đỗ (>=50): {summary['pass_rate']:.1f}%"
            distribution_text = (
                f"Phân bố điểm: {summary['distribution']['Giỏi (>=80)']} giỏi, "
                f"{summary['distribution']['Khá (60-80)']} khá, {summary['distribution']['Trung bình (40-60)']} trung bình, "
                f"{summary['distribution']['Yếu (<40)']} yếu"
            )
            
            # Thêm thông tin sinh viên điểm cao
            strong_text = "Chưa có"
            if summary["strong_students"]:
                strong_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["strong_students"]])
            strong_students_text = f"Sinh viên xuất sắc (>=80): {strong_text}"
            
            # Thêm thông tin sinh viên cần cải thiện (40-60)
            weak_text = "Không có"
            if summary["weak_students"]:
                weak_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["weak_students"]])
            weak_students_text = f"Sinh viên cần cải thiện (40-60): {weak_text}"
            
            # Thêm thông tin sinh viên điểm thấp (<40)
            low_text = "Không có"
            if summary["low_score_students"]:
                low_text = ", ".join([f"{item['name']} ({item['score']})" for item in summary["low_score_students"]])
            low_students_text = f"Sinh viên không đạt (<40): {low_text}"
            
            # Ghép thành bullet points
            reply = (
                f"📈 **Phân tích chi tiết lớp {classroom.name}**\n"
                f"• {avg_score_text}\n"
                f"• {pass_rate_text}\n"
                f"• {distribution_text}\n"
                f"• {strong_students_text}\n"
                f"• {weak_students_text}\n"
                f"• {low_students_text}"
            )
            actions = [
                "Xem biểu đồ phân bố điểm của lớp này",
                "Lọc sinh viên dưới 60 điểm",
                "Tạo kế hoạch phụ đạo ngắn cho nhóm yếu",
            ]
            return {"reply": reply, "suggested_actions": actions}

        if subject is not None:
            classes = self.db.query(Classroom).filter(Classroom.subject_id == subject.id).all()
            class_summaries = []
            for item in classes:
                summary = self._class_score_summary(item, subject)
                class_summaries.append((item.name, summary["avg_score"], summary["pass_rate"]))
            class_summaries.sort(key=lambda item: item[1], reverse=True)

            if not class_summaries:
                reply = f"Môn {subject.name} chưa có lớp hoặc chưa có dữ liệu đánh giá để phân tích."
                actions = ["Tạo lớp cho môn này", "Nhập dữ liệu đánh giá", "Tải thêm tài liệu môn học"]
                return {"reply": reply, "suggested_actions": actions}

            best = class_summaries[0]
            worst = class_summaries[-1]
            reply = (
                f"Trong các lớp của môn {subject.name}, lớp học tốt nhất hiện là {best[0]} với điểm trung bình {best[1]:.1f} và tỷ lệ đỗ {best[2]:.1f}%. "
                f"Lớp cần hỗ trợ nhiều nhất là {worst[0]} với điểm trung bình {worst[1]:.1f} và tỷ lệ đỗ {worst[2]:.1f}%."
            )
            actions = [
                "Mở chi tiết lớp tốt nhất để xem chiến lược học tập",
                "Xem lớp kém nhất để lập kế hoạch phụ đạo",
                "So sánh phổ điểm giữa các lớp của môn này",
            ]
            return {"reply": reply, "suggested_actions": actions}

        reply = "Bạn chưa chỉ rõ lớp hoặc môn cần phân tích."
        actions = ["Nêu rõ lớp X", "Hoặc nêu rõ môn X để so sánh các lớp trong môn đó", "Ví dụ: Trong các lớp môn Toán thì lớp nào học tốt?"]
        return {"reply": reply, "suggested_actions": actions}

    def _student_overview_reply(self, student: User) -> Dict[str, Any]:
        histories = (
            self.db.query(AssessmentHistory)
            .filter(AssessmentHistory.user_id == student.id)
            .order_by(AssessmentHistory.timestamp.asc())
            .all()
        )
        scores = [float(item.score or 0) for item in histories]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        recent_scores = scores[-5:]
        recent_avg = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else 0.0
        trend = 0.0
        if len(recent_scores) >= 2:
            trend = round(recent_scores[-1] - recent_scores[0], 1)

        by_subject: Dict[str, List[float]] = defaultdict(list)
        for item in histories:
            subject_name = self._clean_text(getattr(item, "subject", "") or getattr(getattr(item, "subject_obj", None), "name", "") or "Chưa rõ môn")
            by_subject[subject_name].append(float(item.score or 0))

        subject_avgs = sorted(
            ((name, round(sum(values) / len(values), 1)) for name, values in by_subject.items() if values),
            key=lambda item: item[1],
            reverse=True,
        )
        strongest = subject_avgs[0] if subject_avgs else ("Chưa đủ dữ liệu", 0.0)
        weakest = subject_avgs[-1] if subject_avgs else ("Chưa đủ dữ liệu", 0.0)
        enrolled_classes = [classroom.name for classroom in student.enrolled_classes]
        enrolled_subjects = sorted({self._clean_text(getattr(classroom.subject_obj, "name", "") or classroom.subject or "") for classroom in student.enrolled_classes if classroom.subject_id})

        reply = (
            f"Sinh viên {self._clean_text(student.full_name or student.username or f'SV {student.id}')}: đang tham gia {len(enrolled_classes)} lớp, "
            f"điểm trung bình tổng thể {avg_score:.1f}, trung bình 5 bài gần nhất {recent_avg:.1f}. "
            f"Xu hướng gần đây {'đang cải thiện' if trend > 0 else 'đang giảm' if trend < 0 else 'ổn định'}. "
            f"Môn mạnh nhất: {strongest[0]} ({strongest[1]:.1f}); môn cần cải thiện: {weakest[0]} ({weakest[1]:.1f})."
        )
        if enrolled_classes:
            reply += f" Các lớp đang tham gia: {', '.join(enrolled_classes)}."
        actions = [
            "Xem chi tiết kết quả theo từng môn",
            "Lọc ra các lỗi sai phổ biến của sinh viên này",
            "Gợi ý kế hoạch cải thiện cho môn yếu nhất",
        ]
        return {"reply": reply, "suggested_actions": actions}

    def _material_reply(self, subject: Optional[Subject], classroom: Optional[Classroom], message: str) -> Dict[str, Any]:
        clean_msg = self._normalize(message)
        if any(phrase in clean_msg for phrase in ["môn nào thiếu tài liệu", "thiếu tài liệu", "thieu tai lieu"]):
            subjects = self._subject_candidates()
            missing = []
            for item in subjects:
                doc_count = self.db.query(Document).filter(Document.subject_id == item.id).count()
                if doc_count == 0:
                    missing.append(item.name)
            if not missing:
                reply = "Hiện tại tất cả các môn trong hệ thống đều đã có ít nhất một tài liệu."
            else:
                reply = f"Các môn đang thiếu tài liệu gồm: {', '.join(missing)}."
            actions = [
                "Mở danh sách môn thiếu tài liệu",
                "Tải tài liệu cho môn còn trống",
                "Kiểm tra lại tài liệu đã công khai cho sinh viên",
            ]
            return {"reply": reply, "suggested_actions": actions}

        if subject is None and classroom is not None:
            subject = self._resolve_subject({"subject_name": classroom.subject}, {}, classroom)

        if subject is None:
            reply = "Bạn chưa nêu rõ môn học cần xem tài liệu."
            actions = ["Ví dụ: Cho tôi tài liệu môn Cơ sở Hệ điều hành", "Hoặc hỏi: Môn X có tài liệu gì?", "Nếu muốn, tôi có thể kiểm tra môn nào đang thiếu tài liệu"]
            return {"reply": reply, "suggested_actions": actions}

        documents = (
            self.db.query(Document)
            .filter(Document.subject_id == subject.id)
            .order_by(Document.upload_time.desc())
            .all()
        )
        if not documents:
            reply = f"Môn {subject.name} hiện chưa có tài liệu nào được upload."
            actions = ["Tải tài liệu cho môn này", "Kiểm tra danh sách môn thiếu tài liệu", "Tạo bộ tài liệu cơ bản cho môn học"]
            return {"reply": reply, "suggested_actions": actions}

        names = [doc.title or doc.filename or f"Tài liệu {doc.id}" for doc in documents[:8]]
        classes = sorted({doc.classroom.name for doc in documents if doc.classroom is not None})
        reply = (
            f"Môn {subject.name} hiện có {len(documents)} tài liệu: {', '.join(names)}. "
            f"Các tài liệu này đang dùng cho lớp: {', '.join(classes) if classes else 'chưa gắn cho lớp nào'}."
        )
        actions = [
            "Mở từng tài liệu để xem nội dung",
            "Kiểm tra tài liệu nào đang bị ẩn với sinh viên",
            "Liệt kê thêm tài liệu cho môn này",
        ]
        return {"reply": reply, "suggested_actions": actions}

    def _generate_exam_versions(self, subject: Subject, exam_type: str, num_questions: int, num_versions: int, difficulty: Optional[str] = None) -> Dict[str, Any]:
        bank = self.db.query(QuestionBank).filter(QuestionBank.subject_id == subject.id).all()
        if difficulty:
            filtered = [item for item in bank if self._normalize(item.difficulty or "") == difficulty]
            if filtered:
                bank = filtered

        if not bank:
            return {
                "reply": f"Môn {subject.name} chưa có ngân hàng câu hỏi để xuất đề trắc nghiệm.",
                "suggested_actions": [
                    "Tải câu hỏi vào ngân hàng đề",
                    "Đồng bộ câu hỏi từ tài liệu môn học",
                    "Tạo lại đề sau khi có dữ liệu câu hỏi",
                ],
            }

        unique_questions = bank[:]
        random.shuffle(unique_questions)
        needed = num_questions
        if len(unique_questions) < needed:
            needed = len(unique_questions)

        versions = []
        for version_index in range(num_versions):
            random.shuffle(unique_questions)
            selected = unique_questions[:needed]
            version_lines = [f"Đề {version_index + 1} - Môn {subject.name} - {exam_type} - {needed} câu"]
            for idx, item in enumerate(selected, start=1):
                title = self._clean_text(item.content or f"Câu hỏi {item.id}")
                version_lines.append(f"{idx}. {title}")
            versions.append({
                "version": version_index + 1,
                "questions": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "options": item.options,
                        "answer": item.correct_answer,
                        "source_file": item.source_file,
                    }
                    for item in selected
                ],
                "text": "\n".join(version_lines),
            })

        reply = (
            f"Tôi đã chuẩn bị {len(versions)} mã đề trắc nghiệm cho môn {subject.name} với {needed} câu mỗi đề. "
            f"Ngân hàng hiện có ít hơn số câu bạn yêu cầu nên tôi chỉ có thể dùng {len(unique_questions)} câu sẵn có. "
            f"Nếu bạn muốn đủ 30 câu, cần bổ sung thêm câu hỏi vào ngân hàng đề."
        )
        actions = [
            "Xuất đề sang file Word",
            "Xem lại câu hỏi theo mức độ khó",
            "Chỉnh sửa số câu hoặc số mã đề",
        ]
        return {
            "reply": reply,
            "suggested_actions": actions,
            "generated_exam": {
                "subject": subject.name,
                "exam_type": exam_type,
                "num_questions": needed,
                "num_versions": num_versions,
                "versions": versions,
            },
        }

    def _build_general_reply(self, subject: Optional[Subject], classroom: Optional[Classroom]) -> Dict[str, Any]:
        subject_name = subject.name if subject else (classroom.subject if classroom else "")
        if classroom:
            summary = self._class_score_summary(classroom, subject)
            reply = (
                f"Tôi đã tổng hợp dữ liệu lớp {classroom.name}: {summary['student_count']} sinh viên, điểm TB {summary['avg_score']:.1f}, "
                f"tỷ lệ đỗ {summary['pass_rate']:.1f}%. Bạn có thể hỏi về lớp này, môn này, tài liệu, hoặc xuất đề trắc nghiệm."
            )
        elif subject_name:
            classes = self.db.query(Classroom).filter(Classroom.subject_id == subject.id).count() if subject else 0
            reply = (
                f"Môn {subject_name} đang có {classes} lớp trong hệ thống. Bạn có thể hỏi tiếp về lớp, tài liệu, sinh viên hoặc đề thi."
            )
        else:
            reply = "Tôi chỉ xử lý các nhóm: môn học, lớp học, phân tích lớp, sinh viên, tài liệu và đề thi trắc nghiệm."
        actions = [
            "Hỏi về môn học",
            "Hỏi về lớp học",
            "Hỏi về tài liệu hoặc đề thi",
        ]
        return {"reply": reply, "suggested_actions": actions}

    def _build_context_updates(self, intent_type: str, entities: Dict[str, Any], subject: Optional[Subject], classroom: Optional[Classroom], student: Optional[User]) -> Dict[str, Any]:
        updates = {
            "last_intent": intent_type,
            "last_action_type": intent_type,
            "last_entities": entities,
        }
        if subject:
            updates["last_subject"] = subject.name
            updates["last_subject_name"] = subject.name
            updates["last_subject_id"] = subject.id
        elif entities.get("subject_name"):
            updates["last_subject_name"] = entities.get("subject_name")

        if classroom:
            updates["last_class"] = classroom.name
            updates["last_class_name"] = classroom.name
            updates["last_class_id"] = classroom.id

        if student:
            updates["last_student_asked"] = {
                "id": student.id,
                "name": self._clean_text(student.full_name or student.username or f"SV {student.id}"),
                "student_id": student.student_id,
            }
            updates["last_student_id"] = student.id
            updates["last_student_name"] = self._clean_text(student.full_name or student.username or f"SV {student.id}")

        return updates

    def _merge_pending_entities(self, pending_request: Dict[str, Any], current_entities: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(pending_request.get("entities", {}) or {})
        merged.update({key: value for key, value in current_entities.items() if value not in [None, ""]})
        return merged

    def _extract_orbit_targets(self, message: str) -> Dict[str, int]:
        normalized = self._normalize(message)
        tests = 0
        chapters = 0

        test_match = re.search(r"(\d+)\s*(?:bài|bai)\s*(?:kiểm tra|kiem tra|test)", normalized)
        if test_match:
            tests = int(test_match.group(1))

        chapter_match = re.search(r"(\d+)\s*(?:chương|chuong|bài|bai)\s*(?:học|hoc)?", normalized)
        if chapter_match:
            chapters = int(chapter_match.group(1))

        return {"target_tests": tests, "target_chapters": chapters}

    def _is_orbit_directive_request(self, message: str) -> bool:
        normalized = self._normalize(message)
        must_have = any(token in normalized for token in ["orbit", "thúc", "thuc", "yêu cầu", "yeu cau", "chỉ tiêu", "chi tieu", "tuần", "tuan"])
        has_action = any(token in normalized for token in ["làm thêm", "lam them", "học thêm", "hoc them", "phải", "can", "cần", "giao"])
        return must_have and has_action

    def _create_orbit_directive_action(self, teacher_id: int, message: str, student: Optional[User], classroom: Optional[Classroom], subject: Optional[Subject]) -> Dict[str, Any]:
        targets = self._extract_orbit_targets(message)
        target_tests = targets["target_tests"]
        target_chapters = targets["target_chapters"]

        now = datetime.utcnow()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        if not student:
            reply = "Bạn cần nêu rõ sinh viên để tôi giao chỉ tiêu cho Orbit. Ví dụ: 'Giao cho bạn An tuần này làm thêm 2 bài kiểm tra, học thêm 2 chương'."
            return {
                "reply": reply,
                "suggested_actions": [
                    "Giao chỉ tiêu cho sinh viên Nguyễn Văn A",
                    "Thêm số bài kiểm tra cần làm trong tuần",
                    "Thêm số chương cần hoàn thành trong tuần",
                ],
                "intent_type": "orbit_directive_missing_student",
                "confidence": 0.9,
                "needs_more_info": True,
                "missing_fields": ["student_name"],
                "action_metadata": {
                    "action_type": "none",
                    "target": "teacher",
                    "tab_name": "members",
                    "should_auto_execute": False,
                },
            }

        if target_tests <= 0 and target_chapters <= 0:
            reply = "Tôi đã nhận yêu cầu giao chỉ tiêu Orbit nhưng chưa thấy số lượng cụ thể. Bạn hãy nói rõ: thêm bao nhiêu bài kiểm tra hoặc bao nhiêu chương."
            return {
                "reply": reply,
                "suggested_actions": [
                    "Tuần này làm thêm 2 bài kiểm tra",
                    "Tuần này học thêm 2 chương",
                    "Tuần này làm thêm 2 bài kiểm tra và 2 chương",
                ],
                "intent_type": "orbit_directive_missing_target",
                "confidence": 0.9,
                "needs_more_info": True,
                "missing_fields": ["target_tests_or_target_chapters"],
                "action_metadata": {
                    "action_type": "none",
                    "target": "teacher",
                    "tab_name": "members",
                    "should_auto_execute": False,
                },
            }

        directive = OrbitCoachDirective(
            teacher_id=teacher_id,
            student_id=student.id,
            class_id=classroom.id if classroom else None,
            subject_id=subject.id if subject else None,
            target_tests=target_tests,
            target_chapters=target_chapters,
            note=self._clean_text(message),
            week_start=week_start,
            week_end=week_end,
            is_active=True,
        )
        self.db.add(directive)
        self.db.commit()

        student_name = self._clean_text(student.full_name or student.username or f"SV {student.id}")
        parts = []
        if target_tests > 0:
            parts.append(f"{target_tests} bài kiểm tra")
        if target_chapters > 0:
            parts.append(f"{target_chapters} chương")
        target_text = " và ".join(parts)

        reply = (
            f"Đã giao chỉ tiêu tuần này cho Orbit của sinh viên {student_name}: {target_text}. "
            f"Orbit sẽ đốc thúc sát tiến độ, nhắc học nếu chậm, và ghi nhận khen ngợi khi sinh viên cải thiện."
        )

        return {
            "reply": reply,
            "suggested_actions": [
                "Xem lại tiến độ sinh viên sau 2-3 ngày",
                "Giao thêm chỉ tiêu cho nhóm học yếu",
                "Yêu cầu Orbit báo cáo các sinh viên chưa đạt KPI tuần",
            ],
            "intent_type": "orbit_directive_created",
            "confidence": 1.0,
            "class_name": classroom.name if classroom else "",
            "subject": subject.name if subject else "",
            "action_metadata": {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "members",
                "params": {
                    "student_id": student.id,
                    "classroom_id": classroom.id if classroom else None,
                    "directive_id": directive.id,
                },
                "message": reply,
                "should_auto_execute": False,
            },
        }

    def respond(self, teacher_id: int, class_id: int, message: str):
        memory = get_conversation_memory()
        context = memory.get_context(teacher_id, class_id)
        analysis = self.classifier.classify_request(message, context)
        pending_request = memory.get_pending_request(teacher_id, class_id)

        intent_type = analysis["intent_type"]
        entities = analysis["entities"]
        if pending_request and (analysis["needs_follow_up"] or analysis["confidence"] < 0.4 or intent_type == self.classifier.GENERAL_QUESTION):
            intent_type = pending_request.get("intent_type", intent_type)
            entities = self._merge_pending_entities(pending_request, entities)

        explicit_subject = self._find_subject_in_message(message)
        subject = explicit_subject or self._resolve_subject(entities, context)

        explicit_classroom = self._find_classroom_in_message(message, subject)
        classroom = explicit_classroom or self._resolve_classroom(entities, context, subject)

        management_action = self._detect_management_action(message, entities, context)
        if management_action:
            memory.clear_pending_request(teacher_id, class_id)
            memory.add_message(
                teacher_id,
                class_id,
                "user",
                message,
                {"intent": management_action["intent_type"], "confidence": 1.0},
            )
            memory.add_message(
                teacher_id,
                class_id,
                "agent",
                management_action["reply"],
                {
                    "intent": management_action["intent_type"],
                    "subject": management_action.get("subject") or None,
                    "class_name": management_action.get("class_name") or None,
                },
            )
            memory.update_context(
                teacher_id,
                class_id,
                self._build_context_updates(
                    management_action["intent_type"],
                    entities,
                    subject,
                    classroom,
                    None,
                ),
            )
            return management_action

        if self._has_crud_signal(message):
            clarification = self._crud_clarification_response()
            memory.set_pending_request(
                teacher_id,
                class_id,
                {
                    "intent_type": clarification["intent_type"],
                    "entities": entities,
                    "missing_fields": clarification["missing_fields"],
                    "follow_up_question": clarification["reply"],
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            memory.add_message(
                teacher_id,
                class_id,
                "user",
                message,
                {"intent": clarification["intent_type"], "confidence": clarification["confidence"]},
            )
            memory.add_message(
                teacher_id,
                class_id,
                "agent",
                clarification["reply"],
                {"needs_more_info": True, "missing_fields": clarification["missing_fields"]},
            )
            return clarification

        student = self._resolve_student(entities, context, classroom)

        if self._is_orbit_directive_request(message):
            orbit_action = self._create_orbit_directive_action(teacher_id, message, student, classroom, subject)
            memory.clear_pending_request(teacher_id, class_id)
            memory.add_message(
                teacher_id,
                class_id,
                "user",
                message,
                {"intent": orbit_action["intent_type"], "confidence": orbit_action.get("confidence", 1.0)},
            )
            memory.add_message(
                teacher_id,
                class_id,
                "agent",
                orbit_action["reply"],
                {
                    "intent": orbit_action["intent_type"],
                    "subject": orbit_action.get("subject") or None,
                    "class_name": orbit_action.get("class_name") or None,
                },
            )
            memory.update_context(teacher_id, class_id, self._build_context_updates(
                orbit_action["intent_type"],
                entities,
                subject,
                classroom,
                student,
            ))
            return orbit_action

        # If the user just provided a follow-up, try to reuse the previous subject/class/student.
        if not subject and classroom:
            subject = self._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)

        # Compute missing information based on the final resolved entities.
        missing_fields: List[str] = []
        if intent_type == IntentClassifier.COURSE_INFO and subject is None:
            missing_fields.append("subject_name")
        elif intent_type == IntentClassifier.CLASS_OVERVIEW and classroom is None:
            missing_fields.append("class_name")
        elif intent_type == IntentClassifier.CLASS_ANALYTICS and classroom is None and subject is None:
            missing_fields.append("class_or_subject")
        elif intent_type == IntentClassifier.STUDENT_INFO and student is None:
            missing_fields.append("student_name")
        elif intent_type == IntentClassifier.MATERIAL and subject is None and "thiếu tài liệu" not in self._normalize(message):
            missing_fields.append("subject_name")
        elif intent_type == IntentClassifier.EXAM_GENERATION:
            if subject is None:
                missing_fields.append("subject_name")
            if not entities.get("exam_type"):
                missing_fields.append("exam_type")
            if not entities.get("num_questions"):
                missing_fields.append("num_questions")
            if not entities.get("num_versions"):
                missing_fields.append("num_versions")

        if missing_fields:
            follow_up = self.classifier.get_missing_info_message(intent_type, missing_fields)
            memory.set_pending_request(
                teacher_id,
                class_id,
                {
                    "intent_type": intent_type,
                    "entities": entities,
                    "missing_fields": missing_fields,
                    "follow_up_question": follow_up,
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            memory.add_message(
                teacher_id,
                class_id,
                "user",
                message,
                {"intent": intent_type, "confidence": analysis["confidence"]},
            )
            memory.add_message(
                teacher_id,
                class_id,
                "agent",
                follow_up,
                {"needs_more_info": True, "missing_fields": missing_fields},
            )
            return {
                "reply": follow_up,
                "suggested_actions": ["Bổ sung thông tin còn thiếu", "Ví dụ: Môn Cơ sở Hệ điều hành", "Ví dụ: Lớp IT1"],
                "class_name": classroom.name if classroom else "",
                "subject": subject.name if subject else "",
                "intent_type": intent_type,
                "confidence": analysis["confidence"],
                "needs_more_info": True,
                "missing_fields": missing_fields,
                "action_metadata": self.router.route_action(intent_type, context=context, class_id=class_id, student_name=getattr(student, "full_name", None), subject_name=getattr(subject, "name", None)),
            }

        memory.clear_pending_request(teacher_id, class_id)

        # Build the final response.
        if intent_type == IntentClassifier.COURSE_INFO and subject is not None:
            result = self._course_info_reply(subject)
        elif intent_type == IntentClassifier.CLASS_OVERVIEW:
            classroom = classroom or self.db.query(Classroom).filter(Classroom.id == class_id).first()
            if classroom is None:
                result = {"reply": "Không tìm thấy lớp học.", "suggested_actions": ["Chọn lại lớp học", "Kiểm tra mã lớp" ]}
            else:
                subject = subject or self._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)
                result = self._class_overview_reply(classroom, subject, context)
        elif intent_type == IntentClassifier.CLASS_ANALYTICS:
            if classroom is not None:
                subject = subject or self._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)
                result = self._class_analytics_reply(classroom, subject)
            else:
                result = self._class_analytics_reply(None, subject)
        elif intent_type == IntentClassifier.STUDENT_INFO and student is not None:
            result = self._student_overview_reply(student)
        elif intent_type == IntentClassifier.MATERIAL:
            result = self._material_reply(subject, classroom, message)
        elif intent_type == IntentClassifier.EXAM_GENERATION and subject is not None:
            exam_type = entities.get("exam_type") or "multiple_choice"
            num_questions = int(entities.get("num_questions") or 0)
            num_versions = int(entities.get("num_versions") or 0)
            difficulty = entities.get("difficulty")
            result = self._generate_exam_versions(subject, exam_type, num_questions, num_versions, difficulty=difficulty)
        else:
            result = self._build_general_reply(subject, classroom)

        response_intent = intent_type
        if not result.get("reply"):
            result["reply"] = "Tôi chưa xử lý được yêu cầu này."

        result["class_name"] = classroom.name if classroom else result.get("class_name", "")
        result["subject"] = subject.name if subject else result.get("subject", "")
        result["intent_type"] = response_intent
        result["confidence"] = analysis["confidence"]
        result["action_metadata"] = self.router.route_action(
            response_intent,
            context=context,
            class_id=classroom.id if classroom else class_id,
            student_name=self._clean_text(student.full_name or student.username) if student else None,
            subject_name=subject.name if subject else None,
        )

        memory.add_message(
            teacher_id,
            class_id,
            "user",
            message,
            {"intent": response_intent, "confidence": analysis["confidence"]},
        )
        memory.add_message(
            teacher_id,
            class_id,
            "agent",
            result["reply"],
            {
                "intent": response_intent,
                "subject_id": getattr(subject, "id", None),
                "class_id": getattr(classroom, "id", class_id),
                "student_id": getattr(student, "id", None),
            },
        )
        memory.update_context(teacher_id, class_id, self._build_context_updates(response_intent, entities, subject, classroom, student))

        # Persist pending exam info if the user is in the middle of a generator flow.
        if response_intent == IntentClassifier.EXAM_GENERATION and isinstance(result.get("generated_exam"), dict):
            memory.update_context(teacher_id, class_id, {
                "pending_exam_info": {
                    "subject": subject.name,
                    "exam_type": entities.get("exam_type"),
                    "num_questions": entities.get("num_questions"),
                    "num_versions": entities.get("num_versions"),
                    "difficulty": entities.get("difficulty"),
                }
            })

        return result
