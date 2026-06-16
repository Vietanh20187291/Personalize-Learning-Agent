# CHƯƠNG 3. KIẾN TRÚC MULTI-AGENT ĐỀ XUẤT

## 3.1 Động cơ đề xuất kiến trúc

Hệ thống giáo dục trực tuyến truyền thống (LMS) thường gặp ba hạn chế cốt lõi khi áp dụng trí tuệ nhân tạo vào cá nhân hóa học tập.

**Thứ nhất**, các hệ thống LMS hiện tại (Moodle, Canvas, Blackboard) xử lý logic nghiệp vụ theo mô hình đơn thể (monolithic). Toàn bộ chức năng — từ quản lý nội dung, tạo bài kiểm tra, đến đánh giá kết quả — được triển khai trong một khối logic duy nhất. Khi cần mở rộng hoặc thay đổi một chức năng, toàn bộ hệ thống bị ảnh hưởng. Điều này đặc biệt bất lợi trong bối cảnh AI, nơi các mô hình ngôn ngữ lớn (LLM) liên tục được cập nhật và cần thay đổi prompt, tham số mà không làm gián đoạn các chức năng khác.

**Thứ hai**, các hệ thống e-learning hiện có thiếu khả năng cá nhân hóa sâu. Personalization thường dừng ở mức phân luồng đơn giản: nếu sinh viên đạt điểm cao → chuyển sang bài tiếp theo; nếu điểm thấp → yêu cầu học lại [1]. Cách tiếp cận này không phản ánh được sự phức tạp của quá trình học tập thực tế, nơi mỗi sinh viên có mức độ nắm bắt khác nhau ở từng chủ đề, có những hiểu lầm (misconception) đặc thù, và có phong cách học (learning style) riêng.

**Thứ ba**, khả năng phối hợp giữa các chức năng AI bị hạn chế. Trong một hệ thống học tập thông minh, việc tạo đề thi cần thông tin từ quá trình học, việc tư vấn cần hiểu kết quả đánh giá, và việc lập kế hoạch học cần cả hai. Khi các chức năng này hoạt động độc lập, không chia sẻ ngữ cảnh, kết quả là trải nghiệm học tập rời rạc — sinh viên nhận được tư vấn chung chung, đề thi không phù hợp năng lực, và kế hoạch học không phản ánh đúng điểm yếu.

Từ những phân tích trên, luận án đề xuất kiến trúc **Multi-Agent** với một **Agent Hub** đóng vai trò trung tâm điều phối. Mỗi agent được thiết kế như một chuyên gia độc lập, chịu trách nhiệm một lĩnh vực cụ thể (nội dung, lập kế hoạch, đánh giá, tư vấn, kiểm tra), nhưng có khả năng chia sẻ ngữ cảnh và phối hợp thông qua Agent Hub.

Bảng 3.1 so sánh kiến trúc đề xuất với các phương pháp tiếp cận hiện có.

**Bảng 3.1.** So sánh kiến trúc đề xuất với các hệ thống hiện có

| Tiêu chí | LMS truyền thống | Hệ thống AI đơn thể | **Kiến trúc Multi-Agent đề xuất** |
|---|---|---|---|
| Mở rộng chức năng | Thêm module thủ công | Sửa đổi toàn hệ thống | **Thêm agent mới, không ảnh hưởng agent cũ** |
| Cá nhân hóa | Phân luồng theo quy tắc cứng | Personalization theo 1 chiều | **Đa chiều: nội dung + nhịp độ + phong cách** |
| Phối hợp AI | Không có | Giới hạn trong 1 module | **Chia sẻ ngữ cảnh qua Agent Hub** |
| Khả năng phục hồi | Không áp dụng | Lỗi 1 phần → lỗi toàn hệ thống | **Fallback từng agent, hệ thống vẫn hoạt động** |
| Bảo trì prompt | N/A | Tìm trong codebase lớn | **Tập trung trong từng agent** |

## 3.2 Agent Hub Architecture

### 3.2.1 Vai trò của Agent Hub

Agent Hub là thành phần trung tâm của kiến trúc multi-agent, đóng vai trò như một **bộ điều phối (orchestrator)** quản lý toàn bộ vòng đời của các request từ người dùng đến các agent chuyên biệt.

