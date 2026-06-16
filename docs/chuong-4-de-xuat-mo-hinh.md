# CHƯƠNG 4 – ĐỀ XUẤT MÔ HÌNH VÀ KIẾN TRÚC HỆ THỐNG

## 4.1 Mô hình kiến trúc Agent Hub đề xuất

### 4.1.1 Động lực thiết kế (Design Rationale)

Các hệ thống Multi-Agent truyền thống trong giáo dục thường áp dụng một trong hai mô hình kiến trúc sau:

**Mô hình Monolithic:** Một agent duy nhất xử lý mọi tác vụ. Mô hình này đơn giản nhưng không thể mở rộng — khi số lượng chức năng tăng, agent trở nên phức tạp, khó bảo trì và khó kiểm thử độc lập.

**Mô hình Full-Mesh:** Mỗi agent giao tiếp trực tiếp với mọi agent khác. Mô hình này linh hoạt nhưng tạo ra độ phức tạp giao tiếp O(n²) — với n agent, cần n(n-1)/2 kênh giao tiếp. Khi thêm agent mới, phải cập nhật giao thức giao tiếp với tất cả agent hiện có.

**Mô hình Agent Hub đề xuất** giải quyết hạn chế của cả hai mô hình trên:

Trong mô hình Agent Hub, hai hub agent (Orbit và Nova) đóng vai trò **facilitator** — tiếp nhận yêu cầu, phân tích, định tuyến — trong khi các sub-agent đóng vai trò **specialist** — xử lý nghiệp vụ chuyên sâu. Sự tách biệt này cho phép:

1. **Single Entry Point:** Người dùng chỉ cần biết một điểm tiếp xúc duy nhất (Orbit hoặc Nova), không cần biết hệ thống có bao nhiêu sub-agent bên trong.
2. **Transparent Routing:** Hub agent quyết định sub-agent nào xử lý yêu cầu — người dùng không cần chỉ định.
3. **Easy Extensibility:** Thêm agent mới chỉ cần đăng ký với hub agent, không ảnh hưởng agent khác.
4. **Centralized Context:** Hub agent duy trì ngữ cảnh toàn cục, cho phép hội thoại multi-turn liền mạch dù các sub-agent khác nhau xử lý các turn khác nhau.

### 4.1.2 Formal Definition của Agent Hub Model

Định nghĩa hình thức mô hình Agent Hub:

**Định nghĩa 4.1 (Agent Hub).** Cho tập hợp agent chuyên biệt A = {a₁, a₂, ..., aₙ} và tập hợp vai trò người dùng R = {student, teacher}. Một Agent Hub Hᵣ cho vai trò r ∈ R là một cặp Hᵣ = (Iᵣ, Dᵣ) trong đó:
- Iᵣ: M × C → J là hàm phân loại ý định, ánh xạ từ cặp (tin nhắn m, ngữ cảnh c) sang intent type j ∈ J
- Dᵣ: J × E × C → A là hàm định tuyến, ánh xạ từ cặp (intent j, entities e, ngữ cảnh c) sang agent a ∈ A ∪ {Hᵣ}

**Tính chất 4.1 (Star Topology).** Giao tiếp giữa các agent tạo thành đồ thị G = (V, E) với V = {Hₛ, Hₜ, a₁, ..., aₙ} và E = {(Hₛ, aᵢ) : i = 1..n} ∪ {(Hₜ, aᵢ) : i = 1..n}. Đồ thị G là star graph với hai center.

**Tính chất 4.2 (Separation of Concerns).** Mỗi aᵢ ∈ A có miền nhiệm vụ Dᵢ ⊂ D (D là tập mọi nhiệm vụ) sao cho Dᵢ ∩ Dⱼ = ∅ với mọi i ≠ j. Hub agent Hᵣ có nhiệm vụ phân tích và định tuyến, không xử lý nghiệp vụ chuyên biệt.

### 4.1.3 So sánh với các kiến trúc khác

| Tiêu chí | Monolithic | Full-Mesh | Agent Hub (đề xuất) |
|----------|-----------|-----------|---------------------|
| Độ phức tạp giao tiếp | O(1) | O(n²) | O(n) |
| Khả năng mở rộng | Kém | Trung bình | Tốt |
| Điểm lỗi đơn (SPOF) | Agent chính | Không có | Hub agent |
| Độ khó kiểm thử | Trung bình | Cao | Thấp (mỗi agent test độc lập) |
| Trải nghiệm người dùng | Đơn nhất | Phức tạp | Đơn nhất (1 entry point) |
| Overhead điều phối | Không | Cao | Thấp |
| Context Management | Tích hợp | Phân tán | Tập trung tại Hub |

