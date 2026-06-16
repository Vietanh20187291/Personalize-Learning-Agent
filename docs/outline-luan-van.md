# ĐỀ CƯƠNG LUẬN VĂN

## Tên đề tài: Nghiên cứu và phát triển nền tảng học tập trực tuyến cá nhân hóa ứng dụng mô hình Đa tác tử (Multi-Agent System)

---

## CHƯƠNG 1 – GIỚI THIỆU

### 1.1 Đặt vấn đề
- Sự bùng nổ của học trực tuyến và nhu cầu cá nhân hóa trải nghiệm học tập
- Hạn chế của các nền tảng LMS truyền thống: nội dung tĩnh, thiếu khả năng thích ứng, phản hồi chậm trễ
- Vai trò của Trí tuệ nhân tạo (AI) và Large Language Models (LLMs) trong giáo dục
- Tính cấp thiết của việc ứng dụng mô hình đa tác tử (Multi-Agent) để phối hợp nhiều khía cạnh giáo dục

### 1.2 Mục tiêu nghiên cứu
- Mục tiêu tổng quát: Xây dựng nền tảng học tập trực tuyến cá nhân hóa dựa trên kiến trúc Multi-Agent
- Mục tiêu cụ thể:
  - Nghiên cứu và ứng dụng kiến trúc Multi-Agent trong ngữ cảnh giáo dục trực tuyến
  - Thiết kế hệ thống RAG (Retrieval-Augmented Generation) tích hợp để gia tăng độ chính xác của nội dung phản hồi
  - Xây dựng cơ chế đánh giá và phân loại tự động năng lực học sinh
  - Phát triển mô-đun coaching và nhắc nhở học tập cá nhân hóa

### 1.3 Đối tượng và phạm vi nghiên cứu
- Đối tượng: Kiến trúc Multi-Agent trong hệ thống giáo dục trực tuyến; kỹ thuật cá nhân hóa học tập bằng LLM và RAG
- Phạm vi:
  - Phạm vi nội dung: Hệ thống bao gồm đánh giá, lập kế hoạch, gia sư thích ứng, và coaching
  - Phạm vi người dùng: Sinh viên đại học, giáo viên, quản trị viên
  - Phạm vi công nghệ: FastAPI, Next.js, Groq LLM, ChromaDB, SQLAlchemy

### 1.4 Phương pháp nghiên cứu
- Phương pháp nghiên cứu lý thuyết: Tổng quan tài liệu, phân tích so sánh
- Phương pháp原型 (prototype): Thiết kế và triển khai hệ thống prototype
- Phương pháp thực nghiệm: Đánh giá hiệu quả hệ thống qua thực nghiệm với người dùng thực

### 1.5 Đóng góp của luận văn
- Đề xuất kiến trúc Multi-Agent chuyên biệt cho giáo dục trực tuyến cá nhân hóa
- Xây dựng hệ thống RAG pipeline tích hợp cho ngữ cảnh học thuật
- Triển khai và đánh giá hệ thống thực tế với 9 agent chuyên biệt
- Cung cấp bộ khung tham khảo cho các nghiên cứu tiếp theo

### 1.6 Bố cục luận văn
- Mô tả ngắn gọn nội dung từng chương (2→5)

---

## CHƯƠNG 2 – CƠ SỞ LÝ THUYẾT

### 2.1 Hệ thống học tập trực tuyến (E-Learning)
- 2.1.1 Lịch sử phát triển của E-Learning
- 2.1.2 Hệ thống quản lý học tập (LMS) và các nền tảng phổ biến
- 2.1.3 Xu hướng học tập thích ứng (Adaptive Learning)
- 2.1.4 Các thách thức hiện tại của E-Learning

### 2.2 Hệ thống đa tác tử (Multi-Agent System)
- 2.2.1 Khái niệm tác tử (Agent) và hệ thống đa tác tử
- 2.2.2 Phân loại tác tử: Reactive, Deliberative, Hybrid
- 2.2.3 Kiến trúc giao tiếp giữa các tác tử
- 2.2.4 Ứng dụng của Multi-Agent trong giáo dục
- 2.2.5 So sánh với các kiến trúc khác (Monolithic, Microservices)

### 2.3 Trí tuệ nhân tạo tạo sinh (Generative AI) trong giáo dục
- 2.3.1 Large Language Models (LLMs): Tổng quan và tiến bộ gần đây
- 2.3.2 Mô hình ngôn ngữ mở: LLaMA, Gemini và các kiến trúc Transformer
- 2.3.3 Prompt Engineering và Chain-of-Thought reasoning
- 2.3.4 Ứng dụng LLM trong giáo dục: Gia sư AI, tạo câu hỏi, đánh giá

### 2.4 Retrieval-Augmented Generation (RAG)
- 2.4.1 Hạn chế của LLM thuần túy: Hallucination, stale knowledge
- 2.4.2 Kiến trúc RAG: Retrieval → Augmentation → Generation
- 2.4.3 Vector Database và Embedding models
- 2.4.4 Kỹ thuật chunking và retrieval optimization
- 2.4.5 Ứng dụng RAG trong ngữ cảnh giáo dục