Trong hệ thống triển khai, vai trò của Agent Hub được hiện thực hóa thông qua **Nova Teacher Agent** — một agent giao tiếp chính (front-facing agent) tiếp nhận mọi yêu cầu từ giảng viên, phân tích ý định (intent), và điều hướng đến agent chuyên biệt phù hợp.

Vai trò cụ thể của Agent Hub bao gồm:

1. **Tiếp nhận và phân tích ý định (Intent Analysis):** Khi nhận được yêu cầu từ người dùng, Hub sử dụng kết hợp phân tích dựa trên quy tắc (rule-based) và LLM để xác định ý định của người dùng. Các intent được hỗ trợ bao gồm: COURSE_INFO, CLASS_OVERVIEW, CLASS_ANALYTICS, STUDENT_OVERVIEW, MATERIAL, GENERATE_EXAM, CRUD_OPERATION, và các intent khác.

2. **Điều hướng yêu cầu (Request Routing):** Dựa trên intent đã xác định, Hub chuyển tiếp yêu cầu đến agent chuyên biệt cùng với ngữ cảnh cần thiết (subject, classroom, student info).

3. **Quản lý ngữ cảnh hội thoại (Conversation Context Management):** Hub duy trì ngữ cảnh hội thoại bao gồm last_subject, last_class, last_student, pending_request — cho phép các agent tiếp theo hiểu được ngữ cảnh liên tục của cuộc hội thoại.

4. **Hợp nhất phản hồi (Response Aggregation):** Khi nhiều agent tham gia xử lý một yêu cầu phức tạp, Hub thu thập và hợp nhất kết quả trước khi trả về cho người dùng.

Hình 3.1 minh họa vị trí của Agent Hub trong kiến trúc tổng thể.

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND LAYER                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Teacher  │  │ Student  │  │  Admin   │  │  Assessment  │   │
│  │   Page    │  │  Portal  │  │  Page    │  │    Page      │   │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│        │              │              │               │           │
│        └──────────────┴──────────────┴───────────────┘           │
│                              │                                   │
│                    ┌─────────▼─────────┐                         │
│                    │   REST API Layer   │                         │
│                    └─────────┬─────────┘                         │
└──────────────────────────────┼──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                      AGENT HUB LAYER                            │
│                    ┌─────────▼─────────┐                         │
│                    │   Nova Teacher     │                         │
│                    │   Agent (Hub)      │                         │
│                    │                   │                         │
│                    │  ┌─────────────┐  │                         │
│                    │  │   Intent    │  │                         │
│                    │  │  Classifier │  │                         │
│                    │  └──────┬──────┘  │                         │
│                    │         │         │                         │
│                    │  ┌──────▼──────┐  │                         │
│                    │  │   Action    │  │                         │
│                    │  │   Router    │  │                         │
│                    │  └──────┬──────┘  │                         │
│                    └─────────┼─────────┘                         │
│                              │                                   │
│         ┌────────┬───────┬───┴───┬────────┬────────┐            │
│         ▼        ▼       ▼       ▼        ▼        ▼            │
│    ┌────────┐┌───────┐┌──────┐┌──────┐┌──────┐┌──────┐         │
│    │Content ││Plan   ││Eval  ││Assess││Adapt ││Orbit │         │
│    │Agent   ││Agent  ││Agent ││Agent ││Agent ││Agent │         │
│    └────────┘└───────┘└──────┘└──────┘└──────┘└──────┘         │
│                              │                                   │
│                    ┌─────────▼─────────┐                         │
│                    │   Shared Services  │                         │
│                    │ ┌──────┐ ┌──────┐ │                         │
│                    │ │ RAG  │ │Memory│ │                         │
│                    │ │Store │ │System│ │                         │
│                    │ └──────┘ └──────┘ │                         │
│                    └───────────────────┘                         │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                      DATA LAYER                                 │
│                    ┌─────────▼─────────┐                         │
│                    │   PostgreSQL DB    │                         │
│                    └───────────────────┘                         │
│                    ┌───────────────────┐                         │
│                    │   ChromaDB (RAG)   │                         │
│                    └───────────────────┘                         │
└──────────────────────────────────────────────────────────────────┘
```

**Hình 3.1.** Kiến trúc tổng thể Agent Hub với các agent chuyên biệt

### 3.2.2 Agent Registry

Agent Registry là cơ chế quản lý danh tính và khả năng của các agent trong hệ thống. Mỗi agent khi khởi tạo sẽ đăng ký với Hub, cung cấp thông tin về:

- **Agent identifier:** Tên duy nhất (ví dụ: `content_agent`, `planning_agent`)
- **Capabilities:** Danh sách các nhiệm vụ agent có thể xử lý (ví dụ: `document_processing`, `subject_classification`, `rag_indexing`)
- **Dependencies:** Các service agent phụ thuộc (ví dụ: Content Agent phụ thuộc Vector Store)
- **API Key:** Khóa LLM riêng biệt, cho phép cấu hình độc lập cho từng agent

Trong triển khai thực tế, Agent Registry được quản lý thông qua cấu hình tập trung trong `config.py` và module `llm_client.py`, nơi mỗi agent tự resolve API key từ biến môi trường riêng:

```python
# Mỗi agent tự đăng ký API key riêng
class ContentAgent:
    def _resolve_groq_api_key(self):
        candidates = ["GROQ_KEY_CONTENT", "GROQ_API_KEY", "GROQ_KEY_DEBUG"]
        # ...resolve logic
