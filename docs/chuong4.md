# CHƯƠNG 4. ĐỀ XUẤT MÔ HÌNH VÀ KIẾN TRÚC HỆ THỐNG

## 4.1 Phân tích yêu cầu

### 4.1.1 Yêu cầu chức năng

Hệ thống cá nhân hóa học tập được xây dựng để phục vụ hai nhóm người dùng chính: **giảng viên** và **sinh viên**. Dựa trên phân tích nghiệp vụ và khảo sát thực tế tại môi trường đại học, các yêu cầu chức năng được phân loại như sau:

**Bảng 4.1.** Yêu cầu chức năng theo nhóm người dùng

| Mã | Yêu cầu | Nhóm | Mô tả | Độ ưu tiên |
|---|---|---|---|---|
| FR-01 | Quản lý lớp học | GV | Tạo lớp, sinh mã tham gia, thêm/xóa sinh viên | Cao |
| FR-02 | Upload tài liệu | GV | Tải PDF, DOCX, PPTX lên lớp học | Cao |
| FR-03 | Phân loại tài liệu | Hệ thống | Tự động phát hiện môn học từ nội dung file | Trung bình |
| FR-04 | Tạo đề trắc nghiệm | GV | Sinh câu hỏi MCQ từ tài liệu, hỗ trợ nhiều phiên bản | Cao |
| FR-05 | Thi trắc nghiệm | SV | Làm bài kiểm tra trực tuyến, nhận kết quả ngay | Cao |
| FR-06 | Gia sư AI | SV | Chat với Tutor Agent dựa trên tài liệu đang mở | Cao |
| FR-07 | Lập kế hoạch học | SV/Hệ thống | Tự động sinh lịch học cá nhân dựa trên điểm và tiến độ | Cao |
| FR-08 | Theo dõi tiến độ | SV/GV | Xem thời gian học, điểm số, tỷ lệ hoàn thành | Cao |
| FR-09 | Coaching AI | SV | Orbit Agent nhắc nhở, động viên, đề xuất tài liệu | Trung bình |
| FR-10 | Phân tích lớp | GV | Xem phân tích điểm, xu hướng học của lớp | Trung bình |
| FR-11 | Tạo tài liệu ôn tập | SV | Sinh tài liệu ôn từ câu sai tự động | Trung bình |
| FR-12 | Giao chỉ tiêu | GV | Giao mục tiêu học tập tuần cho từng sinh viên | Trung bình |
| FR-13 | Chấm thi giấy | GV | OCR bài thi giấy, chấm tự động bằng OMR | Trung bình |
| FR-14 | AI Insights | SV | Nhận xét AI cá nhân hóa dựa trên toàn bộ dữ liệu học | Cao |

### 4.1.2 Yêu cầu phi chức năng

**Bảng 4.2.** Yêu cầu phi chức năng

| Mã | Yêu cầu | Mô tả | Chỉ tiêu mục tiêu |
|---|---|---|---|
| NFR-01 | Hiệu năng | Thời gian phản hồi Tutor Agent | < 5 giây (P95) |
| NFR-02 | Khả dụng | Hệ thống hoạt động ngay cả khi LLM lỗi | Fallback cho mọi agent |
| NFR-03 | Khả mở rộng | Thêm agent mới không ảnh hưởng agent cũ | Agent Hub architecture |
| NFR-04 | Bảo mật | Phân quyền theo role (teacher/student/admin) | JWT-based auth |
| NFR-05 | Đồng thời | Hỗ trợ nhiều sinh viên học cùng lúc | Horizontal scaling qua Redis |
| NFR-06 | Khả phục hồi | Lỗi 1 agent không gây sập toàn hệ thống | Circuit breaker, fallback |
| NFR-07 | Dễ bảo trì | Prompt tập trung trong từng agent, không phân tán | Modular agent design |
| NFR-08 | Tương thích | Hỗ trợ nhiều LLM provider (Groq, OpenAI, Gemini, Ollama) | Provider-agnostic |
| NFR-09 | Trải nghiệm | Giao diện responsive, hỗ trợ mobile | Next.js responsive |
| NFR-10 | Dữ liệu | Lưu trữ quan hệ (PostgreSQL) + vector (ChromaDB) | Dual storage |

