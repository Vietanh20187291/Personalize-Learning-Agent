# CHƯƠNG 3 – KIẾN TRÚC MULTI-AGENT
## 3.1 Tổng quan kiến trúc hệ thống đề xuất

### 3.1.1 Nguyên tắc thiết kế

Hệ thống đề xuất được xây dựng dựa trên bốn nguyên tắc thiết kế cốt lõi nhằm đảm bảo tính module hóa, khả năng mở rộng và hiệu quả điều phối trong môi trường giáo dục trực tuyến:

**Thứ nhất, nguyên tắc tập trung điều phối (Hub-Centric Orchestration).** Thay vì sử dụng mô hình ngang hàng (peer-to-peer) nơi mọi agent giao tiếp trực tiếp với nhau — gây ra độ phức tạp O(n²) trong giao tiếp — hệ thống áp dụng mô hình Agent Hub, trong đó hai agent đóng vai trò trung tâm điều phối là **Orbit Agent** (hub cho sinh viên) và **Nova Agent** (hub cho giảng viên). Hai hub agent này tiếp nhận mọi yêu cầu từ người dùng, phân tích ý định, và định tuyến đến các agent chuyên biệt phù hợp. Thiết kế này giảm độ phức tạp giao tiếp xuống O(n), đồng thời tạo ra một điểm kiểm soát duy nhất (single point of coordination) giúp dễ dàng thêm agent mới mà không cần thay đổi giao thức giao tiếp tổng thể.

**Thứ hai, nguyên tắc tự chủ (Agent Autonomy).** Mỗi agent chuyên biệt hoạt động như một đơn vị tự chủ với nhiệm vụ, miền tri thức và cơ chế xử lý riêng. AdaptiveAgent tự chủ trong việc tạo lộ trình học và gia sư; EvaluationAgent tự chủ trong việc đánh giá năng lực; AssessmentAgent tự chủ trong việc tạo câu hỏi. Sự tự chủ này cho phép từng agent được phát triển, kiểm thử và tối ưu độc lập.

**Thứ ba, nguyên tắc chia sẻ ngữ cảnh (Shared Context).** Các agent chia sẻ ngữ cảnh thông qua hai cơ chế: (1) cơ sở dữ liệu quan hệ dùng chung (SQLAlchemy ORM) chứa hồ sơ học sinh, kết quả đánh giá, lịch sử học tập; và (2) kho tri thức vector dùng chung (ChromaDB) cho phép truy xuất tài liệu học tập theo ngữ nghĩa. Việc chia sẻ ngữ cảnh giúp các agent có thể phối hợp mà không cần giao tiếp trực tiếp liên tục.

**Thứ tư, nguyên tắc suy giảm mềm (Graceful Degradation).** Khi một thành phần (LLM, ChromaDB, Redis) không khả dụng, hệ thống không sụp đổ mà chuyển sang chế độ suy giảm. Ví dụ: khi ChromaDB lỗi, AdaptiveAgent vẫn trả lời dựa trên template thay vì RAG; khi Groq chạm rate limit, LLMClient tự động chuyển sang Gemini. Thiết kế này đảm bảo tính sẵn sàng cao trong môi trường sản xuất.

### 3.1.2 Kiến trúc phân tầng

Hệ thống được tổ chức theo kiến trúc phân tầng (layered architecture) gồm 5 tầng, mỗi tầng có trách nhiệm riêng và giao tiếp với tầng liền kề qua các interface rõ ràng:

```
┌─────────────────────────────────────────────────────────────────┐
│                 TẦNG PRESENTATION (Frontend)                    │
│    Next.js 16 · React 19 · TypeScript · Framer Motion           │
│    StudentOrbitAgent.tsx          NovaTeacherAgent.tsx           │
│    (Orbit Chat Widget)            (Nova Chat Widget)             │
├─────────────────────────────────────────────────────────────────┤
│                   TẦNG API GATEWAY (FastAPI)                     │
│    /orbit/chat    /teacher-agent/nova-interactive                │
│    /adaptive/*    /assessment/*    /evaluation/*    /planning/*  │
├─────────────────────────────────────────────────────────────────┤
│              TẦNG AGENT HUB (Điều phối trung tâm)                │
│                                                                  │
│    ┌──────────────────┐          ┌──────────────────┐           │
│    │   ORBIT AGENT     │          │    NOVA AGENT     │           │
│    │  (Student Hub)    │          │  (Teacher Hub)    │           │
│    │  Intent classify  │          │  Intent classify  │           │
│    │  Route → sub-agent│          │  Route → sub-agent│           │
│    │  Action metadata  │          │  UI interaction   │           │
│    └──────┬───────────┘          └──────┬───────────┘           │
│           │                              │                        │
│    ┌──────┴──────────────────────────────┴───────────┐          │
│    │            SUB-AGENTS CHUYÊN BIỆT                │          │
│    │  AdaptiveAgent · EvaluationAgent ·               │          │
│    │  AssessmentAgent · PlanningAgent ·               │          │
│    │  ProfilingAgent · ContentAgent · ReviewAgent     │          │
│    └─────────────────────────────────────────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│              TẦNG DỊCH VỤ HỖ TRỢ                                 │
│    LLM Client (Groq→Gemini)  │  RAG Pipeline (ChromaDB)         │
│    ConversationMemory        │  IntentClassifier + ActionRouter  │
├─────────────────────────────────────────────────────────────────┤
│              TẦNG DỮ LIỆU                                        │
│    SQLAlchemy ORM · SQLite/PostgreSQL · Redis (cache)            │
│    ChromaDB (vector store) · JWT Auth                            │
└─────────────────────────────────────────────────────────────────┘
```