```

Cách tiếp cận này cho phép:
- **Cấu hình độc lập:** Thay đổi model hoặc API key của một agent không ảnh hưởng các agent khác
- **Rate limiting riêng:** Mỗi agent có giới hạn gọi API riêng, tránh tranh chấp
- **Failover linh hoạt:** Khi key của agent này hết hạn, agent khác vẫn hoạt động bình thường

Bảng 3.2 liệt kê các agent đã đăng ký trong Registry.

**Bảng 3.2.** Agent Registry — các agent trong hệ thống

| Agent | Khóa cấu hình | Model LLM | Khả năng chính |
|---|---|---|---|
| Nova Teacher Agent (Hub) | `GROQ_KEY_TEACHER` | Llama-3.3-70b | Intent classification, routing |
| Content Agent | `GROQ_KEY_CONTENT` | Llama-3.3-70b | Document processing, RAG indexing |
| Planning Agent | `GROQ_KEY_ADAPTIVE` | Llama-3.3-70b | Study plan generation, schedule adjustment |
| Evaluation Agent | `GROQ_KEY_ADAPTIVE` | Llama-3.3-70b | Performance evaluation, feedback generation |
| Assessment Agent | `LLM_PROVIDER` | Configurable | MCQ generation, Bloom's taxonomy |
| Adaptive Agent | `GROQ_KEY_ADAPTIVE` | Llama-3.3-70b | Personalized tutoring, roadmap |
| Orbit Agent | `GROQ_KEY_ORBIT` | Llama-3.3-70b | Student coaching, monitoring |
| Profiling Agent | `GROQ_KEY_PROFILING` | Llama-3.3-70b | Learner classification |
| Review Agent | `GROQ_KEY_REVIEW` | Llama-3.3-70b | Review material generation |

### 3.2.3 Agent Routing

Agent Routing là cơ chế ánh xạ ý định người dùng (intent) đến agent xử lý phù hợp. Quá trình routing diễn ra trong hai giai đoạn:

**Giai đoạn 1: Intent Classification**

Nova Teacher Agent nhận yêu cầu từ người dùng và phân tích ý định thông qua kết hợp hai phương pháp:

```python
def analyze(self, message, context):
    # 1. Rule-based: nhanh, chính xác cho intent rõ ràng
    intent = self._rule_based_analyze(message, context)
    
    # 2. LLM-based: cho intent phức tạp, mơ hồ
    if intent is None or intent.confidence < 0.7:
        intent = self._llm_single_pass_analyze(message, context)
    
    return intent  # {intent_type, entities, confidence}
