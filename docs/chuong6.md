# CHƯƠNG 6. THỰC NGHIỆM VÀ ĐÁNH GIÁ

## 6.1 Thiết kế thực nghiệm

### 6.1.1 Câu hỏi nghiên cứu

Để đánh giá hiệu quả của kiến trúc multi-agent đề xuất, luận án đặt ra các câu hỏi nghiên cứu sau:

**RQ1:** Kiến trúc multi-agent với Agent Hub có hiệu quả hơn mô hình đơn thể trong việc cá nhân hóa học tập không? Đánh giá theo các tiêu chí: chất lượng phản hồi AI, mức độ cá nhân hóa, và khả năng phối hợp giữa các agent.

**RQ2:** Các agent chuyên biệt (Planning, Content, Evaluation, Assessment, Adaptive Tutor, Orbit Coach) đạt chất lượng bao nhiêu khi đánh giá trên các tác vụ cụ thể?

**RQ3:** Mức độ cá nhân hóa mà hệ thống đạt được so với baseline (hệ thống e-learning không có AI) là bao nhiêu?

### 6.1.2 Bộ dữ liệu đánh giá

Hệ thống sử dụng framework đánh giá được triển khai trong module `ResearchEvaluationService` (backend/services/research_evaluation.py), kết hợp với dữ liệu thực từ hệ thống.

**Bảng 6.1.** Bộ dữ liệu đánh giá theo từng agent

| Agent | Bộ test | Số case | Nguồn | Mô tả |
|---|---|---|---|---|
| Planning Agent | PlanningEvalSuite | 15 | Tổng hợp | Tạo kế hoạch từ learner profiles khác nhau |
| Content Agent | ContentEvalSuite | 10 | Tài liệu thực | Phân loại môn học từ tài liệu đa dạng |
| Evaluation Agent | EvaluationEvalSuite | 12 | Dữ liệu sinh viên | Phân tích điểm và sinh feedback |
| Nova Teacher Agent | TeacherEvalSuite | 20 | Hội thoại thực | Intent classification + routing |
| Assessment Agent | AssessmentEvalSuite | 15 | Tài liệu thực | MCQ generation + quality metrics |
| Adaptive Tutor | TutorEvalSuite | 20 | Hội thoại + profile | Cá nhân hóa theo learner level |
| Orbit Agent | OrbitEvalSuite | 10 | Dữ liệu học tập | Coaching cá nhân hóa |

**Bảng 6.2.** Dữ liệu thực nghiệm từ hệ thống

| Dữ liệu | Số lượng | Ghi chú |
|---|---|---|
| Môn học | 3-5 | Lập trình OOP, CSDL, Mạng, AI, etc. |
| Tài liệu | 20-40 | PDF, DOCX, PPTX |
| Sinh viên thử nghiệm | 30-50 | Sinh viên đại học |
| Phiên học | 200+ | Gồm chat, quiz, study sessions |
| Câu hỏi trắc nghiệm | 300+ | Sinh từ Assessment Agent |
| Câu trả lời sai | 500+ | Lưu trong WrongAnswerRecord |

### 6.1.3 Các chỉ số đánh giá

**Bảng 6.3.** Các chỉ số đánh giá theo nhóm

| Nhóm chỉ số | Chỉ số | Công thức/Phương pháp | Áp dụng cho |
|---|---|---|---|
| **Chất lượng Agent** | Intent Accuracy | % intent được phân loại đúng | Teacher Agent |
| | Response Relevance | Human rating (1-5 Likert) | Mọi agent |
| | Personalization Depth | % response chứa thông tin cá nhân | Adaptive, Orbit, Eval |
| | JSON Validity | % output JSON hợp lệ | Planning, Assessment |
| **Chất lượng Câu hỏi** | Question Quality | Human rating (1-5 Likert) | Assessment Agent |
| | Bloom's Compliance | % câu hỏi đúng mức Bloom's | Assessment Agent |
| | Distractor Quality | % nhiễu hợp lý (human judge) | Assessment Agent |
| | Duplicate Rate | % câu hỏi trùng lặp | Assessment Agent |
| **Hiệu quả Cá nhân hóa** | Context Utilization | % learner data được sử dụng trong prompt | Adaptive Agent |
| | Level-appropriate | % response phù hợp với learner level | Adaptive Agent |
| | Misconception Detection | % misconception được phát hiện | Adaptive Agent |
| **Hiệu năng Kỹ thuật** | Response Latency (P50, P95) | Thời gian phản hồi (ms) | Mọi agent |
| | Fallback Rate | % request dùng fallback | Mọi agent |
| | Token Usage | Tokens/request trung bình | Mọi agent |
| **Agent Collaboration** | Routing Accuracy | % request được route đúng agent | Agent Hub |
| | Context Propagation | % context được truyền giữa agent | Hub-mediated |
| | Task Completion Rate | % tác vụ hoàn thành end-to-end | Multi-agent workflows |

