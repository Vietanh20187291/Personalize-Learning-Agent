# PHỤ LỤC: MÔ TẢ BỘ TEST THỰC NGHIỆM HỆ THỐNG HỌC TẬP CÁ NHÂN HÓA DỰA TRÊN AI

## 1. Tổng quan bộ test

Bộ test thực nghiệm được thiết kế nhằm đánh giá toàn diện các thành phần cốt lõi của hệ thống học tập cá nhân hóa dựa trên trí tuệ nhân tạo. Bộ test bao gồm **912 test case** được phân bổ thành 3 nhóm chính:

| Nhóm | Component | Số test case | Mô tả |
|------|-----------|-------------|--------|
| Multi-Agent | `multi_agent` | 792 | Đánh giá 8 agent trong kiến trúc đa tác tử |
| RAG | `rag` | 120 | Đánh giá khả năng truy xuất và sinh câu trả lời |
| OCR/OMR | `ocr_omr` | — | Đánh giá nhận dạng và chấm thi tự động |

### 1.1. Phân bố độ khó

| Độ khó | Số test case | Tỷ lệ |
|---------|-------------|-------|
| Easy | 91 | 10.0% |
| Medium | 106 | 11.6% |
| Hard | 693 | 76.0% |
| Beginner/Intermediate/Advanced (Profiling) | 46 | 5.0% |

Bộ test được thiết kế chủ yếu ở mức **hard (76%)** nhằm tạo áp lực thực tế lên các agent và đảm bảo kết quả không đạt 100% pass — phản ánh đúng giới hạn thực tế của hệ thống.

### 1.2. Phân bố ngưỡng đạt (pass_threshold)

| Thông số | Giá trị |
|----------|---------|
| Ngưỡng tối thiểu | 0.48 |
| Ngưỡng tối đa | 0.84 |
| Ngưỡng trung bình | 0.612 |

Ngưỡng đạt (pass_threshold) được phân tầng theo độ khó:
- **Easy**: 0.48 – 0.62 (yêu cầu cơ bản, agent cần trả lời đúng trọng tâm)
- **Medium**: 0.48 – 0.66 (yêu cầu đầy đủ từ khóa và ngữ cảnh)
- **Hard**: 0.48 – 0.88 (yêu cầu chính xác, không chứa từ khóa cấm, có bằng chứng)

---

## 2. Chi tiết test suite theo Agent

### 2.1. Nova Teacher Agent (131 test cases)

**Vai trò:** Hỗ trợ giảng viên phân tích lớp học, sinh đề thi, theo dõi sinh viên.

**Các loại test case:**

| Loại test | Số case | Mô tả | Ngưỡng đạt |
|-----------|---------|--------|-----------|
| Class overview | 17 | Truy vấn tổng quan tình hình lớp | 0.62 |
| Analytics risk scan | 17 | Phân tích nhóm yếu, nút thắt học tập | 0.60 |
| Course map | 17 | Tra cứu thông tin môn học | 0.58 |
| Material audit | 17 | Kiểm tra tài liệu còn thiếu | 0.56 |
| Student snapshot | ~17 | Xem chi tiết từng sinh viên | 0.56 |
| Exam generation | 17 | Yêu cầu tạo đề thi | 0.52 |
| Intervention plan | 17 | Lập kế hoạch can thiệp nhóm yếu | 0.76 |
| Comparison brief | 17 | So sánh tiến độ lớp với mục tiêu | 0.78 |
| Follow-up drill | 17 | Câu hỏi tiếp theo có ngữ cảnh | 0.64 |

**Stress tests (5 biến thể × 17 fixture = 85 cases):**

| Biến thể | Mô tả | Từ khóa bắt buộc | Từ khóa cấm | Ngưỡng |
|----------|--------|------------------|-------------|--------|
| Stress summary | Trả lời trong 3 gạch đầu dòng, ưu tiên số liệu | Tên lớp, tên môn | "chung chung", "không rõ" | 0.72 |
| Conflict audit | Chỉ ra mâu thuẫn dữ liệu trước khi kết luận | Tên lớp, tên môn, "mâu thuẫn" | "không biết", "xin lỗi" | 0.74 |
| Time boxed | Đề xuất hành động khẩn cấp trong 60 giây | Tên lớp, tên môn, "hành động" | "tổng quan", "chung chung" | 0.72 |
| Priority drill | Chỉ nêu ưu tiên, không nhắc lại câu hỏi | Tên lớp, tên môn, "ưu tiên" | "không có dữ liệu", "không biết" | 0.74 |
| Distractor filter | Lọc ra vấn đề lớn nhất, bỏ chi tiết phụ | Tên lớp, tên môn, "vấn đề" | "ngoại lệ", "không xác định" | 0.72 |

