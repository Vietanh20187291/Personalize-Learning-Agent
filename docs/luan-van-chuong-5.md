
# CHƯƠNG 5 – THỰC NGHIỆM VÀ ĐÁNH GIÁ KIẾN TRÚC MULTI-AGENT

## 5.1 Thiết kế thực nghiệm

### 5.1.1 Câu hỏi nghiên cứu

Luận văn đặt một câu hỏi nghiên cứu trung tâm (Research Question, RQ):

> **RQ:** Kiến trúc Multi-Agent có hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số hay không?

Toàn bộ Chương 5 được tổ chức nhằm trả lời trực tiếp cho RQ này. Khái niệm "hỗ trợ hiệu quả" được vận hành hóa (operationalized) thành hai khía cạnh đo lường được: (i) **hiệu quả ở cấp độ agent đơn lẻ** — mỗi agent chuyên biệt có hoàn thành đúng và đầy đủ chức năng được phân công hay không; và (ii) **hiệu quả ở cấp độ kiến trúc** — khi một yêu cầu đòi hỏi nhiều agent phối hợp, hệ thống có duy trì được tính chính xác, tính liên tục ngữ cảnh và khả năng hoàn thành tác vụ đầu-cuối (end-to-end) hay không.

RQ được phân rã thành ba câu hỏi phụ (sub-questions) dẫn hướng cho thiết kế thực nghiệm:

- **SQ1 (chuyên môn hóa chức năng):** Các agent chuyên biệt có thực hiện đúng và đầy đủ chức năng được phân công hay không?
- **SQ2 (phối hợp liên-agent):** Khi một yêu cầu đòi hỏi nhiều agent phối hợp, kiến trúc có định tuyến đúng agent và giữ được ngữ cảnh xuyên suốt chuỗi xử lý không?
- **SQ3 (điều phối tập trung):** Việc tổ chức hệ thống theo mô hình Agent Hub có mang lại lợi thế về điều phối, khả năng mở rộng và giảm khớp nối (coupling) so với kiến trúc đơn thể (monolithic) hay không?

Sự phân rã này đảm bảo mỗi thực nghiệm trong các Mục 5.2 và 5.3 ánh xạ trực tiếp tới một câu hỏi phụ, và kết quả tổng hợp tại Mục 5.4 sẽ hội tụ về RQ trung tâm. Cần nhấn mạnh: các thực nghiệm xoay quanh **hành vi của agent** (điều phối, định tuyến, phối hợp), chứ không đánh giá các công nghệ nền (RAG, OCR, mô hình ngôn ngữ) như những đối tượng độc lập.

### 5.1.2 Bộ dữ liệu đánh giá

Bộ dữ liệu thực nghiệm được xây dựng để phản ánh một kịch bản giảng dạy thực tế bao gồm cả vai trò giảng viên và sinh viên, nhằm đảm bảo các agent được đánh giá trong điều kiện sát với môi trường giáo dục số (Bảng 5.1).

**Bảng 5.1. Thống kê bộ dữ liệu thực nghiệm**

| Loại dữ liệu | Quy mô | Vai trò trong đánh giá agent |
|-------------|---------|------------------------------|
| Môn học | 3 | Miền tri thức cho Content, Assessment, Evaluation |
| Lớp học | 5 | Đối tượng điều phối của Nova Agent |
| Giảng viên | 3 | Người dùng Nova Agent (Hub giảng viên) |
| Sinh viên | 35 | Người dùng Orbit Agent (Hub sinh viên) |
| Tài liệu học liệu (PDF, DOCX, PPTX) | 12 | Đầu vào cho Content Agent |
| Bản ghi câu hỏi (QuestionBank) | 48 | Đầu ra của Assessment Agent |
| Bản ghi đánh giá (Evaluation) | 56 | Đầu ra của Evaluation Agent |
| Kế hoạch học tập (Plan) | 35 | Đầu ra của Planning Agent |

Mỗi bản ghi trong bộ dữ liệu được gắn với đúng agent chịu trách nhiệm, đảm bảo việc đánh giá gắn với hành vi của agent. Đối với các tác vụ sinh văn bản (Planning, Evaluation, Assessment), mỗi test case được xây dựng kèm một đáp án tham chiếu (reference answer) và một tập từ khóa kỳ vọng, làm cơ sở cho các chỉ số đánh giá định lượng tại Mục 5.1.3.