```

Các intent được hỗ trợ và agent tương ứng được mô tả trong Bảng 3.3.

**Bảng 3.3.** Intent-Route mapping

| Intent | Mô tả | Agent xử lý | Ví dụ yêu cầu |
|---|---|---|---|
| `COURSE_INFO` | Thông tin môn học | Teacher Agent | "Môn OOP có bao nhiêu bài?" |
| `CLASS_OVERVIEW` | Tổng quan lớp học | Teacher Agent | "Tình hình lớp Python?" |
| `CLASS_ANALYTICS` | Phân tích lớp | Teacher Agent | "Phân tích điểm lớp CNTT1" |
| `STUDENT_OVERVIEW` | Xem sinh viên | Teacher Agent | "Xem hồ sơ sinh viên Nguyễn Văn A" |
| `MATERIAL` | Quản lý tài liệu | Content Agent | "Tải lên tài liệu bài 3" |
| `GENERATE_EXAM` | Tạo đề thi | Assessment Agent | "Tạo 20 câu trắc nghiệm OOP" |
| `CRUD_OPERATION` | Thao tác CRUD | Teacher Agent | "Thêm sinh viên vào lớp" |
| `TUTOR_CHAT` | Hỏi gia sư AI | Adaptive Agent | "Giải thích polymorphism" |
| `PLAN_REQUEST` | Lập kế hoạch học | Planning Agent | "Lập lịch học tuần này" |
| `PROGRESS_CHECK` | Xem tiến độ | Evaluation Agent | "Điểm của tôi thế nào?" |
| `COACHING` | Tư vấn học tập | Orbit Agent | "Tôi nên học gì tiếp?" |

**Giai đoạn 2: Context Enrichment**

Sau khi xác định intent và agent đích, Hub enriches request với ngữ cảnh từ:
- **Conversation Memory:** Lớp học, môn học, sinh viên đang thảo luận
- **Database:** Thông tin lớp, tài liệu, điểm số liên quan
- **Previous Intent:** Intent trước đó để xử lý các yêu cầu liên tiếp (follow-up)

### 3.2.4 Task Orchestration

Task Orchestration là quá trình phối hợp nhiều agent để hoàn thành một tác vụ phức tạp. Hệ thống hỗ trợ hai mẫu orchestration chính:

**Pattern 1: Sequential Pipeline**

Một số tác vụ yêu cầu nhiều agent xử lý tuần tự. Ví dụ: khi giảng viên tải lên tài liệu mới, hệ thống thực hiện pipeline sau:

```
Document Upload → Content Agent (xử lý, phân loại, chunking, embedding)
               → Assessment Agent (tạo ngân hàng câu hỏi từ tài liệu)
               → Notification Service (thông báo sinh viên)
```

Mỗi bước nhận output của bước trước làm input. Nếu một bước thất bại, hệ thống vẫn giữ kết quả của các bước đã hoàn thành.

**Pattern 2: Fan-out with Context Sharing**

Khi sinh viên truy cập tab học tập, hệ thống kích hoạt đồng thời nhiều agent:

```
Student Login → Planning Agent (sinh kế hoạch học)
             → Adaptive Agent (cập nhật roadmap)
             → Orbit Agent (chào + coaching)
             → Evaluation Agent (cập nhật profile)
```

Các agent chia sẻ ngữ cảnh chung (user_id, subject, enrolled_classes) nhưng hoạt động độc lập. Kết quả được tổng hợp và hiển thị trên giao diện học sinh.

**Pattern 3: Hub-Mediated Collaboration**

Khi một agent cần thông tin từ agent khác, nó không giao tiếp trực tiếp mà thông qua Hub:

```
Adaptive Agent: "Sinh viên hỏi về recursion"
    → Hub: truy vấn Evaluation Agent → "Sinh viên sai 3 câu recursion gần đây"
    → Hub: enrich Adaptive Agent context với weak_topics + misconceptions
    → Adaptive Agent: trả lời cá nhân hóa dựa trên dữ liệu đánh giá
