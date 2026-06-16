# CHƯƠNG 5 – THỰC NGHIỆM VÀ ĐÁNH GIÁ KIẾN TRÚC MULTI-AGENT

## 5.1 Thiết kế thực nghiệm

### 5.1.1 Câu hỏi nghiên cứu và chiến lược phân rã

Luận văn đặt ra một câu hỏi nghiên cứu trung tâm nhằm kiểm định giá trị thực tiễn của kiến trúc được đề xuất: liệu kiến trúc Multi-Agent có hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số hay không. Đây là một câu hỏi mang tính khái quát cao, và nếu để nguyên ở dạng đó, khái niệm "hỗ trợ hiệu quả" sẽ là một khái niệm trừu tượng khó đo lường, phụ thuộc vào cảm nhận chủ quan của người đánh giá. Để tránh rủi ro đó, luận văn tiến hành một bước vận hành hóa (operationalization) có hệ thống, trong đó khái niệm trừu tượng nói trên được phân rã thành các biến số định lượng có thể quan sát và đo được trong môi trường phòng thí nghiệm.

Quá trình phân rã được thực hiện theo hai tầng thực chứng có mối quan hệ biện chứng với nhau. Tầng thứ nhất là hiệu quả ở cấp độ tác nhân đơn lẻ (Specialist Level), nhằm khảo sát từng agent khi được cô lập trong một phạm vi nghiệp vụ hẹp; mục tiêu là xác nhận xem mỗi agent có hoàn thành đúng và đầy đủ chức năng sư phạm được giao hay không. Tầng thứ hai là hiệu quả ở cấp độ kiến trúc hệ thống (Architectural Level), nhằm khảo sát năng lực điều phối khi một tác vụ phức tạp đòi hỏi sự tham gia đồng thời của nhiều tác nhân, nơi kiến trúc phải chứng minh được tính chính xác trong định tuyến, tính liên tục của ngữ cảnh và khả năng hoàn thành tác vụ đầu-cuối (end-to-end).

Hai tầng trên được cụ thể hóa bằng hai câu hỏi nghiên cứu phụ, đóng vai trò là các chiều không gian kiểm thử cho toàn bộ chương. SQ1 đặt ra vấn đề chuyên môn hóa chức năng, tức là xem các agent chuyên biệt có thực hiện đúng và đầy đủ chức năng được phân công hay không. SQ2 đặt ra vấn đề phối hợp liên agent, tức là xem khi một yêu cầu đòi hỏi nhiều agent phối hợp thì kiến trúc có định tuyến đúng agent và giữ được ngữ cảnh xuyên suốt chuỗi xử lý không. Cách phân rã này đảm bảo mỗi thực nghiệm đều ánh xạ trực tiếp tới một câu hỏi phụ, và kết quả tổng hợp tại Mục 5.4 hội tụ về câu hỏi nghiên cứu trung tâm.

Cần nhấn mạnh một lựa chọn phương pháp luận quan trọng: các thực nghiệm trong chương này xoay quanh hành vi của agent với tư cách là các đơn vị điều phối và chuyên môn hóa, chứ không đánh giá các công nghệ nền tảng như mô hình ngôn ngữ lớn hay công nghệ nhận dạng ký tự quang học như những đối tượng độc lập, vì câu hỏi nghiên cứu hỏi về kiến trúc và các cơ chế điều phối của nó.

### 5.1.2 Môi trường thực nghiệm và bộ dữ liệu

Việc lựa chọn môi trường thực nghiệm được thực hiện theo nguyên tắc sao cho kết quả có khả năng lặp lại và sát với điều kiện vận hành thực tế của một nền tảng giáo dục số. Toàn bộ hệ thống được triển khai trên máy trạm cá nhân chạy hệ điều hành Windows 11, với bộ xử lý trung hạng và mười sáu gigabyte bộ nhớ, kết nối Internet qua đường truyền băng thông rộng. Lựa chọn cấu hình này có chủ đích, nhằm minh chứng hệ thống không đòi hỏi hạ tầng chuyên dụng đắt tiền mà vẫn vận hành được trong điều kiện của một nhóm nghiên cứu nhỏ. Bảng 5.1 tóm tắt cấu hình môi trường.

**Bảng 5.1. Môi trường phần cứng và phần mềm**

| Thành phần | Cấu hình |
|-----------|----------|
| Hệ điều hành | Windows 11 Pro 10.0.22631 |
| Bộ xử lý | Intel Core i7 / AMD Ryzen 7 |
| RAM | 16 GB |
| Mạng | Internet ≥ 10 Mbps |
| Backend | FastAPI 0.100+, Uvicorn (Python 3.10+) |
| Frontend | Next.js 16, React 19, TypeScript 5 |
| Cơ sở dữ liệu | SQLite 3.x (dev) / PostgreSQL (prod) |
| Kho vector | ChromaDB |
| LLM chính | Groq — llama-3.3-70b-versatile |
| LLM dự phòng | Google Gemini Flash |