---

## 4.2 Mô hình cá nhân hóa đề xuất

### 4.2.1 Learner Profile Model đa chiều

Hệ thống đề xuất mô hình hồ sơ học sinh (Learner Profile) ba chiều:

**Dimension 1 — Knowledge State (Trạng thái kiến thức):**
- Được đại diện bởi tập hợp các `StudentDocumentEvaluation` — mỗi evaluation gắn với một tài liệu cụ thể trong một môn học
- Mỗi evaluation bao gồm: `latest_score` (điểm gần nhất), `attempts` (số lần thử), `is_completed` (đã đạt yêu cầu hay chưa)
- ProfilingAgent tổng hợp knowledge state thành mức: Beginner / Intermediate / Advanced

**Dimension 2 — Behavior Pattern (Mô hình hành vi):**
- Được đại diện bởi các chỉ số hành vi: `StudySession` (thời gian học), `UserLoginSession` (tần suất đăng nhập), `OrbitChatMessage` (tương tác với agent)
- Orbit Agent phân tích behavior pattern qua các hàm `_build_stats()`, `_entry_orbit_mode()`, `_last_activity_at()`
- Ba trạng thái hành vi được phân loại:
  - **Active:** Đăng nhập đều đặn, học >180 phút/tuần, ≥2 bài kiểm tra/tuần
  - **At Risk:** 3-7 ngày không hoạt động, <60 phút/tuần
  - **Inactive:** >7 ngày không hoạt động

**Dimension 3 — Learning Preference (Sở thích học tập):**
- Được suy diễn từ hành vi: môn nào sinh viên hỏi nhiều nhất (`OrbitChatMessage`), tài liệu nào được mở nhiều nhất, thời điểm học tập phổ biến
- Orbit Agent sử dụng preference này để cá nhân hóa đề xuất tài liệu

### 4.2.2 Cơ chế phân loại năng lực tự động

Hệ thống đề xuất quy trình phân loại năng lực tự động 4 bước:

**Bước 1 — Baseline Assessment:** Khi sinh viên mới tham gia lớp, AssessmentAgent tạo bài kiểm tra baseline từ tài liệu môn học. Kết quả được lưu vào `StudentDocumentScoreHistory` với `test_type = "baseline"`.

**Bước 2 — Score Computation:** EvaluationAgent tính toán `test_score` qua hàm `compute_subject_score_metrics()`:
- Lấy tất cả score history không phải baseline
- Tính điểm trung bình có trọng số (bài gần nhất có trọng số cao hơn)
- Xét improvement delta so với baseline

**Bước 3 — Profiling:** ProfilingAgent sử dụng tỷ lệ `correct_count / total_questions` kết hợp với `test_score` để phân loại:
- `score < 40%` → Beginner
- `40% ≤ score < 70%` → Intermediate
- `score ≥ 70%` → Advanced

**Bước 4 — Adaptive Adjustment:** AdaptiveAgent đọc kết quả profiling từ `LearnerProfile` và điều chỉnh:
- **Beginner:** Câu hỏi cơ bản, giải thích chi tiết, nhiều ví dụ
- **Intermediate:** Câu hỏi ứng dụng, tóm tắt ngắn, ít ví dụ hơn
- **Advanced:** Câu hỏi phân tích/synthèse, ít hướng dẫn, đề xuất tài liệu nâng cao

### 4.2.3 Adaptive Learning Path Generation

Orbit Agent đề xuất lộ trình học tập cá nhân hóa qua hàm `_build_recommendation_payload()`:

**Thuật toán ưu tiên môn học (Subject Priority Algorithm):**

```
Function _pick_focus_subject(user_id):
    subject_map ← _collect_subject_learning_map(user_id)
    // Mỗi entry: {subject_name, study_minutes, tests, lessons, latest_score}

    ranked ← sort subject_map by:
        1. Có tài liệu khả dụng? (Có → ưu tiên trước)
        2. latest_score thấp nhất
        3. lessons ít nhất
        4. tests ít nhất
        5. study_minutes ít nhất

    return ranked[0].subject_name
```