```

Mẫu này đảm bảo loose coupling giữa các agent — Adaptive Agent không cần biết Evaluation Agent tồn tại, chỉ cần Hub cung cấp context phù hợp.

## 3.3 Các Agent trong hệ thống

### 3.3.1 Nova Teacher Agent

Nova Teacher Agent là agent trung tâm (Hub Agent), đóng vai trò giao tiếp chính với giảng viên. Khác với các agent chuyên biệt chỉ xử lý một lĩnh vực, Nova Teacher Agent phải hiểu được toàn bộ khả năng của hệ thống để điều hướng yêu cầu đúng chỗ.

**Kiến trúc xử lý:**

```
Input (message + context)
        │
   ┌────▼────┐
   │ Intent   │ ─── Rule-based (nhanh, cho intent rõ ràng)
   │Analysis  │ ─── LLM-based (cho intent phức tạp, mơ hồ)
   └────┬────┘
        │
   ┌────▼────┐
   │ Entity   │ ─── Trích xuất: subject, classroom, student
   │Extraction│ ─── Từ message + conversation context
   └────┬────┘
        │
   ┌────▼────┐
   │ Response │ ─── Xử lý trực tiếp (analytics, info)
   │Generation│ ─── Delegate đến agent khác (exam, planning)
   └────┬────┘
        │
     Response + Context Updates
```

**Intent Classification** sử dụng hybrid approach: phân tích rule-based dựa trên keyword matching (fast path) kết hợp LLM single-pass analysis cho các yêu cầu phức tạp. Ví dụ, yêu cầu "Tạo 20 câu trắc nghiệm OOP" dễ dàng nhận diện qua pattern "tạo" + số lượng + "trắc nghiệm" + tên môn. Tuy nhiên, yêu cầu "Sinh viên nào cần chú ý nhất?" yêu cầu LLM để hiểu ngữ cảnh hội thoại trước đó.

**Conversation Memory** được triển khai với Redis backend (production) và in-memory fallback (development), hỗ trợ:
- Lưu trữ tối đa 20 tin nhắn gần nhất
- TTL (Time-to-Live) 8 giờ
- Context tracking: last_subject, last_class, last_student, pending_request
- Distributed: nhiều backend instance chia sẻ state qua Redis

Nova Teacher Agent hỗ trợ các nghiệp vụ chính:
- Xem thông tin môn học, lớp học
- Phân tích điểm số lớp/sinh viên
- Tạo và giao chỉ tiêu học tập (Orbit Coach Directives)
- Tạo đề thi trắc nghiệm nhiều phiên bản
- Quản lý CRUD (thêm/xóa sinh viên, lớp, môn học)

### 3.3.2 Planning Agent

Planning Agent chịu trách nhiệm tạo và điều chỉnh kế hoạch học tập cá nhân cho sinh viên. Khác với các hệ thống chỉ tạo lộ trình (roadmap) tĩnh, Planning Agent sinh **lịch học cụ thể theo ngày** dựa trên nhiều nguồn dữ liệu.

**Đầu vào cho quá trình lập kế hoạch:**

| Nguồn dữ liệu | Thông tin sử dụng |
|---|---|
| StudentDocumentEvaluation | Điểm số gần nhất, số lần thử, trạng thái hoàn thành |
| Document (visible) | Danh sách tài liệu cần học, thứ tự upload |
| LearnerProfile | Mức năng lực hiện tại |
| OrbitCoachDirective | Chỉ tiêu từ giảng viên (nếu có) |
| StudySession | Thời gian học thực tế |

**Thuật toán xếp hạng ưu tiên (Priority Ranking):**

Planning Agent sử dụng hàm xếp hạng 4 tiêu chí để sắp xếp tài liệu cần học:

```python
def _priority_rank(self, item):
    score = item.latest_score or 0
    attempts = item.attempts or 0
    # Ưu tiên 1: Chưa làm bài (attempts = 0)
    # Ưu tiên 2: Điểm thấp (< 50)
    # Ưu tiên 3: Điểm trung bình (50-70)
    # Giới hạn workload: 1-2 tài liệu/tuần
```

**Điều chỉnh kế hoạch (Schedule Adjustment):**

Planning Agent hỗ trợ sinh viên yêu cầu thay đổi kế hoạch bằng ngôn ngữ tự nhiên:

- "Ưu tiên môn X trước" → điều chỉnh priority
- "Hoãn chương Y sang tuần sau" → dời deadline
- "Tôi muốn tăng/t giảm tải" → thay đổi workload

Agent sử dụng LLM để phân tích yêu cầu và xuất JSON chỉ thị điều chỉnh, đảm bảo ràng buộc workload không vượt quá giới hạn.

### 3.3.3 Content Agent

Content Agent chịu trách nhiệm xử lý toàn bộ vòng đời của tài liệu học tập: tiếp nhận, phân tích, phân loại, chunking, và đánh chỉ mục (indexing) vào vector database.

**Pipeline xử lý tài liệu:**

```
File Upload
    │
    ▼