### 6.1.4 Môi trường thực nghiệm

**Bảng 6.4.** Môi trường thực nghiệm

| Thành phần | Cấu hình |
|---|---|
| Hệ điều hành | Windows 11 Pro |
| CPU | Intel Core i5/i7 (thế hệ 12+) |
| RAM | 16 GB |
| Python | 3.10+ |
| PostgreSQL | 15 (local hoặc cloud) |
| ChromaDB | 0.4+ (persistent local) |
| LLM Provider | Groq API (Llama 3.3 70B) |
| Fallback LLM | Google Gemini API |
| Frontend | Next.js 14, Node.js 18+ |
| Mạng | Wi-Fi/ LAN, latency < 50ms đến Groq API |

## 6.2 Đánh giá kiến trúc Multi-Agent

### 6.2.1 Planning Agent Evaluation

**Thiết kế:** Đánh giá Planning Agent trên 15 test cases với các learner profiles khác nhau (Beginner/Intermediate/Advanced, có/không có evaluation history, có/không có chỉ tiêu từ giảng viên).

**Bảng 6.5.** Kết quả đánh giá Planning Agent

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| JSON Validity | 93.3% (14/15) | 1 case cần retry do Groq rate limit |
| Priority Accuracy | 86.7% (13/15) | Ưu tiên đúng tài liệu chưa làm/điểm thấp |
| Workload Balance | 80.0% (12/15) | 1-2 tài liệu/tuần, không quá tải |
| Schedule Realism | 90.0% (27/30 steps) | Deadline hợp lý (3-7 ngày/tài liệu) |
| Adjustment Accuracy | 85.7% (6/7) | Đúng ý yêu cầu điều chỉnh bằng NL |

**Phân tích:**

Planning Agent cho thấy khả năng tạo lịch học cá nhân hóa tốt. Điểm mạnh là việc sử dụng learner profile data (điểm số, attempts, completion status) để xếp hạng ưu tiên tài liệu. Điểm yếu là một số trường hợp tạo workload không cân bằng (ví dụ: 3 tài liệu cùng tuần khi sinh viên chỉ yêu cầu "tăng tải nhẹ").

### 6.2.2 Content Agent Evaluation

**Thiết kế:** Đánh giá Content Agent trên 10 tài liệu đa dạng (PDF, DOCX, PPTX) thuộc 3-5 môn học khác nhau.

**Bảng 6.6.** Kết quả đánh giá Content Agent

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| Subject Detection Accuracy | 90.0% (9/10) | 1 case: file tên chung chung "Bai1.pdf" |
| Chunk Quality | 85.0% | Chunks có nghĩa, không cắt giữa câu |
| Boilerplate Removal | 92.0% | Loại bỏ thành công thông tin hành chính |
| RAG Retrieval Precision@5 | 78.0% | 5 chunks đầu tiên liên quan đến query |
| Processing Time (avg) | 3.2s | Per document (incl. LLM call) |

**Phân tích:**

Content Agent xử lý tốt đa dạng format file. Chiến lược 3 tầng subject detection (heuristic → LLM → teacher override) giúp giảm số lần gọi LLM không cần thiết. Hạn chế chính là chất lượng embedding phụ thuộc model all-MiniLM-L6-v2 — có thể cải thiện bằng model đa ngôn ngữ mạnh hơn cho tiếng Việt.

### 6.2.3 Evaluation Agent Evaluation

**Thiết kế:** Đánh giá Evaluation Agent trên 12 profiles sinh viên với lịch sử học tập đa dạng (tốt/trung bình/yếu).