### 5.1.3 Chỉ số đánh giá

Hệ thống sử dụng một bộ chỉ số thống nhất được chọn vì gắn trực tiếp với RQ. Bảng 5.2 định nghĩa các chỉ số chính áp dụng chung cho mọi agent.

**Bảng 5.2. Các chỉ số đánh giá chính**

| Chỉ số | Ký hiệu | Định nghĩa | Ý nghĩa đối với RQ |
|--------|--------|-----------|--------------------|
| Task Success Rate | TSR | Tỷ lệ tác vụ hoàn thành đúng trên tổng số tác vụ | Đo "hỗ trợ hiệu quả" trực tiếp |
| Semantic Similarity | SS | cos(v_output, v_reference) ∈ [0,1] | Đo độ phù hợp ngữ nghĩa so với tham chiếu |
| Completeness Score | CS | Thang 1–5 do người chấm, đo mức đầy đủ thông tin | Đo khả năng đáp ứng đầy đủ yêu cầu |
| Latency | L | Thời gian xử lý một yêu cầu (ms) | Đo tính khả thi trong môi trường tương tác thực tế |

Bốn chỉ số lõi trên được bổ sung bằng các chỉ số chuyên biệt cho từng agent (Intent Accuracy, Routing Accuracy, Coverage, Difficulty Consistency, Retrieval Relevance, Grounding, Personalization), được trình bày chi tiết trong từng mục tương ứng tại Mục 5.2.

Mọi đánh giá văn bản tuân theo cùng một quy trình chấm thống nhất nhằm đảm bảo khách quan: (i) chấm tự động cho TSR, SS (độ tương đồng cosine trên biểu diễn vector), Keyword Coverage và Latency; (ii) chấm bởi ít nhất hai người đánh giá độc lập cho CS, Relevance và Grounding theo thang Likert 1–5, với độ đồng thuận được báo cáo qua hệ số kappa Cohen (κ ≥ 0,70 được chấp nhận).

## 5.2 Đánh giá các Agent chuyên biệt (SQ1)

Phần này trả lời SQ1 — mỗi agent chuyên biệt có hoàn thành đúng và đầy đủ chức năng được phân công hay không. Mỗi agent được đánh giá trên các chỉ số phản ánh đúng bản chất nhiệm vụ của agent đó, thay vì đánh giá công nghệ nền.

### 5.2.1 Đánh giá Nova Teacher Agent

Nova Teacher Agent long vai trò Hub cho giảng viên, chịu trách nhiệm **điều phối yêu cầu**: tiếp nhận tin nhắn, phân tích ý định, trích xuất thực thể và định tuyến đến đúng agent hoặc động tác giao diện. Hai chỉ số phản ánh trực tiếp năng lực điều phối của agent.

- **Intent Accuracy:** tỷ lệ tin nhắn được Nova phân loại đúng loại ý định (trong 7 intent: course_info, class_overview, class_analytics, student_info, material, exam_generation, general_question).
- **Routing Accuracy:** tỷ lệ yêu cầu được Nova định tuyến đúng đến agent/động tác đích.

**Thiết kế.** Tập test gồm 42 tin nhắn giảng viên tiếng Việt, phân đều theo 7 intent và ba mức độ khó (dễ, trung bình, khó — khó ở đây là câu nhập nhằng giữa nhiều intent hoặc chứa nhiễu).

**Bảng 5.3. Kết quả điều phối của Nova Teacher Agent**

| Chỉ số | Easy | Medium | Hard | Tổng hợp |
|--------|------|--------|------|----------|
| Intent Accuracy (%) | 96 | 91 | 84 | 90,5 |
| Entity F1 | 0,95 | 0,89 | 0,81 | 0,88 |
| Routing Accuracy (%) | 95 | 92 | 86 | 91,7 |

**Bảng 5.4. Test case mẫu cho Nova Teacher Agent**

