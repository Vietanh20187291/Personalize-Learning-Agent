# CLAUDE.md — AI Personalized Learning Platform

> Luận văn: **Nghiên cứu và phát triển nền tảng học tập trực tuyến cá nhân hóa ứng dụng mô hình Đa tác tử (Multi-Agent System)**

## Tổng quan dự án

Nền tảng học tập trực tuyến cá nhân hóa sử dụng kiến trúc Multi-Agent, xây dựng với **FastAPI** (backend) và **Next.js 16** (frontend). Hệ thống sử dụng LLM (Groq Llama 3.3 70B + Gemini fallback) để tạo trải nghiệm học tập thích ứng cho từng học sinh thông qua RAG, tự động đánh giá, và coaching cá nhân hóa.

## Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 16)                      │
│  React 19 · TypeScript · Tailwind · Framer Motion · Recharts │
├─────────────────────────────────────────────────────────────┤
│                     REST API (FastAPI)                        │
│  /auth · /adaptive · /assessment · /evaluation · /orbit ·    │
│  /planning · /classroom · /upload · /admin · /research       │
├─────────────────────────────────────────────────────────────┤
│                 Multi-Agent System                            │
│  AdaptiveAgent · EvaluationAgent · AssessmentAgent ·         │
│  OrbitAgent · PlanningAgent · ProfilingAgent ·               │
│  TeacherAgent · ContentAgent · ReviewAgent                   │
├─────────────────────────────────────────────────────────────┤
│              LLM Client (Groq → Gemini fallback)             │
│  Model: llama-3.3-70b-versatile · Gemini flash              │
├─────────────────────────────────────────────────────────────┤
│                    RAG Pipeline                               │
│  ChromaDB · LangChain Embeddings · Document Chunking         │
├─────────────────────────────────────────────────────────────┤
│                Memory & Storage                               │
│  SQLAlchemy ORM · SQLite/PostgreSQL · Redis (optional)       │
│  ConversationMemory (Redis/in-memory)                        │
└─────────────────────────────────────────────────────────────┘
```

## Cấu trúc thư mục chính

```
ai-personalized-learning-Test1/
├── backend/
│   ├── main.py                  # FastAPI app entry point, lifespan, CORS
│   ├── config.py                # Settings (DB URL, timeouts, feature flags)
│   ├── agents/                  # Multi-Agent System
│   │   ├── adaptive_agent.py    # Gia sư thích ứng, roadmap, RAG tutoring
│   │   ├── evaluation_agent.py  # Đánh giá học sinh, tính điểm, ranking
│   │   ├── assessment_agent.py  # Tạo câu hỏi trắc nghiệm/tự luận
│   │   ├── orbit_agent.py       # Coaching cá nhân hóa, reminder
│   │   ├── planning_agent.py    # Lập kế hoạch học tập
│   │   ├── profiling_agent.py   # Phân loại profile học sinh
│   │   ├── teacher_agent.py     # Agent hỗ trợ giáo viên
│   │   ├── content_agent.py     # Xử lý nội dung tài liệu
│   │   ├── review_agent.py      # Review/kiểm tra kiến thức
│   │   └── llm_client.py       # LLM client với Groq→Gemini fallback
│   ├── api/                     # REST API endpoints
│   │   ├── auth.py              # Đăng nhập, đăng ký, JWT
│   │   ├── adaptive.py          # Adaptive learning API
│   │   ├── assessment.py        # Assessment/quiz API
│   │   ├── evaluation.py        # Evaluation & scoring API
│   │   ├── orbit.py             # Orbit coaching chat API
│   │   ├── planning.py          # Learning plan API
│   │   ├── classroom.py         # Classroom management
│   │   ├── upload.py            # Document upload & processing
│   │   ├── admin.py             # Admin panel API
│   │   ├── teacher_agent.py     # Teacher agent API
│   │   ├── research.py          # Research API
│   │   ├── my_learning.py       # Student learning dashboard
│   │   ├── exam_generator.py    # Exam generation
│   │   └── exam_ocr.py          # OCR exam scanning
│   ├── db/
│   │   ├── database.py          # SQLAlchemy engine, session factory
│   │   └── models.py            # All ORM models
│   ├── rag/
│   │   ├── vector_store.py      # ChromaDB vector store singleton
│   │   └── embedder.py          # Embedding functions
│   ├── memory/
│   │   ├── conversation_memory.py  # Redis/in-memory conversation state
│   │   ├── intent_classifier.py    # Intent classification
│   │   └── action_router.py        # Route actions by intent
│   ├── services/
│   │   ├── orbit_reminders.py   # Weekly reminder scheduler
│   │   ├── test_ocr_service.py  # OCR processing service
│   │   ├── score_metrics.py     # Score computation utilities
│   │   └── research_evaluation.py
│   └── logs/                    # Runtime logs
├── frontend/
│   ├── app/                     # Next.js App Router pages
│   │   ├── page.tsx             # Dashboard chính (student)
│   │   ├── auth/page.tsx        # Login/Register
│   │   ├── adaptive/page.tsx    # Adaptive learning UI
│   │   ├── assessment/page.tsx  # Quiz/assessment UI
│   │   ├── evaluation/page.tsx  # Evaluation dashboard
│   │   ├── planning/page.tsx    # Learning plan UI
│   │   ├── teacher/page.tsx     # Teacher dashboard
│   │   ├── admin/               # Admin pages (users, subjects, teachers)
│   │   ├── library/page.tsx     # Document library
│   │   ├── upload/page.tsx      # Document upload
│   │   └── my-learning/         # Personal learning tracker
│   └── components/
│       ├── Navbar.tsx
│       ├── AssessmentForm.tsx
│       ├── FileUploader.tsx
│       ├── NovaTeacherAgent.tsx
│       └── StudentOrbitAgent.tsx
├── deploy/                      # Deployment configs
├── docs/                        # Documentation
└── .env                         # Environment variables
```

## Chi tiết các Agent (Multi-Agent System)

### 1. AdaptiveAgent (`agents/adaptive_agent.py`)
- **Chức năng**: Gia sư AI thích ứng, tạo lộ trình học, trả lời câu hỏi dựa trên tài liệu (RAG)
- **LLM**: Groq Llama 3.3 70B
- **RAG**: ChromaDB vector store + LangChain embeddings
- **Key methods**: tạo roadmap, material summary, chat tutoring, adaptive difficulty

### 2. EvaluationAgent (`agents/evaluation_agent.py`)
- **Chức năng**: Đánh giá năng lực học sinh, tính điểm, xếp hạng, tracking tiến độ
- **Metrics**: subject score, effort score, session duration, progress trends
- **RAG**: Context-aware evaluation từ tài liệu đã upload

### 3. AssessmentAgent (`agents/assessment_agent.py`)
- **Chức năng**: Tạo câu hỏi trắc nghiệm (MCQ) và tự luận từ tài liệu học
- **Output**: JSON-formatted questions với đáp án và giải thích

### 4. OrbitAgent (`agents/orbit_agent.py`)
- **Chức năng**: Coaching cá nhân hóa, nhắc nhở học tập hàng tuần
- **Data**: Sử dụng hồ sơ học sinh thực tế (effort score, progress, login history)
- **Features**: Weekly summary, recommendations, motivational messages

### 5. PlanningAgent (`agents/planning_agent.py`)
- **Chức năng**: Tạo và quản lý kế hoạch học tập cá nhân hóa
- **Output**: Study steps với deadline, priority, materials

### 6. ProfilingAgent (`agents/profiling_agent.py`)
- **Chức năng**: Phân loại learner profile (Beginner/Intermediate/Advanced)
- **Basis**: Assessment history, study sessions, document interactions

### 7. TeacherAgent (`agents/teacher_agent.py`)
- **Chức năng**: Hỗ trợ giáo viên quản lý lớp, đề thi, phân tích học sinh
- **Memory**: ConversationMemory (Redis hoặc in-memory)

### 8. ContentAgent (`agents/content_agent.py`)
- **Chức năng**: Xử lý và chunking tài liệu (PDF, DOCX, TXT, PPTX)

### 9. ReviewAgent (`agents/review_agent.py`)
- **Chức năng**: Review kiến thức, spaced repetition

### LLM Client (`agents/llm_client.py`)
- **Fallback chain**: Groq → Gemini (tự động khi rate limit hoặc lỗi)
- **Primary model**: llama-3.3-70b-versatile (Groq)
- **Fallback model**: Gemini Flash

## Database Models (SQLAlchemy)

**Core**: `User`, `Subject`, `Classroom`, `Document`
**Learning**: `LearningRoadmap`, `StudySession`, `StudentLearningPlan`, `StudentLearningPlanStep`
**Assessment**: `AssessmentHistory`, `QuestionBank`, `AssessmentResult`
**Evaluation**: `StudentDocumentEvaluation`, `StudentDocumentScoreHistory`, `StudentLearningProgress`
**Chat**: `OrbitChatSession`, `OrbitChatMessage`, `OrbitCoachDirective`
**System**: `UserLoginSession`, `DocumentPublication`, `Chunk`

## RAG Pipeline

1. **Document Upload** → ContentAgent chunking (PDF/DOCX/PPTX/TXT)
2. **Embedding** → LangChain embeddings
3. **Storage** → ChromaDB vector database (`backend/chroma_db/`)
4. **Retrieval** → Agents query ChromaDB for context-relevant chunks
5. **Generation** → LLM generates personalized response with RAG context

## Memory System

- **ConversationMemory**: Redis (production) hoặc in-memory (dev)
- **TTL**: 8 giờ mặc định, configurable
- **Intent Classification**: Phân loại ý định người dùng để routing
- **Action Router**: Dispatch action theo intent

## API Endpoints chính

| Endpoint | Module | Mô tả |
|----------|--------|--------|
| `/auth/*` | auth.py | Login, register, JWT |
| `/adaptive/*` | adaptive.py | Adaptive learning, roadmap |
| `/assessment/*` | assessment.py | Quiz generation, submission |
| `/evaluation/*` | evaluation.py | Scoring, analytics |
| `/orbit/*` | orbit.py | Coaching chat |
| `/planning/*` | planning.py | Learning plans |
| `/classroom/*` | classroom.py | Class management |
| `/upload/*` | upload.py | Document upload |
| `/teacher-agent/*` | teacher_agent.py | Teacher AI assistant |

## Công nghệ sử dụng

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS, Framer Motion |
| Backend | FastAPI, Uvicorn/Gunicorn |
| Database | SQLAlchemy ORM, SQLite (dev), PostgreSQL (prod) |
| Vector DB | ChromaDB |
| LLM | Groq (Llama 3.3 70B), Google Gemini (fallback) |
| RAG | LangChain, ChromaDB |
| Cache/Memory | Redis (optional), in-memory fallback |
| Auth | JWT, bcrypt password hashing |

## Chạy dự án

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Biến môi trường (.env)

```
GROQ_KEY_ADAPTIVE=gsk_xxx
GROQ_KEY_EVALUATION=gsk_xxx
GROQ_KEY_ASSESSMENT=gsk_xxx
GROQ_KEY_ORBIT=gsk_xxx
GEMINI_API_KEY=AIzaSyxxx
DATABASE_URL=sqlite:///./sql_db/app.db
REDIS_URL=redis://localhost:6379
```

## Quy trình hoạt động chính

1. **Onboarding**: Đăng ký → join lớp → upload tài liệu
2. **Assessment**: AssessmentAgent tạo quiz → học sinh làm → EvaluationAgent chấm điểm
3. **Profiling**: ProfilingAgent phân loại level → AdaptiveAgent tạo roadmap
4. **Adaptive Learning**: AdaptiveAgent tutoring qua RAG → điều chỉnh theo level
5. **Planning**: PlanningAgent tạo kế hoạch → OrbitAgent nhắc nhở
6. **Coaching**: OrbitAgent coaching hàng tuần dựa trên dữ liệu thực

## Ghi chú phát triển

- Tất cả agents dùng chung pattern: `__init__(db_session)`, resolve API key từ env, khởi tạo Groq client
- Agent fallback graceful: nếu LLM/ChromaDB lỗi, agent vẫn chạy ở chế độ degraded
- Frontend dùng Next.js App Router (app directory), mỗi page là một Server/Client component
- CORS enabled cho localhost development
- Password hashing: bcrypt
- JWT token-based authentication