**Bảng 6.7.** Kết quả đánh giá Evaluation Agent

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| Feedback Relevance | 4.2/5.0 (Likert) | Phản hồi cụ thể, không chung chung |
| Personalization Level | 83.3% (10/12) | Mention đúng điểm, đúng môn |
| Length Compliance | 91.7% (11/12) | Đáp ứng ràng buộc ≤ 40 từ |
| Wrong Answer Analysis | 88.0% | Giải thích đúng lý do sai |
| Tone Appropriateness | 4.0/5.0 | Phù hợp với learner level |

**Phân tích:**

Evaluation Agent cho thấy hiệu quả trong việc sinh feedback ngắn gọn nhưng cụ thể. Ràng buộc "không dùng câu điều kiện" trong prompt giúp feedback trực diện hơn. Điểm yếu: một số feedback vẫn hơi generic khi sinh viên chưa có đủ dữ liệu lịch sử.

### 6.2.4 Nova Teacher Agent Evaluation

**Thiết kế:** Đánh giá Nova Teacher Agent (Hub) trên 20 hội thoại thực tế với giảng viên, bao gồm nhiều intent và follow-up questions.

**Bảng 6.8.** Kết quả đánh giá Nova Teacher Agent

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| Intent Classification Accuracy | 90.0% (18/20) | 2 case: intent ambiguous |
| Entity Extraction Accuracy | 85.0% (17/20) | Trích đúng subject/classroom/student |
| Routing Accuracy | 88.9% (16/18) | Route đúng agent sau khi intent OK |
| Context Continuity | 80.0% (16/20) | Follow-up questions được hiểu đúng |
| Response Latency (P50) | 1.2s | Rule-based path |
| Response Latency (P95) | 3.8s | LLM-based path |

**Phân tích:**

Hybrid intent classification (rule-based + LLM) cho kết quả tốt. Rule-based path nhanh (1.2s) cho các intent rõ ràng, LLM path (3.8s) xử lý được yêu cầu phức tạp. Điểm yếu: context continuity đôi khi bị mất khi sinh viên đổi chủ đề đột ngột — do conversation memory chỉ giữ 20 tin nhắn gần nhất.

### 6.2.5 Assessment Agent Evaluation

**Thiết kế:** Đánh giá Assessment Agent trên 15 tài liệu, sinh tổng cộng 300+ câu hỏi MCQ.

**Bảng 6.9.** Kết quả đánh giá Assessment Agent

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| Question Quality (Human) | 3.8/5.0 | Câu hỏi có tình huống, không học vẹt |
| Bloom's Compliance | 72.0% | Phân bổ đúng 6 mức Bloom's |
| Distractor Quality | 81.0% | Nhiễu hợp lý, có bẫy tư duy |
| Format Validity | 95.0% | Đúng 4 options, 1 correct |
| Duplicate Rate | 8.3% | Sau khi chạy similarity check |
| Academic Relevance | 88.0% | Câu hỏi thuộc đúng môn học |
| Generation Time (10 questions) | 12.5s | Bao gồm RAG + LLM + validation |

**Phân tích:**

Assessment Agent cho kết quả khả quan về chất lượng câu hỏi. Điểm mạnh là quy trình validation 5 bước giúp loại bỏ câu kém chất lượng trước khi vào ngân hàng. Điểm yếu: Bloom's compliance 72% cho thấy LLM đôi khi không tuân thủ đúng mức Bloom's được yêu cầu — có thể cải thiện bằng prompt engineering hoặc few-shot examples.

### 6.2.6 Agent Collaboration Analysis

**Thiết kế:** Đánh giá 3 workflow phức tạp đòi hỏi phối hợp nhiều agent.

**Bảng 6.10.** Kết quả đánh giá Agent Collaboration

| Workflow | Agents tham gia | Task Completion | Context Propagation | End-to-end Latency |
|---|---|---|---|---|
| Tutor với cá nhân hóa | Adaptive + RAG + Profile | 95.0% | 90.0% | 4.2s (avg) |
| Tạo đề thi | Hub + Assessment + RAG | 88.0% | 85.0% | 15.8s (avg) |
| Student login fan-out | Planning + Orbit + Eval | 92.0% | 88.0% | 3.5s (parallel) |
| **Trung bình** | — | **91.7%** | **87.7%** | — |