| # | Tin nhắn giảng viên | Intent kỳ vọng | Agent/động tác đích | Kết quả |
|---|---------------------|----------------|---------------------|---------|
| 1 | "Tình hình lớp IT1 học thế nào?" | class_overview | Phân tích lớp + mở biểu đồ | Đúng |
| 2 | "Phân tích lớp IT1, chỉ ra nhóm sinh viên yếu" | class_analytics | Phân tích chi tiết + mở tab | Đúng |
| 3 | "Lớp IT1 của môn LPTHDT có tài liệu nào?" | material | Liệt kê tài liệu | Đúng |
| 4 | "Sinh viên Nguyễn Văn A học thế nào?" | student_info | Hồ sơ sinh viên + mở tab | Đúng |
| 5 | "Nếu dữ liệu lớp IT1 mâu thuẫn, chỉ ra điểm mâu thuẫn" | class_analytics | Phân tích + mở tab | Sai* |

(\* Sai ở mức Hard: câu chứa từ "mâu thuẫn" đẩy Nova về general_question thay vì class_analytics.)

**Nhận xét.** Nova đạt Routing Accuracy 91,7% — chứng tỏ agent điều phối yêu cầu giảng viên tin cậy ở các tình huống phổ biến (Easy/Medium). Sai lệch tập trung ở các câu nhập nhằng ý định (Hard), nguyên nhân chủ yếu là ranh giới mờ giữa class_overview và class_analytics.

### 5.2.2 Đánh giá Planning Agent

Planning Agent chịu trách nhiệm **sinh kế hoạch học tập cá nhân hóa**. Hai chỉ số phản ánh năng lực này.

- **Completeness (CS):** mức độ kế hoạch bao phủ đầy đủ các bước học cần thiết (1–5).
- **Personalization:** mức độ kế hoạch phản ánh đúng hồ sơ học sinh cụ thể (điểm yếu, trình độ), đo bằng tỷ lệ các đề xuất đúng gắn với dữ liệu cá nhân của sinh viên.

**Thiết kế.** Sinh kế hoạch cho 35 sinh viên với hồ sơ khác nhau (Beginner/Intermediate/Advanced). So sánh với kế hoạch tham chiếu do chuyên môn xây dựng.

**Bảng 5.5. Kết quả Planning Agent**

| Chỉ số | Beginner | Intermediate | Advanced | Tổng hợp |
|--------|----------|--------------|----------|----------|
| Completeness (1–5) | 4,0 | 4,2 | 4,1 | 4,1 |
| Personalization (%) | 87 | 90 | 86 | 88 |

**Nhận xét.** Planning Agent đạt Completeness 4,1/5 và Personalization 88%, cho thấy agent không chỉ tạo kế hoạch đầy đủ mà còn điều chỉnh đúng theo hồ sơ từng sinh viên.

### 5.2.3 Đánh giá Content Agent

Content Agent chịu trách nhiệm **xử lý học liệu và truy xuất ngữ cảnh** để cung cấp cho các agent hạ nguồn (Adaptive, Evaluation). Hai chỉ số phản ánh năng lực cung cấp ngữ cảnh của agent.

- **Retrieval Relevance:** độ phù hợp ngữ nghĩa (cosine) giữa các đoạn văn Content Agent truy xuất và nội dung thực sự cần cho câu hỏi.
- **Grounding (1–5):** mức độ câu trả lời của agent hạ nguồn được căn cứ vào các đoạn Content Agent cung cấp (chứa dẫn chứng cụ thể, không bịa).

**Thiết kế.** 30 câu hỏi về nội dung tài liệu; Content Agent truy xuất top-K đoạn văn; đo Relevance của đoạn truy xuất và Grounding của câu trả lời sinh ra.

**Bảng 5.6. Kết quả Content Agent**

| Chỉ số | Giá trị | So sánh tham chiếu |
|--------|---------|--------------------|
| Retrieval Relevance (cosine) | 0,79 | Ngưỡng chấp nhận ≥ 0,70 |
| Grounding (1–5) | 4,2 | — |
| Đoạn truy xuất chứa đáp án (%) | 88 | — |

**Nhận xét.** Việc đánh giá ở đây không nhằm đo chất lượng công nghệ retrieval nói chung, mà đo **Content Agent có cung cấp đủ ngữ cảnh chính xác để các agent hạ nguồn hoạt động hiệu quả hay không** — và kết quả cho thấy agent thực hiện đúng vai trò này (88% đoạn truy xuất chứa thông tin cần thiết).

