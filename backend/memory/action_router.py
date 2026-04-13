"""
Action Router - xác định hành động UI cần thực hiện dựa trên intent
"""
from typing import Dict, Optional
from .intent_classifier import IntentClassifier

class ActionRouter:
    """Định tuyến hành động sang các UI component phù hợp"""
    
    def __init__(self):
        self.classifier = IntentClassifier()
    
    def route_action(self, intent_type: str, context: Dict = None, class_id: int = None, student_name: str = None) -> Dict:
        """
        Tính toán hành động UI cần thực hiện
        
        Returns:
            {
                "action_type": "navigate" | "open_tab" | "show_modal" | "highlight",
                "target": Nhắm tới component nào (tab_name, modal_type, v.v.),
                "params": Dữ liệu truyền sang component {class_id, student_id, subject_id, ...},
                "message": Thông báo đưa ra người dùng,
                "should_auto_execute": Boolean - có tự động thực hiện không,
            }
        """
        context = context or {}
        
        if intent_type == IntentClassifier.CLASS_OVERVIEW:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "class_analytics",
                "params": {
                    "classroom_id": class_id,
                },
                "message": f"Đang mở bảng điều khiển lớp học...",
                "should_auto_execute": True,
            }
        
        elif intent_type == IntentClassifier.STUDENT_OVERVIEW:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "student_detailed",
                "params": {
                    "classroom_id": class_id,
                    "student_name": student_name,
                },
                "message": f"Đang tìm thông tin chi tiết của sinh viên...",
                "should_auto_execute": True,
            }
        
        elif intent_type == IntentClassifier.SUBJECT_MANAGEMENT:
            return {
                "action_type": "open_tab",
                "target": "admin",
                "tab_name": "subjects",
                "params": {},
                "message": "Đang mở bảng quản lý môn học...",
                "should_auto_execute": True,
            }
        
        elif intent_type == IntentClassifier.EXAM_CREATION:
            return {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "exam",
                "params": {
                    "classroom_id": class_id,
                    "mode": "create",
                },
                "message": "Đang mở công cụ tạo đề thi, bạn cần cung cấp: Môn học, loại đề (trắc nghiệm/tự luận/hỗn hợp), số câu hỏi, số mã đề",
                "should_auto_execute": True,
            }
        
        elif intent_type == IntentClassifier.DOCUMENT_MANAGEMENT:
            return {
                "action_type": "open_tab",
                "target": "teacher",
                "tab_name": "documents",
                "params": {
                    "classroom_id": class_id,
                },
                "message": "Đang mở bảng quản lý tài liệu...",
                "should_auto_execute": True,
            }
        
        elif intent_type == IntentClassifier.LEARNING_RESULTS:
            return {
                "action_type": "open_tab",
                "target": "learning_results",
                "tab_name": "class_analytics",
                "params": {
                    "classroom_id": class_id,
                },
                "message": "Đang mở bảng quản lý kết quả học tập...",
                "should_auto_execute": True,
            }
        
        else:  # GENERAL_QUESTION
            return {
                "action_type": "show_chat",
                "target": "chat_panel",
                "params": {},
                "message": None,
                "should_auto_execute": False,
            }
    
    def get_missing_info_message(self, intent_type: str, missing_fields: list) -> str:
        """Tạo tin nhắn yêu cầu thông tin còn thiếu"""
        
        if intent_type == IntentClassifier.EXAM_CREATION:
            if "subject" in missing_fields:
                return "Bạn chưa nêu rõ môn học. Ví dụ: 'Tạo đề trắc nghiệm môn Cơ sở hệ điều hành'"
            if "exam_type" in missing_fields:
                return "Bạn chưa nêu loại đề thi. Hãy chọn: trắc nghiệm, tự luận, hoặc hỗn hợp"
            if "num_questions" in missing_fields:
                return "Bạn chưa nêu số câu hỏi. Ví dụ: '20 câu trắc nghiệm'"
        
        if intent_type == IntentClassifier.STUDENT_OVERVIEW:
            if "student_identifier" in missing_fields:
                return "Bạn chưa nêu rõ sinh viên nào. Vui lòng cung cấp tên hoặc MSSV"
        
        return "Vui lòng cung cấp thêm thông tin chi tiết"