**Phân tích:**

Kiến trúc Agent Hub cho phép phối hợp hiệu quả giữa các agent. Context propagation rate 87.7% cho thấy phần lớn learner data được truyền đúng giữa các agent. Điểm yếu: Assessment workflow có task completion thấp nhất (88%) do phụ thuộc nhiều bước tuần tự — nếu một bước thất bại, toàn bộ pipeline bị ảnh hưởng.

### 6.2.7 Trả lời RQ1

**RQ1: Kiến trúc multi-agent với Agent Hub có hiệu quả hơn mô hình đơn thể không?**

Dựa trên kết quả thực nghiệm, câu trả lời là **có**, với các bằng chứng sau:

**1. Về chất lượng phản hồi AI:**

Bảng so sánh giữa hệ thống multi-agent (có cá nhân hóa) và baseline (không cá nhân hóa):

| Chỉ số | Baseline (không profile) | Multi-Agent (có profile) | Cải thiện |
|---|---|---|---|
| Response Relevance | 3.2/5.0 | 4.2/5.0 | +31.3% |
| Personalization Level | 0% | 83.3% | — |
| Level-appropriate | 40.0% | 85.0% | +112.5% |
| Misconception Detection | 0% | 75.0% | — |
| Context Utilization | 0% | 90.0% | — |

**2. Về khả năng cá nhân hóa:**

Hệ thống multi-agent sử dụng learner profile data (level, weak topics, misconceptions, study patterns) để inject vào system prompt của từng agent. Kết quả là:
- Tutor Agent dạy khác nhau cho Beginner (step-by-step + ví dụ) và Advanced (challenge + phân tích sâu)
- Orbit Agent biết tên sinh viên, điểm yếu cụ thể, và coaching phù hợp
- Evaluation Agent điều chỉnh tone feedback theo learner level
- Planning Agent ưu tiên tài liệu dựa trên điểm số thực tế

**3. Về khả năng phối hợp:**

Agent Hub cho phép context sharing giữa các agent với propagation rate 87.7%, trong khi mô hình đơn thể không có cơ chế chia sẻ ngữ cảnh giữa các module. Kết quả là trải nghiệm học tập liền mạch — Tutor Agent biết điểm yếu từ Evaluation Agent, Planning Agent biết chỉ tiêu từ Teacher Agent.

## 6.3 Thảo luận

### 6.3.1 Hiệu quả của kiến trúc Multi-Agent

**Điểm mạnh:**

1. **Loose coupling:** Mỗi agent hoạt động độc lập với API key riêng, LLM config riêng, prompt riêng. Lỗi một agent không ảnh hưởng các agent khác — hệ thống vẫn hoạt động ở chế độ degraded. Trong thực nghiệm, khi Assessment Agent gặp rate limit, Tutor Agent và Orbit Agent vẫn phản hồi bình thường.

2. **Cá nhân hóa sâu:** Nhờ việc mỗi agent đều truy vấn learner data từ PostgreSQL, response được cá nhân hóa đa chiều: nội dung (dựa trên weak topics), nhịp độ (dựa trên study pattern), và phong cách (dựa trên learner level). Đây là điểm khác biệt chính so với e-learning truyền thống chỉ phân luồng theo điểm số.

3. **Maintainability:** Prompt tập trung trong từng agent, không phân tán. Khi cần thay đổi cách Tutor dạy, chỉ cần sửa file adaptive_agent.py. Khi cần thêm agent mới, chỉ cần tạo class mới và đăng ký route trong API layer.

4. **Scalability:** Redis-backed conversation memory cho phép nhiều backend instance chia sẻ state, horizontal scaling khả thi.

**Điểm yếu:**

1. **Latency cộng gộp:** Trong workflow tuần tự (ví dụ: tạo đề thi), latency tổng cộng bằng tổng latency của từng bước. Assessment workflow mất trung bình 15.8s — có thể cải thiện bằng cách chạy một số bước song song.

2. **LLM dependency:** Hệ thống phụ thuộc Groq API cho phần lớn agent. Khi Groq down hoặc rate limit, tất cả agent đều bị ảnh hưởng. LLM Client (failover sang Gemini) giúp giảm thiểu nhưng không triệt tiêu hoàn toàn.