┌──────────────┐
│  Format       │  PDF → PyPDFLoader
│  Detection    │  DOCX → Docx2txtLoader
│  & Loading    │  PPTX → python-pptx
│               │  TXT → TextLoader
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Subject      │  1. Filename heuristics
│  Detection    │  2. LLM classification (if uncertain)
│               │  3. Teacher assignment override
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Chunking     │  RecursiveCharacterTextSplitter
│  & Embedding  │  chunk_size=1000, overlap=200
│               │  Embedding: all-MiniLM-L6-v2
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Vector Store │  ChromaDB (persistent)
│  Indexing     │  Metadata: {subject, source, class_id}
└──────────────┘
```

**Phát hiện môn học (Subject Detection)** sử dụng chiến lược 3 tầng:
1. **Heuristic:** Phân tích tên file (ví dụ: "Bai_giang_OOP.pdf" → "Lập trình hướng đối tượng")
2. **LLM Classification:** Nếu heuristic không đủ tự tin, gọi LLM với prompt phân loại dựa trên nội dung
3. **Teacher Override:** Giảng viên có thể chỉ định môn học trực tiếp khi upload

Content Agent cũng quản lý visibility của tài liệu thông qua bảng `DocumentPublication`, cho phép giảng viên ẩn/hiện tài liệu theo tiến độ giảng dạy.

### 3.3.4 Evaluation Agent

Evaluation Agent cung cấp khả năng đánh giá năng lực học sinh theo nhiều chiều: phân tích điểm số tổng quan, phản hồi AI về kết quả bài kiểm tra, và phân tích chi tiết từng câu sai.

**Ba chế độ đánh giá:**

**1. Progress Analysis (chat_about_progress):**
- Tổng hợp điểm từ AssessmentHistory và StudentDocumentEvaluation
- Sinh nhận xét AI dựa trên xu hướng điểm (tăng/giảm/ổn định)
- So sánh hiệu suất giữa các môn học

**2. Performance Feedback (evaluate_performance):**
- Đánh giá một bài kiểm tra cụ thể
- Sử dụng prompt "AI Lecturer" với ràng buộc:
  - Tối đa 40 từ
  - Không dùng câu điều kiện ("nếu...")
  - Phải cụ thể: chỉ đúng điểm, đúng câu sai
  - Tone: khuyến khích nhưng thẳng thắn

**3. Wrong Answer Analysis (analyze_quiz_answers):**
- Phân tích từng câu trả lời sai
- Lưu vào WrongAnswerRecord để Tracking misconceptions
- Kết hợp với Review Agent để sinh tài liệu ôn tập

**Cá nhân hóa đánh giá:**

Evaluation Agent sử dụng learner profile để điều chỉnh phản hồi:

| Mức năng lực | Chiến lược phản hồi |
|---|---|
| Beginner | Tập trung vào khái niệm cơ bản, dùng ngôn ngữ đơn giản, khích lệ nhiều |
| Intermediate | Nhấn mạnh phân tích sai lệch, gợi ý chiến lược cải thiện |
| Advanced | Thử thách phản biện, đề xuất mở rộng, so sánh quan điểm |

### 3.3.5 Assessment Agent

Assessment Agent là agent phức tạp nhất trong hệ thống, chịu trách nhiệm tạo câu hỏi trắc nghiệm (MCQ) chất lượng cao dựa trên tài liệu học tập. Khác với nhiều hệ thống chỉ sinh câu hỏi từ template, Assessment Agent sử dụng quy trình nhiều bước đảm bảo chất lượng.

**Quy trình tạo câu hỏi:**

```
Document Content
       │
       ▼