**Tầng Presentation (Frontend):** Xây dựng bằng Next.js 16 với React 19 và TypeScript. Tầng này bao gồm hai widget giao tiếp chính: `StudentOrbitAgent.tsx` cho sinh viên (chat với Orbit) và `NovaTeacherAgent.tsx` cho giảng viên (chat với Nova). Điểm đặc biệt là Nova Teacher Agent có khả năng nhận `action_metadata` từ backend để tự động mở tab, biểu đồ hoặc component giao diện tương ứng — tạo ra trải nghiệm "chat-driven UI" thay vì chỉ chat đơn thuần.

**Tầng API Gateway (FastAPI):** Đóng vai trò trung gian giữa frontend và agent layer. Mỗi API endpoint tương ứng với một chức năng cụ thể: `/orbit/chat` cho Orbit, `/teacher-agent/nova-interactive` cho Nova, `/adaptive/*` cho adaptive learning, v.v. FastAPI đảm bảo validation đầu vào (Pydantic models), CORS, JWT authentication, và logging.

**Tầng Agent Hub:** Đây là tầng cốt lõi của luận văn, chi tiết tại Mục 3.2 và 3.3.

**Tầng Dịch vụ hỗ trợ:** Bao gồm LLM Client với fallback tự động, RAG pipeline dựa trên ChromaDB, ConversationMemory (Redis hoặc in-memory), IntentClassifier và ActionRouter.

**Tầng Dữ liệu:** SQLAlchemy ORM với SQLite (development) hoặc PostgreSQL (production), ChromaDB cho vector storage, Redis cho distributed caching, và JWT cho authentication.

### 3.1.3 Sơ đồ kiến trúc tổng thể

Sơ đồ sau minh họa luồng tương tác hoàn chỉnh giữa người dùng, hai Hub Agent và các sub-agent:

```
    SINH VIÊN                              GIẢNG VIÊN
        │                                      │
        ▼                                      ▼
  ┌─────────────┐                      ┌─────────────┐
  │ Student UI  │                      │ Teacher UI  │
  │  (Orbit     │                      │  (Nova      │
  │  Widget)    │                      │  Widget)    │
  └──────┬──────┘                      └──────┬──────┘
         │ POST /orbit/chat                   │ POST /nova-interactive
         ▼                                    ▼
  ┌─────────────┐                      ┌─────────────┐
  │  ORBIT HUB  │                      │  NOVA HUB   │
  │   AGENT     │                      │   AGENT     │
  │             │                      │             │
  │ Phân tích   │                      │ Intent      │
  │ intent →    │                      │ Classify →  │
  │ định tuyến  │                      │ Entity      │
  │ sub-agent   │                      │ Extract →   │
  │             │                      │ Route →     │
  │ Trả về      │                      │ sub-agent   │
  │ action_     │                      │             │
  │ metadata    │                      │ Trả về      │
  │             │                      │ action_     │
  └──────┬──────┘                      │ metadata +  │
         │                             │ UI actions  │
         │  Gọi sub-agent              └──────┬──────┘
         │                                    │
    ┌────┴────────────────────────────────────┴────┐
    │                                               │
    │  ┌──────────────┐  ┌──────────────┐          │
    │  │ Adaptive     │  │ Evaluation   │          │
    │  │ Agent        │  │ Agent        │          │
    │  └──────────────┘  └──────────────┘          │
    │  ┌──────────────┐  ┌──────────────┐          │
    │  │ Assessment   │  │ Planning     │          │
    │  │ Agent        │  │ Agent        │          │
    │  └──────────────┘  └──────────────┘          │
    │  ┌──────────────┐  ┌──────────────┐          │
    │  │ Profiling    │  │ Content      │          │
    │  │ Agent        │  │ Agent        │          │
    │  └──────────────┘  └──────────────┘          │
    │                                               │
    │           SHARED DATA LAYER                   │
    │  ┌─────────────────────────────────┐         │
    │  │ SQLAlchemy ORM · ChromaDB ·     │         │
    │  │ ConversationMemory              │         │
    │  └─────────────────────────────────┘         │
    └───────────────────────────────────────────────┘
```

---

## 3.2 Thiết kế Hub Agent: Orbit Agent và Nova Agent

### 3.2.1 Orbit Agent — Hub Agent cho sinh viên

Orbit Agent đóng vai trò là **Agent Hub duy nhất cho sinh viên**, là điểm tiếp nhận và điều phối mọi yêu cầu từ phía người học. Thay vì sinh viên phải tương tác riêng lẻ với từng agent chuyên biệt (AdaptiveAgent, EvaluationAgent, PlanningAgent...), Orbit Agent cung cấp một giao diện thống nhất (unified interface) qua widget chat `StudentOrbitAgent.tsx`.