### 2.2. Planning Agent (91 test cases)

**Vai trò:** Tạo và điều chỉnh kế hoạch học tập cá nhân hóa cho sinh viên.

| Loại test | Số case | Mô tả | Ngưỡng đạt |
|-----------|---------|--------|-----------|
| Regenerate plan | 10 | Tạo kế hoạch học mới từ tài liệu đã đăng ký | 0.52 |
| Prioritize subject | 10 | Ưu tiên môn yếu học trước | 0.50 |
| Rebalance workload | 10 | Cân bằng lại khi quá tải | 0.50 |
| Catch-up sprint | 10 | Bù kịp sau khi nghỉ 3 ngày | 0.66 |
| Exam week compression | 10 | Nén nội dung ôn thi 5 ngày | 0.68 |

**Stress tests (4 biến thể × 10 fixture = 40 cases):**

| Biến thể | Mô tả | Ngưỡng |
|----------|--------|--------|
| Overload triage | Sắp xếp không quá 4 bước để kịp môn trong 1 tuần | 0.70 |
| Focus reroute | Đề xuất cắt bỏ học phần để tập trung | 0.68 |
| Deadline squeeze | Rút gọn kế hoạch, nêu phần cần học trước | 0.72 |
| Misdirection guard | Chỉ tập trung 1 môn trong 7 ngày, không bị lệch | 0.72 |

### 2.3. Evaluation Agent (100 test cases)

**Vai trò:** Giải thích tiến độ học tập, chỉ ra môn yếu, gợi ý ôn tập.

| Loại test | Số case | Mô tả | Ngưỡng |
|-----------|---------|--------|--------|
| Weak subject | 10 | Hỏi môn yếu nhất | 0.50 |
| Overdue documents | 10 | Hỏi tài liệu trễ hạn | 0.50 |
| Trend analysis | 10 | Phân tích tiến bộ 2 tuần | 0.50 |
| Revision priority | 10 | Gợi ý tài liệu ôn tập trước kỳ thi | 0.52 |
| Evidence check | 10 | Yêu cầu giải thích dựa trên bằng chứng dữ liệu | 0.66 |
| Contradiction audit | 10 | Xử lý mâu thuẫn giữa điểm số và tiến độ | 0.66 |

**Stress tests (4 biến thể × 10 fixture = 40 cases):**

| Biến thể | Mô tả | Từ khóa cấm | Ngưỡng |
|----------|--------|-------------|--------|
| Evidence brief | Lập bản ghi ngắn chỉ dựa trên số liệu | "chung chung", "không rõ" | 0.70 |
| Risk signal | Nhận diện dấu hiệu suy giảm học tập | "không biết", "xin lỗi" | 0.72 |
| Ranked next step | Nêu 3 bước tiếp theo ưu tiên | "ngoại lệ", "không xác định" | 0.68 |
| Contradiction resolver | Giải thích cách ra kết luận khi điểm và tiến độ không khớp | "chung chung", "không có dữ liệu" | 0.72 |

### 2.4. Orbit Agent (90 test cases)

**Vai trò:** Theo dõi kỷ luật học tập, nhắc nhở, coaching.

| Loại test | Số case | Mô tả | Ngưỡng |
|-----------|---------|--------|--------|
| Progress check | 10 | Hỏi tiến độ học | 0.48 |
| Study plan | 10 | Yêu cầu lập kế hoạch tuần | 0.48 |
| Discipline check | 10 | Kiểm tra kỷ luật và quên học | 0.48 |
| Recovery plan | 10 | Kế hoạch phục hồi sau nghỉ học | 0.62 |
| Procrastination scan | 10 | Phát hiện dấu hiệu trì hoãn | 0.58 |

**Stress tests (4 biến thể × 10 fixture = 40 cases):**

| Biến thể | Mô tả | Ngưỡng |
|----------|--------|--------|
| Weekly drill | Gom thông tin tuần, chỉ ra nguy cơ bị bỏ sót | 0.68 |
| Recovery sprint | Đề xuất kế hoạch phục hồi 7 ngày | 0.70 |
| Discipline audit | Đánh giá kỷ luật, nêu 1 hành động cần làm ngay | 0.70 |
| Priority shift | Đề xuất vị trí ưu tiên môn trong tuần | 0.72 |