Bộ dữ liệu thực nghiệm được xây dựng để phản ánh một kịch bản giảng dạy thực tế có cấu trúc hoàn chỉnh, bao gồm đủ cả hai vai trò người dùng là giảng viên và sinh viên. Việc đảm bảo sự hiện diện của cả hai vai trò là quan trọng, vì hai Hub Agent của hệ thống được thiết kế để phục vụ hai nhóm người dùng khác nhau, và nếu thiếu một trong hai thì việc đánh giá năng lực điều phối sẽ không trọn vẹn. Bảng 5.2 trình bày quy mô bộ dữ liệu.

**Bảng 5.2. Bộ dữ liệu thực nghiệm**

| Loại dữ liệu | Quy mô | Vai trò trong đánh giá |
|-------------|---------|------------------------|
| Môn học | 3 | Miền tri thức cho Content, Assessment |
| Lớp học | 5 | Đối tượng điều phối của Nova |
| Giảng viên | 3 | Người dùng Nova Agent |
| Sinh viên | 35 | Người dùng Orbit Agent |
| Tài liệu học liệu | 12 | Đầu vào cho Content Agent |
| Câu hỏi trong ngân hàng | 48 | Đầu ra của Assessment Agent |
| Bản ghi đánh giá | 56 | Đầu ra của Evaluation Agent |
| Kế hoạch học tập | 35 | Đầu ra của Planning Agent |

Mỗi bản ghi được gắn với đúng agent chịu trách nhiệm xử lý, và đối với các tác vụ sinh văn bản, mỗi ca kiểm thử được xây dựng kèm một đáp án tham chiếu cùng tập từ khóa kỳ vọng, tạo cơ sở cho việc đánh giá định lượng.

### 5.1.3 Bộ chỉ số đánh giá

Việc lựa chọn chỉ số đánh giá tuân theo hai tiêu chí: phải gắn trực tiếp với câu hỏi nghiên cứu, và phải súc tích để tránh hiện tượng người đọc bị ngợp trước khối lượng chỉ số quá lớn. Do đó, thay vì sử dụng hàng chục chỉ số phức tạp, luận văn quyết định chỉ giữ lại năm chỉ số cốt lõi, nhưng được chọn sao cho bao quát cả hai khía cạnh cần đo lường là chất lượng hoàn thành và chi phí thực thi. Bảng 5.3 định nghĩa năm chỉ số và vai trò của chúng.

**Bảng 5.3. Năm chỉ số đánh giá và vai trò**

| Chỉ số | Ký hiệu | Định nghĩa | Phục vụ |
|--------|--------|-----------|---------|
| Task Success Rate | TSR | Tỷ lệ tác vụ hoàn thành đúng trên tổng số | SQ1 |
| Pass Rate | PR | Tỷ lệ tác vụ đạt ngưỡng chất lượng quy định | SQ1 |
| End-to-End Success Rate | E2E | Tỷ lệ chuỗi đa agent hoàn thành đầy đủ | SQ2 |
| Latency | L | Thời gian xử lý một yêu cầu (ms) | Chi phí |
| Token Consumption | TC | Tổng token (prompt + completion) | Chi phí |

Task Success Rate đo độ tin cậy cơ bản, Pass Rate đo cả việc kết quả có đủ tốt để sử dụng, còn End-to-End Success Rate có ý nghĩa đặc biệt quan trọng vì nó phản ánh trực tiếp khả năng phối hợp liên agent. Hai chỉ số còn lại đảm bảo kiến trúc không chỉ hiệu quả về chức năng mà còn khả thi về chi phí, một điều kiện cần để kết quả nghiên cứu có giá trị ứng dụng.

## 5.2 Đánh giá agent chuyên biệt — SQ1

Phần này trả lời câu hỏi phụ thứ nhất. Mỗi agent được đánh giá trên năm chỉ số ở Bảng 5.3. Bảy đối tượng được khảo sát bao gồm năm agent chuyên biệt (Evaluation, Assessment, Planning, Tutor, Content) và hai Hub Agent (Nova, Orbit). Đối với từng agent, luận văn trình bày trước một số mẫu ca kiểm thử cụ thể, sau đó đến bảng kết quả định lượng và phần phân tích.

### 5.2.1 Evaluation Agent

Evaluation Agent đảm nhiệm chức năng phân tích tiến độ học tập, bao gồm xác định môn yếu, phát hiện tài liệu quá hạn và gợi ý thứ tự ôn tập. Đây là agent cung cấp cho người học bức tranh tổng quan về năng lực hiện tại. Bảng 5.4 trình bày ba mẫu ca kiểm thử đại diện cho ba lớp nghiệp vụ mà agent phải xử lý.

**Bảng 5.4. Mẫu ca kiểm thử Evaluation Agent**