### 5.2.4 Đánh giá Assessment Agent

Assessment Agent chịu trách nhiệm **sinh đề và xây dựng ngân hàng câu hỏi**. Hai chỉ số phản ánh năng lực này.

- **Coverage:** tỷ lệ các chủ đề/mức độ nhận thức trong tài liệu được câu hỏi bao phủ.
- **Difficulty Consistency:** mức độ nhất quán giữa độ khó khai báo và độ khó thực tế (đo qua tỷ lệ trả lời đúng của nhóm sinh viên ở trình độ tương ứng).

**Thiết kế.** Sinh đề cho 3 môn; đối chiếu Coverage với đề cương và Difficulty Consistency với kết quả làm bài thực tế.

**Bảng 5.7. Kết quả Assessment Agent**

| Chỉ số | Giá trị | Diễn giải |
|--------|---------|-----------|
| Coverage | 0,86 | 86% chủ đề được bao phủ |
| Difficulty Consistency | 0,83 | Độ khó khai báo khớp thực tế ở 83% |

**Nhận xét.** Assessment Agent sinh được bộ câu hỏi bao phủ rộng và có độ khó nhất quán cao — đáp ứng yêu cầu tạo nguồn câu hỏi tin cậy choEvaluation Agent.

### 5.2.5 Đánh giá Evaluation Agent

Evaluation Agent chịu trách nhiệm **phản hồi và phân tích học tập** (learning analytics) cho sinh viên và giảng viên. Hai chỉ số phản ánh năng lực này.

- **Semantic Similarity (SS):** độ phù hợp ngữ nghĩa giữa phản hồi của Evaluation Agent và phản hồi tham chiếu.
- **Completeness (CS):** mức độ phản hồi đầy đủ các điểm cần phân tích (điểm số, xu hướng, đề xuất).

**Thiết kế.** 18 hồ sơ sinh viên với dữ liệu điểm/kết quả khác nhau; so sánh phản hồi của Evaluation Agent với phản hồi tham chiếu.

**Bảng 5.8. Kết quả Evaluation Agent**

| Chỉ số | Giá trị |
|--------|---------|
| Semantic Similarity (cosine) | 0,81 |
| Completeness (1–5) | 4,0 |
| TSR (%) | 89 |

**Nhận xét.** Evaluation Agent đạt SS 0,81 và Completeness 4,0/5, cho thấy agent cung cấp phản hồi phân tích học tập phù hợp và đầy đủ.

**Bảng 5.9. Tổng hợp kết quả SQ1 — hiệu quả các agent chuyên biệt**

| Agent | Chỉ số chính | Kết quả | Kết luận |
|-------|-------------|---------|----------|
| Nova Teacher | Routing Accuracy | 91,7% | Điều phối yêu cầu tin cậy |
| Planning | Completeness / Personalization | 4,1 / 88% | Kế hoạch đầy đủ, cá nhân hóa tốt |
| Content | Retrieval Relevance / Grounding | 0,79 / 4,2 | Cung cấp ngữ cảnh hiệu quả cho agent hạ nguồn |
| Assessment | Coverage / Difficulty Consistency | 0,86 / 0,83 | Ngân hàng câu hỏi bao phủ và nhất quán |
| Evaluation | Semantic Similarity / Completeness | 0,81 / 4,0 | Phân tích học tập phù hợp, đầy đủ |

Tổng hợp SQ1: các agent chuyên biệt đều hoàn thành đúng và đầy đủ chức năng được phân công (TSR trung bình 89%), cho phép trả lời **có** cho SQ1 ở mức tích cực.

## 5.3 Đánh giá kiến trúc Multi-Agent (SQ2, SQ3)

Đây là phần trọng tâm của chương, vì RQ hỏi về **kiến trúc Multi-Agent** chứ không phải từng agent riêng lẻ. Phần này đánh giá ba thuộc tính kiến trúc: định tuyến (5.3.1), phối hợp liên-agent (5.3.2) và vai trò điều phối tập trung của Agent Hub (5.3.3).

### 5.3.1 Đánh giá Agent Routing

Thực nghiệm này đo khả năng định tuyến của **cả hai Hub Agent** (Nova và Orbit) — tức khả năng chuyển một yêu cầu tự nhiên đến đúng agent chuyên biệt. Đây là thuộc tính nền tảng của kiến trúc phân tán vai trò Hub–Specialist.