### 2.5. Profiling Agent (97 test cases)

**Vai trò:** Phân loại trình độ người học dựa trên kết quả đánh giá.

**Các test case kiểm tra phân loại trình độ:**

| Cặp correct/total | Trình độ kỳ vọng | Ngưỡng đạt |
|-------------------|-------------------|-----------|
| 1/10 | Beginner | 0.80 |
| 2/10 | Beginner (borderline) | 0.82 |
| 3/10 | Beginner | 0.80 |
| 4/10 | Beginner | 0.80 |
| 5/10 | Intermediate (borderline) | 0.84 |
| 7/8 | Advanced (near miss) | 0.88 |
| 7/10 | Intermediate (borderline) | 0.84 |
| 8/10 | Advanced (borderline) | 0.86 |
| 9/10 | Advanced | 0.84 |

Profiling agent có ngưỡng cao nhất (0.80–0.88) vì đây là bài toán phân loại tất nhiên — agent chỉ cần trả về đúng nhãn trình độ.

### 2.6. Adaptive Agent (82 multi-agent + 120 RAG = 202 total cases)

**Vai trò:** Tạo lộ trình học, trả lời câu hỏi dựa trên tài liệu học tập.

**Multi-Agent test cases (82):**

| Loại test | Mô tả | Ngưỡng |
|-----------|--------|--------|
| Roadmap generation | Tạo lộ trình từ tài liệu cụ thể | 0.48 |
| Summary chat | Tóm tắt nội dung tài liệu | 0.48 |
| Concept explanation | Giải thích khái niệm cốt lõi | 0.48 |
| Contrast analysis | So sánh với tài liệu khác | 0.58 |
| Retrieval trace | Trả lời dựa trên tài liệu, có trích dẫn | 0.58 |

**Stress tests (3 biến thể):**

| Biến thể | Mô tả | Từ khóa cấm | Ngưỡng |
|----------|--------|-------------|--------|
| Trap summary | Tóm tắt bỏ qua chi tiết không có bằng chứng | "không rõ", "không biết" | 0.66 |
| Contrast compare | So sánh, chỉ ra phần phải ôn ngay | "chung chung", "ngoại lệ" | 0.68 |
| Grounded answer | Trả lời bám sát tài liệu, không suy đoán | "suy đoán", "không có" | 0.68 |

### 2.7. Content Agent (40 test cases)

**Vai trò:** Phân tích tài liệu học tập, dự đoán môn học.

| Loại test | Mô tả | Ngưỡng |
|-----------|--------|--------|
| Quick analyze | Phân tích nhanh tài liệu | 0.48 |
| Process file | Xử lý sâu tài liệu | 0.48 |

**Stress tests (2 biến thể):**

| Biến thể | Mô tả | Từ khóa cấm | Ngưỡng |
|----------|--------|-------------|--------|
| Source-trace | Nêu môn học theo kiểu kiểm định nguồn | "không rõ", "ngoại lệ" | 0.62 |
| Noise-filter | Kết luận 1 câu tài liệu thuộc môn gì | "chung chung", "không biết" | 0.64 |

### 2.8. Assessment Agent (161 test cases)

**Vai trò:** Sinh câu hỏi trắc nghiệm từ ngân hàng câu hỏi.

Test cases được sinh với số lượng câu hỏi biến đổi: 5, 6, 7, 8, 9, 10, 12, 15 câu. Mỗi fixture sinh 3 loại test:
- **Quiz variant**: số câu hỏi biến đổi (ngưỡng 0.52)
- **Stress #1**: số câu tăng + 5 (ngưỡng 0.66)
- **Stress #2**: số câu tăng + 7 (ngưỡng 0.66)

---

## 3. Bộ test RAG (120 test cases)

### 3.1. Cấu trúc

RAG test sinh 5 biến thể prompt cho mỗi câu hỏi trong QuestionBank:

| Biến thể | Mô tả | Đặc điểm | Ngưỡng |
|----------|--------|-----------|--------|
| **Direct** | Truy vấn sự thật trực tiếp từ ngân hàng | Copy y nguyên câu hỏi gốc | 0.48 |
| **Paraphrase** | Truy vấn diễn đạt lại | Yêu cầu giải thích nội dung cốt lõi | 0.56 |
| **Synthesis** | Truy vấn tổng hợp | Phải bám sát tài liệu, tránh thông tin ngoài | 0.56 |
| **Adversarial** | Truy vấn đối kháng | Chứa nhận định sai, yêu cầu loại bỏ | 0.56 |
| **Evidence** | Truy vấn cần bằng chứng | Yêu cầu trả lời dựa trên tài liệu nguồn | 0.56 |