**Thuật toán đề xuất tài liệu (Document Recommendation Algorithm):**

```
Function _pick_document_by_evaluation(user, subject_name):
    docs ← available_documents_for_classroom(user, subject)

    // Ưu tiên 1: Tài liệu chưa làm bài kiểm tra
    missing ← docs WHERE evaluation.attempts == 0
    IF missing ≠ ∅:
        return missing[0], "Bạn chưa làm bài kiểm tra cho tài liệu này."

    // Ưu tiên 2: Tài liệu có điểm thấp nhất (<60)
    low ← sort docs WHERE evaluation.score < 60 BY score ASC
    IF low ≠ ∅:
        return low[0], "Điểm kiểm tra gần nhất còn thấp"

    // Ưu tiên 3: Tài liệu có điểm thấp nhất (tổng quát)
    all ← sort docs BY evaluation.score ASC
    return all[0], "Tài liệu này có điểm thấp nhất"
```

---

## 4.3 Mô hình Intent Classification hai lớp

### 4.3.1 Layer 1: LLM-based Classification

Nova Agent sử dụng LLM (Llama 3.3 70B) để phân loại intent trong vòng 2 giây. LLM nhận input gồm:
- System prompt: "Phân loại intent cho Teacher Agent và trích xuất entities. Chỉ trả JSON."
- User prompt: danh sách intent hợp lệ, entities có thể trích xuất, context (last_intent, last_subject, last_class, last_student), và message gốc

LLM trả về JSON:
```json
{
  "intent_type": "class_overview",
  "entities": {
    "class_name": "IT1",
    "subject_name": "Lập trình hướng đối tượng"
  },
  "confidence": 0.95
}
```

**Ưu điểm:** Hiểu ngữ nghĩa tốt, xử lý được câu hỏi phức tạp và không chính xác (fuzzy matching).
**Nhược điểm:** Latency ~800-2000ms, cost per call.

### 4.3.2 Layer 2: Rule-based Fallback

`IntentClassifier` sử dụng keyword matching với:
- 7 nhóm từ khóa cho 7 intent types, mỗi nhóm 5-12 từ khóa
- Strong phrase overrides cho các pattern phổ biến (VD: "kết quả lớp X" → class_overview với confidence 0.95)
- Entity extraction bằng regex patterns cho tiếng Việt

**Ưu điểm:** Latency <1ms, zero cost, deterministic.
**Nhược điểm:** Không hiểu ngữ nghĩa, phải maintain keyword list.

### 4.3.3 Hybrid Strategy

Nova Agent kết hợp hai lớp:
1. Khởi động LLM call song song trong `ThreadPoolExecutor`
2. Đặt timeout 2 giây
3. Nếu LLM trả về trong thời gian → sử dụng kết quả LLM
4. Nếu timeout → sử dụng rule-based fallback
5. Cache kết quả phân loại (LRU, 500 entries) để lần sau trả về ngay

Kết quả: trung bình 85% request sử dụng LLM path, 15% fallback rule-based, 100% request cache hit ở lần thứ hai.

---

## 4.4 Mô hình Chat-Driven UI Interaction

### 4.4.1 Action Metadata Protocol

Hệ thống đề xuất một protocol giao tiếp giữa agent và frontend qua `action_metadata`:

```typescript
interface ActionMetadata {
  action_type: "open_tab" | "open_route" | "open_document" | "show_chat";
  target: "teacher" | "student";
  tab_name: string;           // Tên tab/component cần mở
  params: Record<string, any>; // Tham số truyền cho component
  message?: string;            // Thông báo hiển thị
  should_auto_execute: boolean; // Tự động thực hiện hay cần xác nhận
  confirm_button_text?: string; // Text nút xác nhận (nếu không auto)
}
```

**Semantic của các action_type:**

- `open_tab`: Mở một tab trong giao diện teacher dashboard (VD: subjects, members, exam)
- `open_route`: Chuyển sang route khác (VD: /evaluation)
- `open_document`: Mở tài liệu trong adaptive learning view
- `show_chat`: Hiển thị kết quả trong chat panel (không mở thêm UI)

### 4.4.2 Nova Interactive Flow