## 4.2 Mô hình nền tảng học tập đề xuất

### 4.2.1 Kiến trúc tổng thể

Hệ thống được thiết kế theo kiến trúc **3-tier** (3 lớp) kết hợp **Multi-Agent Pattern**:

```
┌────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION TIER                               │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                  Next.js Frontend                             │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │ │
│  │  │ Teacher  │ │ Student  │ │  Admin   │ │   Assessment   │ │ │
│  │  │ Dashboard│ │ Portal   │ │  Panel   │ │    Module      │ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ HTTP/REST
                                 │
┌────────────────────────────────┼───────────────────────────────────┐
│                    APPLICATION TIER                                │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   FastAPI Backend                              │ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────┐│ │
│  │  │              Agent Hub Layer                             ││ │
│  │  │                                                         ││ │
│  │  │  ┌────────────────────────────────────────────────────┐ ││ │
│  │  │  │  Nova Teacher Agent (Hub)                          │ ││ │
│  │  │  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │ ││ │
│  │  │  │  │  Intent   │ │  Action  │ │  Conversation   │  │ ││ │
│  │  │  │  │Classifier │ │  Router  │ │    Memory       │  │ ││ │
│  │  │  │  └──────────┘ └──────────┘ └──────────────────┘  │ ││ │
│  │  │  └────────────────────────────────────────────────────┘ ││ │
│  │  │                          │                              ││ │
│  │  │       ┌──────┬──────┬───┴───┬──────┬──────┐           ││ │
│  │  │       ▼      ▼      ▼       ▼      ▼      ▼           ││ │
│  │  │  ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐    ││ │
│  │  │  │Adapt ││Plan  ││Eval  ││Assess││Content││Orbit │    ││ │
│  │  │  │Agent ││Agent ││Agent ││Agent ││Agent ││Agent │    ││ │
│  │  │  └──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘    ││ │
│  │  │     └───────┴───────┴───────┴───────┴───────┘         ││ │
│  │  │                          │                              ││ │
│  │  │              ┌───────────▼───────────┐                 ││ │
│  │  │              │   Shared Services      │                 ││ │
│  │  │              │ ┌─────┐ ┌───────────┐ │                 ││ │
│  │  │              │ │ RAG │ │  LLM       │ │                 ││ │
│  │  │              │ │Store│ │  Client    │ │                 ││ │
│  │  │              │ └─────┘ └───────────┘ │                 ││ │
│  │  │              └───────────────────────┘                 ││ │
│  │  └─────────────────────────────────────────────────────────┘│ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
┌────────────────────────────────┼───────────────────────────────────┐
│                       DATA TIER                                    │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  PostgreSQL   │  │  ChromaDB    │  │  File Storage           │ │
│  │  (Relational) │  │  (Vector DB) │  │  (Documents/Media)      │ │
│  │              │  │              │  │                          │ │
│  │ • Users      │  │ • Embeddings │  │ • PDF files              │ │
│  │ • Subjects   │  │ • Chunks     │  │ • DOCX files             │ │
│  │ • Documents  │  │ • Metadata   │  │ • PPTX files             │ │
│  │ • Classes    │  │              │  │ • Generated exams        │ │
│  │ • Scores     │  │              │  │                          │ │
│  │ • Plans      │  │              │  │                          │ │
│  │ • Sessions   │  │              │  │                          │ │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

**Hình 4.1.** Kiến trúc tổng thể 3-tier của hệ thống

### 4.2.2 Luồng xử lý hệ thống

Luồng xử lý chính của hệ thống được phân thành 3 nhóm theo vai trò người dùng:

**Luồng 1: Giảng viên (Teacher Flow)**

```
Giảng viên đăng nhập
        │
        ├──► Teacher Dashboard
        │    ├── Tạo lớp học → sinh mã tham gia
        │    ├── Upload tài liệu → Content Agent xử lý
        │    │    ├── Phát hiện môn học (heuristic + LLM)
        │    │    ├── Chunking & Embedding → ChromaDB
        │    │    └── Tự động sinh ngân hàng câu hỏi
        │    ├── Tạo đề thi → Assessment Agent
        │    │    ├── Sinh MCQ theo Bloom's taxonomy
        │    │    ├── Tạo nhiều phiên bản
        │    │    └── Xuất DOCX + answer key
        │    ├── Xem phân tích lớp → Evaluation Agent
        │    └── Giao chỉ tiêu học tập → Orbit Coach Directive
        │
        └──► Nova Teacher Agent (Chat)
             ├── Intent classification (hybrid)
             ├── Routing đến agent chuyên biệt
             └── Phản hồi kết quả