### 2.5 Cá nhân hóa trong học tập
- 2.5.1 Mô hình học sinh (Learner Model): Knowledge, Behavior, Preference
- 2.5.2 Kỹ thuật phân loại năng lực học sinh (Profiling)
- 2.5.3 Lộ trình học tập thích ứng (Adaptive Learning Path)
- 2.5.4 Các phương pháp đánh giá tự động (Automated Assessment)
- 2.5.5 Spaced Repetition và Retrieval Practice

### 2.6 Các công trình liên quan
- 2.6.1 Nền tảng học tập thích ứng thương mại (Khan Academy, Duolingo, Coursera)
- 2.6.2 Nghiên cứu học thuật về Multi-Agent trong giáo dục
- 2.6.3 Nghiên cứu về RAG và LLM trong giáo dục
- 2.6.4 Phân tích khoảng trống nghiên cứu (Research Gap)

---

## CHƯƠNG 3 – KIẾN TRÚC MULTI-AGENT

### 3.1 Tổng quan kiến trúc hệ thống đề xuất
- 3.1.1 Nguyên tắc thiết kế: Modularity, Autonomy, Coordination
- 3.1.2 Kiến trúc phân tầng: Presentation Layer → API Layer → Agent Layer → Data Layer
- 3.1.3 Sơ đồ kiến trúc tổng thể

### 3.2 Thiết kế các Agent chuyên biệt

#### 3.2.1 AdaptiveAgent – Gia sư thích ứng
- Vai trò: Tạo lộ trình học, tutoring dựa trên tài liệu (RAG), điều chỉnh độ khó
- Cơ chế hoạt động: RAG retrieval → Context augmentation → LLM generation
- Phân loại học sinh: Beginner / Intermediate / Advanced

#### 3.2.2 EvaluationAgent – Đánh giá năng lực
- Vai trò: Chấm điểm, xếp hạng, tracking tiến độ học tập
- Metrics: Effort Score, Subject Score, Progress Trend
- Tích hợp RAG cho đánh giá context-aware

#### 3.2.3 AssessmentAgent – Tạo câu hỏi tự động
- Vai trò: Sinh câu hỏi trắc nghiệm và tự luận từ tài liệu
- Output: JSON-formatted với đáp án, giải thích, mức độ khó

#### 3.2.4 OrbitAgent – Coaching cá nhân hóa
- Vai trò: Nhắc nhở học tập, coaching tuần, tạo động lực
- Data-driven: Sử dụng hồ sơ, lịch sử login, effort score

#### 3.2.5 PlanningAgent – Lập kế hoạch học tập
- Vai trò: Tạo kế hoạch cá nhân hóa với deadline, priority

#### 3.2.6 ProfilingAgent – Phân loại profile
- Vai trò: Phân loại learner dựa trên assessment, study sessions

#### 3.2.7 TeacherAgent – Hỗ trợ giáo viên
- Vai trò: Quản lý lớp, tạo đề thi, phân tích học sinh
- Memory: ConversationMemory (Redis/in-memory)

#### 3.2.8 ContentAgent và ReviewAgent
- ContentAgent: Xử lý tài liệu đa định dạng (PDF, DOCX, PPTX, TXT)
- ReviewAgent: Ôn tập kiến thức, spaced repetition

### 3.3 Cơ chế giao tiếp và phối hợp giữa các Agent
- 3.3.1 Shared Database Pattern: Agents trao đổi qua SQLAlchemy ORM
- 3.3.2 LLM Client chung với Fallback: Groq → Gemini
- 3.3.3 RAG Shared Context: ChromaDB làm nguồn tri thức chung
- 3.3.4 Conversation Memory: Redis distributed hoặc in-memory

### 3.4 Pipeline RAG tích hợp
- 3.4.1 Document Ingestion: Upload → Chunking → Embedding → ChromaDB
- 3.4.2 Query Pipeline: User query → Vector search → Context augmentation → LLM response
- 3.4.3 Graceful Degradation: Fallback khi ChromaDB/LLM không khả dụng

### 3.5 Thiết kế giao diện người dùng (Frontend)
- 3.5.1 Kiến trúc Next.js App Router
- 3.5.2 Student Dashboard: Adaptive learning, assessment, planning
- 3.5.3 Teacher Dashboard: Class management, student analytics
- 3.5.4 Admin Panel: User, subject, teacher management

### 3.6 Thiết kế cơ sở dữ liệu
- 3.6.1 Mô hình ER (Entity-Relationship)
- 3.6.2 Các bảng chính và quan hệ
- 3.6.3 Chiến lược migration và compatibility

---

## CHƯƠNG 4 – ĐỀ XUẤT MÔ HÌNH VÀ KIẾN TRÚC HỆ THỐNG

