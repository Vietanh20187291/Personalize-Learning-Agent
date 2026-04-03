import os
import json
import random
import re
import urllib.request
import urllib.error
from pathlib import Path
from sqlalchemy.orm import Session
from groq import Groq
import google.generativeai as genai
from dotenv import load_dotenv
from db.models import QuestionBank, LearnerProfile, Subject
from rag.vector_store import get_vector_store

load_dotenv()

class AssessmentAgent:
    def __init__(self, db: Session):
        self.db = db
        self.provider = os.getenv("ASSESSMENT_LLM_PROVIDER", "ollama").strip().lower()
        self.model = os.getenv(
            "ASSESSMENT_LLM_MODEL",
            "gemini-1.5-flash" if self.provider == "gemini" else "mixtral-8x7b-instruct",
        )
        self.ollama_fallback_model = os.getenv("ASSESSMENT_OLLAMA_FALLBACK_MODEL", "qwen2.5:14b")

        self.client = None
        self.api_key = os.getenv("GROQ_KEY_ASSESSMENT")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = None
        self.ollama_host = os.getenv("ASSESSMENT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        if self.provider == "groq":
            if not self.api_key:
                raise ValueError("Thiếu GROQ_KEY_ASSESSMENT cho provider=groq")
            self.client = Groq(api_key=self.api_key)
        elif self.provider == "gemini":
            if not self.gemini_api_key:
                print("⚠️ Thiếu GEMINI_API_KEY, fallback sang Ollama.")
                self.provider = "ollama"
                self.model = self.ollama_fallback_model
            else:
                try:
                    genai.configure(api_key=self.gemini_api_key)
                    self.gemini_model = genai.GenerativeModel(self.model)
                except Exception as e:
                    print(f"⚠️ Khởi tạo Gemini lỗi ({e}), fallback sang Ollama.")
                    self.provider = "ollama"
                    self.model = self.ollama_fallback_model

        self.vector_store = get_vector_store()

    def _chat_json(self, prompt: str, system_prompt: str, temperature: float, max_tokens: int):
        if self.provider == "groq":
            res = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = res.choices[0].message.content
            clean = re.sub(r'```json|```', '', raw).strip()
            return json.loads(clean)

        ollama_model = self.model
        if self.provider == "gemini":
            try:
                merged_prompt = f"{system_prompt}\n\n{prompt}"
                res = self.gemini_model.generate_content(
                    merged_prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                        "response_mime_type": "application/json",
                    },
                )
                raw = (getattr(res, "text", "") or "").strip()
                if not raw:
                    raise ValueError("Gemini trả về nội dung rỗng")
                clean = re.sub(r'```json|```', '', raw).strip()
                return json.loads(clean)
            except Exception as e:
                print(f"⚠️ Gemini lỗi ({e}), fallback sang Ollama.")
                ollama_model = self.ollama_fallback_model

        # Ollama (free local): gọi REST API, ép output JSON qua prompt.
        payload = {
            "model": ollama_model,
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

        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            clean = re.sub(r'```json|```', '', content).strip()
            return json.loads(clean)

    # ========================
    # SUBJECT HELPER
    # ========================
    def _resolve_subject_id(self, subject: str):
        sub = self.db.query(Subject).filter(Subject.name == subject).first()
        if sub:
            return sub.id

        sub = Subject(name=subject, description=f"Môn {subject}")
        self.db.add(sub)
        self.db.flush()
        return sub.id

    def _clean_text(self, text: str):
        return re.sub(r"\s+", " ", text or "").strip()

    def _is_meaningful_text(self, text: str, min_len: int = 10):
        t = self._clean_text(text)
        if len(t) < min_len:
            return False
        if not re.search(r"[A-Za-zÀ-ỹ]", t):
            return False
        if re.search(r"^(a|b|c|d)$", t.lower()):
            return False
        if re.search(r"[\uFFFD]", t):
            return False
        return True

    def _is_valid_question(self, q: str, concept: str):
        q_clean = self._clean_text(q).lower()
        c_clean = self._clean_text(concept).lower()

        if len(q_clean) < 18 or len(q_clean) > 260:
            return False
        if "_____" in q_clean or "chi tiết còn thiếu" in q_clean:
            return False
        if c_clean and c_clean not in q_clean and len(set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", q_clean)).intersection(set(re.findall(r"[A-Za-zÀ-ỹ0-9_]{4,}", c_clean)))) == 0:
            return False
        return True

    def _is_valid_options(self, options):
        if len(options) != 4:
            return False

        seen = set()
        for opt in options:
            clean = re.sub(r'^[A-D][\.)]', '', str(opt)).strip()
            low = clean.lower()
            if not self._is_meaningful_text(clean, min_len=8):
                return False
            if low in seen:
                return False
            seen.add(low)
        return True

    def _build_rag_context(self, subject: str, allowed_files=None):
        query = f"Tổng hợp tất cả khái niệm cốt lõi và chương mục của môn {subject}"

        # Chroma thường lưu metadata source dạng đường dẫn (vd: temp_uploads/file.pdf)
        # trong khi allowed_files chỉ là tên file. Vì vậy cần lọc mềm theo basename.
        docs = self.vector_store.similarity_search(query, k=120)

        if allowed_files:
            allowed_set = {self._clean_text(str(x)).lower() for x in allowed_files if self._clean_text(str(x))}
            filtered_docs = []
            for d in docs:
                src = self._clean_text(str((d.metadata or {}).get("source", ""))).lower()
                src_base = Path(src).name.lower() if src else ""
                if src in allowed_set or src_base in allowed_set:
                    filtered_docs.append(d)

            # Nếu lọc theo lớp bị rỗng do metadata lệch format, fallback dùng toàn bộ docs của môn.
            if filtered_docs:
                docs = filtered_docs

        if not docs:
            return ""

        lines = []
        seen = set()
        for d in docs:
            for raw_ln in (d.page_content or "").splitlines():
                ln = self._clean_text(raw_ln)
                if len(ln) < 20:
                    continue
                key = ln.lower()
                if key in seen:
                    continue
                seen.add(key)
                lines.append(ln)

        raw_context = "\n".join(lines)[:30000]
        return raw_context

    def _subject_domain_keywords(self, subject: str):
        subject_low = self._clean_text(subject).lower()
        base = {
            t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", subject_low)
        }
        domain_map = {
            "hệ điều hành": {
                "tiến trình", "process", "thread", "luồng", "deadlock", "bế tắc", "semaphore",
                "synchronization", "đồng bộ", "lập lịch", "cpu", "bộ nhớ", "page", "paging",
                "system call", "system calls", "interrupt", "kernel", "phân phối", "resource",
            },
            "cơ sở dữ liệu": {
                "sql", "schema", "table", "quan hệ", "ràng buộc", "truy vấn", "transaction",
                "normalization", "khóa", "index", "database", "cơ sở dữ liệu",
            },
            "mạng": {"tcp", "ip", "router", "switch", "protocol", "giao thức", "lan", "wan", "dns", "http", "https"},
            "lập trình": {"hàm", "biến", "mảng", "vòng lặp", "class", "object", "object-oriented", "thuật toán", "đệ quy"},
            "giải tích": {"đạo hàm", "tích phân", "limit", "hàm số", "giới hạn", "gradient"},
            "xác suất": {"biến ngẫu nhiên", "kỳ vọng", "phương sai", "xác suất", "phân phối"},
        }

        matched = set(base)
        for key, keywords in domain_map.items():
            if key in subject_low:
                matched.update(keywords)
        return matched

    def _fallback_concepts_for_subject(self, subject: str, limit: int = 12):
        subject_low = self._clean_text(subject).lower()
        fallback_map = {
            "hệ điều hành": [
                "Chức năng của hệ điều hành",
                "Khái niệm tiến trình",
                "Lập lịch CPU",
                "Đồng bộ tiến trình",
                "Bế tắc và phòng tránh bế tắc",
                "Quản lý bộ nhớ",
                "Phân trang và phân đoạn",
                "Hệ thống tệp",
            ],
            "cơ sở dữ liệu": [
                "Mô hình dữ liệu quan hệ",
                "Khóa chính và khóa ngoại",
                "Chuẩn hóa dữ liệu",
                "Giao dịch và tính ACID",
                "Chỉ mục và tối ưu truy vấn",
                "Ràng buộc toàn vẹn",
            ],
            "mạng": [
                "Mô hình OSI và TCP/IP",
                "Địa chỉ IP và subnet",
                "Giao thức TCP và UDP",
                "Định tuyến và chuyển mạch",
                "DNS và HTTP",
            ],
            "lập trình": [
                "Biến và kiểu dữ liệu",
                "Cấu trúc điều khiển",
                "Hàm và tham số",
                "Mảng và danh sách",
                "Lập trình hướng đối tượng",
            ],
        }

        concepts = []
        for key, vals in fallback_map.items():
            if key in subject_low:
                concepts.extend(vals)

        if not concepts:
            concepts = [
                f"Khái niệm nền tảng của {subject}",
                f"Nguyên lý cốt lõi của {subject}",
                f"Ứng dụng thực tiễn trong {subject}",
                f"Phân tích vấn đề trong {subject}",
            ]

        dedup = []
        seen = set()
        for c in concepts:
            k = self._clean_text(c).lower()
            if not k or k in seen:
                continue
            seen.add(k)
            dedup.append(self._clean_text(c))
        return dedup[:limit]

    def clean_rag(self, docs):
        subject = getattr(self, "_active_subject", "").strip()
        subject_keywords = self._subject_domain_keywords(subject)

        admin_keywords = [
            "giảng viên", "giáo viên", "gvc", "gv", "số điện thoại", "điện thoại", "liên hệ",
            "email", "tài liệu tham khảo", "tham khảo", "lịch học", "nội quy", "thời lượng",
            "mã học phần", "khoa", "bộ môn", "phòng học", "điểm danh", "họ và tên", "ngày", "tháng",
            "tài liệu", "slide", "pdf", "ppt", "docx", "chapter", "phần 1", "phần 2", "bài tập", "bài thực hành", "câu 2", "câu 3", "câu 4",
        ]
        noise_patterns = [
            r"\b\d{2,4}[\.\-\s]?\d{2,4}[\.\-\s]?\d{2,4}\b",
            r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
            r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
            r"[\uFFFD]{1,}",
        ]
        noise_verbs = ["nêu", "trình bày", "liệt kê", "mô tả", "giải thích", "hãy", "cho biết"]

        cleaned_sentences = []
        seen = set()
        for doc in docs or []:
            text = self._clean_text(getattr(doc, "page_content", ""))
            if not text:
                continue

            for raw_sentence in re.split(r"[\n\r。.!?;:]+", text):
                sentence = self._clean_text(raw_sentence)
                if len(sentence) < 30 or len(sentence) > 300:
                    continue

                low = sentence.lower()
                if any(v in low for v in noise_verbs):
                    continue
                if any(k in low for k in admin_keywords):
                    continue
                if any(re.search(p, sentence) for p in noise_patterns):
                    continue
                if not re.search(r"[A-Za-zÀ-ỹ]", sentence):
                    continue

                tokens = {t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", sentence)}
                domain_hints = {
                    "hệ điều hành", "tiến trình", "process", "thread", "luồng", "deadlock", "bế tắc",
                    "semaphore", "đồng bộ", "lập lịch", "cpu", "bộ nhớ", "kernel", "page", "paging",
                    "interrupt", "resource", "file", "memory", "processes",
                }
                if subject_keywords and not subject_keywords.intersection(tokens):
                    if not any(h in low for h in domain_hints):
                        continue

                if self._looks_like_admin_name_line(sentence):
                    continue

                key = low
                if key in seen:
                    continue
                seen.add(key)
                cleaned_sentences.append(sentence)

        return cleaned_sentences

    def _looks_like_admin_name_line(self, text: str):
        low = text.lower()
        if any(k in low for k in ["gv", "giảng viên", "giáo viên", "khoa", "bộ môn", "nội quy", "lịch học"]):
            return True
        if re.search(r"\b[A-ZÀ-Ỹ]{2,}(?:\s+[A-ZÀ-Ỹ]{2,}){1,4}\b", text) and re.search(r"\d", text):
            return True
        return False

    def clean_rag_content(self, docs):
        return self.clean_rag(docs)

    def _is_domain_consistent(self, text: str, subject: str):
        low = self._clean_text(text).lower()
        subject_keywords = self._subject_domain_keywords(subject)
        if any(k in low for k in subject_keywords):
            return True

        # Loại các từ khóa lệch domain phổ biến.
        cross_domain_blacklist = {
            "hệ điều hành": ["chemistry", "hóa", "phản ứng", "ml", "machine learning", "neural", "bayes", "enzyme"],
            "cơ sở dữ liệu": ["neural", "hóa", "sinh học", "di truyền"],
            "mạng": ["hóa", "phản ứng", "sinh học", "dna"],
        }
        for domain, blacklist in cross_domain_blacklist.items():
            if domain in subject.lower() and any(k in low for k in blacklist):
                return False
        return True

    def extract_concepts(self, clean_texts, subject=None):
        subject = subject or getattr(self, "_active_subject", "")
        concepts = []
        seen = set()
        subject_low = self._clean_text(subject).lower()
        subject_markers = self._subject_domain_keywords(subject)
        noise_concept_keywords = [
            "tanenbaum", "silberschatz", "nguyên lý hệ điều hành bộ môn", "tài liệu tham khảo",
            "phần 1", "phần 2", "bài tập", "ví dụ", "slide", "chapter", "mục lục", "nguồn", "tham khảo",
        ]

        for text in clean_texts or []:
            concept = self._rewrite_to_concept(text)
            concept = self._clean_text(concept)
            concept = re.sub(r"^[\-•\d\.\)\(]+\s*", "", concept).strip()
            concept = re.sub(r"\s+", " ", concept)
            if len(concept) < 8 or len(concept) > 120:
                continue
            if concept.lower() == self._clean_text(text).lower():
                continue
            if not re.search(r"[A-Za-zÀ-ỹ]", concept):
                continue
            if any(k in concept.lower() for k in noise_concept_keywords):
                continue
            if not self._is_domain_consistent(concept, subject):
                continue
            concept_tokens = {t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", concept)}
            if len(concept_tokens) < 2:
                continue
            if len(set(re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", concept.lower())).intersection(set(re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", self._clean_text(text).lower())))) > 12:
                continue

            key = concept.lower()
            if key in seen:
                continue
            seen.add(key)
            concepts.append(concept)

        return concepts

    def _rewrite_to_concept(self, sentence: str):
        text = self._clean_text(sentence)
        text = re.sub(r'^[\-•\d\.\)\(]+\s*', '', text)
        text = re.sub(r'^([A-ZÀ-Ỹ][^,]{0,80}?),\s*', '', text)

        lowered = text.lower()
        if any(k in lowered for k in ["tanenbaum", "silberschatz", "hà quang thụy", "có các hệ điều hành nào"]):
            return ""
        if "làm đầy đủ bài tập" in lowered or "bài thực hành" in lowered:
            return ""
        if "viết chương trình mô phỏng" in lowered and "bế tắc" in lowered:
            return "Phòng tránh bế tắc trong bài toán nhà triết học"
        if "một vị trí trong hệ thống bị hỏng" in lowered and "tiếp tục làm việc" in lowered:
            return "Khả năng chịu lỗi của hệ thống"
        if all(k in lowered for k in ["cpu", "bộ nhớ", "thiết bị ngoại vi"]):
            return "Thành phần của hệ thống máy tính"
        if "tiến trình (process) là gì" in lowered or ("tiến trình" in lowered and "chương trình đang được thực thi" in lowered):
            return "Khái niệm tiến trình"
        if "hệ điều hành có những chức năng gì" in lowered:
            return "Chức năng của hệ điều hành"
        if "hệ điều hành đóng vai trò gì" in lowered:
            return "Vai trò của hệ điều hành"
        if "nguyên lý cơ bản xây dựng hệ điều hành" in lowered:
            return "Nguyên lý xây dựng hệ điều hành"
        replacements = [
            (r'^(nêu|hãy|trình bày|giải thích|mô tả|cho biết|phân tích)\s+', ''),
            (r'^(trong môn|trong hệ thống|trong thực tế của môn)\s+.*?,\s*', ''),
            (r'\s+là gì\??$', ''),
            (r'\s+đóng vai trò gì\??$', ''),
            (r'\s+có những gì\??$', ''),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        if len(text) > 90:
            for marker in [" là gì", " là ", " gồm ", " bao gồm ", " có ", " được ", " giúp ", " đóng vai trò "]:
                pos = lowered.find(marker)
                if pos > 0:
                    candidate = self._clean_text(text[:pos])
                    if len(candidate) >= 6:
                        text = candidate
                        break

        if 'bao gồm' in lowered or 'gồm' in lowered:
            left = re.split(r'\b(?:bao gồm|gồm)\b', text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if left:
                text = f"Các thành phần của {left}"
        elif 'chức năng' in lowered and 'hệ điều hành' in lowered:
            text = 'Chức năng của hệ điều hành'
        elif 'hệ điều hành' in lowered and 'là gì' not in lowered:
            text = re.sub(r'\b(hệ điều hành)\b.*', r'\1', text, flags=re.IGNORECASE)
            text = self._clean_text(text)

        text = re.sub(r'\s+', ' ', text).strip(' .,:;"\'')
        text = re.sub(r'\b(tiến trình|hệ điều hành|luồng|bộ nhớ|bế tắc|đồng bộ|cpu|database|sql|mạng)\b.*$', r'\1', text, flags=re.IGNORECASE)

        # Cắt thêm các mô tả dài còn sót lại sau khi rewrite
        for marker in [" là một chương trình đang được thực thi", " là một nội dung", " giúp mô tả", " được dùng để", " thường được hiểu như thế nào"]:
            text = text.replace(marker, "")

        if len(text) > 120:
            text = text[:120].rsplit(" ", 1)[0]

        text = re.sub(r'\b(tan(enbaum)?|silberschatz|hà quang thụy)\b.*$', '', text, flags=re.IGNORECASE)
        text = self._clean_text(text)
        return text

    def generate_question(self, concept: str, subject: str, bloom_level: str = "understand"):
        concept = self._clean_text(concept)
        subject = self._clean_text(subject)
        bloom_level = (bloom_level or "understand").lower()

        templates = {
            "remember": [
                "Khái niệm nào sau đây phù hợp nhất với '{concept}'?",
                "Phát biểu nào mô tả đúng nhất về '{concept}'?",
            ],
            "understand": [
                "Trong môn '{subject}', '{concept}' được hiểu như thế nào?",
                "Mục tiêu chính của khái niệm '{concept}' là gì?",
            ],
            "apply": [
                "Trong tình huống thực tế của môn '{subject}', khái niệm '{concept}' được áp dụng như thế nào?",
                "Khi giải quyết một bài toán của môn '{subject}', cách sử dụng đúng của '{concept}' là gì?",
            ],
            "analyze": [
                "Điểm nào sau đây phân biệt đúng nhất '{concept}' với các khái niệm gần nghĩa trong môn '{subject}'?",
                "Yếu tố nào cho thấy '{concept}' đang được áp dụng đúng trong bối cảnh môn '{subject}'?",
            ],
        }

        question = random.choice(templates.get(bloom_level, templates["understand"]))
        question = question.format(concept=concept, subject=subject)

        correct = self._build_correct_answer(concept, subject, bloom_level)
        distractors = self._build_distractors(concept, subject, bloom_level)

        options_raw = [correct] + distractors[:3]
        if len(options_raw) < 4:
            options_raw.extend([f"Nội dung khác liên quan đến {subject}"] * (4 - len(options_raw)))

        order = [0, 1, 2, 3]
        random.shuffle(order)
        labels = ["A", "B", "C", "D"]
        final_options = []
        correct_label = "A"

        for pos, idx in enumerate(order):
            final_options.append(f"{labels[pos]}. {options_raw[idx]}")
            if idx == 0:
                correct_label = labels[pos]

        q = {
            "question": question,
            "options": final_options,
            "correct_answer": correct_label,
            "bloom_level": bloom_level,
            "explanation": f"Khái niệm trọng tâm: '{concept}'.",
        }
        return q

    def _build_correct_answer(self, concept: str, subject: str, bloom_level: str):
        concept = self._clean_text(concept)
        subject = self._clean_text(subject)
        if bloom_level == "remember":
            return f"{concept} là khái niệm cốt lõi trong môn {subject}."
        if bloom_level == "apply":
            return f"{concept} được dùng để xử lý tình huống thực tế của môn {subject}."
        if bloom_level == "analyze":
            return f"{concept} giúp phân tích cách hệ thống hoặc quá trình vận hành trong môn {subject}."
        return f"{concept} là nội dung giúp hiểu đúng các nguyên lý của môn {subject}."

    def _build_distractors(self, concept: str, subject: str, bloom_level: str):
        subject = self._clean_text(subject)
        concept = self._clean_text(concept)
        base = [
            f"Khái niệm này chỉ mang tính minh họa phụ và không quyết định bản chất của {subject}.",
            f"Nội dung này chủ yếu liên quan đến thủ tục hành chính thay vì kiến thức chuyên môn của {subject}.",
            f"Ý nghĩa của nội dung này thiên về mô tả bề mặt, không hỗ trợ xử lý vấn đề cốt lõi trong {subject}.",
            f"Phát biểu này nhấn mạnh thông tin phụ trợ hơn là nguyên lý vận hành chính trong {subject}.",
        ]
        if bloom_level == "analyze":
            base[1] = f"Phát biểu này chỉ phản ánh bề mặt của vấn đề và không cho thấy quan hệ cấu trúc bên trong."
        return base

    def validate_question(self, q):
        question = self._clean_text(q.get("question", ""))
        options = q.get("options", []) or []
        if len(options) != 4:
            return False
        if len(question) < 15:
            return False

        subject = getattr(self, "_active_subject", "")
        subject_low = subject.lower()
        forbidden_phrases = []
        q_tokens = set(re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", question.lower()))

        cleaned_opts = []
        for opt in options:
            opt_clean = self._clean_text(re.sub(r'^[A-D][\.)]\s*', '', str(opt)))
            if len(opt_clean) < 10:
                return False
            low = opt_clean.lower()
            if any(p in low for p in forbidden_phrases):
                return False
            if self._is_similar_to_question(question, opt_clean):
                return False
            cleaned_opts.append(opt_clean)

        if len(set(cleaned_opts)) != 4:
            return False

        if subject_low and not self._is_domain_consistent(question, subject):
            return False

        # Reject nếu các lựa chọn quá giống nhau về cấu trúc.
        token_sets = [set(re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", o.lower())) for o in cleaned_opts]
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                union = token_sets[i].union(token_sets[j])
                if union and len(token_sets[i].intersection(token_sets[j])) / len(union) > 0.85:
                    return False

        return True

    def _is_similar_to_question(self, question: str, option: str):
        q = self._clean_text(question).lower()
        o = self._clean_text(re.sub(r'^[A-D][\.)]\s*', '', str(option))).lower()
        if not q or not o:
            return False
        if o in q or q in o:
            return True
        q_tokens = {t for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", q)}
        o_tokens = {t for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{4,}", o)}
        if not q_tokens:
            return False
        overlap = len(q_tokens.intersection(o_tokens)) / max(len(q_tokens), 1)
        return overlap >= 0.95

    def generate_questions_from_concepts(self, concepts, count):
        subject = getattr(self, "_active_subject", "môn học")
        bloom_targets = self._build_bloom_schedule(count)
        questions = []
        used_questions = set()
        unique_concepts = []
        seen = set()

        for c in concepts or []:
            clean = self._clean_text(c)
            if len(clean) < 8:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_concepts.append(clean)

        if not unique_concepts:
            return []

        for index in range(count):
            concept = unique_concepts[index % len(unique_concepts)]
            bloom_level = bloom_targets[index % len(bloom_targets)]
            q = self.generate_question(concept, subject, bloom_level=bloom_level)
            if not self.validate_question(q):
                continue

            q_key = self._clean_text(q["question"]).lower()
            if q_key in used_questions:
                continue
            used_questions.add(q_key)
            questions.append(q)

        return questions

    def _build_bloom_schedule(self, count: int):
        if count <= 0:
            return []
        targets = [
            ("remember", max(1, round(count * 0.2))),
            ("understand", max(1, round(count * 0.3))),
            ("apply", max(1, round(count * 0.3))),
            ("analyze", max(1, round(count * 0.2))),
        ]
        schedule = []
        for level, amount in targets:
            schedule.extend([level] * amount)
        while len(schedule) < count:
            schedule.append("understand")
        return schedule[:count]

    # ========================
    # MAIN API
    # ========================
    def get_or_create_quiz(self, subject: str, user_id: int, num_questions: int = 20, allowed_files=None):
        self._resolve_subject_id(subject)

        # Nếu đã có thì lấy random
        existing_query = self.db.query(QuestionBank).filter(QuestionBank.subject == subject)
        if allowed_files:
            existing_query = existing_query.filter(QuestionBank.source_file.in_(allowed_files))
        existing = existing_query.all()

        if len(existing) >= num_questions:
            random.shuffle(existing)
            return self._format(existing[:num_questions])

        # Nếu chưa đủ → generate mới
        needed = num_questions - len(existing)
        print(f"🚀 Generating {needed} questions for subject: {subject}")

        self._generate_from_rag_concepts(subject, needed, allowed_files=allowed_files)

        questions_query = self.db.query(QuestionBank).filter(QuestionBank.subject == subject)
        if allowed_files:
            questions_query = questions_query.filter(QuestionBank.source_file.in_(allowed_files))
        questions = questions_query.all()

        random.shuffle(questions)
        return self._format(questions[:num_questions])

    # ========================
    # FORMAT OUTPUT
    # ========================
    def _format(self, questions):
        result = []
        for q in questions:
            try:
                options = json.loads(q.options)
            except:
                options = []

            bloom_level = "understand"
            explanation = q.explanation or ""
            bloom_match = re.match(r"\[bloom:(remember|understand|apply|analyze)\]\s*(.*)", explanation, re.IGNORECASE)
            if bloom_match:
                bloom_level = bloom_match.group(1).lower()
                explanation = bloom_match.group(2).strip()

            result.append({
                "id": q.id,
                "content": q.content,
                "options": options,
                "correct_answer": q.correct_answer,
                "bloom_level": bloom_level,
                "explanation": explanation
            })
        return result

    # ========================
    # CORE GENERATION (RAG CONCEPT -> MCQ)
    # ========================
    def _generate_from_rag_concepts(self, subject: str, count: int, allowed_files=None):
        try:
            subject_id = self._resolve_subject_id(subject)
            self._active_subject = subject
            rag_context = self._build_rag_context(subject, allowed_files=allowed_files)
            docs = [type("Doc", (), {"page_content": rag_context})()]
            clean_texts = self.clean_rag(docs)
            concepts = self.extract_concepts(clean_texts, subject)
            source_for_generated = allowed_files[0] if allowed_files else "AI_GENERATED"

            if not concepts:
                print("⚠️ Không trích xuất được concept từ RAG, dùng fallback concepts.")
                concepts = self._fallback_concepts_for_subject(subject, limit=max(8, count))

            generated = self.generate_questions_from_concepts(concepts, count)

            if not generated:
                # Fallback cuối: luôn đảm bảo có câu hỏi hợp lệ để không chặn luồng làm bài.
                fallback_concepts = self._fallback_concepts_for_subject(subject, limit=max(8, count))
                generated = self.generate_questions_from_concepts(fallback_concepts, count)

            inserted = 0
            used_questions = set()

            for mcq in generated:
                q = mcq["question"]
                final_opts = mcq["options"]
                ans = mcq["correct_answer"]
                bloom_level = mcq.get("bloom_level", "understand")
                exp = f"[bloom:{bloom_level}] {mcq.get('explanation', '')}"

                q_key = q.lower()
                if q_key in used_questions:
                    continue
                if self.db.query(QuestionBank).filter(QuestionBank.subject == subject, QuestionBank.content == q).first():
                    continue
                used_questions.add(q_key)

                db_q = QuestionBank(
                    subject_id=subject_id,
                    subject=subject,
                    difficulty="Basic",
                    content=q,
                    options=json.dumps(final_opts, ensure_ascii=False),
                    correct_answer=ans,
                    explanation=exp,
                    is_used=False,
                    source_file=source_for_generated
                )

                self.db.add(db_q)
                inserted += 1

            self.db.commit()
            print(f"✅ Generated {inserted} questions from {len(concepts)} concepts")

        except Exception as e:
            self.db.rollback()
            print(f"❌ Error: {e}")