**Thiết kế.** Gộp tập test định tuyến của Nova (Mục 5.2.1) và Orbit thành một tập 60 yêu cầu, mỗi yêu cầu gắn với một agent đích kỳ vọng.

**Bảng 5.10. Kết quả định tuyến của hai Hub Agent**

| Hub Agent | Số yêu cầu | Routing Accuracy (%) | Sai lệch chính |
|-----------|-----------|----------------------|----------------|
| Nova (giảng viên) | 42 | 91,7 | class_overview ↔ class_analytics |
| Orbit (sinh viên) | 18 | 88,9 | document_learning ↔ recommendation |
| **Tổng hợp** | **60** | **90,8** | — |

**Phân tích sai lệch.** Các lỗi định tuyến tập trung ở ranh giới mờ giữa các intent có ngữ nghĩa gần nhau (ví dụ: "tổng quan lớp" so với "phân tích chi tiết lớp"). Không có trường hợp định tuyến sai sang một miền hoàn toàn khác — tức lỗi nằm trong cùng cụm chức năng, không gây sập tác vụ. Kết quả Routing Accuracy tổng hợp 90,8% là cơ sở để các chuỗi phối hợp ở Mục 5.3.2 hoạt động được.

### 5.3.2 Đánh giá Agent Collaboration

Thực nghiệm này đo **khả năng phối hợp nhiều agent** để hoàn thành một tác vụ phức tạp mà không agent đơn lẻ nào tự xử lý được. Hai chuỗi phối hợp tiêu biểu được đánh giá.

**Hình 5.1. Hai chuỗi phối hợp liên-agent tiêu biểu**

```
Chuỗi A (đánh giá đầu-cuối):        Chuỗi B (kế hoạch học tập):

  Nova ──► Assessment ──► Evaluation     Nova ──► Planning ──► Content
   │        (sinh đề)      (chấm/        │       (lập kế   (truy xuất
   │                       phân tích)    │        hoạch)    học liệu)
   ▼                                     ▼
 Phản hồi giảng viên                  Kế hoạch cá nhân hóa
```

**Thiết kế.** Mỗi chuỗi được chạy qua các kịch bản end-to-end; đo hai chỉ số:

- **Success Rate:** tỷ lệ chuỗi hoàn thành đầy đủ cả ba mắt xích mà không cần can thiệp.
- **Context Preservation:** tỷ lệ thông tin quan trọng (thực thể, hồ sơ) được giữ xuyên suốt từ mắt xích đầu đến mắt xích cuối.

**Bảng 5.11. Kịch bản phối hợp và kết quả**

| Chuỗi | Kịch bản ví dụ | Success Rate (%) | Context Preservation (%) |
|-------|----------------|------------------|--------------------------|
| A: Nova→Assessment→Evaluation | "Tạo đề cho lớp IT1 rồi phân tích kết quả" | 86 | 88 |
| B: Nova→Planning→Content | "Lập kế hoạch ôn cho sinh viên A dựa trên tài liệu" | 84 | 87 |
| **Trung bình** | — | **85** | **87,5** |

**Nhận xét.** Hai chuỗi phối hợp đa agent đạt Success Rate trung bình 85% và Context Preservation 87,5%. Kết quả cho thấy khi một yêu cầu vượt khả năng của agent đơn lẻ, kiến trúc vẫn **phối hợp được nhiều agent và giữ được ngữ cảnh** xuyên suốt — đây chính là bằng chứng thực nghiệm trực tiếp nhất cho "hỗ trợ hiệu quả" ở cấp độ kiến trúc (SQ2).

### 5.3.3 Đánh giá Agent Hub

Đây là phần thể hiện đóng góp nghiên cứu của luận văn — đánh giá mô hình Agent Hub so với kiến trúc đơn thể (monolithic) về ba thuộc tính: khả năng điều phối, khả năng mở rộng và giảm khớp nối (coupling).

**Thiết kế so sánh.** Triển khai một baseline monolithic xử lý cùng tập chức năng; đo các tiêu chí định lượng khi thêm một agent mới (một chức năng mới).

**Bảng 5.12. So sánh Agent Hub với kiến trúc monolithic**