```

**Luồng 2: Sinh viên (Student Flow)**

```
Sinh viên đăng nhập
        │
        ├──► Trang chủ
        │    ├── Nhập mã lớp → Tham gia lớp học
        │    ├── Chọn môn → Xem tài liệu
        │    └── Tab "Học tập" → AI Insights cá nhân hóa
        │
        ├──► Tab Gia sư (Adaptive)
        │    ├── Chọn môn → tải tài liệu
        │    ├── Chat với Tutor Agent
        │    │    ├── RAG retrieval từ ChromaDB
        │    │    ├── Personalized context (level, weak topics, misconceptions)
        │    │    └── LLM response cá nhân hóa
        │    └── Làm bài kiểm tra → Assessment Agent
        │         ├── Sinh câu hỏi từ ngân hàng
        │         ├── Chấm điểm tự động
        │         ├── Lưu wrong answers → Review material
        │         └── Cập nhật LearnerProfile
        │
        ├──► Orbit Agent (Coach)
        │    ├── Coaching cá nhân hóa (LLM-powered)
        │    ├── Đề xuất tài liệu ưu tiên
        │    ├── Nhắc nhở học tập
        │    └── Theo dõi kỷ luật
        │
        └──► Tab Kế hoạch học
             ├── Kế hoạch tự động từ Planning Agent
             └── Điều chỉnh bằng ngôn ngữ tự nhiên
```

**Luồng 3: Hệ thống tự động (System Flow)**

```
Sự kiện hệ thống
        │
        ├──► Sinh viên login
        │    ├── Planning Agent: sinh/cập nhật kế hoạch
        │    ├── Orbit Agent: chào + coaching
        │    └── Profile update: cập nhật learner level
        │
        ├──► Upload tài liệu mới
        │    ├── Content Agent: xử lý + indexing
        │    └── Assessment Agent: warm-up question bank
        │
        └──► Sinh viên nộp bài kiểm tra
             ├── Chấm điểm + lưu wrong answers
             ├── Evaluation Agent: feedback
             ├── Profile update: cập nhật level nếu cần
             └── Planning Agent: điều chỉnh kế hoạch