**Cơ chế hoạt động của Orbit Agent:**

1. **Tiếp nhận yêu cầu:** Sinh viên gửi tin nhắn qua POST `/orbit/chat` với tham số `{user_id, subject, message, class_id, document_id, source_file, session_id}`.

2. **Phân tích ý định (Intent Classification):** Orbit Agent sử dụng hệ thống phân loại ý định dựa trên từ khóa (keyword-based intent classifier) để xác định loại yêu cầu:
   - `_is_entry_message()`: Tin nhắn bắt đầu phiên học (VD: "bắt đầu học", "hello orbit")
   - `_is_progress_overview_request()`: Yêu cầu xem kết quả học tập (VD: "thành tích học tập", "kết quả của tôi")
   - `_should_recommend_study()`: Yêu cầu đề xuất học tập (VD: "nên học gì", "học gì tiếp")
   - `_is_open_document_request()`: Yêu cầu mở tài liệu (VD: "mở tài liệu môn X")
   - `_is_summary_request()`: Yêu cầu tóm tắt (VD: "tóm tắt tài liệu")
   - `_is_document_learning_request()`: Câu hỏi về nội dung tài liệu đang mở

3. **Định tuyến đến sub-agent (Agent Routing):** Dựa trên kết quả phân loại ý định, Orbit Agent điều phối đến agent chuyên biệt:
   - **Entry message** → Orbit xử lý trực tiếp: xây dựng báo cáo nhanh gồm trạng thái cảm xúc (Orbit Happy/Angry), thông tin đăng nhập, thời gian học, tiến độ hiện tại.
   - **Progress overview** → Orbit gọi dữ liệu từ EvaluationAgent + xây dựng action_metadata để mở tab Evaluation.
   - **Recommendation/study** → Orbit gọi `_build_recommendation_payload()` phân tích đa môn để chọn môn ưu tiên + tài liệu đề xuất → chuyển kết quả kèm `action_metadata: {action_type: "open_document"}` để frontend tự động mở tài liệu.
   - **Document context** → Orbit gọi AdaptiveAgent.chat_with_tutor() để gia sư RAG trả lời dựa trên tài liệu đang mở.
   - **Summary request** → Orbit lấy tóm tắt nhanh từ ChromaDB chunks + gọi AdaptiveAgent nếu cần.

4. **Xây dựng action_metadata:** Orbit không chỉ trả về text reply mà còn trả về `action_metadata` — một object JSON chỉ thị cho frontend thực hiện hành động giao diện:
   ```json
   {
     "action_type": "open_document",
     "target": "student",
     "tab_name": "adaptive",
     "params": {
       "subject": "Lập trình hướng đối tượng",
       "document_id": 12,
       "filename": "OOP_Chapter1.pdf"
     },
     "should_auto_execute": false,
     "confirm_button_text": "OK, mở tài liệu đề xuất"
   }
   ```
   Hoặc cho kết quả học tập:
   ```json
   {
     "action_type": "open_route",
     "target": "student",
     "tab_name": "evaluation",
     "params": {"route": "/evaluation"},
     "should_auto_execute": true
   }
   ```

5. **Quản lý phiên và bộ nhớ:** Mỗi phiên chat được lưu vào bảng `OrbitChatSession` và `OrbitChatMessage`. Orbit Agent duy trì ngữ cảnh hội thoại qua session, cho phép sinh viên hỏi follow-up mà không cần lặp lại thông tin.

**Cơ chế cá nhân hóa của Orbit Agent:**

Orbit Agent xây dựng profile ngữ cảnh phong phú cho từng sinh viên thông qua các hàm helper:

- `_build_stats(user_id)`: Thu thập 15 chỉ số thống kê bao gồm tổng thời gian học, tuần này, tháng này, số bài kiểm tra, số bài đạt, số tin nhắn Orbit, thời gian chat. Các chỉ số được tính cho 3 khoảng thời gian (total/week/month) để phát hiện xu hướng.
- `_entry_orbit_mode(user_id)`: Xác định trạng thái cảm xúc dựa trên điểm trung bình và thời gian đăng nhập gần nhất. Nếu sinh viên nghỉ lâu hoặc điểm thấp → "angry" (nghiêm khắc); ngược lại → "happy" (động viên).
- `_build_weak_topics_summary(user_id, subject_name)`: Trích xuất các tài liệu có điểm thấp (<50) và câu sai gần đây từ bảng `StudentDocumentEvaluation` và `WrongAnswerRecord`.
- `_pick_focus_subject(user_id)`: Phân tích đa môn để xếp hạng môn cần ưu tiên nhất dựa trên: (1) môn chưa có tài liệu khả dụng, (2) môn có điểm thấp nhất, (3) môn học ít nhất.
- `_build_recommendation_payload(user_id)`: Tổng hợp đề xuất tài liệu cụ thể dựa trên evaluation history — ưu tiên tài liệu chưa làm bài kiểm tra, sau đó là tài liệu có điểm thấp nhất.

### 3.2.2 Nova Agent — Hub Agent cho giảng viên