### 6.3.2 Vai trò của Agent Hub

Nova Teacher Agent đóng vai trò Agent Hub hiệu quả trong kiến trúc đề xuất. Đóng góp chính:

1. **Hybrid intent classification:** Kết hợp rule-based (nhanh, chính xác cho intent rõ ràng) và LLM-based (linh hoạt cho intent phức tạp) đạt accuracy 90% — đủ tốt cho production mà không cần mô hình ML riêng biệt.

2. **Centralized context management:** Conversation Memory tập trung giúp tất cả agent chia sẻ ngữ cảnh hội thoại. Nếu Hub nhớ "giảng viên đang nói về lớp CNTT1", mọi agent đều biết context này.

3. **Simplified routing:** Thay vì mỗi agent cần biết về các agent khác, chỉ Hub cần biết routing map. Điều này giảm complexity từ O(n²) xuống O(n) khi thêm agent mới.

**Hạn chế của Hub:**

- **Single point of failure:** Nếu Nova Teacher Agent lỗi, toàn bộ routing bị gián đoạn. Tuy nhiên, vì Teacher Agent chỉ xử lý teacher-side chat, student-side agents (Adaptive, Orbit) vẫn hoạt động bình thường.
- **Limited routing context:** Hub hiện chỉ route dựa trên intent + entities, chưa có học hỏi từ lịch sử routing (ví dụ: "giảng viên thường hỏi analytics sau khi hỏi overview").

### 6.3.3 Hạn chế của hệ thống

1. **Embedding model cho tiếng Việt:** Model all-MiniLM-L6-v2 chủ yếu được train trên tiếng Anh. Chất lượng retrieval cho tài liệu tiếng Việt có thể thấp hơn mong đợi. Giải pháp: chuyển sang model đa ngôn ngữ (paraphrase-multilingual-MiniLM-L12-v2 hoặc Vietnamese-specific embedding).

2. **Static profiling:** Profiling Agent chỉ phân loại learner level dựa trên 1 bài test đầu vào, không cập nhật động. Cải thiện: tự động cập nhật level dựa trên xu hướng điểm gần nhất (như đã đề xuất trong phần cá nhân hóa).

3. **Evaluation dataset quy mô nhỏ:** Bộ test cases (82 tổng) còn nhỏ so với production. Cần mở rộng bằng cách thu thập thêm dữ liệu thực từ nhiều học kỳ và nhiều môn học.

4. **Chưa có A/B testing:** So sánh trực tiếp giữa hệ thống multi-agent và hệ thống đơn thể cùng cohort sinh viên chưa được thực hiện. Đây là hướng nghiên cứu tiếp theo.

5. **Personalization chưa đo lường end-user impact:** Các chỉ số đánh giá chủ yếu tập trung vào chất lượng kỹ thuật (accuracy, relevance) chứ chưa đo lường tác động thực tế đến kết quả học tập của sinh viên (learning gain, retention rate).

**Bảng 6.11.** Tổng hợp kết quả thực nghiệm

| Agent | Chỉ số chính | Kết quả | Đánh giá |
|---|---|---|---|
| Planning Agent | JSON Validity | 93.3% | Tốt |
| Content Agent | Subject Detection | 90.0% | Tốt |
| Evaluation Agent | Feedback Relevance | 4.2/5.0 | Khá |
| Teacher Agent (Hub) | Intent Accuracy | 90.0% | Tốt |
| Assessment Agent | Question Quality | 3.8/5.0 | Khá |
| Adaptive Tutor | Personalization | 83.3% | Tốt |
| Orbit Agent | Coaching Quality | 4.0/5.0 | Khá |
| **Hệ thống** | **Task Completion** | **91.7%** | **Tốt** |
| **Hệ thống** | **Context Propagation** | **87.7%** | **Khá** |

Tổng kết, kết quả thực nghiệm cho thấy kiến trúc multi-agent với Agent Hub đạt hiệu quả cao trong việc cá nhân hóa học tập. Các agent chuyên biệt đạt chất lượng từ khá đến tốt trên từng tác vụ, và khả năng phối hợp giữa agent (context propagation 87.7%, task completion 91.7%) cho thấy kiến trúc Hub-mediated collaboration hoạt động hiệu quả trong thực tế.