Luồng tương tác hoàn chỉnh giữa Nova Agent và frontend:

```
Giảng viên: "Kết quả lớp IT1"
    │
    ▼
[NovaTeacherAgent.tsx] POST /nova-interactive
    │
    ▼
[TeacherAgent.respond()]
    │
    ├─► ConversationMemory.get_context() → context (last_subject, last_class, ...)
    ├─► analyze(message, context) → intent=class_overview, entities={class_name:"IT1"}
    ├─► _find_classroom_in_message() → Classroom(id=1, name="IT1", subject_id=5)
    ├─► _class_overview_reply(classroom, subject) → reply text + suggested_actions
    └─► ActionRouter.route_action(class_overview) → action_metadata
    │
    ▼
Response JSON:
{
  "reply": "📊 Tình hình học tập lớp IT1\n• Số sinh viên: 35\n• Điểm TB: 67.3\n...",
  "suggested_actions": ["Xem biểu đồ phân bố điểm", "Lọc sinh viên dưới 60"],
  "intent_type": "class_overview",
  "confidence": 0.95,
  "action_metadata": {
    "action_type": "open_tab",
    "tab_name": "class_analytics",
    "should_auto_execute": true
  }
}
    │
    ▼
[NovaTeacherAgent.tsx] receives response
    │
    ├─► Display reply text in chat panel
    └─► Process action_metadata:
         IF should_auto_execute → router.push("/teacher?tab=class_analytics&id=1")
         ELSE → show confirm button
```

### 4.4.3 Multi-turn Context Management

Nova Agent quản lý ngữ cảnh hội thoại multi-turn qua `ConversationMemory`:

**Ví dụ hội thoại multi-turn:**

| Turn | Giảng viên | Nova phân tích | Context update |
|------|-----------|---------------|----------------|
| 1 | "Môn Lập trình hướng đối tượng có những lớp nào?" | intent=course_info, subject="LPTHDT" | last_subject="LPTHDT" |
| 2 | "Tình hình lớp IT1?" | intent=class_overview, class="IT1" (subject kế thừa từ turn 1) | last_class="IT1" |
| 3 | "Sinh viên Nguyễn Văn A học thế nào?" | intent=student_info, student="Nguyễn Văn A" (class kế thừa từ turn 2) | last_student="Nguyễn Văn A" |
| 4 | "Nó cần cải thiện gì?" | intent=student_info (follow-up), needs_follow_up=true → kế thừa last_intent, last_student | (giữ nguyên) |

Trong turn 4, giảng viên sử dụng đại từ "nó" — IntentClassifier phát hiện `needs_follow_up` và kế thừa intent + entities từ context trước đó.

**Pending Request Mechanism:** Khi thông tin chưa đủ, Nova lưu pending request và merge với tin nhắn tiếp theo:

```
Turn 1: "Xuất đề trắc nghiệm"
→ missing_fields: [subject_name, num_questions, num_versions]
→ Nova: "Bạn đang thiếu thông tin: subject_name, num_questions, num_versions.
         Ví dụ: 'Xuất đề trắc nghiệm môn Toán với 30 câu và 2 mã đề'"
→ Lưu pending_request = {intent_type: "exam_generation", entities: {exam_type: "multiple_choice"}}

Turn 2: "Môn Lập trình hướng đối tượng 20 câu 2 mã đề"
→ intent = general_question (confidence thấp) → merge với pending_request
→ entities merged: {exam_type: "multiple_choice", subject_name: "LPTHDT",
                    num_questions: 20, num_versions: 2}
→ Gọi AssessmentAgent tạo đề
```

---

## 4.5 Mô hình Coaching tự động

### 4.5.1 Orbit Coaching Engine

Orbit Agent triển khai mô hình coaching tự động dựa trên LLM với system prompt được cá nhân hóa động cho từng sinh viên:

**Cấu trúc System Prompt của Orbit Agent:**

