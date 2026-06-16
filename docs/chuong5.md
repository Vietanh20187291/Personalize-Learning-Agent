# CHƯƠNG 5. TRIỂN KHAI HỆ THỐNG

## 5.1 Công nghệ sử dụng

Hệ thống được triển khai trên nền tảng công nghệ hiện đại, được lựa chọn dựa trên yêu cầu về hiệu năng, khả năng mở rộng và phù hợp với bối cảnh học thuật. Bảng 5.1 tổng hợp các công nghệ chính.

**Bảng 5.1.** Tổng hợp công nghệ sử dụng

| Thành phần | Công nghệ | Phiên bản | Lý do chọn |
|---|---|---|---|
| Backend Framework | FastAPI | 0.100+ | Async, auto-doc (OpenAPI), hiệu năng cao |
| Frontend Framework | Next.js (React) | 14+ | SSR, routing, responsive UI |
| Ngôn ngữ Backend | Python | 3.10+ | Hỗ trợ AI/ML ecosystem phong phú |
| Ngôn ngữ Frontend | TypeScript | 5+ | Type safety, developer experience |
| CSDL Quan hệ | PostgreSQL | 15+ | ACID, JSON support, scalable |
| Vector Database | ChromaDB | 0.4+ | Lightweight, persistent, Python-native |
| ORM | SQLAlchemy | 2.0+ | Type-safe, migration support |
| Embedding Model | all-MiniLM-L6-v2 | — | 384 dims, CPU-optimized, chất lượng tốt |
| LLM Primary | Llama 3.3 70B | — | Qua Groq API, fast inference |
| LLM Fallback | Google Gemini | — | Failover khi Groq không khả dụng |
| LLM Client | Groq SDK | — | Low-latency LLM inference |
| HTTP Client | Axios | — | Request/response interceptor |
| CSS Framework | Tailwind CSS | 3+ | Utility-first, responsive nhanh |
| File Processing | PyPDF, python-docx, python-pptx | — | Parse PDF, DOCX, PPTX |
| Task Queue | Background tasks | — | FastAPI background processing |

## 5.2 Backend Architecture

Backend được triển khai theo kiến trúc **modular monolith** — một ứng dụng FastAPI duy nhất nhưng được phân tách rõ ràng thành các module độc lập. Cấu trúc thư mục như sau:

```
backend/
├── main.py                    # FastAPI app entry point
├── config.py                  # Settings & configuration
├── database.py                # DB connection & session
├── agents/                    # Multi-Agent Layer
│   ├── teacher_agent.py       # Nova Teacher Agent (Hub)
│   ├── adaptive_agent.py      # Adaptive Tutor Agent
│   ├── planning_agent.py      # Planning Agent
│   ├── content_agent.py       # Content Agent
│   ├── evaluation_agent.py    # Evaluation Agent
│   ├── assessment_agent.py    # Assessment Agent
│   ├── orbit_agent.py         # Orbit Coaching Agent
│   ├── profiling_agent.py     # Profiling Agent
│   ├── review_agent.py        # Review Agent
│   └── llm_client.py          # LLM Client (failover)
├── api/                       # API Router Layer
│   ├── auth.py                # Authentication
│   ├── adaptive.py            # Tutor & Roadmap
│   ├── assessment.py          # Quiz & Test
│   ├── orbit.py               # Coaching & Progress
│   ├── planning.py            # Study Plans
│   ├── my_learning.py         # Student Dashboard + AI Insights
│   ├── teacher_agent.py       # Teacher Chat
│   ├── classroom.py           # Class Management
│   ├── upload.py              # File Upload
│   ├── document.py            # Document Viewer
│   ├── evaluation.py          # Evaluation
│   ├── exam_generator.py      # OCR Exam
│   └── admin.py               # Admin Panel
├── db/
│   ├── models.py              # SQLAlchemy Models (30+ tables)
│   └── database.py            # Connection pooling
├── memory/
│   ├── conversation_memory.py # Session Memory (Redis/Local)
│   └── action_router.py       # UI Action Routing
├── rag/
│   └── vector_store.py        # ChromaDB Integration
├── services/
│   ├── research_evaluation.py # Agent Evaluation Framework
│   ├── orbit_reminders.py     # Weekly Reminders
│   └── system_health.py       # Health Monitoring
└── logging_config.py          # Structured Logging
```