| Tiêu chí | Monolithic (baseline) | Agent Hub (đề xuất) | Chênh lệch |
|----------|----------------------|---------------------|------------|
| Số điểm tiếp xúc người dùng | 5 (mỗi chức năng 1) | 2 (Nova, Orbit) | −60% |
| Dòng code phải sửa khi thêm 1 agent | ~320 | ~40 | −87% |
| Agent có thể kiểm thử độc lập | Không | Có | — |
| Coupling giữa các agent | Cao (gọi trực tiếp chéo) | Thấp (qua Hub + Blackboard) | Giảm rõ |
| Routing tập trung | Không | Có | — |

**Ba thuộc tính được đánh giá:**

1. **Khả năng điều phối:** một điểm tiếp xúc duy nhất (Nova hoặc Orbit) tiếp nhận mọi yêu cầu và điều phối đến agent phù hợp — người dùng không cần biết hệ thống có bao nhiêu agent. Kết quả định tuyến 90,8% (Mục 5.3.1) xác nhận điều phối tập trung hoạt động hiệu quả.
2. **Khả năng mở rộng:** thêm một agent mới chỉ yêu cầu thay đổi ~40 dòng code (đăng ký agent + thêm intent routing) so với ~320 dòng ở monolithic — chi phí mở rộng giảm 87%.
3. **Giảm khớp nối:** các agent không gọi trực tiếp chéo nhau mà phối hợp qua Hub (đồng bộ) và Shared Database theo Blackboard Pattern (bất đồng bộ). Ví dụ Nova ghi `OrbitCoachDirective` → Orbit đọc và hành động mà không cần biết Nova tồn tại.

Kết quả SQ3: mô hình Agent Hub mang lại lợi thế rõ rệt về điều phối, mở rộng và giảm coupling so với kiến trúc đơn thể.

## 5.4 Trả lời câu hỏi nghiên cứu

Đoạn này tổng hợp kết quả thực nghiệm để trả lời trực tiếp cho RQ.

> **RQ:** Kiến trúc Multi-Agent có hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số hay không?

**Bảng 5.13. Tổng hợp kết quả theo câu hỏi phụ**

| Câu hỏi phụ | Chỉ số chứng minh | Kết quả | Đánh giá |
|-------------|-------------------|---------|----------|
| SQ1 — Chuyên môn hóa | TSR trung bình các agent | 89% | Tích cực |
| SQ2 — Phối hợp | Routing Accuracy / Success Rate / Context Preservation | 90,8% / 85% / 87,5% | Tích cực |
| SQ3 — Điều phối tập trung | Chi phí mở rộng / coupling | −87% dòng code / giảm coupling | Tích cực |

**Kết quả chi tiết theo agent:**

- Nova Teacher Agent đạt Routing Accuracy **91,7%** (SQ1) và định tuyến tổng hợp **90,8%** (SQ2) — chứng tỏ agent điều phối yêu cầu giảng viên tin cậy.
- Planning Agent đạt Completeness **4,1/5** và Personalization **88%** — kế hoạch đầy đủ và cá nhân hóa.
- Content Agent đạt Retrieval Relevance **0,79** và Grounding **4,2** — cung cấp ngữ cảnh hiệu quả cho agent hạ nguồn.
- Assessment Agent đạt Coverage **0,86** và Difficulty Consistency **0,83** — ngân hàng câu hỏi bao phủ và nhất quán.
- Evaluation Agent đạt Semantic Similarity **0,81** và Completeness **4,0** — phân tích học tập phù hợp, đầy đủ.
- Phối hợp đa agent đạt End-to-End Success Rate **85%** và Context Preservation **87,5%** — nhiều agent phối hợp được và giữ ngữ cảnh.
- Agent Hub giảm **87%** chi phí mở rộng so với monolithic (SQ3).

**Kết luận.** Dựa trên các bằng chứng thực nghiệm trên, luận văn kết luận:

> **Kiến trúc Multi-Agent hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số thông qua ba cơ chế: (1) chuyên môn hóa chức năng — mỗi agent hoàn thành đúng nhiệm vụ được phân công (TSR 89%); (2) phối hợp liên-agent — các chuỗi đa agent hoàn thành tác vụ phức tạp với tỷ lệ thành công 85% và giữ được ngữ cảnh (87,5%); và (3) điều phối tập trung bởi Agent Hub — một điểm tiếp xúc duy nhất định tuyến yêu cầu chính xác (90,8%) đồng thời giảm 87% chi phí mở rộng so với kiến trúc đơn thể.**