Nova Agent (được triển khai trong lớp `TeacherAgent`) đóng vai trò là **Agent Hub duy nhất cho giảng viên**, cung cấp giao diện chat thông minh kết hợp với khả năng điều khiển giao diện người dùng. Nova Agent có hai đặc điểm khác biệt so với Orbit:

1. **Giao tiếp agent hai chiều:** Nova không chỉ gọi sub-agent mà còn nhận kết quả trả về và chuyển đổi thành hành động giao diện cụ thể.
2. **Tương tác giao diện (UI Interaction):** Nova trả về `action_metadata` với `should_auto_execute: true`, cho phép frontend tự động mở tab, biểu đồ, hoặc form mà giảng viên không cần click thêm.

**Kiến trúc phân loại ý định hai lớp (Two-Layer Intent Classification):**

Nova Agent sử dụng kiến trúc phân loại ý định hai lớp độc đáo để đảm bảo cả tốc độ lẫn độ chính xác:

**Lớp 1 — LLM-based classification (nhanh, timeout 2 giây):** Nova gửi message đến LLM (Groq Llama 3.3 70B) với system prompt yêu cầu phân loại intent và trích xuất entities. LLM trả về JSON gồm `intent_type`, `entities`, `confidence`. Để đảm bảo không làm chậm trải nghiệm người dùng, Nova đặt timeout 2 giây cho LLM call trong một `ThreadPoolExecutor` riêng biệt.

**Lớp 2 — Rule-based fallback (tức thì):** Nếu LLM timeout hoặc lỗi, Nova tự động chuyển sang rule-based classifier (`IntentClassifier`) sử dụng từ khóa matching với 7 loại intent:
- `course_info`: Thông tin môn học ("môn nào", "bao nhiêu lớp")
- `class_overview`: Tổng quan lớp học ("tình hình lớp", "kết quả lớp IT1")
- `class_analytics`: Phân tích chi tiết ("phân tích lớp", "tỷ lệ đỗ")
- `student_info`: Thông tin sinh viên ("sinh viên A học thế nào")
- `material`: Tài liệu ("tài liệu môn X", "môn nào thiếu tài liệu")
- `exam_generation`: Tạo đề thi ("xuất đề", "30 câu trắc nghiệm")
- `general_question`: Câu hỏi chung

**Trích xuất thực thể (Entity Extraction):**

`IntentClassifier.extract_entities()` sử dụng regex patterns để trích xuất các thực thể từ tin nhắn tiếng Việt:
- `subject_name`: Môn học (VD: "Lập trình hướng đối tượng")
- `class_name`: Lớp học (VD: "IT1", "IT2") — với boundary-aware matching để tránh IT1 match IT10
- `student_name`: Sinh viên (VD: "Nguyễn Văn A")
- `exam_type`: Loại đề ("trắc nghiệm", "tự luận")
- `num_questions`, `num_versions`: Số lượng câu hỏi và mã đề
- `difficulty`: Độ khó ("dễ", "trung bình", "khó")

Hệ thống cũng hỗ trợ **context carryover**: nếu tin nhắn hiện tại thiếu thông tin, Nova tự động bổ sung từ ngữ cảnh hội thoại trước đó (`last_subject_name`, `last_class_name`, `last_student_name`). Điều này cho phép hội thoại multi-turn tự nhiên.

**Định tuyến hành động (Action Routing):**

Sau khi phân loại intent và trích xuất entities, Nova sử dụng `ActionRouter` để quyết định hành động giao diện:

| Intent | Action Type | Target UI | Auto-execute |
|--------|------------|-----------|-------------|
| `class_overview` | `open_tab` | `class_analytics` | ✅ |
| `class_analytics` | `open_tab` | `class_analytics` | ✅ |
| `student_info` | `open_tab` | `student_detailed` | ✅ |
| `material` | `open_tab` | `documents` | ✅ |
| `exam_generation` | `open_tab` | `exam` | ✅ |
| `course_info` | `open_tab` | `subjects` | ✅ |
| `general_question` | `show_chat` | `chat_panel` | ❌ |

Ví dụ minh họa: Khi giảng viên hỏi **"Kết quả lớp IT1 thế nào?"**, Nova Agent thực hiện:

1. Intent classify → `class_overview` (confidence: 0.95)
2. Entity extract → `class_name: "IT1"`
3. Resolve classroom → tìm Classroom object có tên "IT1" trong database
4. Business logic → gọi `_class_overview_reply()` tính toán: số sinh viên, điểm trung bình, tỷ lệ đỗ, phân bố điểm (Yếu/TB/Khá/Giỏi), danh sách sinh viên xuất sắc và cần cải thiện
5. Action route → `action_type: "open_tab"`, `tab_name: "class_analytics"`, `should_auto_execute: true`
6. Frontend nhận response gồm `reply` (văn bản phân tích) + `action_metadata` (chỉ thị mở giao diện)

Kết quả: giảng viên vừa thấy **văn bản phân tích** trong chat panel, vừa thấy **biểu đồ/tab phân tích** được mở tự động bên cạnh — trải nghiệm chat-driven UI.

**Quản lý hội thoại (Conversation Memory):**

