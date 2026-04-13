import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.models import AssessmentHistory, Classroom, Document, User
from rag.vector_store import get_vector_store


class TeacherAgent:
    def __init__(self, db: Session):
        self.db = db
        self.provider = os.getenv("TEACHER_AGENT_LLM_PROVIDER", "ollama").strip().lower()

        default_model = "gpt-4o-mini" if self.provider == "openai" else "llama3"
        self.model = os.getenv("TEACHER_AGENT_MODEL", default_model).strip()

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url = os.getenv("TEACHER_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.openai_fallback_to_ollama = os.getenv("TEACHER_AGENT_OPENAI_FALLBACK_TO_OLLAMA", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }

        self.ollama_host = os.getenv("TEACHER_AGENT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv(
            "TEACHER_AGENT_OLLAMA_MODEL",
            os.getenv("ASSESSMENT_OLLAMA_FALLBACK_MODEL", "llama3"),
        ).strip()
        self.fallback_model = os.getenv("TEACHER_AGENT_FALLBACK_MODEL", "qwen2.5:14b").strip()
        self.request_timeout = int(os.getenv("TEACHER_AGENT_REQUEST_TIMEOUT", "20"))
        self.vector_store = get_vector_store()

    def _get_ollama_models(self):
        req = urllib.request.Request(
            f"{self.ollama_host}/api/tags",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", []) or []
                names = []
                for model in models:
                    name = str(model.get("name", "")).strip()
                    if name:
                        names.append(name)
                return names
        except Exception:
            return []

    def _check_ollama_available(self):
        return bool(self._get_ollama_models())

    def _clean_text(self, text: str):
        return re.sub(r"\s+", " ", text or "").strip()

    def _resolve_classroom(self, class_id: int, teacher_id: int):
        classroom = self.db.query(Classroom).filter(Classroom.id == class_id).first()
        if not classroom:
            raise ValueError("Không tìm thấy lớp học")
        if classroom.teacher_id != teacher_id:
            raise ValueError("Bạn không có quyền truy cập lớp học này")
        return classroom

    def _build_class_stats(self, classroom: Classroom):
        students = [student for student in classroom.students if getattr(student, "role", "student") == "student"]
        student_ids = [student.id for student in students]
        student_name_map = {student.id: self._clean_text(getattr(student, "full_name", "") or f"SV {student.id}") for student in students}

        if student_ids:
            histories = self.db.query(AssessmentHistory).filter(
                AssessmentHistory.user_id.in_(student_ids),
                AssessmentHistory.subject_id == classroom.subject_id,
            ).order_by(desc(AssessmentHistory.timestamp)).all()
        else:
            histories = []

        avg_score = 0.0
        if histories:
            avg_score = sum(float(item.score or 0) for item in histories) / len(histories)

        latest_scores = []
        latest_by_student: Dict[int, float] = {}
        seen_students = set()
        for item in histories:
            if item.user_id in seen_students:
                continue
            seen_students.add(item.user_id)
            score = float(item.score or 0)
            latest_scores.append(score)
            latest_by_student[item.user_id] = score

        score_bands = {"<40": 0, "40-60": 0, "60-80": 0, ">=80": 0}
        for score in latest_scores:
            if score < 40:
                score_bands["<40"] += 1
            elif score < 60:
                score_bands["40-60"] += 1
            elif score < 80:
                score_bands["60-80"] += 1
            else:
                score_bands[">=80"] += 1

        weak_students = []
        for uid, score in sorted(latest_by_student.items(), key=lambda x: x[1]):
            if score <= 55:
                weak_students.append({
                    "user_id": uid,
                    "name": student_name_map.get(uid, f"SV {uid}"),
                    "score": round(score, 1),
                })
        weak_students = weak_students[:5]

        weak_area_hint = "Chưa đủ dữ liệu đánh giá"
        if latest_scores:
            lowest = min(latest_scores)
            if lowest < 40:
                weak_area_hint = "Cần củng cố kiến thức nền tảng và ôn lại khái niệm cơ bản"
            elif lowest < 60:
                weak_area_hint = "Nên tăng bài tập vận dụng và kiểm tra nhanh theo chương"
            else:
                weak_area_hint = "Có thể nâng độ khó bài tập và chuyển sang bài phân tích"

        return {
            "student_count": len(students),
            "document_count": self.db.query(Document).filter(Document.class_id == classroom.id).count(),
            "history_count": len(histories),
            "avg_score": round(avg_score, 1),
            "weak_area_hint": weak_area_hint,
            "score_bands": score_bands,
            "weak_students": weak_students,
        }

    def _detect_intent(self, message: str):
        low = self._clean_text(message).lower()
        if (
            any(k in low for k in ["tình hình lớp", "tinh hinh lop", "lớp", "class", "sĩ số", "si so"])
            and any(k in low for k in ["tóm tắt", "tom tat", "summary", "đề xuất", "de xuat"])
        ):
            return "class_overview"
        if (
            any(k in low for k in ["học sinh", "hoc sinh", "sinh viên", "sinh vien", "student"])
            and any(k in low for k in ["tóm tắt", "tom tat", "tình hình", "ket qua", "kết quả", "cải thiện", "cai thien"])
        ):
            return "student_overview"
        if any(k in low for k in ["đề", "quiz", "câu hỏi", "kiểm tra", "trắc nghiệm"]):
            return "quiz"
        if any(k in low for k in ["tóm tắt", "tom tat", "summary", "nội dung tài liệu", "hoc lieu"]):
            return "summary"
        if any(k in low for k in ["điểm yếu", "yeu", "phân tích", "phan tich", "cải thiện", "cai thien"]):
            return "analysis"
        if any(k in low for k in ["kế hoạch", "ke hoach", "lộ trình", "lo trinh", "buổi tới", "buoi toi"]):
            return "plan"
        return "general"

    def _calc_trend(self, scores: List[float]):
        if len(scores) < 2:
            return 0.0
        return round(float(scores[-1]) - float(scores[0]), 1)

    def _find_student_in_class(self, classroom: Classroom, message: str):
        clean_msg = self._clean_text(message).lower()
        candidates = []
        for student in classroom.students:
            if getattr(student, "role", "student") != "student":
                continue
            full_name = self._clean_text(getattr(student, "full_name", ""))
            username = self._clean_text(getattr(student, "username", ""))
            student_code = self._clean_text(getattr(student, "student_id", ""))

            keys = [full_name.lower(), username.lower(), student_code.lower()]
            score = 0
            for key in keys:
                if key and key in clean_msg:
                    score += len(key)
            if score > 0:
                candidates.append((score, student))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _build_student_overview(self, student: User):
        enrolled_classes = [c for c in getattr(student, "enrolled_classes", []) if getattr(student, "id", None)]
        class_count = len(enrolled_classes)

        histories = (
            self.db.query(AssessmentHistory)
            .filter(AssessmentHistory.user_id == student.id)
            .order_by(AssessmentHistory.timestamp.asc())
            .all()
        )

        total_tests = len(histories)
        scores = [float(h.score or 0) for h in histories]
        overall_avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        trend = self._calc_trend(scores)

        by_subject: Dict[str, List[float]] = {}
        for item in histories:
            subject_name = self._clean_text(getattr(item, "subject", "")) or (
                self._clean_text(getattr(getattr(item, "subject_obj", None), "name", ""))
            ) or "Chưa rõ môn"
            by_subject.setdefault(subject_name, []).append(float(item.score or 0))

        subject_avgs: List[Tuple[str, float]] = []
        for subject_name, subject_scores in by_subject.items():
            if not subject_scores:
                continue
            subject_avgs.append((subject_name, round(sum(subject_scores) / len(subject_scores), 1)))
        subject_avgs.sort(key=lambda x: x[1], reverse=True)

        strongest_subject = subject_avgs[0] if subject_avgs else ("Chưa đủ dữ liệu", 0.0)
        weakest_subject = subject_avgs[-1] if subject_avgs else ("Chưa đủ dữ liệu", 0.0)

        recent_scores = scores[-5:] if len(scores) > 5 else scores
        recent_avg = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else 0.0

        return {
            "class_count": class_count,
            "total_tests": total_tests,
            "overall_avg": overall_avg,
            "recent_avg": recent_avg,
            "trend": trend,
            "strongest_subject": strongest_subject,
            "weakest_subject": weakest_subject,
        }

    def _extract_key_phrases(self, context: str, limit: int = 6):
        tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", (context or "").lower())
        stop = {
            "trong", "được", "các", "những", "theo", "với", "cho", "của", "một", "này",
            "that", "this", "from", "with", "have", "will", "about", "trên", "dưới",
        }
        freq: Dict[str, int] = {}
        for token in tokens:
            if token in stop or token.isdigit():
                continue
            freq[token] = freq.get(token, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in ranked[:limit]]

    def _rule_based_reply(self, classroom: Classroom, message: str, stats: dict, allowed_files: List[str], context: str):
        intent = self._detect_intent(message)
        avg_score = float(stats.get("avg_score", 0))
        weak_students = stats.get("weak_students", []) or []
        score_bands = stats.get("score_bands", {}) or {}
        top_terms = self._extract_key_phrases(context, limit=6)

        if intent == "class_overview":
            weakest_group = ", ".join(
                [f"{item['name']} ({item['score']})" for item in weak_students[:3]]
            ) if weak_students else "chưa xác định vì thiếu dữ liệu điểm gần nhất"
            docs_text = ", ".join(allowed_files[:3]) if allowed_files else "chưa có tài liệu"
            reply = (
                f"Tình hình lớp {classroom.name}: có {stats.get('student_count', 0)} sinh viên, "
                f"{stats.get('document_count', 0)} tài liệu đã upload, điểm trung bình hiện tại {avg_score:.1f}. "
                f"Phân bố điểm gần nhất: <40 là {score_bands.get('<40', 0)}, 40-60 là {score_bands.get('40-60', 0)}, "
                f"60-80 là {score_bands.get('60-80', 0)}, >=80 là {score_bands.get('>=80', 0)}. "
                f"Nhóm cần hỗ trợ ngay: {weakest_group}. Tài liệu tiêu biểu: {docs_text}."
            )
            actions = [
                "Mở phụ đạo 20 phút cho nhóm dưới 60 điểm trong buổi gần nhất",
                "Ra 1 mini-quiz 8-10 câu cho 3 chủ điểm trọng tâm của lớp",
                "Chốt checklist đầu ra buổi tới và đối chiếu lại sau khi kiểm tra nhanh",
            ]
            return reply, actions

        if intent == "student_overview":
            target_student = self._find_student_in_class(classroom, message)
            if not target_student:
                sample_names = [
                    self._clean_text(getattr(s, "full_name", ""))
                    for s in classroom.students
                    if getattr(s, "role", "student") == "student"
                ]
                sample_text = ", ".join([n for n in sample_names[:5] if n]) or "chưa có danh sách"
                reply = (
                    f"Mình chưa xác định được học sinh cụ thể trong lớp {classroom.name}. "
                    f"Bạn hãy nêu rõ họ tên hoặc mã sinh viên. Danh sách gợi ý: {sample_text}."
                )
                actions = [
                    "Gửi lại yêu cầu kèm đúng tên học sinh (ví dụ: ABX)",
                    "Có thể kèm MSSV để nhận diện chính xác hơn",
                    "Sau khi xác định học sinh, mình sẽ tóm tắt kết quả và đề xuất cải thiện",
                ]
                return reply, actions

            student_data = self._build_student_overview(target_student)
            strong_name, strong_score = student_data["strongest_subject"]
            weak_name, weak_score = student_data["weakest_subject"]
            trend_text = (
                "đang cải thiện" if student_data["trend"] > 3 else
                "giảm nhẹ" if student_data["trend"] < -3 else
                "đang ổn định"
            )
            student_label = self._clean_text(getattr(target_student, "full_name", "")) or self._clean_text(getattr(target_student, "username", ""))

            reply = (
                f"Tình hình học tập của {student_label}: đã tham gia {student_data['class_count']} lớp, "
                f"có {student_data['total_tests']} bài đánh giá, điểm trung bình toàn bộ {student_data['overall_avg']:.1f} "
                f"(5 bài gần nhất {student_data['recent_avg']:.1f}) và xu hướng {trend_text}. "
                f"Môn mạnh nhất hiện tại: {strong_name} ({strong_score:.1f}). "
                f"Môn cần cải thiện: {weak_name} ({weak_score:.1f})."
            )
            actions = [
                f"Cho {student_label} luyện 2 bài ngắn bám môn {weak_name} trong tuần này",
                "Đặt mốc kiểm tra lại sau 7 ngày bằng quiz 10 câu",
                "Kèm 1 phiên ôn tập cá nhân theo lỗi sai thường gặp",
            ]
            return reply, actions

        if intent == "quiz":
            if avg_score < 45:
                mix = "60% nhớ-hiểu, 30% vận dụng cơ bản, 10% phân tích"
            elif avg_score < 65:
                mix = "35% nhớ-hiểu, 45% vận dụng, 20% phân tích"
            else:
                mix = "20% nhớ-hiểu, 45% vận dụng, 35% phân tích"

            reply = (
                f"Đề xuất cho lớp {classroom.name}: tạo quiz 12-15 câu theo tỉ lệ {mix}. "
                f"Ưu tiên bám 3 chủ điểm xuất hiện nhiều trong tài liệu: {', '.join(top_terms[:3]) if top_terms else 'khái niệm cốt lõi của môn học'}. "
                f"Kết thúc bằng 2 câu phân tích lỗi sai thường gặp để đo mức hiểu thật."
            )
            actions = [
                "Sinh 15 câu trắc nghiệm theo Bloom cho buổi tới",
                "Tạo 1 mini-quiz 5 câu mở đầu để rà lại kiến thức nền",
                "Lưu kết quả quiz để so sánh trước/sau buổi học",
            ]
            return reply, actions

        if intent == "summary":
            docs_text = ", ".join(allowed_files[:5]) if allowed_files else "chưa có tài liệu"
            focus_text = ", ".join(top_terms[:5]) if top_terms else "chưa trích được từ khóa nổi bật"
            reply = (
                f"Tóm tắt nhanh lớp {classroom.name}: có {stats.get('student_count', 0)} sinh viên, "
                f"điểm trung bình {avg_score:.1f}, hiện có {stats.get('document_count', 0)} tài liệu ({docs_text}). "
                f"Các trọng tâm nên dạy: {focus_text}. "
                f"Nên chia buổi học theo nhịp 15-20-15 phút: ôn nền, luyện vận dụng, chốt lỗi sai."
            )
            actions = [
                "Yêu cầu agent tạo dàn ý slide theo 3 trọng tâm",
                "Tạo checklist kiến thức tối thiểu cần đạt sau buổi",
                "Soạn 3 câu hỏi khởi động và 3 câu hỏi kết thúc buổi",
            ]
            return reply, actions

        if intent == "analysis":
            weak_text = (
                "; ".join([f"{item['name']} ({item['score']})" for item in weak_students[:3]])
                if weak_students
                else "Chưa có danh sách cụ thể từ dữ liệu hiện tại"
            )
            reply = (
                f"Phân tích lớp {classroom.name}: điểm TB {avg_score:.1f}, phân bố điểm "
                f"<{score_bands.get('<40', 0)} | 40-60:{score_bands.get('40-60', 0)} | 60-80:{score_bands.get('60-80', 0)} | >=80:{score_bands.get('>=80', 0)}. "
                f"Nhóm cần hỗ trợ ưu tiên: {weak_text}."
            )
            actions = [
                "Tổ chức nhóm phụ đạo 20 phút cho SV <=55 điểm",
                "Thiết kế 1 worksheet chỉ tập trung các lỗi sai chính",
                "Đánh giá lại sau 1 buổi bằng mini-quiz 8 câu",
            ]
            return reply, actions

        if intent == "plan":
            reply = (
                f"Kế hoạch buổi tới cho lớp {classroom.name}: 10 phút ôn nhanh, 25 phút dạy trọng tâm, "
                f"20 phút luyện bài tập theo cặp, 10 phút kiểm tra nhanh. "
                f"Giữ trọng tâm ở: {', '.join(top_terms[:3]) if top_terms else 'nội dung chính của tài liệu lớp'}."
            )
            actions = [
                "Chuẩn bị mục tiêu học tập theo 3 mức: đạt, khá, tốt",
                "Tạo 2 bài tập tình huống bám tài liệu lớp",
                "Chốt buổi bằng 5 câu exit ticket",
            ]
            return reply, actions

        reply = (
            f"Tôi đã tổng hợp dữ liệu lớp {classroom.name}: {stats.get('student_count', 0)} sinh viên, "
            f"{stats.get('document_count', 0)} tài liệu, điểm TB {avg_score:.1f}. "
            f"Bạn có thể yêu cầu theo 4 hướng: tóm tắt tài liệu, tạo quiz, phân tích điểm yếu, hoặc lập kế hoạch buổi học."
        )
        actions = [
            "Tóm tắt học liệu chính của lớp",
            "Đề xuất bộ câu hỏi kiểm tra theo mức độ",
            "Phân tích nhóm sinh viên cần hỗ trợ",
        ]
        return reply, actions

    def _build_relevant_context(self, classroom: Classroom, message: str, allowed_files: List[str]):
        query = f"{classroom.subject}. {classroom.name}. {message}"
        try:
            docs = self.vector_store.similarity_search(query, k=30, filter={"subject": {"$eq": classroom.subject}})
        except Exception:
            docs = []

        allowed_set = {self._clean_text(str(name)).lower() for name in allowed_files if self._clean_text(str(name))}
        filtered_docs = []
        for doc in docs:
            source = self._clean_text(str((doc.metadata or {}).get("source", ""))).lower()
            source_base = Path(source).name.lower() if source else ""
            if not allowed_set or source in allowed_set or source_base in allowed_set:
                filtered_docs.append(doc)

        docs = filtered_docs or docs

        snippets = []
        seen = set()
        for doc in docs:
            text = self._clean_text(getattr(doc, "page_content", ""))
            if len(text) < 25:
                continue
            compact = text[:320]
            key = compact.lower()
            if key in seen:
                continue
            seen.add(key)
            snippets.append(compact)

        return "\n".join(snippets[:8])

    def _chat_json_openai(self, system_prompt: str, prompt: str, temperature: float = 0.2, max_tokens: int = 900):
        if not self.openai_api_key:
            raise RuntimeError("Thiếu OPENAI_API_KEY cho TEACHER_AGENT_LLM_PROVIDER=openai")

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        req = urllib.request.Request(
            f"{self.openai_base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            clean = re.sub(r"```json|```", "", str(content)).strip()
            if not clean:
                raise RuntimeError("OpenAI trả về nội dung rỗng")
            return json.loads(clean)

    def _chat_json_ollama(self, system_prompt: str, prompt: str, temperature: float = 0.2, max_tokens: int = 900):
        model_names = self._get_ollama_models()
        if not model_names:
            raise RuntimeError("Ollama chưa sẵn sàng hoặc chưa có model")

        # Ưu tiên model được cấu hình; nếu không có thì thử fallback; cuối cùng lấy model đầu tiên sẵn có.
        candidates = [self.ollama_model, self.model, self.fallback_model]
        for common in ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "llama3:8b", "mistral:7b"]:
            candidates.append(common)
        for available in model_names:
            candidates.append(available)

        ordered = []
        seen = set()
        for c in candidates:
            k = self._clean_text(str(c))
            if not k or k in seen:
                continue
            seen.add(k)
            ordered.append(k)

        def call_ollama(model_name: str):
            payload = {
                "model": model_name,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }

            req = urllib.request.Request(
                f"{self.ollama_host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("message", {}).get("content", "")
                clean = re.sub(r"```json|```", "", content).strip()
                return json.loads(clean)

        last_exc = None
        for model_name in ordered:
            try:
                return call_ollama(model_name)
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc or RuntimeError("Không gọi được model Ollama")

    def _chat_json(self, system_prompt: str, prompt: str, temperature: float = 0.2, max_tokens: int = 900):
        if self.provider == "openai":
            try:
                return self._chat_json_openai(system_prompt, prompt, temperature=temperature, max_tokens=max_tokens)
            except Exception:
                if not self.openai_fallback_to_ollama:
                    raise
                return self._chat_json_ollama(system_prompt, prompt, temperature=temperature, max_tokens=max_tokens)

        return self._chat_json_ollama(system_prompt, prompt, temperature=temperature, max_tokens=max_tokens)

    def respond(self, teacher_id: int, class_id: int, message: str):
        classroom = self._resolve_classroom(class_id, teacher_id)
        stats = self._build_class_stats(classroom)
        documents = self.db.query(Document).filter(Document.class_id == classroom.id).all()
        allowed_files = [doc.filename for doc in documents if doc.filename]
        intent = self._detect_intent(message)

        # Các truy vấn tóm tắt lớp/học sinh cần phản hồi nhanh và bám số liệu thật,
        # không phụ thuộc vector search hay LLM để tránh trả lời lệch trọng tâm.
        if intent in {"class_overview", "student_overview"}:
            fallback_reply, fallback_actions = self._rule_based_reply(
                classroom=classroom,
                message=message,
                stats=stats,
                allowed_files=allowed_files,
                context="",
            )
            return {
                "reply": fallback_reply,
                "suggested_actions": fallback_actions,
                "class_name": classroom.name,
                "subject": classroom.subject,
            }

        context = self._build_relevant_context(classroom, message, allowed_files)

        if not context:
            context = "Chưa có đủ ngữ cảnh từ tài liệu lớp. Hãy hỏi về cách tổ chức buổi học, kiểm tra, hoặc tải thêm tài liệu lên lớp."

        document_names = ", ".join(allowed_files[:10]) if allowed_files else "Chưa có tài liệu"

        system_prompt = (
            "Bạn là trợ lý AI cho giảng viên đại học. "
            "Nhiệm vụ là hỗ trợ giảng viên ra quyết định dạy học dựa trên dữ liệu lớp, tài liệu và tình hình học tập. "
            "Trả lời ngắn gọn, thực dụng, có hành động rõ ràng. "
            "Không bịa dữ liệu ngoài thông tin được cung cấp. "
            "Luôn trả về JSON hợp lệ với 2 khóa: reply và suggested_actions."
        )

        prompt = f"""
Thông tin lớp học:
- Tên lớp: {classroom.name}
- Môn học: {classroom.subject}
- Số sinh viên: {stats['student_count']}
- Số tài liệu: {stats['document_count']}
- Số bản ghi đánh giá: {stats['history_count']}
- Điểm trung bình gần nhất: {stats['avg_score']}
- Gợi ý chuyên môn: {stats['weak_area_hint']}

Danh sách tài liệu:
{document_names}

Ngữ cảnh tài liệu liên quan:
{context[:10000]}

Câu hỏi của giảng viên:
{message}

Quy tắc ưu tiên:
- Nếu câu hỏi yêu cầu tóm tắt tình hình lớp: bắt buộc nêu rõ số sinh viên, điểm trung bình, số tài liệu và nhận xét ngắn về nhóm cần hỗ trợ.
- Nếu câu hỏi yêu cầu tóm tắt học sinh cụ thể: bắt buộc nêu số lớp đã tham gia, kết quả học tập (điểm TB/xu hướng), môn mạnh và môn cần cải thiện.
- Tuyệt đối không trả lời lệch sang tạo quiz nếu người dùng đang yêu cầu tóm tắt tình hình.

Yêu cầu đầu ra:
1) reply: trả lời trực tiếp, tối đa 180 từ, ưu tiên hướng dẫn thực thi.
2) suggested_actions: mảng 3 phần tử, mỗi phần tử là một hành động ngắn giảng viên có thể làm ngay.

Trả về đúng schema:
{{
  "reply": "...",
  "suggested_actions": ["...", "...", "..."]
}}
""".strip()

        try:
            data = self._chat_json(system_prompt, prompt)
            reply = self._clean_text(str(data.get("reply", "")))
            suggested_actions = data.get("suggested_actions", [])
            if not isinstance(suggested_actions, list):
                suggested_actions = []
            suggested_actions = [self._clean_text(str(item)) for item in suggested_actions if self._clean_text(str(item))][:3]

            if not reply:
                reply = f"Tôi đã tổng hợp dữ liệu lớp {classroom.name}. Bạn có thể yêu cầu cụ thể hơn để tôi đề xuất bài kiểm tra, roadmap, hoặc phân tích tài liệu."

            if not suggested_actions:
                suggested_actions = [
                    "Yêu cầu agent tóm tắt tài liệu lớp",
                    "Đề xuất 5 câu hỏi kiểm tra theo môn học",
                    "Phân tích điểm yếu của lớp dựa trên lịch sử học tập",
                ]

            return {
                "reply": reply,
                "suggested_actions": suggested_actions,
                "class_name": classroom.name,
                "subject": classroom.subject,
            }
        except Exception as exc:
            fallback_reply, fallback_actions = self._rule_based_reply(
                classroom=classroom,
                message=message,
                stats=stats,
                allowed_files=allowed_files,
                context=context,
            )
            return {
                "reply": fallback_reply,
                "suggested_actions": fallback_actions,
                "class_name": classroom.name,
                "subject": classroom.subject,
                "error": str(exc),
            }