┌──────────────┐
│  RAG Context  │  ChromaDB similarity search
│  Retrieval    │  k=60 chunks, filter by subject
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Concept      │  Trích xuất khái niệm từ RAG content
│  Extraction   │  Lọc: academic relevance, domain consistency
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  MCQ          │  LLM generation với Bloom's taxonomy
│  Generation   │  JSON format, strict validation
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Quality      │  1. Kiểm tra format (4 options, 1 correct)
│  Validation   │  2. Kiểm tra duplicate (similarity check)
│               │  3. Kiểm tra generic options
│               │  4. Kiểm tra diversity (fingerprinting)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Question     │  Lưu vào QuestionBank
│  Bank Storage │  Metadata: difficulty, source_file, subject
└──────────────┘
```

**Phân cấp theo Bloom's Taxonomy:**

Assessment Agent sinh câu hỏi theo 6 mức độ tư duy:

| Level | Mô tả | Ví dụ câu hỏi |
|---|---|---|
| Remember | Nhớ lại kiến thức | "Khái niệm X được định nghĩa là gì?" |
| Understand | Hiểu và giải thích | "Phát biểu nào mô tả đúng nhất X?" |
| Apply | Áp dụng vào tình huống | "Cho đoạn code sau, kết quả là gì?" |
| Analyze | Phân tích thành phần | "Sự khác biệt giữa X và Y là gì?" |
| Evaluate | Đánh giá và phán đoán | "Phương án nào tối ưu nhất? Vì sao?" |
| Create | Sáng tạo và tổng hợp | "Thiết kế giải pháp cho bài toán sau" |

**Kiểm tra chất lượng (Quality Validation):**

Assessment Agent thực hiện nhiều lớp kiểm tra để đảm bảo câu hỏi đạt chất lượng:

1. **Format validation:** Đảm bảo đúng 4 lựa chọn, đúng 1 đáp án, có giải thích
2. **Diversity check:** Sử dụng option fingerprinting để phát hiện lựa chọn quá giống nhau
3. **Domain consistency:** Kiểm tra câu hỏi có thuộc đúng lĩnh vực môn học
4. **Generic option filtering:** Loại bỏ các lựa chọn quá chung chung ("Tất cả đều đúng", "Không có đáp án đúng")
5. **Similarity detection:** So sánh với câu hỏi đã có trong ngân hàng để tránh trùng lặp

**Hỗ trợ nhiều LLM Provider:**

Assessment Agent được thiết kế provider-agnostic, hỗ trợ:
- **Groq** (fast inference, Llama models)
- **OpenAI** (GPT models)
- **Google Gemini**
- **Ollama** (local inference)

## 3.4 Agent Interaction Workflow

Hệ thống hỗ trợ nhiều workflow phức tạp đòi hỏi sự phối hợp giữa nhiều agent. Dưới đây là hai workflow tiêu biểu.

**Workflow 1: Sinh viên hỏi Tutor AI**

```
Sinh viên: "Giải thích đệ quy cho tôi"
        │
        ▼
[Adaptive Agent]
   1. Nhận user_id + subject
   2. _build_student_context(user_id, subject)
      ├─ Query LearnerProfile → level: "Intermediate"
      ├─ Query StudentDocumentEvaluation → weak: "Recursion (35đ)"
      ├─ Query WrongAnswerRecord → 3 câu sai recursion gần đây
      ├─ Query StudentDocumentEvaluation → strong: "Arrays (85đ)"
      └─ Query StudentLearningProgress → 120 phút học
   3. Inject context vào system prompt
   4. RAG retrieval: ChromaDB → tài liệu recursion
   5. Gọi LLM với personalized system prompt
   6. Kết quả: giải thích step-by-step + kiểm tra misconception
        │
        ▼
Response: "Bạn đang nhầm lẫn giữa đệ quy tail và non-tail..."
```

**Workflow 2: Giảng viên tạo đề thi**

```
Giảng viên: "Tạo 20 câu trắc nghiệm OOP, 2 phiên bản"
        │
        ▼
[Nova Teacher Agent (Hub)]
   1. Intent: GENERATE_EXAM
   2. Entity extraction: subject=OOP, count=20, versions=2
   3. Route → Assessment Agent
        │
        ▼
[Assessment Agent]
   1. RAG context retrieval (ChromaDB, filter: OOP)
   2. Concept extraction from RAG content
   3. MCQ generation with Bloom's taxonomy schedule
   4. Quality validation (5 bước)
   5. Lưu vào QuestionBank
   6. Tạo 2 phiên bản với câu hỏi khác nhau
        │
        ▼
[Nova Teacher Agent (Hub)]
   7. Tạo OCR exam batch (answer key + OMR layout)
   8. Sinh file DOCX
   9. Trả về download link