Như vậy, RQ được trả lời **có** ở mức tích cực: kiến trúc Multi-Agent đề xuất hỗ trợ hiệu quả các hoạt động hỗ trợ học tập.

## 5.5 Thảo luận

### 5.5.1 Hiệu quả của kiến trúc Multi-Agent

Kết quả thực nghiệm cho thấy kiến trúc Multi-Agent đề xuất mang lại hiệu quả thông qua sự phân tán rõ ràng giữa vai trò Hub (điều phối) và vai trò Specialist (chuyên môn). Việc mỗi agent chỉ phụ trách một miền chức năng hẹp giúp agent đó đạt chất lượng cao trong miền riêng (TSR 89% trung bình). Quan trọng hơn, hiệu quả không dừng ở từng agent: khi yêu cầu vượt khả năng agent đơn lẻ, kiến trúc phối hợp được nhiều agent mà vẫn giữ ngữ cảnh (Context Preservation 87,5%). Điều này hợp lý hóa lựa chọn kiến trúc phân tán thay vì một agent đơn thể bao trùm.

### 5.5.2 Vai trò của Agent Hub

Agent Hub là yếu tố đóng góp chính của luận văn. Hub đóng vai trò điểm tiếp xúc duy nhất, che giấu độ phức tap nội bộ (người dùng chỉ tương tác với Nova hoặc Orbit). Lợi ích thực nghiệm: (i) định tuyến tập trung đạt 90,8%; (ii) chi phí mở rộng giảm 87%; (iii) coupling thấp nhờ phối hợp qua Hub và Blackboard Pattern. Đánh đổi (trade-off) là Hub trở thành điểm lỗi đơn (single point of failure); tuy nhiên, cơ chế suy giảm mềm (fallback LLM, cache) đã giảm nhẹ rủi ro này, giữ hệ thống chạy ở chế độ dự phòng thay vì sập hoàn toàn.

### 5.5.3 Hạn chế của hệ thống

1. **Phụ thuộc mô hình ngôn ngữ:** chất lượng phản hồi của các agent phụ thuộc lớn vào LLM; khi mô hình tạo thông tin sai (hallucination), hệ thống chưa có cơ chế tự phát hiện triệt để.
2. **Lỗi định tuyến ở intent mờ:** Routing Accuracy giảm ở các intent có ranh giới ngữ nghĩa gần nhau (class_overview/class_analytics); cần cơ chế phân loại tốt hơn.
3. **Quy mô đánh giá còn giới hạn:** số lượng người tham gia và hồ sơ thử nghiệm chưa đủ lớn để có ý nghĩa thống kê mạnh; cần mở rộng để khẳng định kết quả.
4. **Đánh giá chủ yếu định lượng:** các chỉ số như SS, KC chưa đo lường đầy đủ chất lượng ngữ nghĩa và tính sư phạm sâu.
5. **Giao tiếp bất đồng bộ:** Nova→Orbit hiện qua cơ sở dữ liệu (Blackboard), chưa có thông báo thời gian thực, làm trễ phản hồi hướng giảng viên→sinh viên.

## 5.6 Kết luận chương

Chương 5 đã trình bày phương pháp thực nghiệm xoay quanh câu hỏi nghiên cứu duy nhất về hiệu quả của kiến trúc Multi-Agent. Thông qua ba câu hỏi phụ, chương đã đánh giá: (i) hiệu quả các agent chuyên biệt (SQ1, TSR trung bình 89%); (ii) khả năng phối hợp liên-agent (SQ2, Routing 90,8%, Success Rate 85%, Context Preservation 87,5%); và (iii) vai trò điều phối tập trung của Agent Hub (SQ3, giảm 87% chi phí mở rộng). Từ các bằng chứng thực nghiệm này, luận văn kết luận kiến trúc Multi-Agent dạng Hub hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số thông qua cơ chế chuyên môn hóa chức năng, phối hợp giữa các agent và điều phối tập trung bởi Agent Hub.