Nova Agent sử dụng `ConversationMemory` với hai backend:
- **Redis** (production): Cho phép nhiều backend instance chia sẻ trạng thái hội thoại, hỗ trợ horizontal scaling.
- **In-memory** (development): Fallback khi Redis không khả dụng.

ConversationMemory lưu trữ:
- `conversation_history`: Lịch sử tin nhắn (user + agent) với metadata (intent, confidence, entities)
- `context`: Ngữ cảnh hiện tại (last_subject, last_class, last_student, pending_request)
- `pending_request`: Yêu cầu đang chờ thêm thông tin (VD: giảng viên nói "xuất đề" nhưng chưa nêu môn → Nova hỏi lại và lưu pending request)

**Cơ chế CRUD Detection:**

Nova Agent có khả năng phát hiện yêu cầu CRUD (Create/Read/Update/Delete) trên các entity hệ thống:
- Phát hiện operation từ từ khóa: "thêm/tạo/xóa/sửa/cập nhật"
- Phát hiện entity_type: "môn học/lớp/tài liệu"
- Nếu đủ thông tin → mở form quản lý tương ứng với dữ liệu điền sẵn
- Nếu thiếu → trả về `crud_clarification_response` với hướng dẫn cụ thể

**Orbit Directive — Giao tiếp từ Nova đến Orbit:**

Một tính năng quan trọng thể hiện giao tiếp giữa hai Hub Agent là **Orbit Directive**. Khi giảng viên yêu cầu qua Nova (VD: "Giao bạn An tuần này làm thêm 2 bài kiểm tra"), Nova tạo bản ghi `OrbitCoachDirective` trong database chứa:
- `teacher_id`, `student_id`, `class_id`, `subject_id`
- `target_tests`, `target_chapters` (chỉ tiêu tuần)
- `week_start`, `week_end` (khung thời gian)
- `is_active` (trạng thái)

Orbit Agent, khi coaching sinh viên, sẽ đọc các directive active thông qua `_get_active_directives()` và đưa vào system prompt LLM để đốc thúc sinh viên theo chỉ tiêu. Đây là cơ chế **asynchronous agent communication** qua shared database — Nova ghi, Orbit đọc.

---

## 3.3 Thiết kế các Agent chuyên biệt (Sub-Agents)

### 3.3.1 AdaptiveAgent — Gia sư thích ứng

**Vai trò:** Cung cấp trải nghiệm gia sư AI cá nhân hóa dựa trên nội dung tài liệu học tập cụ thể. AdaptiveAgent là sub-agent được gọi bởi cả Orbit Agent (cho sinh viên) và trực tiếp qua API `/adaptive/*`.

**Kiến trúc kép:** AdaptiveAgent kết hợp hai chế độ hoạt động:
1. **Roadmap Generation:** Tạo lộ trình học tập (learning roadmap) cho một môn học dựa trên tài liệu đã upload. Roadmap gồm các session có tiêu đề, mô tả, level difficulty và tài liệu tham khảo.
2. **RAG Tutoring:** Chat gia sư sử dụng Retrieval-Augmented Generation. Khi sinh viên hỏi về nội dung tài liệu, AdaptiveAgent: (a) truy xuất các đoạn văn liên quan từ ChromaDB, (b) xây dựng context augmented prompt, (c) gửi đến LLM để tạo câu trả lời có căn cứ từ tài liệu.

**Tích hợp ChromaDB:** AdaptiveAgent khởi tạo vector store qua `get_vector_store()` — một singleton pattern với thread-safe locking. Mỗi tài liệu upload được chunking, embedding và lưu vào ChromaDB với metadata gồm `subject_id` và `source_file`. Khi query, AdaptiveAgent sử dụng similarity search để lấy top-K chunks phù hợp nhất.

**Fallback mechanism:** Nếu ChromaDB hoặc embedding model không khả dụng, AdaptiveAgent chuyển sang chế độ fallback — trả lời dựa trên material brief cache thay vì RAG. Cache này chứa tóm tắt tài liệu được xây dựng từ lần xử lý đầu tiên.

### 3.3.2 EvaluationAgent — Đánh giá năng lực

**Vai trò:** Phân tích và giải thích tiến độ học tập của sinh viên, cung cấp insight về môn yếu, tài liệu cần ôn tập và xu hướng phát triển.

**Metrics đa chiều:** EvaluationAgent tính toán các chỉ số:
- **Test Score:** Điểm trung bình từ `StudentDocumentScoreHistory`, chỉ tính các bài không phải baseline
- **Effort Score:** Cường độ học tập dựa trên thời gian học (`StudySession`) và số bài kiểm tra
- **Progress Trend:** Xu hướng điểm qua 5 bài gần nhất (đang cải thiện/ổn định/đang giảm)

**Context-aware evaluation:** EvaluationAgent tích hợp RAG qua ChromaDB để giải thích đánh giá có căn cứ từ tài liệu cụ thể, không chỉ đưa ra số liệu chung chung.

### 3.3.3 AssessmentAgent — Tạo câu hỏi tự động

**Vai trò:** Sinh câu hỏi trắc nghiệm (MCQ) và tự luận từ ngân hàng câu hỏi (`QuestionBank`) dựa trên tài liệu học.