| # | Đầu vào (câu hỏi sinh viên) | Đáp án tham chiếu kỳ vọng |
|---|------------------------------|---------------------------|
| 1 | "Môn nào tôi đang yếu nhất?" | Chỉ môn có điểm TB thấp nhất + đề xuất ôn |
| 2 | "Tôi có tài liệu nào quá hạn chưa?" | Liệt kê tài liệu trễ hạn, sắp đến hạn |
| 3 | "Tài liệu nào nên ôn trước kỳ thi?" | Ưu tiên tài liệu điểm thấp, chưa đạt |

**Bảng 5.5. Kết quả Evaluation Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,89 | 0,88 | 1.420 | 680 |

Phân tích cho thấy Evaluation Agent đạt Task Success Rate 0,89, nghĩa là gần chín mươi phần trăm yêu cầu phân tích được hoàn thành đúng. Pass Rate 0,88 cho thấy phần lớn kết quả không chỉ hoàn thành mà còn đạt ngưỡng chất lượng. Độ trễ 1.420 mili giây nằm trong vùng chấp nhận được cho tương tác thời gian thực, và mức tiêu thụ token 680 là hợp lý. Nhược điểm nhỏ quan sát được là ở các tình huống biên khi dữ liệu điểm có tính mâu thuẫn nội bộ, agent đôi khi đưa ra phán đoán chưa hoàn toàn nhất quán.

### 5.2.2 Assessment Agent

Assessment Agent sinh đề kiểm tra và xây dựng ngân hàng câu hỏi, đóng vai trò cung cấp nguyên liệu đầu vào cho toàn bộ quy trình đánh giá. Chất lượng của agent này ảnh hưởng trực tiếp đến chất lượng phía sau, do đó yêu cầu không chỉ là tạo được câu hỏi mà còn phải đảm bảo độ phủ chủ đề và độ nhất quán độ khó. Bảng 5.6 trình bày ba mẫu ca kiểm thử.

**Bảng 5.6. Mẫu ca kiểm thử Assessment Agent**

| # | Đầu vào | Đáp án tham chiếu kỳ vọng |
|---|----------|---------------------------|
| 1 | "Tạo 10 câu trắc nghiệm môn LPTHDT" | 10 câu MCQ đủ content, options, đáp án, giải thích |
| 2 | "Sinh đề 15 câu từ tài liệu OOP.pdf" | 15 câu gắn đúng source_file |
| 3 | "Tạo 2 mã đề khó cho môn CSDL" | 2 bộ câu hỏi độ khó nhất quán |

**Bảng 5.7. Kết quả Assessment Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,91 | 0,89 | 2.180 | 1.240 |

Assessment Agent đạt Task Success Rate cao nhất nhóm agent chuyên biệt, ở mức 0,91, và Pass Rate 0,89. Độ trễ 2.180 mili giây cao hơn Evaluation một chút nhưng vẫn chấp nhận được, vì việc sinh câu hỏi bản chất đòi hỏi nhiều thao tác xử lý hơn. Mức tiêu thụ token 1.240 phản ánh khối lượng văn bản đầu ra lớn đặc trưng của tác vụ sinh đề. Kết quả khẳng định agent cung cấp nguồn câu hỏi đầy đủ và đáng tin cậy, sẵn sàng phục vụ Evaluation ở các chuỗi phối hợp.

### 5.2.3 Planning Agent

Planning Agent tạo và điều chỉnh kế hoạch học tập cá nhân hóa. Đặc điểm nổi bật là agent phải phản hồi được các yêu cầu điều chỉnh linh hoạt như ưu tiên một môn lên trước hay thêm bớt tài liệu. Bảng 5.8 trình bày ba mẫu ca kiểm thử bao phủ cả chế độ tạo mới và chế độ điều chỉnh.

**Bảng 5.8. Mẫu ca kiểm thử Planning Agent**

| # | Đầu vào | Đáp án tham chiếu kỳ vọng |
|---|----------|---------------------------|
| 1 | "Tạo kế hoạch học mới cho tôi" | Lộ trình theo tài liệu chưa qua |
| 2 | "Ưu tiên môn LPTHDT học trước tuần này" | LPTHDT đẩy lên đầu, môn khác lùi |
| 3 | "Thêm 2 tài liệu CSDL vào lịch tuần này" | 2 tài liệu CSDL xuất hiện trong plan tuần |

**Bảng 5.9. Kết quả Planning Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,88 | 0,87 | 1.950 | 720 |

Planning Agent đạt TSR 0,88 và PR 0,87, với độ trễ 1.950 mili giây và token 720. Agent tạo và điều chỉnh kế hoạch đúng theo yêu cầu, đặc biệt phản hồi tốt với các lệnh "đẩy lên trước" và "thêm tài liệu". Đây là kết quả có ý nghĩa quan trọng, vì năng lực điều chỉnh kế hoạch của Planning là nền tảng cho cơ chế phối hợp liên agent theo kiểu Nova giao chỉ thị rồi Orbit đốc thúc, sẽ phân tích ở Mục 5.3.

### 5.2.4 Tutor Agent

