"""
Action router for the teacher agent.
Maps the supported intents to UI actions and missing-information prompts.
"""
from typing import Dict, List, Optional

from .intent_classifier import IntentClassifier


class ActionRouter:
    def route_action(
        self,
        intent_type: str,
        context: Dict = None,
        class_id: int = None,
        student_name: str = None,
        subject_name: str = None,
    ) -> Dict:
        context = context or {}

        if intent_type == IntentClassifier.COURSE_INFO:
            return {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "subjects",
                "params": {"subject_name": subject_name},
                "message": "Đang mở phần thông tin môn học...",
                "should_auto_execute": True,
            }

        if intent_type == IntentClassifier.CLASS_OVERVIEW:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "class_analytics",
                "params": {"classroom_id": class_id},
                "message": "Đang mở tổng quan lớp học...",
                "should_auto_execute": True,
            }

        if intent_type == IntentClassifier.CLASS_ANALYTICS:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "class_analytics",
                "params": {
                    "classroom_id": class_id,
                    "subject_name": subject_name,
                },
                "message": "Đang mở phân tích lớp học...",
                "should_auto_execute": True,
            }

        if intent_type == IntentClassifier.STUDENT_INFO:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "student_detailed",
                "params": {
                    "classroom_id": class_id,
                    "student_name": student_name,
                },
                "message": "Đang tìm thông tin sinh viên...",
                "should_auto_execute": True,
            }

        if intent_type == IntentClassifier.MATERIAL:
            return {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "documents",
                "params": {"classroom_id": class_id, "subject_name": subject_name},
                "message": "Đang mở tài liệu môn học...",
                "should_auto_execute": True,
            }

        if intent_type == IntentClassifier.EXAM_GENERATION:
            return {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "exam",
                "params": {"classroom_id": class_id, "mode": "create"},
                "message": "Đang mở công cụ tạo đề thi...",
                "should_auto_execute": True,
            }

        return {
            "action_type": "show_chat",
            "target": "chat_panel",
            "params": {},
            "message": None,
            "should_auto_execute": False,
        }

    def get_missing_info_message(self, intent_type: str, missing_fields: List[str]) -> str:
        classifier = IntentClassifier()
        return classifier.get_missing_info_message(intent_type, missing_fields)