**FastAPI Application Configuration:**

File `main.py` cấu hình ứng dụng với:
- **CORS middleware:** Cho phép cross-origin requests từ frontend
- **Router registration:** 17 API routers với prefix `/api/`
- **Startup events:** Warm-up question banks cho tài liệu mới
- **Error handling:** Global exception handler trả JSON error response

Mỗi API router tuân thủ mẫu thiết kế:
1. Nhận request qua Pydantic model validation
2. Xác thực user (user_id + role check)
3. Khởi tạo agent với database session
4. Gọi agent method
5. Lưu kết quả vào database
6. Trả về JSON response

## 5.3 Frontend Architecture

Frontend được triển khai bằng Next.js 14 với App Router, sử dụng TypeScript và Tailwind CSS.

**Cấu trúc trang (Pages):**

```
frontend/app/
├── page.tsx                    # Trang chủ (chọn vai trò)
├── adaptive/
│   └── page.tsx                # Tab Gia sư (Tutor Agent)
├── assessment/
│   └── page.tsx                # Làm bài kiểm tra
├── evaluation/
│   └── page.tsx                # Xem kết quả đánh giá
├── my-learning/
│   └── page.tsx                # Tab Học tập (AI Insights)
├── teacher/
│   └── page.tsx                # Giảng viên Dashboard
├── admin/
│   ├── teachers/page.tsx       # Quản lý tài khoản
│   └── subjects/page.tsx       # Quản lý môn học
└── test/
    └── page.tsx                # Test/Debug page
```

**Các component chính:**

| Component | Chức năng |
|---|---|
| AgentConversationCard | Chat UI tái sử dụng cho mọi agent |
| OrbitPanel | Panel coaching浮动 (floating) cho sinh viên |
| AssessmentForm | Form làm bài trắc nghiệm |
| FileUploader | Upload tài liệu (drag & drop) |
| DocumentManager | Quản lý tài liệu của lớp |
| LearningDashboard | Dashboard tiến độ học tập |
| Navbar | Navigation bar theo role |

**Giao tiếp với Backend:**

Frontend giao tiếp với backend hoàn toàn qua REST API, sử dụng Axios client với:
- Base URL từ environment variable
- Long request config (timeout 60s cho LLM calls)
- Slow notice indicator khi request vượt 3.5s
- Error normalization wrapper

## 5.4 Database Design

Hệ thống sử dụng **PostgreSQL** làm cơ sở dữ liệu quan hệ chính, với hơn 30 bảng được thiết kế để hỗ trợ đầy đủ các yêu cầu chức năng. Thiết kế tuân thủ nguyên tắc normalization (3NF) kết hợp denormalization có chọn lọc cho performance.