Tutor Agent, còn gọi là Adaptive Agent, đóng vai trò gia sư thích ứng, trả lời câu hỏi dựa trên học liệu qua cơ chế truy xuất tăng cường thế hệ. Đặc trưng là câu trả lời phải có căn cứ vào tài liệu cụ thể chứ không được suy diễn tự do. Bảng 5.10 trình bày ba mẫu ca kiểm thử từ tóm tắt đến giải thích và gợi ý ôn.

**Bảng 5.10. Mẫu ca kiểm thử Tutor Agent**

| # | Đầu vào | Đáp án tham chiếu kỳ vọng |
|---|----------|---------------------------|
| 1 | "Tóm tắt tài liệu này" | Tóm tắt nội dung chính của tài liệu đang mở |
| 2 | "Giải thích khái niệm đóng gói (encapsulation)" | Giải thích căn cứ tài liệu, có ví dụ |
| 3 | "Phần nào trong tài liệu cần ôn lại?" | Chỉ các phần trọng tâm chưa nắm vững |

**Bảng 5.11. Kết quả Tutor Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,87 | 0,85 | 2.540 | 980 |

Tutor Agent đạt TSR 0,87 và PR 0,85, thấp hơn một chút so với các agent sinh văn bản thuần túy, phản ánh đúng thực tế tác vụ gia sư dựa trên tài liệu khó hơn do đòi hỏi truy xuất và tổng hợp chính xác. Độ trễ 2.540 mili giây cao nhất nhóm vì cơ chế truy xuất cần thêm bước tìm đoạn tài liệu liên quan. Nhìn chung, agent hoàn thành tốt vai trò gia sư dựa trên học liệu.

### 5.2.5 Content Agent

Content Agent xử lý học liệu và truy xuất ngữ cảnh cho các agent hạ nguồn. Khác với các agent trực tiếp tạo sản phẩm cho người dùng, Content Agent thường hoạt động ở lớp nền. Việc đánh giá không nhằm đo công nghệ truy xuất nói chung mà nhằm trả lời câu hỏi hẹp: agent có cung cấp đủ ngữ cảnh chính xác cho agent hạ nguồn không. Bảng 5.12 trình bày ba mẫu ca kiểm thử mô phỏng ba lớp hoạt động.

**Bảng 5.12. Mẫu ca kiểm thử Content Agent**

| # | Đầu vào | Đáp án tham chiếu kỳ vọng |
|---|----------|---------------------------|
| 1 | Tài liệu OOP.pdf (upload) | Chunking + lưu ChromaDB + nhận diện môn |
| 2 | "Tài liệu này thuộc môn gì?" | Trả về môn học tương ứng |
| 3 | Truy vấn "kế thừa trong OOP" | Top-K đoạn chứa nội dung kế thừa |

**Bảng 5.13. Kết quả Content Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,90 | 0,88 | 1.180 | 540 |

Content Agent đạt TSR 0,90 và PR 0,88, với độ trễ thấp nhất nhóm chỉ 1.180 mili giây, do các thao tác xử lý học liệu về cơ bản là phép tính cục bộ nhanh. Mức tiêu thụ token 540 cũng thấp nhất. Kết quả khẳng định agent xử lý học liệu nhanh và cung cấp ngữ cảnh chính xác cho các agent hạ nguồn.

### 5.2.6 Nova Agent (Hub giảng viên)

Nova Agent là một trong hai Hub Agent, đóng vai trò điều phối mọi yêu cầu từ giảng viên. Nova phải phân loại ý định, trích xuất thực thể như tên lớp hay môn học, và định tuyến đến đúng agent chuyên biệt. Đặc biệt, Nova còn điều khiển giao diện qua cơ chế siêu dữ liệu hành động, mở tab hoặc biểu đồ tương ứng. Bảng 5.14 trình bày ba mẫu ca kiểm thử.

**Bảng 5.14. Mẫu ca kiểm thử Nova Agent**

| # | Đầu vào (câu hỏi giảng viên) | Kỳ vọng: ý định + hành động giao diện |
|---|-------------------------------|----------------------------------------|
| 1 | "Tình hình lớp IT1 học thế nào?" | Tổng quan lớp + mở biểu đồ |
| 2 | "Tạo đề 20 câu cho môn LPTHDT" | Tạo đề + mở tab đề |
| 3 | "Chỉ ra nhóm sinh viên yếu nhất lớp IT1" | Phân tích chi tiết + mở tab phân tích |

**Bảng 5.15. Kết quả Nova Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,93 | 0,92 | 1.560 | 860 |

Nova đạt TSR 0,93 và PR 0,92, cao nhất toàn bộ nhóm agent, phản ánh đúng thực tế các Hub Agent xử lý yêu cầu ở lớp điều phối vốn có tính cấu trúc cao hơn. Sai lệch quan sát được chủ yếu nằm ở ranh giới mờ giữa hai ý định gần nhau là tổng quan lớp và phân tích chi tiết lớp, tuy nhiên sai lệch này không gây sập tác vụ vì cả hai đều dẫn đến xử lý trong cùng cụm chức năng.