```

### 4.2.3 Các thành phần chính

Hệ thống được cấu thành từ các module chính sau:

**1. API Gateway Layer (FastAPI)**

Đóng vai trò entry point cho tất cả yêu cầu từ frontend. Cung cấp hơn 50 REST API endpoints, được tổ chức thành các router:

| Router | Prefix | Chức năng |
|---|---|---|
| auth | /api/auth | Đăng nhập, xác thực, profile |
| classroom | /api/classroom | Quản lý lớp, tham gia, CRUD |
| upload | /api/upload | Upload tài liệu, xử lý file |
| adaptive | /api/adaptive | Tutor chat, roadmap, log session |
| assessment | /api/assessment | Tạo và làm bài kiểm tra |
| orbit | /api/orbit | Orbit coaching, progress, directives |
| planning | /api/planning | Kế hoạch học tập |
| teacher_agent | /api/teacher-agent | Nova Teacher Agent chat |
| my_learning | /api/my-learning | Tab học tập, AI insights |
| evaluation | /api/evaluation | Đánh giá năng lực |
| exam_generator | /api/exam-generator | Tạo đề thi OCR |
| admin | /api/admin | Quản trị hệ thống |

**2. Multi-Agent Layer**

Gồm 9 agent chuyên biệt như đã mô tả chi tiết trong Chương 3. Mỗi agent được triển khai như một Python class độc lập, nhận database session và tự resolve LLM credentials.

**3. Shared Services Layer**

Các dịch vụ dùng chung mà nhiều agent cùng sử dụng:
- **RAG Store:** ChromaDB + HuggingFace embeddings (all-MiniLM-L6-v2)
- **LLM Client:** Wrapper hỗ trợ failover giữa Groq và Gemini
- **Conversation Memory:** Redis-based (production) hoặc in-memory (dev)
- **Research Evaluation:** Framework đánh giá hiệu năng agent

## 4.3 Knowledge Retrieval Module

Knowledge Retrieval Module (KRM) chịu trách nhiệm biến tài liệu học tập thô (PDF, DOCX, PPTX) thành kiến thức có thể truy vấn cho các agent. Module này được triển khai thông qua sự phối hợp giữa Content Agent và ChromaDB vector store.

**Kiến trúc Knowledge Retrieval Module:**

```
┌─────────────────────────────────────────────────────────────┐
│              KNOWLEDGE RETRIEVAL MODULE                      │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │   Document  │    │   Embedding   │    │   Vector      │  │
│  │   Ingestion │───►│   Pipeline    │───►│   Store       │  │
│  │             │    │              │    │  (ChromaDB)    │  │
│  │ • PDF parse │    │ • Chunking   │    │               │  │
│  │ • DOCX parse│    │ • Cleaning   │    │ • Similarity  │  │
│  │ • PPTX parse│    │ • Embedding  │    │   search      │  │
│  │ • TXT parse │    │ • Metadata   │    │ • Filtering   │  │
│  └─────────────┘    └──────────────┘    └───────┬───────┘  │
│                                                  │          │
│                    ┌──────────────────────────────┘          │
│                    │                                         │
│                    ▼                                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Retrieval Strategies                     │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │  │
│  │  │ Subject-     │  │ Document-    │  │ Content-   │ │  │
│  │  │ filtered     │  │ specific     │  │ based      │ │  │
│  │  │ search       │  │ retrieval    │  │ fallback   │ │  │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Hình 4.2.** Kiến trúc Knowledge Retrieval Module

**Quá trình Ingestion (Đánh chỉ mục):**

1. **Document Loading:** Content Agent nhận file upload, chọn loader phù hợp (PyPDFLoader cho PDF, Docx2txtLoader cho DOCX, Presentation cho PPTX, TextLoader cho TXT).

2. **Text Cleaning:** Loại bỏ nội dung không liên quan (thông tin giảng viên, SĐT, email, quy chế môn học) bằng pattern matching. Normalize khoảng trắng và loại bỏ dòng ngắn hơn 18 ký tự.

3. **Subject Detection:** Chiến lược 3 tầng: filename heuristics → LLM classification → teacher override.

4. **Chunking:** Sử dụng RecursiveCharacterTextSplitter với chunk_size=1000 ký tự, overlap=200 ký tự, đảm bảo ngữ cảnh không bị cắt đứt giữa câu.

5. **Embedding:** Mỗi chunk được chuyển thành vector 384 chiều bằng model all-MiniLM-L6-v2 (CPU-optimized, phù hợp triển khai không cần GPU).

6. **Indexing:** Vector + metadata (subject, source_file, class_id) được lưu vào ChromaDB collection `ai_learning_collection` với chế độ persistent storage.

**Chiến lược Retrieval:**

Module hỗ trợ nhiều chiến lược truy vấn:

- **Subject-filtered search:** Lọc theo môn học để đảm bảo context đúng lĩnh vực. Sử dụng ChromaDB filter: `{"subject": {"$eq": "Lập trình hướng đối tượng"}}`
- **Document-specific retrieval:** Khi sinh viên đang mở 1 tài liệu cụ thể, chỉ truy vấn chunks từ tài liệu đó. Filter: `{"source": {"$eq": "Bai3_Inheritance.pdf"}}`
- **Content-based fallback:** Khi vector store không khả dụng, agent đọc trực tiếp file từ disk, fallback không cần RAG.

## 4.4 Assessment Support Module

Assessment Support Module (ASM) cung cấp toàn bộ quy trình kiểm tra đánh giá: từ tạo câu hỏi đến chấm điểm và phản hồi. Module được triển khai qua sự phối hợp của Assessment Agent, Evaluation Agent, và Review Agent.

**Kiến trúc Assessment Support Module:**

