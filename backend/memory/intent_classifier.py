"""
Intent Classifier - phân loại ý định của giảng viên
Giúp xác định giảng viên muốn làm gì: xem tình hình lớp, sinh viên, quản lý môn, tạo đề thi, etc.
"""
import re
from typing import Dict, List, Tuple, Optional

class IntentClassifier:
    """Phân loại ý định người dùng"""
    
    # Intent types
    CLASS_OVERVIEW = "class_overview"  # Tóm tắt lớp, điểm số, sinh viên
    STUDENT_OVERVIEW = "student_overview"  # Tóm tắt sinh viên cụ thể
    SUBJECT_MANAGEMENT = "subject_management"  # CRUD môn học
    EXAM_CREATION = "exam_creation"  # Tạo/xuất đề thi
    DOCUMENT_MANAGEMENT = "document_management"  # Quản lý tài liệu
    LEARNING_RESULTS = "learning_results"  # Xem kết quả học tập
    GENERAL_QUESTION = "general_question"  # Hỏi chung
    
    ACTION_TYPES = [
        CLASS_OVERVIEW,
        STUDENT_OVERVIEW,
        SUBJECT_MANAGEMENT,
        EXAM_CREATION,
        DOCUMENT_MANAGEMENT,
        LEARNING_RESULTS,
        GENERAL_QUESTION,
    ]
    
    def __init__(self):
        self.keywords = {
            self.CLASS_OVERVIEW: [
                "tình hình lớp", "tinh hinh lop", "tóm tắt lớp", "tom tat lop",
                "summary class", "class overview", "how is the class",
                "sĩ số", "si so", "average score", "điểm trung bình",
                "tất cả sinh viên", "tat ca sinh vien",
            ],
            self.STUDENT_OVERVIEW: [
                "sinh viên", "sinh vien", "học sinh", "hoc sinh", "student",
                "tóm tắt", "tom tat", "summary", "kết quả", "ket qua",
                "tình hình", "tinh hinh", "cách học", "cach hoc",
            ],
            self.SUBJECT_MANAGEMENT: [
                "quản lý môn", "quan ly mon", "add subject", "create subject",
                "xóa môn", "xoa mon", "delete subject", "edit subject",
                "sửa môn", "sua mon", "danh sách môn", "danh sach mon",
            ],
            self.EXAM_CREATION: [
                "tạo đề", "tao de", "create exam", "generate exam",
                "xuất đề", "xuat de", "export exam", "bài kiểm tra",
                "bai kiem tra", "quiz", "trắc nghiệm", "trac nghiem",
                "câu hỏi", "cau hoi", "exam", "test",
            ],
            self.DOCUMENT_MANAGEMENT: [
                "tài liệu", "tai lieu", "document", "file",
                "upload", "quản lý tài liệu", "quan ly tai lieu",
                "sửa tài liệu", "sua tai lieu", "xóa tài liệu", "xoa tai lieu",
            ],
            self.LEARNING_RESULTS: [
                "kết quả học tập", "ket qua hoc tap",
                "quản lý kết quả", "quan ly ket qua",
                "learning results", "grades", "điểm", "diem",
            ],
        }
    
    def clean_text(self, text: str) -> str:
        """Chuẩn hóa text"""
        return re.sub(r"\s+", " ", text or "").strip().lower()
    
    def classify(self, message: str, context: Dict = None) -> Tuple[str, float, List[str]]:
        """
        Phân loại ý định
        
        Args:
            message: Câu hỏi của giảng viên
            context: Ngữ cảnh từ Conversation Memory (optional)
        
        Returns:
            (intent_type, confidence, matched_keywords)
        """
        clean_msg = self.clean_text(message)
        context = context or {}
        
        # Tìm từ khóa phù hợp nhất
        scores = {}
        keyword_matches = {}
        
        for intent_type, keywords in self.keywords.items():
            score = 0
            matches = []
            for keyword in keywords:
                if keyword in clean_msg:
                    score += len(keyword)
                    matches.append(keyword)
            scores[intent_type] = score
            keyword_matches[intent_type] = matches
        
        # Nếu không tìm thấy từ khóa phù hợp, sử dụng context
        max_score = max(scores.values())
        if max_score == 0:
            # Sử dụng last_action_type từ context nếu có
            last_action = context.get("last_action_type")
            if last_action and last_action in self.ACTION_TYPES:
                # Giả định câu hỏi tiếp theo liên quan đến câu hỏi trước
                return (last_action, 0.3, [])
            
            return (self.GENERAL_QUESTION, 0.0, [])
        
        # Tìm intent có score cao nhất
        best_intent = max(scores, key=scores.get)
        confidence = min(1.0, max_score / 50.0)  # Normalize confidence
        
        return (best_intent, confidence, keyword_matches.get(best_intent, []))
    
    def extract_names(self, message: str) -> List[str]:
        """Trích xuất tên sinh viên/môn học từ message"""
        # Tìm các từ được dấu ngoặc kép hoặc sau "khoá" nhất định
        names = re.findall(r'"([^"]+)"', message)
        if not names:
            # Tìm các cụm từ Tiếng Việt (từ 2+ từ)
            words = message.split()
            for i in range(len(words) - 1):
                if self._looks_like_name(words[i]) and self._looks_like_name(words[i + 1]):
                    names.append(f"{words[i]} {words[i + 1]}")
        
        return names
    
    def _looks_like_name(self, word: str) -> bool:
        """Kiểm tra xem từ có vẻ như là một phần của tên không"""
        return len(word) > 1 and not any(keyword in word.lower() for keyword in [
            "vui", "lòng", "hãy", "cho", "tạo", "xóa", "sửa", "như", "nào"
        ])
    
    def get_required_info(self, intent_type: str, context: Dict = None) -> Dict:
        """
        Xác định thông tin cần thiết cho một intent cụ thể
        
        Returns:
            {
                "required": ["subject", "num_questions"],  # Bắt buộc
                "optional": ["num_versions"],  # Tùy chọn
                "collected": {...}  # Thông tin đã của context
            }
        """
        context = context or {}
        
        if intent_type == self.EXAM_CREATION:
            return {
                "required": ["subject", "exam_type"],
                "optional": ["num_questions", "num_versions", "difficulty"],
                "collected": context.get("pending_exam_info", {}),
            }
        
        if intent_type == self.SUBJECT_MANAGEMENT:
            return {
                "required": ["action"],  # "add", "edit", "delete"
                "optional": ["subject_name", "description"],
                "collected": {},
            }
        
        if intent_type == self.STUDENT_OVERVIEW:
            return {
                "required": ["student_identifier"],  # Tên hoặc MSSV
                "optional": [],
                "collected": {"last_student_asked": context.get("last_student_asked")},
            }
        
        return {
            "required": [],
            "optional": [],
            "collected": {},
        }
