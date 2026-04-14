"""
Intent classifier for the teacher agent.
Focuses only on the product domains:
- course_info
- class_overview
- class_analytics
- student_info
- material
- exam_generation
"""
import re
from typing import Any, Dict, List, Optional, Tuple


class IntentClassifier:
    COURSE_INFO = "course_info"
    CLASS_OVERVIEW = "class_overview"
    CLASS_ANALYTICS = "class_analytics"
    STUDENT_INFO = "student_info"
    MATERIAL = "material"
    EXAM_GENERATION = "exam_generation"
    GENERAL_QUESTION = "general_question"

    # Backward-compatible aliases used by older code paths.
    STUDENT_OVERVIEW = STUDENT_INFO
    DOCUMENT_MANAGEMENT = MATERIAL
    EXAM_CREATION = EXAM_GENERATION
    SUBJECT_MANAGEMENT = COURSE_INFO
    LEARNING_RESULTS = CLASS_ANALYTICS

    ACTION_TYPES = [
        COURSE_INFO,
        CLASS_OVERVIEW,
        CLASS_ANALYTICS,
        STUDENT_INFO,
        MATERIAL,
        EXAM_GENERATION,
        GENERAL_QUESTION,
    ]

    def __init__(self):
        self.keywords = {
            self.COURSE_INFO: [
                "môn", "mon", "subject", "course", "lớp nào", "bao nhiêu lớp", "có những lớp", "danh sách lớp",
                "lớp của môn", "course info", "thông tin môn", "thong tin mon",
            ],
            self.CLASS_OVERVIEW: [
                "tình hình lớp", "tinh hinh lop", "kết quả lớp", "ket qua lop", "trình độ lớp", "trinh do lop",
                "lớp học thế nào", "lop hoc the nao", "lớp x học thế nào", "class overview", "lớp ra sao",
                "lớp đó", "lớp này", "tóm tắt lớp", "tom tat lop",
            ],
            self.CLASS_ANALYTICS: [
                "phân tích lớp", "phan tich lop", "điểm trung bình", "diem trung binh", "tỷ lệ đỗ", "ty le do",
                "tỷ lệ trượt", "ty le truot", "phân bố điểm", "phan bo diem", "yếu", "yeu", "giỏi", "gioi",
                "lớp nào học tốt", "lớp nào kém", "so sánh lớp", "so sanh lop", "class analytics",
            ],
            self.STUDENT_INFO: [
                "sinh viên", "sinh vien", "học sinh", "hoc sinh", "student", "mssv", "học thế nào", "hoc the nao",
                "cần cải thiện", "can cai thien", "đang tham gia môn gì", "tham gia lớp nào",
            ],
            self.MATERIAL: [
                "tài liệu", "tai lieu", "học liệu", "hoc lieu", "document", "file", "thiếu tài liệu", "thieu tai lieu",
                "môn nào thiếu tài liệu", "cho tôi tài liệu", "cho toi tai lieu", "materials",
            ],
            self.EXAM_GENERATION: [
                "xuất đề", "xuat de", "tạo đề", "tao de", "trắc nghiệm", "trac nghiem", "2 mã đề", "2 ma de",
                "30 câu", "câu hỏi", "cau hoi", "exam", "quiz", "generate exam", "đề thi", "de thi",
            ],
        }

    def clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip().lower()

    def _score_intents(self, clean_msg: str) -> Tuple[str, float, List[str]]:
        scores: Dict[str, int] = {}
        matches: Dict[str, List[str]] = {}

        for intent_type, keywords in self.keywords.items():
            score = 0
            matched: List[str] = []
            for keyword in keywords:
                if keyword in clean_msg:
                    matched.append(keyword)
                    score += max(2, len(keyword))
            scores[intent_type] = score
            matches[intent_type] = matched

        # Strong phrase overrides for the most common cases.
        if "lớp" in clean_msg and any(term in clean_msg for term in ["học thế nào", "kết quả", "tình hình", "trình độ", "ra sao", "học tập"]):
            return self.CLASS_OVERVIEW, 0.95, matches.get(self.CLASS_OVERVIEW, [])

        if any(phrase in clean_msg for phrase in ["tình hình lớp", "kết quả lớp", "trình độ lớp", "lớp học thế nào", "lớp ra sao"]):
            return self.CLASS_OVERVIEW, 0.95, matches.get(self.CLASS_OVERVIEW, [])

        if any(phrase in clean_msg for phrase in ["điểm trung bình", "tỷ lệ đỗ", "tỷ lệ trượt", "phân bố điểm", "lớp nào học tốt", "lớp nào kém", "so sánh lớp"]):
            return self.CLASS_ANALYTICS, 0.96, matches.get(self.CLASS_ANALYTICS, [])

        if any(phrase in clean_msg for phrase in ["thiếu tài liệu", "cho tôi tài liệu", "cho toi tai lieu"]):
            return self.MATERIAL, 0.96, matches.get(self.MATERIAL, [])

        if any(phrase in clean_msg for phrase in ["xuất đề", "tạo đề", "2 mã đề", "30 câu", "trắc nghiệm", "đề thi"]):
            return self.EXAM_GENERATION, 0.97, matches.get(self.EXAM_GENERATION, [])

        if any(phrase in clean_msg for phrase in ["sinh viên", "học sinh", "student", "cần cải thiện", "học thế nào", "tham gia môn gì"]):
            return self.STUDENT_INFO, 0.94, matches.get(self.STUDENT_INFO, [])

        if any(phrase in clean_msg for phrase in ["môn nào", "có những lớp", "bao nhiêu lớp", "danh sách lớp", "lớp của môn"]):
            return self.COURSE_INFO, 0.95, matches.get(self.COURSE_INFO, [])

        if scores and max(scores.values()) > 0:
            intent_type = max(scores, key=scores.get)
            confidence = min(1.0, scores[intent_type] / 40.0)
            return intent_type, confidence, matches.get(intent_type, [])

        return self.GENERAL_QUESTION, 0.0, []

    def _extract_number(self, text: str, patterns: List[str]) -> Optional[int]:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    continue
        return None

    def extract_entities(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        context = context or {}
        clean_msg = self.clean_text(message)
        entities: Dict[str, Any] = {
            "subject_name": None,
            "class_name": None,
            "student_name": None,
            "student_identifier": None,
            "exam_type": None,
            "num_questions": None,
            "num_versions": None,
            "difficulty": None,
            "needs_follow_up": False,
        }

        quoted = re.findall(r'"([^"]+)"', message)
        if quoted:
            entities["student_name"] = quoted[0].strip()

        # Generic subject/class/student extraction from phrases after keywords.
        subject_patterns = [
            r"(?:môn học|mon hoc)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,80})",
            r"(?:môn|subject|course)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,80})",
            r"(?:của môn|cua mon)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,80})",
        ]
        class_patterns = [
            r"(?:lớp học|lop hoc)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,60})",
            r"(?:lớp|class)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,60})",
        ]
        student_patterns = [
            r"(?:sinh viên|học sinh|student)\s+([A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-_. ]{1,60})",
            r"(?:sinh viên|học sinh|student)\s+([A-Za-zÀ-ỹ0-9]+)",
        ]

        for pattern in subject_patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .,!?:;-")
                candidate = re.sub(r"^(?:học|hoc)\s+", "", candidate, flags=re.IGNORECASE)
                candidate = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+(?:môn|mon|lớp|lop|class)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,!?:;-")
                if candidate:
                    entities["subject_name"] = candidate
                    break

        for pattern in class_patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .,!?:;-")
                candidate = re.split(r"\b(?:cho|thuộc|thuoc|của|cua|trong)\s+(?:môn|mon|subject|course)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,!?:;-")
                if candidate:
                    entities["class_name"] = candidate
                    break

        for pattern in student_patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .,!?:;-")
                if candidate:
                    entities["student_name"] = candidate
                    break

        # Exam fields.
        if any(token in clean_msg for token in ["trắc nghiệm", "trac nghiem", "multiple choice"]):
            entities["exam_type"] = "multiple_choice"
        elif any(token in clean_msg for token in ["tự luận", "tu luan", "essay"]):
            entities["exam_type"] = "essay"
        elif any(token in clean_msg for token in ["hỗn hợp", "hon hop", "mixed"]):
            entities["exam_type"] = "mixed"

        num_questions = self._extract_number(clean_msg, [r"(\d+)\s*câu", r"(\d+)\s*question", r"(\d+)\s*questions"])
        if num_questions is not None:
            entities["num_questions"] = num_questions

        num_versions = self._extract_number(clean_msg, [r"(\d+)\s*mã đề", r"(\d+)\s*ma de", r"(\d+)\s*version", r"(\d+)\s*versions"])
        if num_versions is not None:
            entities["num_versions"] = num_versions

        difficulty = None
        if any(token in clean_msg for token in ["dễ", "de", "easy"]):
            difficulty = "easy"
        elif any(token in clean_msg for token in ["trung bình", "trung binh", "medium"]):
            difficulty = "medium"
        elif any(token in clean_msg for token in ["khó", "kho", "hard"]):
            difficulty = "hard"
        if difficulty:
            entities["difficulty"] = difficulty

        # Context fallback for follow-up turns.
        if not entities["subject_name"]:
            for key in ["last_subject_name", "last_subject"]:
                if context.get(key):
                    entities["subject_name"] = context.get(key)
                    break

        if not entities["class_name"] and context.get("last_class_name"):
            entities["class_name"] = context.get("last_class_name")

        if not entities["student_name"] and context.get("last_student_name"):
            entities["student_name"] = context.get("last_student_name")

        if any(pronoun in clean_msg for pronoun in ["nó", "đó", "do", "lớp đó", "môn đó", "sinh viên đó", "cái đó"]):
            entities["needs_follow_up"] = True

        return entities

    def classify_request(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        context = context or {}
        clean_msg = self.clean_text(message)
        intent_type, confidence, matched_keywords = self._score_intents(clean_msg)
        entities = self.extract_entities(message, context)

        # Keep the previous intent if the current message is clearly a follow-up.
        if intent_type == self.GENERAL_QUESTION and context.get("last_intent") in self.ACTION_TYPES:
            if entities["needs_follow_up"] or len(clean_msg.split()) <= 4:
                intent_type = context.get("last_intent")
                confidence = 0.35

        # Slight boost if the message explicitly mentions the previous subject/class/student.
        if context.get("last_subject_name") and context.get("last_subject_name").lower() in clean_msg:
            confidence = min(1.0, confidence + 0.05)
        if context.get("last_class_name") and context.get("last_class_name").lower() in clean_msg:
            confidence = min(1.0, confidence + 0.05)
        if context.get("last_student_name") and context.get("last_student_name").lower() in clean_msg:
            confidence = min(1.0, confidence + 0.05)

        required = self.get_required_info(intent_type, context)
        missing_fields = []
        for field in required.get("required", []):
            if field == "subject_name" and not entities.get("subject_name"):
                missing_fields.append(field)
            elif field == "class_name" and not entities.get("class_name"):
                missing_fields.append(field)
            elif field == "student_name" and not entities.get("student_name") and not entities.get("student_identifier"):
                missing_fields.append(field)
            elif field == "exam_type" and not entities.get("exam_type"):
                missing_fields.append(field)
            elif field == "num_questions" and not entities.get("num_questions"):
                missing_fields.append(field)
            elif field == "num_versions" and not entities.get("num_versions"):
                missing_fields.append(field)

        # Intent-specific, flexible missing info checks.
        if intent_type == self.COURSE_INFO and not entities.get("subject_name"):
            missing_fields.append("subject_name")
        elif intent_type == self.CLASS_OVERVIEW and not entities.get("class_name"):
            missing_fields.append("class_name")
        elif intent_type == self.CLASS_ANALYTICS and not (entities.get("class_name") or entities.get("subject_name")):
            missing_fields.append("class_or_subject")
        elif intent_type == self.STUDENT_INFO and not (entities.get("student_name") or entities.get("student_identifier")):
            missing_fields.append("student_name")
        elif intent_type == self.MATERIAL and not entities.get("subject_name") and not any(word in clean_msg for word in ["môn nào thiếu tài liệu", "thieu tai lieu"]):
            missing_fields.append("subject_name")
        elif intent_type == self.EXAM_GENERATION:
            if not entities.get("subject_name"):
                missing_fields.append("subject_name")
            if not entities.get("exam_type"):
                missing_fields.append("exam_type")
            if not entities.get("num_questions"):
                missing_fields.append("num_questions")
            if not entities.get("num_versions"):
                missing_fields.append("num_versions")

        needs_follow_up = bool(missing_fields)
        follow_up_question = None
        if needs_follow_up:
            follow_up_question = self.get_missing_info_message(intent_type, missing_fields)

        return {
            "intent_type": intent_type,
            "confidence": confidence,
            "matched_keywords": matched_keywords,
            "entities": entities,
            "required": required,
            "missing_fields": missing_fields,
            "needs_follow_up": needs_follow_up,
            "follow_up_question": follow_up_question,
        }

    def classify(self, message: str, context: Optional[Dict] = None) -> Tuple[str, float, List[str]]:
        result = self.classify_request(message, context)
        return result["intent_type"], result["confidence"], result["matched_keywords"]

    def get_required_info(self, intent_type: str, context: Optional[Dict] = None) -> Dict:
        context = context or {}
        requirements = {
            self.COURSE_INFO: {
                "required": ["subject_name"],
                "optional": [],
                "collected": {"last_subject_name": context.get("last_subject_name")},
            },
            self.CLASS_OVERVIEW: {
                "required": ["class_name"],
                "optional": [],
                "collected": {"last_class_name": context.get("last_class_name")},
            },
            self.CLASS_ANALYTICS: {
                "required": [],
                "optional": ["class_name", "subject_name"],
                "collected": {"last_class_name": context.get("last_class_name"), "last_subject_name": context.get("last_subject_name")},
            },
            self.STUDENT_INFO: {
                "required": ["student_name"],
                "optional": [],
                "collected": {"last_student_name": context.get("last_student_name")},
            },
            self.MATERIAL: {
                "required": ["subject_name"],
                "optional": [],
                "collected": {"last_subject_name": context.get("last_subject_name")},
            },
            self.EXAM_GENERATION: {
                "required": ["subject_name", "exam_type", "num_questions", "num_versions"],
                "optional": ["difficulty"],
                "collected": context.get("pending_exam_info", {}),
            },
            self.GENERAL_QUESTION: {
                "required": [],
                "optional": [],
                "collected": {},
            },
        }
        return requirements.get(intent_type, requirements[self.GENERAL_QUESTION])

    def get_missing_info_message(self, intent_type: str, missing_fields: List[str]) -> str:
        if intent_type == self.COURSE_INFO:
            return "Bạn chưa nêu rõ môn học. Ví dụ: 'Môn Cơ sở Hệ điều hành có những lớp nào?'"

        if intent_type == self.CLASS_OVERVIEW:
            return "Bạn chưa nêu rõ lớp học. Ví dụ: 'Lớp IT1 học thế nào?'"

        if intent_type == self.CLASS_ANALYTICS:
            return "Bạn chưa nêu rõ lớp hoặc môn cần phân tích. Ví dụ: 'Phân tích lớp IT1' hoặc 'Trong các lớp môn Toán thì lớp nào học tốt?'"

        if intent_type == self.STUDENT_INFO:
            return "Bạn chưa nêu rõ sinh viên. Ví dụ: 'Sinh viên A học thế nào?'"

        if intent_type == self.MATERIAL:
            return "Bạn chưa nêu rõ môn học cần xem tài liệu. Ví dụ: 'Cho tôi tài liệu môn Cơ sở Hệ điều hành'"

        if intent_type == self.EXAM_GENERATION:
            missing = ", ".join(missing_fields)
            return f"Bạn đang thiếu thông tin: {missing}. Ví dụ: 'Xuất đề trắc nghiệm môn Toán với 30 câu và 2 mã đề'"

        return "Bạn vui lòng bổ sung thêm thông tin để tôi xử lý chính xác hơn"