```

**Workflow 3: Sinh viên login — Fan-out orchestration**

```
Sinh viên đăng nhập
        │
        ├──→ [Planning Agent]
        │    Sinh/cập nhật kế hoạch học tuần
        │
        ├──→ [Orbit Agent]
        │    Chào + coaching cá nhân hóa
        │    "Minh à, tuần này bạn toàn học sau 10h tối..."
        │
        ├──→ [Evaluation Agent]
        │    Cập nhật learner profile từ điểm gần nhất
        │
        └──→ [Adaptive Agent]
              Cập nhật roadmap dựa trên profile mới
```

Hình 3.2 tóm tắt các tương tác giữa agent dưới dạng sequence diagram.

```
┌────────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│  User  │  │ Hub  │  │Adapt │  │Plan  │  │Assess│  │Eval  │  │Content│
└───┬────┘  └───┬──┘  └───┬──┘  └───┬──┘  └───┬──┘  └───┬──┘  └───┬──┘
    │           │         │         │         │         │         │
    │──chat─────►│         │         │         │         │         │
    │           │──route──►│         │         │         │         │
    │           │   context│──build──┤         │         │         │
    │           │   (profile)       │ profile  │         │         │
    │           │         │──RAG─────────────────────────────────►│
    │           │         │◄──chunks│         │         │         │
    │           │         │──LLM───►│         │         │         │
    │           │◄─reply──│         │         │         │         │
    │◄─reply────│         │         │         │         │         │
    │           │         │         │         │         │         │
    │──"tạo đề"─►│         │         │         │         │         │
    │           │─────────────────────────►│         │         │
    │           │         │         │  RAG───────────────────►│
    │           │         │         │◄─questions│         │         │
    │           │◄─exam───────────────────│         │         │
    │◄─download─│         │         │         │         │         │
    │           │         │         │         │         │         │
    │──"điểm"──►│         │         │         │         │         │
    │           │─────────────────────────────────────►│         │
    │           │         │         │         │  profile│         │
    │◄─feedback─│◄─────────────────────────────────│         │
    │           │         │         │         │         │         │
```

**Hình 3.2.** Sequence diagram — các tương tác giữa agent trong hệ thống

## 3.5 Tổng kết chương

Chương 3 đã trình bày kiến trúc multi-agent đề xuất cho hệ thống cá nhân hóa học tập. Các đóng góp chính bao gồm:

1. **Agent Hub Architecture:** Kiến trúc với Nova Teacher Agent đóng vai trò trung tâm điều phối, đảm bảo loose coupling giữa các agent chuyên biệt. Hub tiếp nhận yêu cầu, phân tích ý định, và điều hướng đến agent phù hợp — cho phép hệ thống mở rộng bằng cách thêm agent mới mà không ảnh hưởng các agent hiện có.

2. **Agent Registry và Routing:** Cơ chế quản lý danh tính agent và ánh xạ intent đến agent xử lý. Kết hợp rule-based và LLM-based intent classification cho phép xử lý cả yêu cầu rõ ràng lẫn mơ hồ.

3. **Chín agent chuyên biệt:** Mỗi agent tập trung vào một lĩnh vực — Content (tài liệu), Planning (kế hoạch), Evaluation (đánh giá), Assessment (kiểm tra), Adaptive (gia sư), Orbit (coaching), Profiling (phân loại), Review (ôn tập), và Teacher (giao tiếp giảng viên). Sự phân tách này cho phép phát triển, kiểm thử, và triển khai độc lập.

4. **Ba mẫu orchestration:** Sequential Pipeline (xử lý tuần tự), Fan-out with Context Sharing (kích hoạt song song), và Hub-Mediated Collaboration (phối hợp qua Hub) — đảm bảo linh hoạt trong xử lý cả tác vụ đơn giản lẫn phức tạp.

5. **Cá nhân hóa sâu:** Thông qua việc chia sẻ learner profile, wrong answer history, và misconception data giữa các agent thông qua Hub, hệ thống có thể điều chỉnh nội dung, phản hồi, và kế hoạch học tập theo từng cá nhân sinh viên.

Chương tiếp theo sẽ đi vào chi tiết mô hình nền tảng học tập và kiến trúc hệ thống triển khai.