### 5.2.7 Orbit Agent (Hub sinh viên)

Orbit Agent là Hub Agent thứ hai, điều phối yêu cầu từ sinh viên. Orbit tiếp nhận câu hỏi, phân tích ý định, định tuyến đến agent chuyên biệt, đồng thời xây dựng phản hồi cá nhân hóa nhờ hồ sơ ngữ cảnh động chứa điểm số, thời gian học và chủ đề yếu. Bảng 5.16 trình bày ba mẫu ca kiểm thử định tuyến.

**Bảng 5.16. Mẫu ca kiểm thử Orbit Agent**

| # | Đầu vào (câu hỏi sinh viên) | Kỳ vọng: agent định tuyến đến |
|---|------------------------------|-------------------------------|
| 1 | "Kết quả học tập của tôi thế nào?" | Evaluation Agent |
| 2 | "Sắp xếp lại lịch học tuần này" | Planning Agent |
| 3 | "Tóm tắt tài liệu môn này" | Tutor / Content Agent |

**Bảng 5.17. Kết quả Orbit Agent**

| Chỉ số | TSR | PR | Latency (ms) | Token |
|--------|------|------|--------------|-------|
| Giá trị | 0,91 | 0,90 | 1.340 | 760 |

Orbit định tuyến chính xác và tạo phản hồi cá nhân hóa rõ rệt nhờ cơ chế hồ sơ ngữ cảnh động.

### 5.2.8 Tổng hợp kết quả SQ1

Bảng 5.18 tổng hợp kết quả của cả bảy agent theo năm chỉ số.

**Bảng 5.18. Tổng hợp kết quả các agent chuyên biệt**

| Agent | TSR | PR | Latency (ms) | Token | Đánh giá |
|-------|------|------|--------------|-------|----------|
| Evaluation | 0,89 | 0,88 | 1.420 | 680 | Tích cực |
| Assessment | 0,91 | 0,89 | 2.180 | 1.240 | Tích cực |
| Planning | 0,88 | 0,87 | 1.950 | 720 | Tích cực |
| Tutor | 0,87 | 0,85 | 2.540 | 980 | Tích cực |
| Content | 0,90 | 0,88 | 1.180 | 540 | Tích cực |
| Nova (Hub) | 0,93 | 0,92 | 1.560 | 860 | Tích cực |
| Orbit (Hub) | 0,91 | 0,90 | 1.340 | 760 | Tích cực |
| **Trung bình** | **0,90** | **0,88** | **1.881** | **826** | — |

Phân tích bảng tổng hợp cho phép rút ra hai nhận xét quan trọng. Thứ nhất, Task Success Rate trung bình là 0,90 và không có agent nào dưới 0,87, nghĩa là toàn bộ các agent chuyên biệt đều hoàn thành đúng chức năng ở mức cao và ổn định. Thứ hai, hai Hub Agent (Nova 0,93, Orbit 0,91) đạt TSR cao hơn phần lớn các agent chuyên biệt, phản ánh đúng đặc thù lớp điều phối có tính cấu trúc cao. Câu trả lời cho SQ1 do đó là có, ở mức tích cực.

## 5.3 Đánh giá kiến trúc — SQ2

Đây là phần trọng tâm, vì câu hỏi nghiên cứu hỏi về kiến trúc Multi-Agent chứ không phải từng agent riêng lẻ. Phần này đánh giá ba thuộc tính theo trình tự từ đơn giản đến phức tạp: năng lực định tuyến, năng lực phối hợp liên agent, và vai trò điều phối tập trung của Agent Hub. Chỉ số trọng tâm ở phần này là End-to-End Success Rate.

### 5.3.1 Đánh giá năng lực định tuyến

Thực nghiệm đo khả năng định tuyến của cả hai Hub Agent, tức là khả năng chuyển một yêu cầu tự nhiên đến đúng agent chuyên biệt. Đây là thuộc tính nền tảng, vì nếu định tuyến sai ngay từ đầu thì mọi cơ chế phối hợp phía sau đều không có ý nghĩa. Bảng 5.19 trình bày bốn mẫu ca kiểm thử định tuyến đại diện.

**Bảng 5.19. Mẫu ca kiểm thử định tuyến**

| # | Yêu cầu | Hub | Agent đích kỳ vọng | Kết quả |
|---|---------|-----|--------------------|---------|
| 1 | "Kết quả học của tôi" | Orbit | Evaluation | Đúng |
| 2 | "Sắp xếp lại lịch học" | Orbit | Planning | Đúng |
| 3 | "Tạo đề cho lớp IT1" | Nova | Assessment | Đúng |
| 4 | "Tóm tắt tài liệu" | Orbit | Tutor/Content | Đúng |

**Bảng 5.20. Kết quả định tuyến hai Hub Agent**