**Cơ chế hoạt động:** AssessmentAgent lấy câu hỏi từ database đã được xây dựng sẵn từ quá trình xử lý tài liệu (ContentAgent). Mỗi câu hỏi có content, options (JSON), correct_answer, explanation, difficulty và source_file. AssessmentAgent hỗ trợ lọc theo môn, file nguồn và số lượng.

### 3.3.4 PlanningAgent — Lập kế hoạch học tập

**Vai trò:** Tạo và điều chỉnh kế hoạch học tập cá nhân hóa cho sinh viên.

**Chế độ hoạt động:**
- **Regenerate:** Tạo kế hoạch hoàn toàn mới dựa trên tài liệu đã đăng ký và năng lực hiện tại
- **Adjust:** Điều chỉnh kế hoạch hiện tại theo yêu cầu (VD: "ưu tiên môn X", "tuần này quá tải", "rút gọn kế hoạch thi")

Kết quả là danh sách `StudentLearningPlanStep` có thứ tự, deadline, priority và tài liệu liên quan.

### 3.3.5 ProfilingAgent — Phân loại trình độ

**Vai trò:** Phân loại learner profile thành 3 mức: Beginner, Intermediate, Advanced dựa trên kết quả assessment.

**Ngưỡng phân loại:** Dựa trên tỷ lệ correct/total:
- `< 40%` → Beginner
- `40% – 70%` → Intermediate
- `> 70%` → Advanced

Kết quả profiling được lưu vào `LearnerProfile` và sử dụng bởi AdaptiveAgent để điều chỉnh độ khó của nội dung và câu hỏi.

### 3.3.6 ContentAgent — Xử lý tài liệu

**Vai trò:** Xử lý tài liệu đa định dạng (PDF, DOCX, TXT, PPTX) — đọc nội dung, phân tích, dự đoán môn học và chuẩn bị cho quá trình chunking.

### 3.3.7 ReviewAgent — Ôn tập kiến thức

**Vai trò:** Hỗ trợ ôn tập dựa trên spaced repetition, nhắc lại các khái niệm sinh viên đã sai trong assessment trước đó.

---

## 3.4 Cơ chế giao tiếp và phối hợp giữa các Agent

### 3.4.1 Phối hợp qua Agent Hub (Hub-Based Coordination)

Hệ thống sử dụng mô hình **Star Topology** (mô hình sao) thay vì **Full Mesh** (mô hình lưới đầy đủ). Trong mô hình sao:

- **Orbit Agent** là hub center cho toàn bộ giao tiếp liên quan đến sinh viên
- **Nova Agent** là hub center cho toàn bộ giao tiếp liên quan đến giảng viên
- Các sub-agent (Adaptive, Evaluation, Assessment, Planning, Profiling, Content, Review) **không giao tiếp trực tiếp với nhau** mà chỉ giao tiếp qua hub agent

Ưu điểm của mô hình này:
1. **Đơn giản hóa giao tiếp:** Thay vì n(n-1)/2 kết nối, chỉ cần 2n kết nối (mỗi sub-agent kết nối với 1 hub)
2. **Dễ thêm agent mới:** Chỉ cần đăng ký với hub agent, không cần cập nhật tất cả agent khác
3. **Kiểm soát tập trung:** Hub agent có thể log, monitor và quyết định routing dựa trên context toàn cục
4. **Tránh xung đột:** Hub agent đảm bảo không có hai sub-agent xử lý cùng một yêu cầu

### 3.4.2 Shared Database làm kênh giao tiếp bất đồng bộ

Ngoài việc gọi trực tiếp (synchronous call), các agent giao tiếp bất đồng bộ (asynchronous communication) qua cơ sở dữ liệu dùng chung:

**Ví dụ 1 — Nova → Orbit (OrbitCoachDirective):** Giảng viên giao chỉ tiêu qua Nova → ghi vào bảng `OrbitCoachDirective` → Orbit đọc directive khi coaching sinh viên. Đây là giao tiếp **bất đồng bộ, không đồng thời** — Nova và Orbit chạy ở các thời điểm khác nhau.

**Ví dụ 2 — AssessmentAgent → EvaluationAgent:** AssessmentAgent ghi kết quả bài kiểm tra vào `StudentDocumentScoreHistory` và `AssessmentHistory` → EvaluationAgent đọc các bảng này để tính toán điểm và xu hướng. EvaluationAgent không cần biết AssessmentAgent đã tạo dữ liệu khi nào — nó chỉ cần query dữ liệu hiện có.

**Ví dụ 3 — AdaptiveAgent → ProfilingAgent:** AdaptiveAgent ghi learning progress vào `StudentLearningProgress` và `StudySession` → ProfilingAgent sử dụng dữ liệu này để phân loại trình độ → AdaptiveAgent đọc kết quả profiling để điều chỉnh nội dung.

Mô hình giao tiếp này tương tự như **Blackboard Architecture** trong Multi-Agent System — cơ sở dữ liệu đóng vai trò là "bảng đen" (blackboard) nơi các agent đọc/ghi thông tin mà không cần biết agent nào sẽ sử dụng dữ liệu.

### 3.4.3 LLM Client dùng chung với Fallback tự động