```
Bạn là Orbit — AI học tập cá nhân (coach) cho sinh viên {student_name}.

### THÔNG TIN HỌC SINH:
- Tên: {student_name}
- Môn đang theo dõi: {subject_name}
- Tổng đã học: {total_study} phút, {total_lessons} bài đạt, {total_tests} bài kiểm tra
- Tuần này: {week_study} phút, {week_tests} bài kiểm tra, {week_lessons} bài đạt
- Tháng này: {month_study} phút, {month_tests} bài kiểm tra
- Số ngày không hoạt động: {days_inactive}
- Các phần đang yếu: {weak_topics}
- {discipline_signal}

### CHỈ TIÊU TUẦN TỪ GIẢNG VIÊN:
- Chỉ tiêu: {target_tests} bài kiểm tra và {target_chapters} chương
- Ghi chú: {note}

### NHIỆM VỤ:
- Gọi tên học sinh ít nhất 1 lần
- Phân tích dữ liệu, đưa ra nhận xét CỤ THỂ
- Nếu yếu → đề xuất ôn lại phần đó
- Nếu tốt → khen ngợi và đề xuất thử thách nâng cao
- Nếu nghỉ lâu → nghiêm khắc nhưng động viên
```

**Discipline Signal — Tín hiệu kỷ luật:**

Orbit Agent tự động phát hiện 4 trạng thái kỷ luật và điều chỉnh giọng điệu coaching:

| Điều kiện | Signal | Giọng điệu |
|-----------|--------|-----------|
| ≥7 ngày không hoạt động | NGHỈ QUÁ LÂU | Cực kỳ nghiêm khắc |
| Tuần chưa có hoạt động | TUẦN NÀY CHƯA CÓ HOẠT ĐỘNG | Nhắc nhở nghiêm túc |
| Tuần học <60 phút | CƯỜNG ĐỘ HỌC THẤP | Khuyên tăng thời lượng |
| Tuần học ≥180 phút + ≥2 tests | TÍN HIỆU TỐT | Khen ngợi, giữ nhịp |

### 4.5.2 Orbit Directive — Giao tiếp Nova→Orbit

Cơ chế Orbit Directive thể hiện **asynchronous inter-agent communication** giữa hai Hub Agent:

**Flow:**
1. Giảng viên nói với Nova: "Giao bạn An tuần này làm thêm 2 bài kiểm tra"
2. Nova phát hiện `_is_orbit_directive_request()` → tạo `OrbitCoachDirective` record
3. Nova gửi Notification cho cả sinh viên và giảng viên
4. Khi Orbit Agent coaching sinh viên, nó gọi `_get_active_directives()` → đọc directive → đưa vào system prompt
5. Orbit Agent đốc thúc sinh viên theo chỉ tiêu với ngữ cảnh đầy đủ

Đây là ví dụ điển hình của **Blackboard Pattern**: Nova ghi "chỉ tiêu" vào blackboard (database), Orbit đọc từ blackboard và hành động — hai agent không cần giao tiếp đồng bộ.

---

## 4.6 Mô hình RAG cải tiến cho giáo dục

### 4.6.1 Subject-aware Document Retrieval

Hệ thống đề xuất cơ chế truy xuất tài liệu có nhận thức môn học (subject-aware retrieval):

- Mỗi document chunk trong ChromaDB có metadata: `subject_id`, `source_file`
- Khi AdaptiveAgent query, nó truyền `allowed_filenames` để giới hạn retrieval trong phạm vi tài liệu của môn/lớp cụ thể
- Điều này tránh tình trạng trả về nội dung từ tài liệu không liên quan — vấn đề phổ biến trong RAG khi corpus lớn

### 4.6.2 Context Window Optimization

AdaptiveAgent sử dụng `roadmap_context` — một chuỗi tóm tắt tài liệu hiện tại — để hướng dẫn LLM tập trung vào đúng tài liệu:

```
roadmap_context = "Tài liệu đang mở: OOP_Chapter1.pdf. 
                   Hỗ trợ người học bám sát tài liệu này, không lái sang tài liệu khác.
                   Tóm tắt nhanh: [900 chars summary]
                   Ý chính:
                   - Điểm A
                   - Điểm B"
```

Cơ chế này đảm bảo câu trả lời được "neo" (anchored) vào tài liệu cụ thể, giảm hallucination.

### 4.6.3 Citation & Grounding

Khi AdaptiveAgent sử dụng RAG, nó không chỉ trả lời mà còn chỉ rõ nguồn:
- `source_file` được truyền trong response để frontend hiển thị nguồn
- System prompt hướng dẫn LLM "chỉ trả lời dựa trên nội dung tài liệu, không suy đoán ngoài nguồn"

---

## 4.7 Kiến trúc triển khai hệ thống