| Hub Agent | Số yêu cầu | Định tuyến đúng | Tỷ lệ |
|-----------|-----------|-----------------|-------|
| Nova (giảng viên) | 42 | 39 | 0,93 |
| Orbit (sinh viên) | 18 | 16 | 0,89 |
| **Tổng hợp** | **60** | **55** | **0,92** |

Một nhận xét quan trọng từ phân tích các ca sai là: toàn bộ các lỗi định tuyến đều tập trung ở ranh giới mờ giữa các ý định có ngữ nghĩa gần nhau, chẳng hạn ranh giới giữa tổng quan lớp và phân tích chi tiết lớp. Quan trọng hơn, không có trường hợp nào agent bị định tuyến sang một miền hoàn toàn khác. Điều này có ý nghĩa thực tiễn lớn, vì ngay cả khi xảy ra sai lệch, lỗi vẫn nằm trong cùng một cụm chức năng, do đó người dùng vẫn nhận được phản hồi có liên quan và tác vụ không bị sập.

### 5.3.2 Đánh giá năng lực phối hợp liên agent

Nếu định tuyến đo hành vi của từng Hub độc lập, thì phối hợp liên agent đo hành vi của toàn bộ kiến trúc khi nhiều agent cùng làm việc. Đây là phần khó nhất và ý nghĩa nhất, vì nó trả lời trực tiếp liệu kiến trúc Multi-Agent có thực sự cần thiết. Nếu một agent đơn thể giải được mọi tác vụ thì không có lý do xây dựng kiến trúc phức tạp nhiều agent. Do đó, thực nghiệm tập trung vào các tác vụ mà về bản chất không agent đơn lẻ nào tự xử lý được.

Hai chuỗi phối hợp tiêu biểu được lựa chọn để đánh giá. Chuỗi A là chuỗi đánh giá đầu-cuối: Nova tiếp nhận yêu cầu giảng viên, chuyển sang Assessment sinh đề, rồi sang Evaluation chấm và phân tích. Chuỗi B là chuỗi kế hoạch học tập: Nova tiếp nhận, chuyển sang Planning lập kế hoạch, rồi sang Content truy xuất học liệu. Hình 5.1 minh họa hai chuỗi.

**Hình 5.1. Hai chuỗi phối hợp liên agent tiêu biểu**

```
Chuỗi A (đánh giá đầu-cuối):        Chuỗi B (kế hoạch học tập):

  Nova ──► Assessment ──► Evaluation     Nova ──► Planning ──► Content
   │        (sinh đề)     (chấm/         │       (lập kế   (truy xuất
   │                       phân tích)    │        hoạch)    học liệu)
   ▼                                     ▼
 Phản hồi giảng viên                  Kế hoạch cá nhân hóa
```

Để đo lường, luận văn sử dụng End-to-End Success Rate, định nghĩa là tỷ lệ chuỗi hoàn thành đầy đủ mọi mắt xích mà không cần can thiệp. Bảng 5.21 trình bày bốn mẫu kịch bản đầu-cuối.

**Bảng 5.21. Mẫu kịch bản phối hợp đầu-cuối**

| # | Kịch bản | Chuỗi agent | E2E kỳ vọng |
|---|----------|-------------|-------------|
| 1 | "Tạo đề cho lớp IT1 rồi phân tích kết quả" | Nova → Assessment → Evaluation | Đạt |
| 2 | "Lập kế hoạch ôn cho sinh viên A theo tài liệu" | Nova → Planning → Content | Đạt |
| 3 | "Tìm môn kém rồi tạo đề ôn cho lớp IT1" | Nova → Evaluation → Assessment | Đạt |
| 4 | "Điều chỉnh kế hoạch theo kết quả của tôi" | Orbit → Evaluation → Planning | Đạt |

**Bảng 5.22. Kết quả phối hợp liên agent**

| Chuỗi | Kịch bản | E2E | Latency (ms) | Token |
|-------|----------|-----|--------------|-------|
| Nova → Assessment → Evaluation | Tạo đề rồi phân tích | 0,86 | 5.120 | 2.860 |
| Nova → Planning → Content | Lập kế hoạch theo tài liệu | 0,84 | 4.860 | 2.180 |
| Nova → Evaluation → Assessment | Tìm môn yếu rồi tạo đề | 0,85 | 5.340 | 2.940 |
| Orbit → Evaluation → Planning | Điều chỉnh kế hoạch theo kết quả | 0,83 | 4.640 | 2.320 |
| **Trung bình** | — | **0,845** | **4.990** | **2.575** |

Phân tích kết quả cho thấy bốn chuỗi phối hợp đạt E2E trung bình 0,845, dao động trong khoảng hẹp từ 0,83 đến 0,86. Độ trễ trung bình của một chuỗi ba bước là khoảng 4.990 mili giây, và token trung bình khoảng 2.575; cần lưu ý đây là chi phí của toàn bộ chuỗi gồm ba lần gọi agent, nên khi quy về mỗi bước thì hoàn toàn hợp lý. Ý nghĩa của kết quả này rất quan trọng: nó chứng minh khi một yêu cầu vượt khả năng của bất kỳ agent đơn lẻ nào, kiến trúc vẫn phối hợp nhiều agent để hoàn thành tác vụ với tỷ lệ đầu-cuối hơn tám mươi tư phần trăm. Đây là bằng chứng thực nghiệm mạnh mẽ nhất cho việc kiến trúc Multi-Agent hỗ trợ hiệu quả hoạt động học tập ở cấp độ kiến trúc.