Tất cả agent sử dụng LLM Client (Groq SDK) với mô hình `llama-3.3-70b-versatile`. Khi Groq chạm rate limit (HTTP 429) hoặc lỗi server (HTTP 500), `LLMClient` tự động chuyển sang Google Gemini Flash model. Cơ chế fallback này đảm bảo hệ thống luôn có khả năng phản hồi kể cả khi provider chính gặp sự cố.

### 3.4.4 Conversation Memory — Quản lý ngữ cảnh hội thoại

`ConversationMemory` cung cấp cơ chế quản lý ngữ cảnh hội thoại cho cả Orbit và Nova:

- **Backend linh hoạt:** Redis (production, distributed) hoặc in-memory (development)
- **TTL (Time-to-Live):** 8 giờ mặc định, configurable qua environment variable
- **Thread-safe:** Sử dụng `threading.RLock()` để đảm bảo an toàn trong môi trường multi-threaded
- **Session management:** Mỗi cặp (teacher_id, class_id) hoặc (user_id) có session riêng với context độc lập
- **Pending request tracking:** Khi Nova cần thêm thông tin, nó lưu pending request vào memory. Tin nhắn tiếp theo của người dùng được merge với pending data để tạo yêu cầu hoàn chỉnh.

---

## 3.5 Pipeline RAG tích hợp

### 3.5.1 Document Ingestion Pipeline

Quá trình nạp tài liệu vào hệ thống diễn ra theo pipeline:

1. **Upload:** Giảng viên upload tài liệu (PDF, DOCX, PPTX, TXT) qua API `/upload`
2. **Processing:** ContentAgent đọc nội dung sử dụng LangChain loaders: `PyPDFLoader` cho PDF, `Docx2txtLoader` cho DOCX, `Presentation` cho PPTX, `TextLoader` cho TXT
3. **Chunking:** Tài liệu được chia thành các đoạn (chunks) nhỏ hơn với metadata (subject_id, source_file)
4. **Embedding:** Mỗi chunk được chuyển thành vector embedding
5. **Storage:** Vector và metadata được lưu vào ChromaDB tại thư mục `backend/chroma_db/`

### 3.5.2 Query Pipeline

Khi agent cần tìm kiếm thông tin từ tài liệu:

1. **Query → Embedding:** Câu hỏi của người dùng được chuyển thành vector embedding
2. **Similarity Search:** ChromaDB thực hiện similarity search để tìm top-K chunks phù hợp nhất
3. **Context Augmentation:** Các chunks được nối thành context string
4. **LLM Generation:** Context string + câu hỏi gốc được gửi đến LLM với instruction trả lời dựa trên context

### 3.5.3 Graceful Degradation

Nếu ChromaDB hoặc embedding model không khả dụng:
- AdaptiveAgent chuyển sang chế độ fallback: sử dụng `MATERIAL_BRIEF_CACHE` (cache tóm tắt tài liệu)
- EvaluationAgent bỏ qua RAG context, chỉ sử dụng dữ liệu số liệu từ database
- Các agent vẫn hoạt động, chỉ giảm chất lượng câu trả lời

---

## 3.6 Thiết kế giao diện người dùng (Frontend)

### 3.6.1 Kiến trúc Next.js App Router

Frontend sử dụng Next.js 16 với App Router, mỗi route là một thư mục chứa `page.tsx`. Các trang chính:

| Route | Chức năng | Người dùng |
|-------|----------|-----------|
| `/` | Dashboard chính | Sinh viên |
| `/adaptive` | Học tập thích ứng | Sinh viên |
| `/evaluation` | Kết quả đánh giá | Sinh viên |
| `/planning` | Kế hoạch học tập | Sinh viên |
| `/teacher` | Dashboard giảng viên | Giảng viên |
| `/admin/*` | Quản trị hệ thống | Admin |

### 3.6.2 StudentOrbitAgent Widget

`StudentOrbitAgent.tsx` là widget chat floating hiển thị ở góc dưới màn hình. Điểm đặc biệt:
- **Context-aware suggestions:** Widget hiển thị câu gợi ý khác nhau tùy route — VD: ở trang `/adaptive` thì gợi ý "Tóm tắt tài liệu này", ở trang `/evaluation` thì gợi ý "Thành tích học của tôi"
- **Action metadata handling:** Khi Orbit trả về `action_metadata`, widget hiển thị nút xác nhận (VD: "OK, mở tài liệu đề xuất") hoặc tự động thực hiện hành động
- **Subtitle động:** Header widget thay đổi theo context — "Tutor Agent · Học tập cá nhân hóa" ở `/adaptive`, "Evaluation Agent · Đánh giá năng lực" ở `/evaluation`

### 3.6.3 NovaTeacherAgent Widget

`NovaTeacherAgent.tsx` là widget chat dành cho giảng viên với khả năng chat-driven UI:
- **Auto-execute actions:** Khi Nova trả về `should_auto_execute: true`, widget tự động mở tab/biểu đồ tương ứng bằng `router.push()` hoặc state change
- **Suggested questions:** Hiển thị 4 câu hỏi mẫu để giảng viên nhanh chóng bắt đầu
- **Bootstrap tự động:** Widget tự động lấy `teacher_id` và `class_id` từ localStorage và URL params