### 4.7.1 Backend Stack

| Thành phần | Công nghệ | Vai trò |
|-----------|----------|---------|
| Web Framework | FastAPI | REST API, CORS, Pydantic validation |
| ASGI Server | Uvicorn (dev) / Gunicorn (prod) | Xử lý concurrent requests |
| ORM | SQLAlchemy 2.0 | Database abstraction |
| Database | SQLite (dev) / PostgreSQL (prod) | Persistent storage |
| Vector DB | ChromaDB + LangChain | RAG pipeline |
| LLM | Groq (Llama 3.3 70B) + Gemini (fallback) | AI reasoning |
| Cache | Redis (optional) | Conversation memory, rate limiting |
| Auth | JWT + bcrypt | Authentication & authorization |

### 4.7.2 Frontend Stack

| Thành phần | Công nghệ | Vai trò |
|-----------|----------|---------|
| Framework | Next.js 16 + React 19 | SSR/CSR hybrid |
| Language | TypeScript | Type safety |
| Styling | Tailwind CSS | Utility-first styling |
| Animation | Framer Motion | UI transitions |
| Charts | Recharts | Data visualization |
| Markdown | react-markdown | Rich text rendering |

### 4.7.3 Security Architecture

- **Authentication:** JWT token-based, token được lưu trong localStorage
- **Password:** bcrypt hashing qua `hash_password()` trong `auth.py`
- **Authorization:** Role-based (student/teacher/admin), mỗi API endpoint kiểm tra role
- **CORS:** Enabled cho localhost development
- **Input Validation:** Pydantic BaseModel cho tất cả request bodies
- **SQL Injection Prevention:** SQLAlchemy ORM parameterized queries
- **API Key Management:** LLM API keys trong `.env`, không hardcode

### 4.7.4 Deployment Architecture

```
                    ┌──────────────┐
                    │   Internet   │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │ Load Balancer │
                    │  (optional)  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │                         │
     ┌────────┴────────┐      ┌────────┴────────┐
     │  Backend #1     │      │  Backend #2     │
     │  FastAPI +       │      │  FastAPI +       │
     │  Gunicorn        │      │  Gunicorn        │
     └────────┬─────────┘      └────────┬─────────┘
              │                          │
     ┌────────┴──────────────────────────┴─────────┐
     │           Shared Data Layer                  │
     │  PostgreSQL · ChromaDB · Redis               │
     └──────────────────────────────────────────────┘
              │
     ┌────────┴─────────┐
     │  Frontend (CDN)  │
     │  Next.js Static  │
     └──────────────────┘
```

---

## 4.8 Đảm bảo chất lượng hệ thống

### 4.8.1 Graceful Degradation Matrix

Hệ thống được thiết kế để suy giảm mềm khi các thành phần gặp sự cố:

| Thành phần lỗi | Ảnh hưởng | Chế độ fallback |
|---------------|-----------|----------------|
| Groq API rate limit | LLM không gọi được | Tự động chuyển sang Gemini |
| Groq + Gemini đều lỗi | Không có LLM | Template-based response (Orbit fallback, Nova rule-based) |
| ChromaDB lỗi | RAG không khả dụng | AdaptiveAgent dùng material brief cache |
| Redis lỗi | ConversationMemory không distributed | Tự động chuyển sang in-memory |
| Database lỗi | Không truy cập dữ liệu | HTTP 503 Service Unavailable |
| Intent Cache miss | Chậm hơn lần đầu | Gọi LLM/rule-based bình thường |

### 4.8.2 Error Handling Strategy

Mỗi agent tuân thủ nguyên tắc **never crash**:
- Tất cả LLM calls được bọc trong try/except
- Exception được log và tự động fallback
- Frontend hiển thị thông báo thân thiện thay vì stack trace
- API trả về structured error JSON với `retryable` flag

### 4.8.3 Logging và Observability

Hệ thống sử dụng structured logging:
- **Request logging:** Mỗi API request được log với request_id, duration, status
- **LLM tracing:** Mỗi LLM call được log qua `emit_llm_request()`, `emit_llm_response()`, `emit_llm_error()`
- **Performance breakdown:** Nova Agent log chi tiết từng phase (cache lookup, LLM call, DB query, business logic)
- **Debug stream:** WebSocket-based debug stream cho development