### 5.3.3 Đánh giá vai trò điều phối tập trung của Agent Hub

Phần này trình bày đóng góp nghiên cứu chính của luận văn, đó là đánh giá mô hình Agent Hub so với kiến trúc đơn thể truyền thống. Câu hỏi đặt ra là liệu việc tổ chức theo mô hình có trung tâm điều phối có mang lại lợi ích thực sự về điều phối, mở rộng và giảm khớp nối hay không. Để trả lời, luận văn triển khai một đường cơ sở đơn thể xử lý cùng tập chức năng, rồi đo các tiêu chí khi thêm một agent mới. Bảng 5.23 trình bày kết quả so sánh.

**Bảng 5.23. So sánh Agent Hub với kiến trúc monolithic**

| Tiêu chí | Monolithic | Agent Hub | Chênh lệch |
|----------|-----------|-----------|------------|
| Số điểm tiếp xúc người dùng | 5 | 2 (Nova, Orbit) | −60% |
| Dòng code phải sửa khi thêm 1 agent | ~320 | ~40 | −87% |
| Agent có thể kiểm thử độc lập | Không | Có | — |
| Coupling giữa các agent | Cao (gọi chéo) | Thấp (Hub + Blackboard) | Giảm rõ |
| Routing tập trung | Không | Có | — |

Phân tích bảng so sánh cho phép rút ra ba kết luận về ba thuộc tính cốt lõi. Thứ nhất, về khả năng điều phối, một điểm tiếp xúc duy nhất tiếp nhận mọi yêu cầu và đạt tỷ lệ định tuyến 0,92 (từ Bảng 5.20). Thứ hai, về khả năng mở rộng, chi phí thêm agent giảm tám mươi bảy phần trăm, từ khoảng ba trăm hai mươi dòng xuống khoảng bốn mươi dòng, một lợi thế có ý nghĩa lớn cho khả năng phát triển lâu dài. Thứ ba, về giảm khớp nối, các agent phối hợp qua Hub theo cơ chế đồng bộ và qua cơ sở dữ liệu dùng chung theo mô hình Blackboard ở cơ chế bất đồng bộ, nghĩa là Nova có thể ghi một chỉ thị học tập vào cơ sở dữ liệu còn Orbit đọc chỉ thị đó khi đốc thúc sinh viên, hai agent hoàn toàn không cần đồng bộ thời gian hay biết về sự tồn tại của nhau.

## 5.4 Trả lời câu hỏi nghiên cứu

Sau khi đã có kết quả chi tiết ở hai mục trước, phần này tổng hợp bằng chứng để trả lời trực tiếp câu hỏi nghiên cứu trung tâm. Bảng 5.24 tổng hợp kết quả theo hai câu hỏi phụ.

**Bảng 5.24. Tổng hợp kết quả theo câu hỏi phụ**

| Câu hỏi phụ | Chỉ số chứng minh | Kết quả | Đánh giá |
|-------------|-------------------|---------|----------|
| SQ1 — Chuyên môn hóa | TSR / PR trung bình | 0,90 / 0,88 | Tích cực |
| SQ2 — Phối hợp | E2E / Routing | 0,845 / 0,92 | Tích cực |
| (Mở rộng kiến trúc) | Chi phí thêm agent | −87% dòng code | Tích cực |

Đối với SQ1, bằng chứng là TSR trung bình 0,90 và PR trung bình 0,88, cả hai đều cao và ổn định, không agent nào dưới ngưỡng chấp nhận. Câu trả lời cho SQ1 là tích cực. Đối với SQ2, bằng chứng là E2E 0,845 và tỷ lệ định tuyến 0,92, cho thấy kiến trúc không chỉ định tuyến đúng mà còn hoàn thành đầy đủ chuỗi phức tạp. Câu trả lời cho SQ2 cũng tích cực.

Từ các bằng chứng trên, luận văn kết luận: kiến trúc Multi-Agent hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số thông qua ba cơ chế. Cơ chế thứ nhất là chuyên môn hóa chức năng, mỗi agent hoàn thành đúng nhiệm vụ với TSR trung bình 0,90 và PR 0,88. Cơ chế thứ hai là phối hợp liên agent, các chuỗi đa agent hoàn thành tác vụ phức tạp với E2E 0,845. Cơ chế thứ ba là điều phối tập trung bởi Agent Hub, một điểm tiếp xúc duy nhất định tuyến chính xác 0,92, đồng thời giảm tám mươi bảy phần trăm chi phí mở rộng so với kiến trúc đơn thể, với chi phí thực thi hợp lý (độ trễ khoảng năm giây, khoảng 2.575 token cho một chuỗi ba bước). Câu hỏi nghiên cứu trung tâm được trả lời là có.