### 3.6.4 Nova Chat-Driven UI — Tương tác giao diện qua chat

Đây là tính năng đặc biệt của Nova Agent, minh họa sự khác biệt giữa "chatbot đơn thuần" và "agent-driven UI":

**Ví dụ tương tác hoàn chỉnh:**

1. Giảng viên: *"Kết quả lớp IT1 thế nào?"*
2. Nova phân tích: intent = `class_overview`, class = "IT1"
3. Nova tính toán: 35 sinh viên, điểm TB 67.3, tỷ lệ đỗ 74.3%, phân bố (8 giỏi, 12 khá, 10 TB, 5 yếu)
4. Nova trả về:
   - `reply`: "📊 Tình hình học tập lớp IT1 • Số sinh viên: 35 • Điểm trung bình: 67.3 • Tỷ lệ đỗ: 74.3%..."
   - `action_metadata`: `{action_type: "open_tab", tab_name: "class_analytics", should_auto_execute: true}`
5. Frontend nhận `action_metadata` → tự động mở tab phân tích lớp với biểu đồ phân bố điểm

Kết quả: Giảng viên vừa đọc phân tích text trong chat, vừa thấy biểu đồ chi tiết mở ra bên cạnh — **một câu hỏi, hai kênh thông tin**.

---

## 3.7 Thiết kế cơ sở dữ liệu

### 3.7.1 Mô hình ER (Entity-Relationship)

Hệ thống sử dụng SQLAlchemy ORM với các bảng chính được tổ chức thành 6 nhóm:

**Nhóm Core:**
- `users`: Thông tin người dùng (student/teacher/admin) với password hashing
- `subjects`: Môn học
- `classrooms`: Lớp học, quan hệ N-N với users qua bảng `enrollments`
- `documents`: Tài liệu học, quan hệ với subject và classroom

**Nhóm Learning:**
- `learning_roadmaps`: Lộ trình học do AdaptiveAgent tạo
- `study_sessions`: Phiên học tập (tracking thời gian)
- `student_learning_plans` / `student_learning_plan_steps`: Kế hoạch học tập

**Nhóm Assessment:**
- `assessment_histories`: Lịch sử làm bài
- `question_banks`: Ngân hàng câu hỏi
- `assessment_results`: Kết quả chi tiết từng câu

**Nhóm Evaluation:**
- `student_document_evaluations`: Đánh giá năng lực theo tài liệu
- `student_document_score_histories`: Lịch sử điểm theo tài liệu
- `student_learning_progress`: Tiến độ tổng hợp (updated bởi Orbit)
- `wrong_answer_records`: Câu sai (cho Orbit weak topics)

**Nhóm Chat/Orbit:**
- `orbit_chat_sessions` / `orbit_chat_messages`: Phiên và tin nhắn Orbit
- `orbit_coach_directives`: Chỉ tiêu tuần từ giảng viên (Nova → Orbit)
- `notifications`: Thông báo hệ thống

**Nhóm System:**
- `user_login_sessions`: Phiên đăng nhập (tracking)
- `document_publications`: Trạng thái công khai tài liệu
- `chunks`: Document chunks cho RAG
- `research_evaluation_cases` / `research_experiment_runs`: Dữ liệu thực nghiệm

### 3.7.2 Migration và Compatibility

Hệ thống sử dụng `models.Base.metadata.create_all(bind=engine)` để tự động tạo bảng mới. Hàm `ensure_orbit_login_tracking_column()` trong `main.py` thực hiện ALTER TABLE ADD COLUMN cho các cột mới — đảm bảo backward compatibility với dữ liệu cũ mà không cần migration tool riêng biệt.

---

## 3.8 Đảm bảo chất lượng và tính ổn định

### 3.8.1 LLM Fallback Chain

`LLMClient` triển khai fallback chain Groq → Gemini:
- Primary: Groq API với `llama-3.3-70b-versatile`
- Fallback: Google Gemini Flash (tự động kích hoạt khi Groq rate limit 429 hoặc server error 500)
- Mỗi agent có resolve API key riêng từ nhiều biến môi trường (VD: `GROQ_KEY_ADAPTIVE`, `GROQ_KEY_EVALUATION`, `GROQ_KEY_ORBIT`...)

### 3.8.2 Intent Cache

Nova Agent sử dụng `intent_cache` (LRU, max 500 entries) để cache kết quả phân loại intent. Khi cùng một message được gửi lại, Nova trả về kết quả cache ngay lập tức thay vì gọi LLM lần nữa — giảm latency từ ~800ms xuống ~1ms.

### 3.8.3 Performance Monitoring

Nova Agent có hệ thống performance monitoring chi tiết (`_perf_log`) đo:
- Cache lookup time
- LLM call time
- DB query time và count (qua SQLAlchemy event hooks)
- Total request time
- Breakdown theo phase: before_analyze, analyze, preprocess, business, postprocess

### 3.8.4 Connection Pooling

Database sử dụng connection pooling với:
- `pool_size = 20`
- `max_overflow = 40`
- `pool_timeout = 30s`
- `pool_recycle = 1800s`
- `pool_pre_ping = true` (tự động phát hiện và loại broken connections)