**Sơ đồ Entity-Relationship (các bảng chính):**

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  users   │     │  subjects    │     │  classrooms  │
│──────────│     │──────────────│     │──────────────│
│ id (PK)  │     │ id (PK)      │     │ id (PK)      │
│ username │     │ name         │     │ name         │
│ role     │     │ description  │     │ class_code   │
│ full_name│     │ icon         │     │ subject_id(FK│────► subjects
│ student_id│    └──────────────┘     │ teacher_id(FK│────► users
└────┬─────┘                          └──────┬───────┘
     │                                       │
     │ enrollments (N-N)                     │
     ├───────────────────────────────────────┘
     │
     ├──┬──────────────────┬──────────────────┐
     │  │                  │                  │
     ▼  ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│ documents    │  │ learning_roadmaps│  │study_sessions│
│──────────────│  │──────────────────│  │──────────────│
│ id (PK)      │  │ id (PK)          │  │ id (PK)      │
│ title        │  │ user_id (FK)     │  │ user_id (FK) │
│ filename     │  │ subject_id (FK)  │  │ subject_id   │
│ subject_id(FK│  │ level_assigned   │  │ duration_min │
│ class_id(FK) │  │ roadmap_data(JSON│  │ start_time   │
│ file_path    │  │ current_session  │  └──────────────┘
└──────┬───────┘  └──────────────────┘
       │
       ▼
┌───────────────────────┐
│student_doc_evaluations │
│───────────────────────│
│ id (PK)               │
│ user_id (FK)          │
│ document_id (FK)      │
│ subject_id (FK)       │
│ latest_score          │
│ attempts              │
│ is_completed          │
│ last_test_at          │
└───────────┬───────────┘
            │
            ▼
┌─────────────────────────┐  ┌──────────────────────────┐
│student_doc_score_history │  │ wrong_answer_records     │
│─────────────────────────│  │──────────────────────────│
│ id (PK)                 │  │ id (PK)                  │
│ user_id (FK)            │  │ user_id (FK)             │
│ document_id (FK)        │  │ document_id (FK)         │
│ score                   │  │ question_text            │
│ test_type               │  │ options_json             │
│ tested_at               │  │ student_choice           │
└─────────────────────────┘  │ correct_answer           │
                             │ explanation              │
┌──────────────────────┐     └──────────────────────────┘
│ learner_profiles     │
│──────────────────────│     ┌──────────────────────────┐
│ id (PK)              │     │ question_bank            │
│ user_id (FK)         │     │──────────────────────────│
│ subject_id (FK)      │     │ id (PK)                  │
│ current_level        │     │ subject_id (FK)          │
│ total_tests          │     │ difficulty               │
│ avg_score            │     │ content                  │
└──────────────────────┘     │ options (JSON)           │
                             │ correct_answer           │
┌──────────────────────┐     │ explanation              │
│ student_learning_    │     │ source_file              │
│ progress             │     └──────────────────────────┘
│──────────────────────│
│ user_id (PK, FK)     │     ┌──────────────────────────┐
│ lessons_completed    │     │ orbit_chat_sessions      │
│ tests_completed      │     │──────────────────────────│
│ total_study_minutes  │     │ id (PK)                  │
│ total_agent_messages │     │ user_id (FK)             │
│ last_active_at       │     │ class_id (FK)            │
└──────────────────────┘     │ message_count            │
                             └──────────┬───────────────┘
┌──────────────────────┐                │
│ student_learning_    │                ▼
│ plans                │     ┌──────────────────────────┐
│──────────────────────│     │ orbit_chat_messages      │
│ id (PK)              │     │──────────────────────────│
│ user_id (FK)         │     │ id (PK)                  │
│ status               │     │ session_id (FK)          │
│ generated_at         │     │ user_id (FK)             │
└──────┬───────────────┘     │ role (user/assistant)    │
       │                     │ content                  │
       ▼                     └──────────────────────────┘
┌──────────────────────────┐
│student_learning_plan_steps│
│──────────────────────────│
│ id (PK)                  │
│ plan_id (FK)             │
│ document_id (FK)         │
│ step_order               │
│ planned_date             │
│ priority_group           │
│ latest_score             │
│ reason                   │
│ is_completed             │
└──────────────────────────┘
```

**Hình 5.1.** Sơ đồ Entity-Relationship của cơ sở dữ liệu PostgreSQL

**Bảng 5.2.** Thống kê cơ sở dữ liệu

| Nhóm bảng | Số bảng | Bảng tiêu biểu |
|---|---|---|
| User & Auth | 3 | users, user_login_sessions |
| Subject & Class | 3 | subjects, classrooms, enrollments |
| Document & Content | 4 | documents, document_publications, chunks, question_bank |
| Learning & Progress | 8 | learner_profiles, student_learning_progress, student_doc_evaluations, student_doc_score_history, wrong_answer_records, learning_roadmaps, student_learning_plans, student_learning_plan_steps |
| Assessment | 3 | assessment_history, assessment_results, study_sessions |
| Orbit & Chat | 5 | orbit_chat_sessions, orbit_chat_messages, orbit_coach_directives, orbit_weekly_reminder_logs, notifications |
| Exam OCR | 3 | test_ocr_exam_batches, test_ocr_grading_runs, test_ocr_grading_results |
| Research | 4 | research_evaluation_cases, research_experiment_runs, research_experiment_item_results, research_report_snapshots |
| **Tổng** | **33** | |

## 5.5 Multi-Agent Services

Mỗi agent được triển khai như một Python class độc lập, tuân thủ interface chung:

```python
class AgentTemplate:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = self._resolve_groq_api_key()
        self.model = "llama-3.3-70b-versatile"
        self.client = Groq(api_key=self.api_key)
```

**Cơ chế cá nhân hóa qua shared data:**

Mỗi agent truy vấn learner data từ PostgreSQL để cá nhân hóa phản hồi:

```python
def _build_student_context(self, user_id, subject):
    # Learner Profile
    profile = db.query(LearnerProfile).filter_by(user_id=user_id).first()
    level = profile.current_level  # Beginner/Intermediate/Advanced
    
    # Weak Topics
    weak_docs = db.query(StudentDocumentEvaluation).filter(
        user_id=user_id, latest_score < 50
    ).all()
    
    # Misconceptions
    wrong_answers = db.query(WrongAnswerRecord).filter(
        user_id=user_id
    ).order_by(created_at.desc()).limit(5).all()
    
    # Inject vào LLM prompt
    return f"Mức năng lực: {level}. Điểm yếu: {weak_topics}. Hay sai: {misconceptions}"
```

**LLM Configuration per Agent:**

| Agent | Temperature | Max Tokens | Response Format |
|---|---|---|---|
| Teacher (Hub) | 0.3 | 2000 | Free text |
| Adaptive (Tutor) | 0.35 | Default | Free text |
| Planning | 0.2 | 3000 | JSON |
| Assessment | 0.3 | 6000 | JSON |
| Evaluation | 0.3 | 800 | Free text |
| Content | 0.2 | 1000 | JSON |
| Orbit (Coach) | 0.5 | 800 | Free text |
| Review | 0.3 | 2000 | Markdown |
| Profiling | Rule-based | — | String |

## 5.6 Knowledge Retrieval Service

Knowledge Retrieval Service được triển khai qua module `backend/rag/vector_store.py` và Content Agent, cung cấp hai hàm core:

**1. Indexing Service (add_documents_to_db):**

```python
def add_documents_to_db(docs, subject, source_file):
    """
    Input: List[Document] — các text chunks đã processing
    Output: Lưu vào ChromaDB persistent collection
    
    Metadata: {subject, source, class_id}
    Embedding: all-MiniLM-L6-v2 (384 dims)
    Collection: ai_learning_collection (persistent)
    """
```

**2. Retrieval Service (similarity_search):**

```python
def similarity_search(query, k=20, filter=None):
    """
    Input: query string, số kết quả, filter metadata
    Output: List[Document] — chunks có similarity cao nhất
    
    Filter hỗ trợ:
    - {"subject": {"$eq": "Python"}} — lọc theo môn
    - {"source": {"$in": ["file1.pdf", "file2.pdf"]}} — lọc theo file
    """
```

**Pre-processing Pipeline trong Content Agent:**

- **Boilerplate removal:** Loại bỏ thông tin hành chính (giảng viên, SĐT, email, quy chế) bằng 17 regex patterns
- **Short line filtering:** Bỏ dòng < 18 ký tự
- **Deduplication:** Loại bỏ duplicate lines (case-insensitive)
- **Length capping:** Giới hạn 28,000 ký tự mỗi tài liệu

## 5.7 Assessment Support Service

Assessment Support Service bao gồm 3 quy trình chính:

**1. Question Generation Service (Assessment Agent):**

```python
def generate_questions_from_concepts(concepts, subject, num_questions, difficulty):
    """
    Input: danh sách concepts + subject + params
    Process:
      1. Bloom's taxonomy scheduling (phân bổ mức độ)
      2. LLM MCQ generation per concept
      3. Quality validation (5 bước)
      4. Bank storage
    
    Output: List[Question] — validated MCQ questions
    """
```

**2. Quiz Delivery Service:**

```python
def get_or_create_quiz(user_id, subject, source_file, level):
    """
    Lấy quiz từ question bank hoặc sinh mới nếu chưa có.
    Hỗ trợ:
    - Chapter test (10 câu, 1 tài liệu)
    - Final exam (20 câu, tất cả tài liệu)
    """
```

**3. Grading & Feedback Service:**

```python
def analyze_quiz_answers(answers, questions, user_id):
    """
    Input: sinh viên answers + correct answers
    Process:
      1. So sánh → score
      2. Wrong answer → WrongAnswerRecord
      3. Evaluation Agent → AI feedback
      4. Profile update → LearnerProfile
    
    Output: score + feedback + review material
    """
```

## 5.8 Các chức năng chính của hệ thống

### 5.8.1 Cá nhân hóa Tutor AI

Khi sinh viên hỏi Tutor Agent, hệ thống thực hiện cá nhân hóa 4 tầng:

**Tầng 1 — Dynamic Learner Profile:** Truy vấn `LearnerProfile` để xác định mức năng lực hiện tại (Beginner/Intermediate/Advanced).

**Tầng 2 — Weak Topics Analysis:** Truy vấn `StudentDocumentEvaluation` để xác định tài liệu có điểm thấp (< 50), kết hợp với `WrongAnswerRecord` để phát hiện câu sai gần đây.

**Tầng 3 — Context Injection:** Inject toàn bộ learner data vào system prompt LLM với hướng dẫn dạy khác nhau theo level. Beginner nhận giải thích step-by-step + ví dụ đời thường, Advanced nhận challenge + phân tích sâu.

**Tầng 4 — RAG Grounding:** Kết hợp learner context với tài liệu thực tế (RAG retrieval) để đảm bảo câu trả lời vừa cá nhân hóa vừa chính xác về mặt nội dung.

### 5.8.2 Coaching cá nhân hóa (Orbit Agent)

Orbit Agent sử dụng LLM để coaching dựa trên dữ liệu học sinh thực tế:

- **Tên sinh viên:** Gọi tên cá nhân trong response
- **Thống kê học tập:** Thời gian học, số bài kiểm tra, số bài đạt
- **Điểm yếu cụ thể:** Tài liệu điểm thấp, câu sai lặp lại
- **Chỉ tiêu từ giảng viên:** OrbitCoachDirective đang active
- **Pattern nhận diện:** Nghỉ quá lâu → nghiêm khắc; học tốt → khen ngợi

### 5.8.3 AI Insights

Tab "Học tập" hiển thị nhận xét AI tổng hợp toàn bộ dữ liệu học tập:

- **Summary:** 1-2 câu tóm tắt gọi tên sinh viên
- **Điểm mạnh:** Dựa trên tài liệu có điểm cao (≥ 75)
- **Điểm yếu:** Dựa trên tài liệu điểm thấp (< 50) và câu sai
- **Đề xuất:** "Ôn lại chương X", "Làm thêm 2 bài kiểm tra về Y"
- **Study pattern:** Phát hiện thói quen (học dồn cuối tuần, hay học đêm)
- **Động viên:** Cá nhân hóa theo tình hình

### 5.8.4 Kế hoạch học tự động

Planning Agent sinh lịch học cụ thể theo ngày, ưu tiên tài liệu theo điểm số:

| Priority Group | Điều kiện | Hành động |
|---|---|---|
| no_score | Chưa làm bài | Học trước, deadline sớm |
| low_score | Điểm < 50 | Học lại, ôn tập kỹ |
| medium_score | 50 ≤ Điểm < 75 | Ôn tập nhẹ |
| good_score | Điểm ≥ 75 | Giữ làm tài liệu tham khảo |

Sinh viên có thể yêu cầu điều chỉnh bằng ngôn ngữ tự nhiên: "Ưu tiên môn X", "Hoãn chương Y", "Tăng/giảm tải".

### 5.8.5 Tạo và chấm kiểm tra tự động

Hỗ trợ hai hình thức:

**Trực tuyến (Online):**
- Assessment Agent sinh câu hỏi từ ngân hàng hoặc RAG
- Sinh viên làm trên giao diện web
- Chấm tự động, lưu wrong answers, sinh feedback

**Trên giấy (Offline/OCR):**
- Tạo đề in (DOCX) với answer key + OMR layout
- Scan bài thi → OCR nhận diện → OMR chấm
- Import kết quả vào database