## 5.5 Thảo luận

### 5.5.1 Về hiệu quả của kiến trúc Multi-Agent

Kết quả cho thấy kiến trúc Multi-Agent mang lại hiệu quả thông qua sự phân tách rõ ràng giữa vai trò điều phối do các Hub Agent đảm nhận và vai trò chuyên môn do các agent chuyên biệt đảm nhận. Khi mỗi agent chỉ phụ trách một miền hẹp, agent đó đạt chất lượng cao trong chính miền của mình, được phản ánh qua TSR trung bình 0,90. Quan trọng hơn, hiệu quả không dừng ở từng agent riêng lẻ: khi yêu cầu vượt khả năng của bất kỳ agent đơn lẻ nào, kiến trúc vẫn phối hợp nhiều agent để hoàn thành tác vụ với E2E 0,845. Điều này hợp lý hóa lựa chọn kiến trúc phân tán thay vì agent đơn thể bao trùm, vì nếu dùng agent đơn thể, các tác vụ phức tạp đòi hỏi nhiều năng lực chuyên môn khác nhau không thể thực hiện được với chất lượng tương đương.

### 5.5.2 Về vai trò của Agent Hub

Agent Hub là đóng góp chính của luận văn. Hub đóng vai trò điểm tiếp xúc duy nhất, che giấu phần nội bộ phức tạp của hệ thống. Lợi ích thể hiện qua ba phương diện: định tuyến tập trung đạt 0,92; chi phí mở rộng giảm tám mươi bảy phần trăm; mức độ khớp nối thấp nhờ phối hợp qua Hub và Blackboard. Tuy nhiên, luận văn cũng công bố một đánh đổi: việc Hub đóng vai trò trung tâm đồng nghĩa nó trở thành điểm lỗi đơn. Để giảm nhẹ, hệ thống trang bị cơ chế suy giảm mềm — khi LLM chính gặp giới hạn tốc độ thì chuyển sang mô hình dự phòng, khi thành phần lưu trữ gặp lỗi thì chuyển sang đáp ứng dựa trên mẫu cố định, nhờ đó tính sẵn sàng được duy trì.

### 5.5.3 Hạn chế và đe dọa tính hiệu lực

Một nghiên cứu nghiêm túc cần công bố giới hạn, và luận văn trình bày ba nhóm đe dọa tính hiệu lực. Nhóm thứ nhất là hiệu lực nội: chất lượng phản hồi phụ thuộc lớn vào LLM, và khi mô hình tạo thông tin sai (hallucination), hệ thống chưa có cơ chế tự phát hiện triệt để; việc đánh giá có thể chịu thiên kiến người chấm, được giảm nhẹ qua quy trình nhiều người chấm độc lập. Nhóm thứ hai là hiệu lực ngoại: quy mô đánh giá còn giới hạn (35 sinh viên, 12 tài liệu), chưa đủ lớn để khái quát hóa mạnh. Nhóm thứ ba là hiệu lực cấu trúc: bộ năm chỉ số tập trung vào chất lượng hoàn thành và chi phí, chưa đo trực tiếp chất lượng sư phạm sâu, một phần được bù qua xây dựng ca kiểm thử có đánh giá con người. Ngoài ra, giao tiếp Nova→Orbit hiện bất đồng bộ qua cơ sở dữ liệu, chưa có thông báo thời gian thực, làm trễ một số phản hồi hướng giảng viên→sinh viên.

## 5.6 Kết luận chương

Chương năm đã trình bày phương pháp thực nghiệm và kết quả đánh giá kiến trúc Multi-Agent, xoay quanh một câu hỏi nghiên cứu duy nhất về hiệu quả hỗ trợ học tập, với bộ năm chỉ số cốt lõi (TSR, PR, E2E, Latency, Token) bao quát cả chất lượng hoàn thành và chi phí thực thi. Thông qua hai câu hỏi phụ, chương đánh giá kiến trúc ở hai cấp độ. Ở cấp độ tác nhân đơn lẻ, các agent chuyên biệt hoàn thành đúng chức năng với TSR trung bình 0,90. Ở cấp độ kiến trúc, khả năng phối hợp đạt E2E 0,845 và tỷ lệ định tuyến 0,92, chứng minh kiến trúc hoàn thành được các tác vụ phức tạp mà không agent đơn lẻ nào tự xử lý được. Đóng góp nghiên cứu, mô hình Agent Hub, giảm tám mươi bảy phần trăm chi phí mở rộng so với kiến trúc đơn thể. Từ các bằng chứng, luận văn kết luận kiến trúc Multi-Agent dạng Hub hỗ trợ hiệu quả các hoạt động hỗ trợ học tập trong môi trường giáo dục số thông qua cơ chế chuyên môn hóa chức năng, phối hợp liên agent, và điều phối tập trung bởi Agent Hub.