### 3.2. Các chỉ số đánh giá RAG

| Chỉ số | Công thức | Ý nghĩa |
|--------|-----------|---------|
| **Precision@K** | Số chunk liên quan retrieved / Tổng chunks retrieved | Độ chính xác truy xuất |
| **Recall@K** | Số chunk liên quan retrieved / Tổng chunks liên quan | Độ bao phủ truy xuất |
| **MRR** | 1 / rank của chunk liên quan đầu tiên | Chất lượng xếp hạng |
| **Context Coverage** | Từ khóa kỳ vọng có trong context / Tổng từ khóa | Độ bao phủ ngữ cảnh |
| **Answer Similarity** | Cosine similarity(answer, expected_answer) | Độ tương đồng câu trả lời |
| **Faithfulness** | (Groundedness + Keyword Coverage) / 2 | Độ tin cậy câu trả lời |
| **Groundedness** | 1 - Unsupported Token Ratio | Tỷ lệ token có hỗ trợ từ context |
| **Hallucination Risk** | 1 - Groundedness | Nguy cơ ảo giác |

---

## 4. Cơ chế chấm điểm

### 4.1. Multi-Agent Scoring

```
correctness = (keyword_score + semantic_similarity + completeness) / 3 - forbidden_penalty
```

Trong đó:
- **keyword_score**: Tỷ lệ từ khóa kỳ vọng xuất hiện trong output (normalized lowercase)
- **semantic_similarity**: Cosine similarity giữa output và expected_output (TF-based)
- **completeness**: min(observed_items, min_items) / min_items (áp dụng cho quiz/roadmap)
- **forbidden_penalty**: Tỷ lệ từ khóa cấm xuất hiện trong output

**Điều kiện pass:** `correctness >= pass_threshold AND task_success > 0`

### 4.2. RAG Scoring

Đánh giá 2 giai đoạn: truy xuất (retrieval) và sinh câu trả lời (generation).

**Retrieval metrics:** Precision@K, Recall@K, MRR — đo lường dựa trên việc chunk được truy xuất có khớp source_file kỳ vọng hoặc chứa từ khóa liên quan không.

**Generation metrics:** Faithfulness, Groundedness, Hallucination Risk — đo lường dựa trên tỷ lệ token trong câu trả lời có xuất hiện trong context đã truy xuất.

### 4.3. OCR/OMR Scoring

| Chỉ số | Ý nghĩa |
|--------|---------|
| Answer Accuracy | Tỷ lệ câu trả lời nhận dạng đúng |
| Student ID Accuracy | Tỷ lệ nhận dạng đúng MSSV |
| Exam Code Accuracy | Tỷ lệ nhận dạng đúng mã đề |
| CER (Character Error Rate) | Khoảng cách Levenshtein giữa MSSV dự đoán và thực tế |
| F1 Score | Trung bình điều hòa precision và recall |

---

## 5. Cách thức thực hiện test

### 5.1. Thực hiện từng case

Do giới hạn API rate của Groq, bộ test được thiết kế để **chạy từng case một**:

1. Người dùng chọn agent → xem danh sách test case
2. Ấn **"Run case"** cho từng test case
3. Kết quả được lưu tự động vào database (bảng `research_experiment_item_result`)
4. Sau khi chạy xong, xem kết quả ở tab **"Kết quả"**

### 5.2. Xuất báo cáo

Hệ thống hỗ trợ xuất báo cáo dưới 2 dạng:

| Định dạng | Endpoint | Nội dung |
|-----------|----------|----------|
| **CSV** | `GET /api/research/export/results` | Chi tiết từng test case: pass/fail, correctness, latency, error |
| **Markdown** | `POST /api/research/reports/generate` | Báo cáo chương luận văn với bảng metric và thảo luận kết quả |

### 5.3. Cơ chế ghi nhận token

Mỗi test case sử dụng `_TokenUsageRecorder` để theo dõi:
- Số lần gọi LLM (llm_call_count)
- Số prompt tokens và completion tokens
- Model sử dụng
- Độ trễ (latency_ms)

Dữ liệu này được lưu vào `token_usage_json` để phân tích chi phí trong luận văn.