### 4.1 Mô hình cá nhân hóa đề xuất
- 4.1.1 Learner Profile Model: Knowledge State + Behavior Pattern + Learning Preference
- 4.1.2 Cơ chế phân loại năng lực tự động (Automated Profiling)
- 4.1.3 Adaptive Difficulty Engine: Điều chỉnh nội dung theo level
- 4.1.4 Learning Path Generation: Từ profile → roadmap → study plan

### 4.2 Mô hình đánh giá và phản hồi
- 4.2.1 Automated Assessment Generation từ tài liệu học
- 4.2.2 Multi-dimensional Evaluation: Effort Score + Knowledge Score + Progress Trend
- 4.2.3 Feedback Loop: Đánh giá → Profiling → Adaptive Adjustment

### 4.3 Mô hình RAG cải tiến cho giáo dục
- 4.3.1 Subject-aware Chunking: Phân chunk theo môn học và chủ đề
- 4.3.2 Context Window Optimization: Chọn chunks phù hợp năng lực học sinh
- 4.3.3 Citation & Grounding: Đảm bảo câu trả lời dựa trên tài liệu gốc

### 4.4 Mô hình Coaching tự động (OrbitAgent)
- 4.4.1 Weekly Digest Generation từ dữ liệu học tập thực tế
- 4.4.2 Motivational Message Personalization
- 4.4.3 Smart Reminder Scheduling dựa trên học hành

### 4.5 Kiến trúc triển khai hệ thống
- 4.5.1 Backend Stack: FastAPI + SQLAlchemy + ChromaDB + Groq/Gemini
- 4.5.2 Frontend Stack: Next.js + React + TypeScript + Tailwind
- 4.5.3 Deployment Architecture: Uvicorn/Gunicorn, Redis cache
- 4.5.4 Security: JWT authentication, bcrypt hashing, CORS

### 4.6 Đảm bảo chất lượng và tính ổn định
- 4.6.1 LLM Fallback Chain: Groq → Gemini (tự động)
- 4.6.2 Graceful Degradation: Hệ thống vẫn chạy khi LLM/RAG lỗi
- 4.6.3 Connection Pooling & Health Monitoring
- 4.6.4 Conversation Memory TTL và cleanup

---

## CHƯƠNG 5 – THỰC NGHIỆM VÀ ĐÁNH GIÁ

### 5.1 Môi trường thực nghiệm
- 5.1.1 Phần cứng và phần mềm sử dụng
- 5.1.2 Dataset: Tài liệu học, câu hỏi, hồ sơ học sinh
- 5.1.3 Participant: Số lượng và đặc điểm người tham gia

### 5.2 Kịch bản thực nghiệm

#### 5.2.1 Thực nghiệm 1: Đánh giá chất lượng Adaptive Tutoring
- Metric: Relevance, Accuracy, Usefulness (Likert scale)
- So sánh: Có RAG vs Không RAG
- Kết quả và phân tích

#### 5.2.2 Thực nghiệm 2: Đánh giá chất lượng Assessment Generation
- Metric: Question quality, Answer correctness, Difficulty alignment
- So sánh với câu hỏi do giáo viên tạo
- Kết quả và phân tích

#### 5.2.3 Thực nghiệm 3: Đánh giá hiệu quả cá nhân hóa
- Metric: Learning gain, Engagement time, Student satisfaction
- So sánh: Cá nhân hóa vs Không cá nhân hóa
- Kết quả và phân tích

#### 5.2.4 Thực nghiệm 4: Đánh giá hiệu năng hệ thống
- Metric: Response time, Throughput, Resource usage
- LLM Fallback latency: Groq vs Gemini
- RAG retrieval accuracy (Recall@K, MRR)
- Kết quả và phân tích

#### 5.2.5 Thực nghiệm 5: Đánh giá Coaching Effectiveness
- Metric: Student retention, Study consistency, Perceived helpfulness
- OrbitAgent weekly digest evaluation
- Kết quả và phân tích

### 5.3 Kết quả tổng hợp và thảo luận
- 5.3.1 Tổng hợp kết quả từ các thực nghiệm
- 5.3.2 So sánh với các công trình liên quan
- 5.3.3 Thảo luận về ưu điểm và hạn chế

### 5.4 Khuyến nghị và hướng phát triển
- 5.4.1 Cải tiến kiến trúc Agent: Communication protocol, Agent orchestration
- 5.4.2 Nâng cấp RAG: Hybrid search, Re-ranking, Multi-modal
- 5.4.3 Mở rộng: Multi-language, Mobile app, LMS Integration
- 5.4.4 Đạo đức AI trong giáo dục: Bias, Privacy, Transparency

---

## TÀI LIỆU THAM KHẢO
(Dự kiến 40-60 tài liệu, bao gồm journal papers, conference proceedings, technical reports)

## PHỤ LỤC
- Phụ lục A: Sơ đồ ER chi tiết
- Phụ lục B: API Documentation
- Phụ lục C: Survey/Bảng hỏi đánh giá
- Phụ lục D: Source code chính (selected)