```
┌─────────────────────────────────────────────────────────────────┐
│              ASSESSMENT SUPPORT MODULE                           │
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐     │
│  │   Question   │    │   Quiz       │    │   Grading &   │     │
│  │   Generation │───►│   Delivery   │───►│   Feedback    │     │
│  │              │    │              │    │               │     │
│  │ • RAG-based  │    │ • Bloom's    │    │ • Auto-scoring│     │
│  │ • Concept    │    │   taxonomy   │    │ • Wrong answer│     │
│  │   extraction │    │ • Difficulty │    │   tracking    │     │
│  │ • Quality    │    │   levels     │    │ • AI feedback │     │
│  │   validation │    │ • Time limit │    │ • Review      │     │
│  └─────────────┘    └──────────────┘    │   material    │     │
│                                         └───────────────┘     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              OCR Exam Pipeline (Offline)                  │  │
│  │                                                          │  │
│  │  Tạo đề in → Scan bài thi → OCR nhận diện → OMR chấm   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Hình 4.3.** Kiến trúc Assessment Support Module

**Quy trình sinh câu hỏi (Question Generation Pipeline):**

1. **Context Retrieval:** Assessment Agent truy vấn ChromaDB để lấy nội dung tài liệu liên quan (k=60 chunks).

2. **Concept Extraction:** Phân tích RAG content để trích xuất các khái niệm học tập (academic concepts). Lọc bỏ câu không mang tính học thuật (admin info, metadata).

3. **Domain Consistency Check:** Kiểm tra concepts có thuộc đúng lĩnh vực môn học dựa trên bộ từ khóa đặc thù.

4. **MCQ Generation:** Với mỗi concept, LLM sinh câu hỏi trắc nghiệm theo mức Bloom's taxonomy được chỉ định. Mỗi câu gồm: nội dung câu hỏi, 4 lựa chọn (1 đúng, 3 nhiễu), đáp án đúng, và giải thích.

5. **Quality Validation (5 bước):**
   - Format validation: đúng 4 options, 1 correct label
   - Generic option filtering: loại "Tất cả đều đúng", "Không có đáp án"
   - Option diversity: fingerprinting để phát hiện options quá giống
   - Similarity detection: so với QuestionBank hiện có
   - Pool diversity check: đảm bảo ngân hàng câu hỏi đa dạng

6. **Bank Storage:** Câu hỏi hợp lệ được lưu vào bảng QuestionBank với metadata (difficulty, source_file, subject).

**Quy trình chấm và phản hồi (Grading & Feedback Pipeline):**

1. **Auto-scoring:** So sánh đáp án sinh viên với answer key, tính điểm.

2. **Wrong Answer Tracking:** Mỗi câu sai được lưu chi tiết vào WrongAnswerRecord: câu hỏi, lựa chọn của sinh viên, đáp án đúng, giải thích.

3. **Evaluation Feedback:** Evaluation Agent phân tích kết quả và sinh phản hồi AI cá nhân hóa:
   - Beginner: giải thích khái niệm, dùng ngôn ngữ đơn giản
   - Intermediate: phân tích sai lệch, đề xuất chiến lược
   - Advanced: thử thách phản biện, gợi ý mở rộng

4. **Review Material Generation:** Review Agent tổng hợp wrong answers thành tài liệu ôn tập có cấu trúc: khái niệm cốt lõi, ví dụ minh họa, và bài tập thực hành.

5. **Profile Update:** Cập nhật LearnerProfile và StudentDocumentEvaluation sau mỗi bài kiểm tra.

**OCR Exam Pipeline (cho thi giấy):**

Module cũng hỗ trợ quy trình thi trên giấy cho các trường hợp cần:
- Assessment Agent tạo đề thi in (DOCX) với answer key và OMR layout
- Giảng viên in và thu bài thi đã làm
- Scan bài thi → OCR nhận diện thông tin sinh viên và đáp án
- OMR chấm tự động → lưu kết quả vào TestOCRGradingResult

Tổng kết, Knowledge Retrieval Module và Assessment Support Module là hai module nền tảng cung cấp dữ liệu đầu vào cho toàn bộ quá trình cá nhân hóa: KRM đảm bảo agent có context chính xác từ tài liệu, ASM cung cấp dữ liệu đánh giá liên tục để cập nhật learner profile và điều chỉnh lộ trình học.
