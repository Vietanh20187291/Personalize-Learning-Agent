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
            "gpt-4o-mini"
            if self.provider == "openai"
            else ("gemini-1.5-flash" if self.provider == "gemini" else "mixtral-8x7b-instruct"),
        )
        self.ollama_fallback_model = os.getenv("ASSESSMENT_OLLAMA_FALLBACK_MODEL", "qwen2.5:14b")
        self.openai_api_key = os.getenv("ASSESSMENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.openai_base_url = os.getenv("ASSESSMENT_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.openai_fallback_to_ollama = os.getenv("ASSESSMENT_OPENAI_FALLBACK_TO_OLLAMA", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }

        self.client = None
        self.api_key = os.getenv("GROQ_KEY_ASSESSMENT")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = None
        self.ollama_host = os.getenv("ASSESSMENT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        if self.provider == "groq":
            if not self.api_key:
                raise ValueError("Thiếu GROQ_KEY_ASSESSMENT cho provider=groq")
            self.client = Groq(api_key=self.api_key)
        elif self.provider == "openai":
            if not self.openai_api_key:
                raise ValueError("Thiếu OPENAI_API_KEY/ASSESSMENT_OPENAI_API_KEY cho provider=openai")
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

        try:
            self.vector_store = get_vector_store()
        except Exception as exc:
            print(f"⚠️ AssessmentAgent fallback mode (vector store unavailable): {exc}")
            self.vector_store = None

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

        if self.provider == "openai":
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

            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")
                    clean = re.sub(r'```json|```', '', str(raw)).strip()
                    return json.loads(clean)
            except Exception as e:
                if not self.openai_fallback_to_ollama:
                    raise
                print(f"⚠️ OpenAI lỗi ({e}), fallback sang Ollama.")

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
        if self.vector_store is None:
            return ""

        query = f"Tổng hợp tất cả khái niệm cốt lõi và chương mục của môn {subject}"

        # Chroma thường lưu metadata source dạng đường dẫn (vd: temp_uploads/file.pdf)
        # trong khi allowed_files chỉ là tên file. Vì vậy cần lọc mềm theo basename.
        try:
            docs = self.vector_store.similarity_search(query, k=120)
        except Exception as exc:
            print(f"⚠️ AssessmentAgent không truy xuất được RAG context: {exc}")
            return ""

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

    def _is_academic_sentence(self, sentence: str, subject: str):
        low = self._clean_text(sentence).lower()
        if len(low) < 25:
            return False

        academic_blacklist = [
            "phương pháp học", "cách học", "ôn tập", "đáp án", "trắc nghiệm",
            "mục tiêu học", "mục tiêu môn học", "giảng viên", "giáo viên", "khoa", "bộ môn",
            "lịch học", "học phần", "môn học", "hướng dẫn", "ghi chú", "tài liệu tham khảo",
            "slide", "pdf", "docx", "ppt", "điểm danh", "email", "liên hệ",
        ]
        if any(token in low for token in academic_blacklist):
            return False

        if any(token in low for token in ["bài tập lớn", "bài tập về nhà", "phương pháp ôn", "cách làm bài", "mẹo làm bài"]):
            return False

        subject_low = self._clean_text(subject).lower()
        if subject_low and subject_low in low:
            return True

        subject_keywords = self._subject_domain_keywords(subject)
        tokens = {t.lower() for t in re.findall(r"[A-Za-zÀ-ỹ0-9]{2,}", low)}
        if subject_keywords.intersection(tokens):
            return True

        return self._is_domain_consistent(low, subject)

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
            "lưu trữ và phân tích dữ liệu": {
                "lưu trữ", "phân tích", "dữ liệu", "khai phá", "kho dữ liệu", "truy vấn", "chuẩn hóa",
                "biểu diễn", "xử lý", "mô hình", "bảng", "dataset",
            },
            "lập trình hướng đối tượng": {
                "class", "object", "đối tượng", "lớp", "kế thừa", "đa hình", "đóng gói", "trừu tượng",
                "constructor", "method", "property", "interface",
            },
            "cấu trúc dữ liệu và giải thuật": {
                "mảng", "stack", "queue", "ngăn xếp", "hàng đợi", "cây", "đồ thị", "tìm kiếm",
                "sắp xếp", "độ phức tạp", "thuật toán", "linked list", "hash", "heap",
            },
            "an toàn và bảo mật thông tin": {
                "mã hóa", "xác thực", "phân quyền", "băm", "tấn công", "lỗ hổng", "chữ ký số",
                "bảo mật", "an toàn", "kiểm soát truy cập", "cipher", "hash",
            },
            "quản trị công nghệ": {
                "quản trị", "công nghệ", "chiến lược", "quy trình", "dự án", "nguồn lực", "vận hành",
                "chuyển đổi số", "hệ thống", "tổ chức", "điều phối",
            },
            "toán rời rạc": {
                "tập hợp", "quan hệ", "hàm", "logic", "mệnh đề", "đồ thị", "tổ hợp", "suy diễn",
                "quy nạp", "vị từ", "hoán vị", "chỉnh hợp",
            },
            "xử lý dữ liệu đa phương tiện": {
                "ảnh", "âm thanh", "video", "nén", "lọc", "pixel", "codec", "định dạng",
                "độ phân giải", "bitrate", "màu sắc", "tín hiệu",
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
            "lưu trữ và phân tích dữ liệu": [
                "Khái niệm lưu trữ dữ liệu",
                "Mục tiêu của phân tích dữ liệu",
                "Quy trình xử lý dữ liệu",
                "Tổ chức và truy vấn dữ liệu",
                "Tiền xử lý dữ liệu",
                "Trực quan hóa dữ liệu",
                "Khai phá dữ liệu",
                "Kho dữ liệu",
            ],
            "lập trình hướng đối tượng": [
                "Lớp và đối tượng",
                "Đóng gói trong OOP",
                "Kế thừa trong OOP",
                "Đa hình trong OOP",
                "Trừu tượng trong OOP",
                "Constructor và destructor",
            ],
            "cấu trúc dữ liệu và giải thuật": [
                "Mảng và danh sách liên kết",
                "Ngăn xếp và hàng đợi",
                "Cây nhị phân",
                "Đồ thị và duyệt đồ thị",
                "Sắp xếp và tìm kiếm",
                "Độ phức tạp thuật toán",
                "Băm và bảng băm",
            ],
            "an toàn và bảo mật thông tin": [
                "Nguyên tắc an toàn thông tin",
                "Mã hóa và giải mã",
                "Xác thực và phân quyền",
                "Hàm băm mật mã",
                "Chữ ký số",
                "Các mối đe dọa an ninh phổ biến",
            ],
            "quản trị công nghệ": [
                "Chiến lược công nghệ",
                "Quản lý nguồn lực công nghệ",
                "Vận hành hệ thống",
                "Quản trị dự án công nghệ",
                "Chuyển đổi số trong tổ chức",
            ],
            "toán rời rạc": [
                "Mệnh đề và logic",
                "Tập hợp và quan hệ",
                "Hàm và ánh xạ",
                "Quy nạp toán học",
                "Tổ hợp và hoán vị",
                "Lý thuyết đồ thị",
            ],
            "xử lý dữ liệu đa phương tiện": [
                "Biểu diễn ảnh số",
                "Xử lý âm thanh số",
                "Xử lý video số",
                "Kỹ thuật nén dữ liệu",
                "Lọc và biến đổi tín hiệu",
                "Độ phân giải và bitrate",
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

        # Bổ sung concept tổng quát để luôn đủ số lượng câu hỏi fallback khi startup warmup.
        suffix_seeds = [
            "mục tiêu học tập",
            "thành phần cốt lõi",
            "quy trình thực hành",
            "lỗi thường gặp",
            "tiêu chí đánh giá",
            "ứng dụng thực tế",
            "so sánh mô hình",
            "nguyên tắc thiết kế",
            "chiến lược tối ưu",
            "tình huống vận dụng",
            "phân tích rủi ro",
            "kịch bản kiểm thử",
            "bài toán điển hình",
            "mẫu triển khai",
            "thực hành nâng cao",
            "bài học tổng kết",
        ]
        idx = 0
        while len(dedup) < limit:
            seed = suffix_seeds[idx % len(suffix_seeds)]
            candidate = self._clean_text(f"{subject} - {seed} #{idx + 1}")
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                dedup.append(candidate)
            idx += 1

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
                if not self._is_academic_sentence(sentence, subject):
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
            if not self._is_academic_sentence(concept, subject):
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

        if getattr(self, "_disable_llm_generation", False):
            return self._generate_mcq_fallback(concept, subject, bloom_level)

        llm_q = self._generate_mcq_with_llm(concept, subject, bloom_level)
        if llm_q:
            return llm_q

        return self._generate_mcq_fallback(concept, subject, bloom_level)

    def _generate_mcq_with_llm(self, concept: str, subject: str, bloom_level: str):
        system_prompt = (
            "Bạn là chuyên gia thiết kế câu hỏi trắc nghiệm đại học. "
            "Bắt buộc tạo 1 câu hỏi chất lượng cao kiểm tra hiểu biết thực sự, không dùng diễn đạt mơ hồ. "
            "Cấm dùng các cụm như: 'khái niệm này', 'nội dung này', 'quan trọng', 'cốt lõi', 'nền tảng', 'thiết yếu'. "
            "Các phương án phải cùng kiểu nội dung, độ dài gần tương đương, khác nghĩa rõ ràng, và chỉ có 1 đáp án đúng."
        )

        prompt = f"""
Sinh 1 câu hỏi MCQ cho môn "{subject}", concept "{concept}", bloom_level "{bloom_level}".

Yêu cầu bắt buộc:
1) Câu hỏi phải cụ thể, có nội dung học thuật, kiểm tra hiểu biết thật.
2) Có đúng 4 lựa chọn.
3) Mỗi lựa chọn là một ý riêng biệt, không được chỉ đổi từ đồng nghĩa.
4) Nhiễu phải là hiểu sai phổ biến hoặc áp dụng sai nhưng hợp lý.
5) Không chứa nội dung hành chính, meta, hoặc diễn đạt chung chung.

Trả về JSON đúng schema:
{{
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_index": 0,
  "explanation": "..."
}}
""".strip()

        for _ in range(3):
            try:
                data = self._chat_json(prompt, system_prompt, temperature=0.2, max_tokens=900)
            except Exception:
                continue

            question = self._clean_text(str(data.get("question", "")))
            options = data.get("options", [])
            if not isinstance(options, list):
                continue

            options = [self._clean_text(str(o)) for o in options[:4]]
            if len(options) != 4:
                continue

            try:
                correct_index = int(data.get("correct_index", -1))
            except Exception:
                correct_index = -1
            if correct_index < 0 or correct_index > 3:
                continue

            explanation = self._clean_text(str(data.get("explanation", f"Khái niệm trọng tâm: {concept}.")))

            labels = ["A", "B", "C", "D"]
            final_options = [f"{labels[i]}. {options[i]}" for i in range(4)]
            q = {
                "question": question,
                "options": final_options,
                "correct_answer": labels[correct_index],
                "bloom_level": bloom_level,
                "explanation": explanation,
            }

            if self.validate_question(q):
                return q

        return None

    def _generate_mcq_fallback(self, concept: str, subject: str, bloom_level: str):
        concept_low = self._clean_text(concept).lower()
        concept_clean = self._clean_text(concept)
        bloom_level = (bloom_level or "understand").lower()
        mappings = [
            (
                ["tiến trình", "process"],
                "tiến trình",
                [
                    "Tiến trình là chương trình đang thực thi, có không gian địa chỉ và trạng thái riêng.",
                    "Tiến trình là vùng đệm I/O dùng chung cho mọi chương trình trong hệ điều hành.",
                    "Tiến trình là giao thức mạng dùng để đồng bộ dữ liệu giữa các máy tính.",
                    "Tiến trình là bảng ánh xạ tĩnh giữa địa chỉ logic và địa chỉ vật lý.",
                ],
                0,
            ),
            (
                ["lớp", "object", "đối tượng", "oop", "kế thừa", "đa hình", "đóng gói"],
                "lập trình hướng đối tượng",
                [
                    "Lập trình hướng đối tượng tổ chức chương trình quanh lớp và đối tượng để mô hình hóa thực thể thực tế.",
                    "Lập trình hướng đối tượng chỉ là kỹ thuật sắp xếp dữ liệu theo thứ tự thời gian xử lý.",
                    "Lập trình hướng đối tượng là cơ chế truyền dữ liệu giữa các máy chủ qua mạng TCP.",
                    "Lập trình hướng đối tượng bắt buộc mọi hàm phải viết dưới dạng đệ quy để tăng tốc.",
                ],
                0,
            ),
            (
                ["mảng", "danh sách", "stack", "queue", "cây", "đồ thị", "thuật toán"],
                "cấu trúc dữ liệu và giải thuật",
                [
                    "Mảng, danh sách liên kết, ngăn xếp, hàng đợi và đồ thị là các cấu trúc dữ liệu cơ bản.",
                    "Cấu trúc dữ liệu chỉ dùng để lưu tệp đa phương tiện mà không ảnh hưởng đến xử lý thuật toán.",
                    "Giải thuật chỉ là cách đặt tên biến trong chương trình mà không liên quan đến độ phức tạp.",
                    "Cây nhị phân là một giao thức mạng dùng để định tuyến dữ liệu giữa các nút.",
                ],
                0,
            ),
            (
                ["lưu trữ", "phân tích", "dữ liệu", "kho dữ liệu", "khai phá"],
                "lưu trữ và phân tích dữ liệu",
                [
                    "Lưu trữ và phân tích dữ liệu nhấn mạnh việc tổ chức dữ liệu, truy vấn và rút ra tri thức hữu ích.",
                    "Lưu trữ dữ liệu chỉ là lưu văn bản hướng dẫn học tập của giảng viên.",
                    "Phân tích dữ liệu là thao tác viết lại tài liệu theo ngôn ngữ đơn giản mà không cần dữ liệu.",
                    "Kho dữ liệu là một kiểu cáp mạng dùng để kết nối máy chủ với thiết bị ngoại vi.",
                ],
                0,
            ),
            (
                ["bảo mật", "an toàn", "mã hóa", "xác thực", "phân quyền", "hash"],
                "an toàn và bảo mật thông tin",
                [
                    "An toàn thông tin bao gồm xác thực, phân quyền, mã hóa và kiểm soát truy cập.",
                    "An toàn thông tin chỉ là đặt mật khẩu dài hơn cho mọi tệp PDF.",
                    "Mã hóa là cách tăng dung lượng ổ cứng để lưu dữ liệu lâu hơn.",
                    "Phân quyền nghĩa là cho mọi người dùng toàn bộ quyền truy cập như nhau.",
                ],
                0,
            ),
            (
                ["quản trị", "công nghệ", "chuyển đổi số", "dự án", "vận hành"],
                "quản trị công nghệ",
                [
                    "Quản trị công nghệ tập trung vào chiến lược, nguồn lực, quy trình và vận hành hệ thống.",
                    "Quản trị công nghệ là cách viết code theo phong cách nhiều màu sắc nhất có thể.",
                    "Chuyển đổi số chỉ là đổi tên tài liệu sang tiếng Anh.",
                    "Vận hành hệ thống không liên quan đến con người, quy trình hay tài nguyên.",
                ],
                0,
            ),
            (
                ["logic", "mệnh đề", "tập hợp", "quan hệ", "đồ thị", "quy nạp"],
                "toán rời rạc",
                [
                    "Toán rời rạc nghiên cứu mệnh đề, tập hợp, quan hệ, đồ thị và các cấu trúc rời rạc khác.",
                    "Toán rời rạc chủ yếu là phép tính liên tục trên đạo hàm và tích phân.",
                    "Lý thuyết đồ thị là kỹ thuật nén ảnh trong đa phương tiện.",
                    "Quy nạp toán học chỉ áp dụng cho lưu trữ tệp văn bản.",
                ],
                0,
            ),
            (
                ["ảnh", "âm thanh", "video", "nén", "pixel", "codec"],
                "xử lý dữ liệu đa phương tiện",
                [
                    "Xử lý dữ liệu đa phương tiện gồm biểu diễn, nén, lọc và biến đổi ảnh, âm thanh, video.",
                    "Xử lý đa phương tiện chỉ là chỉnh sửa tên file cho ngắn hơn.",
                    "Pixel là một kiểu cấu trúc dữ liệu để lưu bảng băm.",
                    "Codec chỉ dùng để phân quyền truy cập tài liệu trong lớp học.",
                ],
                0,
            ),
            (
                ["deadlock", "bế tắc"],
                "bế tắc",
                [
                    "Các tiến trình giữ tài nguyên và chờ tài nguyên khác theo vòng phụ thuộc khép kín.",
                    "Bộ lập lịch ưu tiên tiến trình có thời gian CPU ngắn nhất trong mọi chu kỳ.",
                    "Hệ thống tăng kích thước bộ nhớ đệm để giảm số lần truy cập đĩa.",
                    "Tiến trình giải phóng toàn bộ tài nguyên ngay khi vào trạng thái chờ I/O.",
                ],
                0,
            ),
            (
                ["lập lịch", "cpu scheduling"],
                "lập lịch CPU",
                [
                    "Tối ưu thông lượng và thời gian đáp ứng bằng cách phân phối CPU hợp lý giữa tiến trình.",
                    "Loại bỏ hoàn toàn ngắt phần cứng để CPU chạy liên tục một tiến trình duy nhất.",
                    "Biến mọi truy cập bộ nhớ ảo thành truy cập trực tiếp đến đĩa cứng.",
                    "Ép mọi tiến trình dùng cùng một mức ưu tiên để tránh chuyển ngữ cảnh.",
                ],
                0,
            ),
        ]

        selected = None
        for keys, topic, opts, correct_idx in mappings:
            if any(k in concept_low for k in keys):
                selected = (topic, opts, correct_idx)
                break

        stem_by_bloom = {
            "remember": "Phát biểu nào mô tả đúng nhất về {topic} trong {subject}?",
            "understand": "Nhận định nào phản ánh đúng bản chất học thuật của {topic} trong {subject}?",
            "apply": "Trong tình huống thực hành, lựa chọn nào áp dụng đúng {topic} của {subject}?",
            "analyze": "Lựa chọn nào phân tích đúng cơ chế vận hành của {topic} trong {subject}?",
        }
        stem = stem_by_bloom.get(bloom_level, stem_by_bloom["understand"])

        if not selected:
            topic = concept
            q_text = stem.format(topic=topic, subject=subject)
            opts = [
                f"{concept} mô tả một nguyên tắc hoặc cơ chế kỹ thuật dùng để giải quyết bài toán trọng tâm của {subject}.",
                f"{concept} là giao thức tầng vận chuyển, chỉ xử lý truyền dữ liệu giữa các máy tính trong mạng diện rộng.",
                f"{concept} là thành phần phần cứng chuyên dụng, tự vận hành hệ thống mà không cần cơ chế quản lý phần mềm.",
                f"{concept} là kỹ thuật mã hóa khóa công khai, mục tiêu chính là xác thực người dùng và bảo mật truyền tin.",
            ]
            correct_idx = 0
        else:
            topic, opts, correct_idx = selected
            question_topic = concept if self._clean_text(topic).lower() == self._clean_text(subject).lower() else topic
            q_text = stem.format(topic=question_topic, subject=subject)

            # Giảm trùng bộ đáp án fallback: gắn ngữ cảnh theo concept hiện tại.
            opts = [
                f"{self._clean_text(opts[0])} Trọng tâm: {concept_clean}.",
                f"{self._clean_text(opts[1])} Trong ngữ cảnh {concept_clean}.",
                f"{self._clean_text(opts[2])} Khi xét {concept_clean}.",
                f"{self._clean_text(opts[3])} Trong phạm vi {concept_clean}.",
            ]

        labels = ["A", "B", "C", "D"]
        q = {
            "question": self._clean_text(q_text),
            "options": [f"{labels[i]}. {self._clean_text(opts[i])}" for i in range(4)],
            "correct_answer": labels[correct_idx],
            "bloom_level": bloom_level,
            "explanation": f"Phương án đúng phản ánh chính xác nội hàm học thuật của '{concept}'.",
        }
        return q

    def _is_option_too_generic(self, text: str):
        low = self._clean_text(text).lower()
        banned_fragments = [
            "khái niệm này",
            "nội dung này",
            "thông tin này",
            "quan trọng",
            "cốt lõi",
            "nền tảng",
            "thiết yếu",
        ]
        return any(p in low for p in banned_fragments)

    def _option_fingerprint(self, text: str):
        low = self._clean_text(text).lower()
        low = re.sub(r"\b(quan trọng|cốt lõi|nền tảng|thiết yếu)\b", "core", low)
        low = re.sub(r"\b(khái niệm|nội dung|thông tin)\b", "item", low)
        tokens = re.findall(r"[a-zà-ỹ0-9]{3,}", low)
        stop = {"trong", "của", "và", "được", "một", "những", "các", "cho", "với", "the", "that", "this"}
        return {t for t in tokens if t not in stop}

    def _normalize_option_text(self, option: str):
        text = self._clean_text(str(option))
        text = re.sub(r"^[A-D][\.)]\s*", "", text, flags=re.IGNORECASE)
        return self._clean_text(text).lower()

    def _option_signature(self, options):
        normalized = [self._normalize_option_text(opt) for opt in (options or [])]
        return "|".join(normalized)

    def _question_pool_has_low_diversity(self, rows):
        if not rows:
            return True

        signatures = []
        for row in rows:
            try:
                parsed = json.loads(row.options) if isinstance(row.options, str) else (row.options or [])
            except Exception:
                parsed = []
            if not isinstance(parsed, list) or len(parsed) != 4:
                continue
            signatures.append(self._option_signature(parsed))

        if not signatures:
            return True

        unique_signatures = set(signatures)
        if len(unique_signatures) <= max(2, len(signatures) // 5):
            return True

        most_common_count = max(signatures.count(sig) for sig in unique_signatures)
        if most_common_count >= max(4, int(len(signatures) * 0.6)):
            return True

        return False

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
            if self._is_option_too_generic(opt_clean):
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

        # Reject nếu các lựa chọn gần như cùng ý nghĩa (chỉ đổi từ đồng nghĩa/đảo cú pháp).
        fp_sets = [self._option_fingerprint(o) for o in cleaned_opts]
        for i in range(len(fp_sets)):
            for j in range(i + 1, len(fp_sets)):
                union = fp_sets[i].union(fp_sets[j])
                if union and len(fp_sets[i].intersection(fp_sets[j])) / len(union) > 0.75:
                    return False

        lengths = [len(o) for o in cleaned_opts]
        if min(lengths) == 0:
            return False
        if max(lengths) / min(lengths) > 2.2:
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
        used_option_signatures = set()
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

        attempts = 0
        max_attempts = max(count * 8, 40)
        while len(questions) < count and attempts < max_attempts:
            concept = unique_concepts[attempts % len(unique_concepts)]
            bloom_level = bloom_targets[attempts % len(bloom_targets)]
            attempts += 1

            q = self.generate_question(concept, subject, bloom_level=bloom_level)
            if not self.validate_question(q):
                continue

            q_key = self._clean_text(q["question"]).lower()
            if q_key in used_questions:
                continue

            option_signature = self._option_signature(q.get("options", []))
            if option_signature in used_option_signatures:
                continue

            used_questions.add(q_key)
            used_option_signatures.add(option_signature)
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

        # Student flow chỉ đọc câu hỏi đã được sinh sẵn trong DB.
        existing_query = self.db.query(QuestionBank).filter(QuestionBank.subject == subject)
        if allowed_files:
            existing_query = existing_query.filter(QuestionBank.source_file.in_(allowed_files))
        existing = existing_query.all()

        if not existing:
            return []

        random.shuffle(existing)
        return self._format(existing[:num_questions])

    def pre_generate_questions_for_document(self, subject: str, source_file: str, count: int = 20, force_refresh: bool = True):
        subject = self._clean_text(subject)
        source_file = self._clean_text(source_file)
        if not subject or not source_file:
            return []

        subject_id = self._resolve_subject_id(subject)
        self._active_subject = subject

        existing_rows = self.db.query(QuestionBank).filter(
            QuestionBank.subject == subject,
            QuestionBank.source_file == source_file,
        ).all()

        should_refresh = force_refresh
        if not should_refresh:
            should_refresh = len(existing_rows) < count or self._question_pool_has_low_diversity(existing_rows)

        if should_refresh:
            self.db.query(QuestionBank).filter(
                QuestionBank.subject == subject,
                QuestionBank.source_file == source_file,
            ).delete(synchronize_session=False)
            self.db.commit()
        else:
            return self._format(existing_rows[:count])

        previous_llm_flag = getattr(self, "_disable_llm_generation", False)
        self._disable_llm_generation = previous_llm_flag

        try:
            concepts = []
            try:
                rag_context = self._build_rag_context(subject, allowed_files=[source_file])
                docs = [type("Doc", (), {"page_content": rag_context})()]
                clean_texts = self.clean_rag(docs)
                concepts = self.extract_concepts(clean_texts, subject)
            except Exception as exc:
                print(f"⚠️ Pre-generate fallback for {source_file}: {exc}")

            if not concepts:
                concepts = self._fallback_concepts_for_subject(subject, limit=max(8, count))

            generated = self.generate_questions_from_concepts(concepts, count)
            if not generated:
                generated = self.generate_questions_from_concepts(
                    self._fallback_concepts_for_subject(subject, limit=max(8, count)),
                    count,
                )

            if len(generated) < count:
                supplemental_concepts = self._fallback_concepts_for_subject(subject, limit=max(count * 2, 16))
                supplemental = self.generate_questions_from_concepts(
                    supplemental_concepts,
                    count - len(generated),
                )
                combined = []
                seen_questions = set()
                for mcq in generated + supplemental:
                    question_text = self._clean_text(mcq.get("question", ""))
                    if not question_text:
                        continue
                    question_key = question_text.lower()
                    if question_key in seen_questions:
                        continue
                    seen_questions.add(question_key)
                    combined.append(mcq)
                generated = combined[:count]

            saved_questions = []
            seen = set()
            for mcq in generated:
                q = self._clean_text(mcq.get("question", ""))
                if not q or q.lower() in seen:
                    continue
                seen.add(q.lower())

                final_opts = mcq.get("options", [])
                ans = mcq.get("correct_answer", "A")
                bloom_level = mcq.get("bloom_level", "understand")
                exp = f"[bloom:{bloom_level}] {mcq.get('explanation', '')}"

                db_q = QuestionBank(
                    subject_id=subject_id,
                    subject=subject,
                    difficulty="Basic",
                    content=q,
                    options=json.dumps(final_opts, ensure_ascii=False),
                    correct_answer=ans,
                    explanation=exp,
                    is_used=False,
                    source_file=source_file,
                )
                self.db.add(db_q)
                self.db.flush()
                saved_questions.append({
                    "id": db_q.id,
                    "content": db_q.content,
                    "options": final_opts,
                    "correct_answer": db_q.correct_answer,
                    "explanation": mcq.get("explanation", ""),
                })

            self.db.commit()
            return saved_questions
        finally:
            self._disable_llm_generation = previous_llm_flag

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