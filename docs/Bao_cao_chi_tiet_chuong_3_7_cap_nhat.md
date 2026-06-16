# Báo cáo chi tiết nội dung sản phẩm AI Personalized Learning Platform

> Ghi chú biên soạn: Nội dung dưới đây đã được cập nhật theo yêu cầu mới của đề tài, trong đó **cơ sở dữ liệu quan hệ sử dụng PostgreSQL** thay cho SQLite trong phần báo cáo, **loại bỏ Orbit Agent** khỏi mô tả kiến trúc hệ thống, và phần triển khai được trình bày theo hướng **triển khai web thực tế trên Docker**.

# Chương 3: Phân tích hệ thống

## 3.1 Phân tích yêu cầu hệ thống

Hệ thống AI Personalized Learning Platform được xây dựng nhằm giải quyết đồng thời nhiều bài toán trong môi trường giáo dục số hiện nay: quản lý học liệu theo lớp học và môn học, hỗ trợ học tập cá nhân hóa cho sinh viên, hỗ trợ giảng viên trong công tác tạo đề – đánh giá – theo dõi tiến độ học tập, đồng thời số hóa quy trình kiểm tra trên giấy thông qua OCR/OMR. Không giống các hệ thống LMS truyền thống chỉ dừng lại ở quản lý nội dung và nộp bài, hệ thống này tích hợp thêm lớp trí tuệ nhân tạo để nâng cao mức độ tương tác, tự động hóa và thích ứng với năng lực thực tế của từng người học.

Từ bài toán thực tế đó, yêu cầu hệ thống được chia thành hai nhóm lớn: yêu cầu chức năng và yêu cầu phi chức năng.

### 3.1.1 Yêu cầu chức năng

Hệ thống cần đáp ứng các nhóm chức năng cốt lõi sau:

**(1) Quản lý người dùng và xác thực truy cập**
- Cho phép đăng nhập, đăng xuất và phân quyền theo vai trò như quản trị viên, giảng viên và sinh viên.
- Cho phép quản trị viên quản lý tài khoản, danh sách giáo viên, sinh viên, và giám sát hoạt động chung của hệ thống.
- Cho phép giảng viên quản lý lớp học do mình phụ trách.
- Cho phép sinh viên tham gia lớp học, truy cập học liệu và sử dụng các tính năng học tập cá nhân hóa.

**(2) Quản lý môn học và lớp học**
- Cho phép tạo môn học độc lập với biểu tượng, mô tả và cấu trúc dữ liệu riêng.
- Cho phép tạo lớp học thuộc một môn học, sinh mã lớp và quản lý danh sách thành viên.
- Cho phép sinh viên tham gia lớp bằng mã lớp.
- Cho phép giảng viên xem danh sách lớp, danh sách sinh viên, tiến độ học và kết quả học tập theo lớp.

**(3) Quản lý học liệu số**
- Cho phép giảng viên tải lên tài liệu học tập ở nhiều định dạng như PDF, DOCX, PPTX, TXT.
- Cho phép phân loại tài liệu theo môn học và lớp học.
- Cho phép công bố hoặc ẩn học liệu đối với sinh viên.
- Cho phép hệ thống phân tích nhanh tài liệu để hỗ trợ gợi ý môn học và nạp dữ liệu vào pipeline RAG.

**(4) Hệ thống hỏi đáp và trợ giảng AI**
- Cung cấp Nova Teacher Agent hỗ trợ giảng viên hỏi nhanh về môn học, lớp học, tài liệu, ngân hàng câu hỏi, tình hình học tập và các tác vụ quản trị học thuật.
- Cung cấp Adaptive Learning Agent hỗ trợ sinh viên học theo tài liệu đang mở, trả lời câu hỏi bám sát ngữ cảnh học liệu.
- Cho phép hệ thống sử dụng dữ liệu truy xuất từ vector database để tạo phản hồi chính xác hơn theo môn học và tài liệu.

**(5) Cá nhân hóa học tập**
- Phân tích điểm số, lịch sử làm bài, mức độ hoàn thành học liệu và thời gian học để tạo learner profile.
- Sinh lộ trình học tổng thể theo mức độ hiện tại của người học.
- Tạo kế hoạch học ngắn hạn theo tài liệu ưu tiên, tài liệu chưa học, tài liệu điểm thấp hoặc chưa hoàn thành.
- Cho phép điều chỉnh kế hoạch học tập khi người học yêu cầu đổi ưu tiên hoặc tăng/giảm tải học trong tuần.

**(6) Sinh câu hỏi, bài kiểm tra và đánh giá học tập**
- Tạo bộ câu hỏi trắc nghiệm từ học liệu và question bank.
- Cho phép sinh đề kiểm tra theo môn, chủ đề, mức độ, số lượng câu hỏi.
- Chấm kết quả bài làm và phân tích tiến độ học theo lịch sử điểm.
- Giải thích lỗi sai ở từng câu hỏi để hỗ trợ cải thiện năng lực.

**(7) OCR/OMR cho đề thi giấy**
- Sinh bộ đề thi trắc nghiệm dạng Word kèm nhiều mã đề.
- Sinh file Excel đáp án tương ứng.
- Sinh phiếu trả lời OMR cho sinh viên điền mã sinh viên, mã đề và đáp án.
- Nhận file PDF chứa bài làm được scan, xử lý OMR để nhận diện đáp án và tính điểm tự động.
- Nhận diện vùng họ tên sinh viên bằng OCR để hỗ trợ tra soát kết quả.

**(8) Dashboard và learning analytics**
- Theo dõi điểm trung bình, xu hướng tiến bộ, tỷ lệ hoàn thành học liệu, thời lượng học tập và mức độ tương tác với AI.
- Cung cấp các chỉ số phục vụ giảng viên đánh giá lớp học và sinh viên đánh giá bản thân.

### 3.1.2 Yêu cầu phi chức năng

Ngoài yêu cầu chức năng, hệ thống cần thỏa mãn các yêu cầu phi chức năng quan trọng để có thể triển khai trong bối cảnh web thực tế.

**(1) Hiệu năng**
- Phản hồi API thông thường cần nhanh, ổn định và đáp ứng tốt với số lượng người dùng đồng thời vừa phải đến lớn.
- Các tác vụ nặng như tạo đề, truy xuất RAG, OCR/OMR phải được tối ưu để không làm treo toàn bộ hệ thống.
- Kết nối cơ sở dữ liệu cần hỗ trợ connection pooling để phục vụ nhiều request đồng thời.

**(2) Khả năng mở rộng**
- Kiến trúc phải hỗ trợ tách lớp frontend, backend API, cơ sở dữ liệu, Redis và vector store.
- Hệ thống phải triển khai được nhiều instance backend/frontend sau load balancer.
- Dữ liệu dùng chung như PostgreSQL, ChromaDB và thư mục tệp tạm cần có cơ chế lưu trữ dùng chung giữa các container.

**(3) Tính sẵn sàng và ổn định**
- Hệ thống phải hoạt động ổn định trong môi trường Docker.
- Có health check cho các dịch vụ lõi như PostgreSQL, Redis, backend.
- Các agent AI cần có cơ chế fallback khi dịch vụ LLM hoặc vector store tạm thời không khả dụng.

**(4) Bảo mật**
- Xác thực tài khoản bằng mật khẩu băm.
- Phân quyền truy cập dữ liệu theo vai trò người dùng.
- Không cho phép sinh viên truy cập học liệu không thuộc lớp của mình hoặc chưa được công bố.
- Hạn chế lộ dữ liệu nhạy cảm thông qua API và tách riêng biến môi trường khi triển khai.

**(5) Tính bảo trì**
- Mã nguồn được tổ chức thành các module rõ ràng: API, agent, service, RAG, database, frontend.
- Hệ thống dễ bổ sung agent mới, thêm API mới hoặc thay đổi chiến lược triển khai.
- Cấu hình được tách qua biến môi trường giúp dễ chuyển đổi giữa môi trường phát triển và production.

**(6) Tính đúng đắn học thuật**
- Câu trả lời AI phải bám sát tài liệu, hạn chế suy diễn ngoài ngữ cảnh.
- Câu hỏi sinh tự động phải có kiểm tra tính hợp lệ, độ đa dạng và chất lượng nhiễu.
- Kết quả OCR phải có khả năng lưu dấu vết debug để phục vụ tra soát khi nhận diện sai.

## 3.2 Phân tích nghiệp vụ hệ thống

### 3.2.1 Quản lý người dùng và phân quyền

Nghiệp vụ quản lý người dùng là tầng nền tảng của hệ thống. Có ba nhóm vai trò chính gồm quản trị viên, giảng viên và sinh viên.

- **Quản trị viên** chịu trách nhiệm khởi tạo hệ thống, quản lý tài khoản, quản lý giáo viên và giám sát tài nguyên chung.
- **Giảng viên** phụ trách môn học, lớp học, học liệu, ngân hàng câu hỏi, hoạt động đánh giá và theo dõi tiến độ sinh viên.
- **Sinh viên** là đối tượng sử dụng học liệu, làm bài đánh giá, nhận tư vấn học tập cá nhân hóa và theo dõi kế hoạch học của mình.

Nghiệp vụ phân quyền đòi hỏi dữ liệu phải được ràng buộc chặt chẽ: lớp học thuộc một môn học; tài liệu gắn với lớp học và môn học; sinh viên chỉ thấy tài liệu của các lớp mình tham gia; giảng viên chỉ thao tác trên dữ liệu thuộc phạm vi giảng dạy hoặc quản trị được cấp quyền.

### 3.2.2 Quản lý môn học và lớp học

Môn học là thực thể nghiệp vụ trung tâm, đóng vai trò liên kết nhiều cấu phần như tài liệu, lộ trình học, learner profile, ngân hàng câu hỏi, thống kê đánh giá và kết quả OCR. Mỗi lớp học là một triển khai cụ thể của môn học cho một nhóm người học.

Nghiệp vụ bao gồm:
- tạo môn học mới;
- cập nhật mô tả và biểu tượng môn học;
- tạo lớp học thuộc một môn;
- sinh mã lớp để sinh viên tham gia;
- gán giảng viên phụ trách;
- thống kê số sinh viên, kết quả học tập và mức độ hoàn thành học liệu theo từng lớp.

Điểm đặc thù của hệ thống là lớp học không chỉ là nơi gom người dùng mà còn là đơn vị gắn kết học liệu, đề thi, question bank và learning analytics.

### 3.2.3 Quản lý học liệu và question bank

Giảng viên tải học liệu lên hệ thống theo từng lớp và môn học. Khi tài liệu được tải lên, hệ thống xử lý theo hai hướng song song:
- lưu metadata tài liệu vào cơ sở dữ liệu PostgreSQL;
- trích xuất nội dung để cắt đoạn, embedding và lưu vào ChromaDB phục vụ RAG.

Từ học liệu đã nạp, hệ thống tiếp tục sinh question bank phục vụ làm bài kiểm tra trực tuyến và sinh đề OCR. Do đó, question bank vừa là một tài nguyên đánh giá, vừa là lớp dữ liệu trung gian giữa học liệu và các tác vụ khảo thí.

Nghiệp vụ này giúp hệ thống giảm phụ thuộc vào việc giảng viên phải nhập tay toàn bộ câu hỏi, đồng thời vẫn cho phép tái sử dụng bộ câu hỏi nhiều lần trong nhiều luồng khác nhau.

### 3.2.4 Hỗ trợ học tập cá nhân hóa

Đây là nghiệp vụ tạo nên giá trị khác biệt của hệ thống. Thay vì áp dụng cùng một lộ trình cho mọi người học, hệ thống quan sát dữ liệu thực tế như:
- số lần làm bài;
- điểm gần nhất theo tài liệu;
- tài liệu nào đã hoàn thành hoặc còn dở dang;
- thời gian đăng nhập và thời lượng học;
- lịch sử tương tác với tác vụ AI;
- tiến độ theo môn và theo từng tài liệu.

Dựa trên các dữ liệu này, hệ thống xây dựng learner profile, sinh roadmap tổng thể theo trình độ hiện tại và tạo kế hoạch học ngắn hạn có thứ tự ưu tiên. Những tài liệu chưa học hoặc có điểm thấp sẽ được đẩy lên trước; tài liệu đã hoàn thành tốt có thể được đưa về cuối làm tài liệu ôn tập.

### 3.2.5 Sinh đề thi và đánh giá học tập

Hệ thống hỗ trợ hai nhóm nghiệp vụ đánh giá:

- **Đánh giá trực tuyến**, trong đó Assessment Agent tạo câu hỏi và bài kiểm tra từ question bank hoặc từ học liệu đã truy xuất qua RAG.
- **Đánh giá trên giấy**, trong đó OCR Exam Generator tạo bộ đề Word, Excel đáp án và phiếu trả lời OMR; sau đó Test OCR Service chấm tự động từ file PDF bài làm.

Kết quả đánh giá không chỉ trả về điểm số mà còn được lưu vào hệ thống để phục vụ Evaluation Agent, learner profile, learning analytics và planning agent.

## 3.3 Phân tích luồng xử lý hệ thống

### 3.3.1 Luồng upload và xử lý tài liệu

Luồng upload tài liệu bắt đầu từ giao diện web của giảng viên. Sau khi người dùng chọn lớp học, môn học và tệp nguồn, frontend gửi tệp qua API upload. Backend tiếp nhận file, lưu vào hệ thống tệp, tạo bản ghi tài liệu trong PostgreSQL, sau đó gọi Content Agent để:
- nhận diện hoặc xác nhận môn học;
- đọc nội dung văn bản từ PDF/DOCX/PPTX/TXT;
- cắt nhỏ tài liệu thành các chunk;
- gắn metadata như môn học và file nguồn;
- ghi vector embedding vào ChromaDB.

Kết quả của luồng này là hệ thống có đồng thời dữ liệu quan hệ trong PostgreSQL và dữ liệu ngữ nghĩa trong vector database, sẵn sàng cho RAG và sinh câu hỏi.

### 3.3.2 Luồng retrieval và truy xuất tri thức

Khi người dùng đặt câu hỏi về một tài liệu hoặc một môn học, backend xác định ngữ cảnh hiện hành: môn học nào, tài liệu nào, lớp học nào. Từ đó hệ thống xây dựng truy vấn retrieval tương ứng để lấy các đoạn nội dung liên quan nhất từ ChromaDB.

Các đoạn văn bản truy xuất được sau đó sẽ được làm sạch, loại bỏ nội dung hành chính hoặc nhiễu, rồi ghép vào prompt dưới vai trò ngữ cảnh tri thức. Đây là bước quan trọng để Large Language Model sinh câu trả lời bám tài liệu hơn thay vì trả lời chung chung.

### 3.3.3 Luồng hội thoại AI

Luồng hội thoại AI khác nhau tùy nhóm người dùng:
- với giảng viên, Nova Teacher Agent tiếp nhận câu hỏi, phân loại intent, trích xuất thực thể, dùng context memory để hiểu yêu cầu trước đó, rồi điều hướng sang nghiệp vụ phù hợp;
- với sinh viên, Adaptive Learning Agent tiếp nhận câu hỏi dựa trên tài liệu đang mở, roadmap hiện tại và nội dung retrieval từ RAG để tạo phản hồi.

Luồng hội thoại gồm các bước: tiếp nhận yêu cầu → nhận diện ý định → lấy ngữ cảnh phiên → truy xuất dữ liệu cần thiết → gọi LLM → lưu lại lịch sử/hoặc cập nhật trạng thái nghiệp vụ → trả phản hồi về frontend.

### 3.3.4 Luồng assessment và learning analytics

Khi sinh viên làm bài đánh giá, hệ thống ghi nhận điểm số, số câu đúng, số câu sai, thời gian làm bài và tài liệu liên quan. Các dữ liệu này được tổng hợp vào nhiều bảng như assessment history, student document evaluation, student document score history và learner profile.

Từ dữ liệu tích lũy đó, hệ thống tính toán các chỉ số analytics như:
- điểm trung bình theo môn;
- điểm gần nhất theo tài liệu;
- xu hướng cải thiện hay suy giảm;
- số tài liệu quá hạn hoặc hoàn thành trễ hạn;
- thời lượng đăng nhập và số phiên học;
- mức độ hoàn thành kế hoạch học tập.

Các chỉ số này vừa phục vụ dashboard trực quan, vừa là dữ liệu đầu vào cho Evaluation Agent và Planning Agent.

# Chương 4: Thiết kế hệ thống AI Agent và Personalized Learning

## 4.1 Kiến trúc AI Agent trong hệ thống

### 4.1.1 Kiến trúc Multi-Agent System

Hệ thống được thiết kế theo mô hình multi-agent, trong đó mỗi agent đảm nhiệm một vai trò chuyên biệt thay vì gom tất cả logic AI vào một khối duy nhất. Cách tiếp cận này giúp hệ thống rõ ràng hơn về trách nhiệm, dễ mở rộng, dễ kiểm thử và phù hợp với bài toán giáo dục nhiều ngữ cảnh.

Các agent chính gồm:
- **Nova Teacher Agent**: hỗ trợ giảng viên trong các tác vụ học thuật và quản trị lớp học;
- **Adaptive Learning Agent**: hỗ trợ học tập cá nhân hóa cho sinh viên;
- **Planning Agent**: tạo và điều chỉnh kế hoạch học tập;
- **Evaluation Agent**: đánh giá tiến độ và phân tích kết quả học;
- **Assessment Agent**: sinh câu hỏi, bài kiểm tra và question bank;
- **Content Agent**: xử lý học liệu đầu vào và nạp dữ liệu vào RAG.

Điểm cốt lõi của kiến trúc này là **tách theo chức năng nghiệp vụ**, không tách chỉ theo mô hình AI. Nhờ đó, mỗi agent có thể dùng nguồn dữ liệu, prompt và luồng xử lý phù hợp nhất với nhiệm vụ của mình.

### 4.1.2 Agent Orchestration và Workflow

Trong hệ thống, orchestration không được xây dựng như một engine workflow phức tạp độc lập, mà được hiện thực theo hướng điều phối ở tầng backend API và service. Luồng điều phối điển hình như sau:

1. Frontend gửi yêu cầu đến endpoint tương ứng.
2. FastAPI router xác định loại nghiệp vụ.
3. Backend khởi tạo agent phù hợp với request và session database hiện tại.
4. Agent truy vấn dữ liệu từ PostgreSQL, ChromaDB hoặc Redis nếu cần.
5. Agent gọi LLM để suy luận hoặc sinh nội dung.
6. Kết quả được kiểm tra, chuẩn hóa, lưu trạng thái và trả về cho frontend.

Ví dụ:
- luồng tải tài liệu: API Upload → Content Agent → Vector Store;
- luồng học tập cá nhân hóa: API Adaptive → Adaptive Agent → RAG + learner profile;
- luồng lập kế hoạch: API Planning → Planning Agent → student document evaluation + learning plan;
- luồng chấm điểm và phân tích: API Evaluation → Evaluation Agent → assessment history + score history;
- luồng OCR: API Test OCR → OCRExamGeneratorService hoặc TestOCRService → OMR/OCR pipeline.

### 4.1.3 Conversational Memory và Context Routing

Một thách thức quan trọng của agent giáo dục là duy trì được ngữ cảnh hội thoại. Hệ thống giải quyết bài toán này bằng cơ chế conversational memory và context routing.

- **Conversational memory** lưu lịch sử trao đổi gần đây, các subject/class/student được nhắc tới gần nhất, intent cuối cùng và các trường dữ liệu còn thiếu cần hỏi tiếp.
- **Context routing** dựa vào intent classifier và action router để quyết định câu hỏi hiện tại nên đi vào nhánh nào: hỏi thông tin lớp, hỏi tài liệu, yêu cầu sinh đề, hay thao tác CRUD học thuật.

Trong môi trường phát triển nhỏ, memory có thể lưu cục bộ trong bộ nhớ. Khi triển khai production trên Docker, hệ thống hỗ trợ **Redis** để chia sẻ memory giữa nhiều backend instance sau load balancer. Đây là điểm rất quan trọng để tránh mất ngữ cảnh khi request tiếp theo đi sang một container backend khác.

## 4.2 Thiết kế các AI Agent

### 4.2.1 Nova Teacher Agent

Nova Teacher Agent là agent phục vụ giảng viên. Vai trò của agent này không phải là dạy học trực tiếp, mà là hỗ trợ truy vấn học thuật và thao tác điều hướng thông minh trong hệ thống.

Các năng lực chính của Nova Teacher Agent gồm:
- hiểu câu hỏi tự nhiên của giảng viên về môn học, lớp học, sinh viên, tài liệu và đề thi;
- phân tích intent như xem thông tin môn, tổng quan lớp, phân tích lớp, xem sinh viên, xem tài liệu, sinh đề;
- trích xuất thực thể như tên môn, tên lớp, tên sinh viên, số câu hỏi, số mã đề, độ khó;
- sử dụng context từ memory để hỗ trợ hội thoại nhiều lượt;
- trả lại không chỉ câu trả lời mà còn gợi ý hành động tiếp theo trên giao diện.

Điểm mạnh của agent này là kết hợp giữa **rule-based routing**, **LLM-based intent analysis**, **cache intent**, và **fallback** khi LLM phản hồi chậm. Thiết kế này giúp hệ thống thực dụng hơn, không lệ thuộc hoàn toàn vào mô hình sinh ngôn ngữ.

### 4.2.2 Adaptive Learning Agent

Adaptive Learning Agent là agent trung tâm cho trải nghiệm học tập cá nhân hóa của sinh viên. Agent này hoạt động dựa trên ba nguồn thông tin chính:
- learner profile và kết quả học trong PostgreSQL;
- tài liệu đang mở hoặc tài liệu thuộc môn đang học;
- nội dung retrieval từ ChromaDB.

Agent đảm nhiệm các nhiệm vụ:
- sinh roadmap tổng thể theo trình độ hiện tại;
- biên tập/tóm tắt học liệu theo ngôn ngữ dễ hiểu;
- trả lời câu hỏi của sinh viên bám vào đúng tài liệu đang mở;
- sinh câu hỏi trắc nghiệm theo từng phiên học;
- đề xuất nội dung ưu tiên theo các tài liệu có điểm thấp hoặc chưa học.

Thiết kế này giúp trải nghiệm học của sinh viên sát dữ liệu thực tế hơn so với chatbot chung chung.

### 4.2.3 Planning Agent

Planning Agent chịu trách nhiệm xây dựng kế hoạch học tập ngắn hạn. Không chỉ dựa trên lịch cố định, agent này xét đến:
- tài liệu mà sinh viên đã có điểm hay chưa;
- tài liệu nào có điểm dưới ngưỡng;
- tài liệu nào chưa hoàn thành;
- khoảng cách giữa các buổi học;
- yêu cầu điều chỉnh của sinh viên như ưu tiên môn nào trước, dời môn nào sau, thêm số tài liệu cần học trong ngày hoặc trong tuần.

Kết quả của Planning Agent được lưu thành `student_learning_plans` và `student_learning_plan_steps`, giúp hệ thống có một thực thể kế hoạch cụ thể để dashboard và evaluation cùng sử dụng.

### 4.2.4 Evaluation Agent

Evaluation Agent đóng vai trò phản ánh tiến độ học tập. Đây là agent tổng hợp dữ liệu lịch sử thay vì sinh nội dung mới từ tài liệu. Agent truy xuất:
- assessment history;
- score history theo tài liệu;
- trạng thái hoàn thành học liệu;
- kế hoạch học hiện tại;
- số liệu đăng nhập và tổng thời lượng học;
- thống kê theo môn.

Từ đó agent trả lời những câu hỏi như:
- môn nào là môn yếu nhất;
- tài liệu nào đang quá hạn;
- xu hướng điểm gần đây tăng hay giảm;
- cần ôn lại tài liệu nào trước.

Evaluation Agent còn tạo lời nhận xét ngắn mang tính cá nhân hóa dựa trên điểm kiểm tra, nỗ lực học tập và tiến bộ so với trước đó.

### 4.2.5 Assessment Agent

Assessment Agent là agent chuyên về khảo thí. Agent này thực hiện:
- trích xuất concept từ học liệu đã retrieval;
- sinh câu hỏi trắc nghiệm theo nhiều mức Bloom như remember, understand, apply, analyze;
- kiểm tra chất lượng câu hỏi và các phương án nhiễu;
- tiền sinh question bank cho từng tài liệu;
- tạo quiz theo tài liệu hoặc theo môn;
- phân tích câu trả lời sai của sinh viên.

Thiết kế của agent có nhiều lớp fallback: nếu LLM chính không dùng được thì dùng mô hình khác hoặc sinh câu hỏi theo heuristics cục bộ. Điều này đảm bảo hệ thống không bị chặn hoàn toàn khi dịch vụ AI bên ngoài gián đoạn.

### 4.2.6 Content Agent

Content Agent là tầng đầu vào của toàn bộ hệ sinh thái AI. Agent này xử lý file học liệu, đọc nội dung, nhận diện môn học và nạp chunk vào vector store.

Vai trò của Content Agent gồm:
- hỗ trợ nhiều định dạng học liệu;
- lấy mẫu văn bản để gợi ý môn học;
- gán metadata subject/source cho chunk;
- chia đoạn văn bản bằng text splitter;
- đẩy document chunks vào ChromaDB.

Có thể xem Content Agent là cầu nối giữa dữ liệu tệp thô và các agent phía sau như Adaptive Agent hoặc Assessment Agent.

## 4.3 Thiết kế hệ thống RAG

### 4.3.1 Pipeline xử lý tài liệu

Pipeline RAG được thiết kế theo trình tự:
1. Người dùng tải file học liệu lên hệ thống.
2. Content Agent chọn loader phù hợp với định dạng file.
3. Nội dung thô được đọc thành văn bản.
4. Văn bản được gắn metadata như môn học, file nguồn, lớp học.
5. Văn bản được chia thành nhiều chunk.
6. Mỗi chunk được embedding và lưu vào ChromaDB.
7. Khi có truy vấn, hệ thống dùng similarity search để lấy lại các chunk gần nghĩa nhất.

Thiết kế pipeline này giúp tái sử dụng cùng một tập dữ liệu học liệu cho nhiều tác vụ khác nhau: hỏi đáp, tóm tắt, sinh câu hỏi, và hỗ trợ đánh giá.

### 4.3.2 Chunking và Embedding

Văn bản được chia nhỏ theo chiến lược chunking dạng đệ quy với kích thước khoảng 1000 ký tự và chồng lấn khoảng 200 ký tự. Cách chia này cân bằng giữa hai mục tiêu:
- giữ được đủ ngữ cảnh trong từng chunk;
- tránh làm chunk quá dài khiến retrieval nhiễu hoặc tốn chi phí embedding.

Chunk overlap được sử dụng để giảm nguy cơ mất mạch nội dung ở ranh giới giữa hai đoạn. Sau khi chunking, mỗi đoạn được biến đổi thành vector embedding để phục vụ truy xuất theo ngữ nghĩa.

### 4.3.3 ChromaDB và Vector Retrieval

ChromaDB được sử dụng như vector database cục bộ/persistent cho hệ thống. Mỗi document chunk được lưu cùng metadata như:
- subject;
- source file;
- trong một số luồng có thể suy ra tài liệu/lớp học liên quan.

Khi có yêu cầu truy vấn, backend thực hiện similarity search theo truy vấn ngữ nghĩa. Tùy ngữ cảnh, hệ thống có thể thêm điều kiện lọc như chỉ lấy chunk của một môn học, hoặc chỉ lấy chunk thuộc file đang mở.

Trong môi trường production Docker, thư mục dữ liệu ChromaDB được mount thành volume dùng chung để hai backend instance đều nhìn thấy cùng một vector store. Điều này rất quan trọng để bảo đảm tính nhất quán của dữ liệu retrieval.

### 4.3.4 Context Injection cho Large Language Model

Context injection là bước chèn nội dung retrieval vào prompt của LLM. Hệ thống không đơn thuần đưa tất cả dữ liệu truy xuất vào prompt mà còn làm sạch nội dung trước khi chèn vào, ví dụ:
- loại bỏ thông tin hành chính như email, số điện thoại, lịch học, nội quy;
- bỏ các đoạn quá ngắn hoặc nhiễu;
- loại bỏ trùng lặp giữa các chunk;
- ưu tiên nội dung đúng domain môn học.

Nhờ đó, phản hồi của LLM trở nên sát nội dung học liệu hơn, giảm ảo giác và tăng giá trị học thuật cho người dùng.

## 4.4 Thiết kế hệ thống học tập cá nhân hóa

### 4.4.1 Learning Roadmap Generation

Roadmap tổng thể là cấu trúc dài hạn mô tả chuỗi buổi học mà sinh viên nên đi qua theo môn học. Adaptive Learning Agent sử dụng learner profile để xác định mức độ hiện tại như Beginner hoặc mức cao hơn, sau đó tạo chuỗi session học tập bám vào tài liệu thực tế đã được công bố trong lớp.

Trong trường hợp có đủ dữ liệu về tài liệu và điểm, roadmap ưu tiên tài liệu chưa học hoặc điểm thấp. Khi dữ liệu chưa đủ, hệ thống dùng fallback roadmap theo khung kiến thức nền tảng – thực hành – tổng ôn.

### 4.4.2 Adaptive Recommendation

Recommendation thích ứng được sinh ra từ việc kết hợp nhiều tín hiệu:
- tài liệu nào chưa được làm bài;
- tài liệu nào có điểm dưới ngưỡng;
- tài liệu nào đã học ổn nhưng cần giữ lại để ôn tập;
- lịch sử tương tác gần đây.

Thay vì đề xuất mơ hồ, hệ thống có thể đưa ra khuyến nghị cụ thể như: ưu tiên học lại tài liệu A trong 3 ngày, sau đó chuyển sang tài liệu B, hoặc ôn tập lại tài liệu C vì điểm gần nhất dưới 40.

### 4.4.3 Learning Analytics và Learner Profile

Learner profile được xây dựng từ dữ liệu định lượng chứ không chỉ từ suy luận chủ quan của AI. Các trường dữ liệu quan trọng gồm:
- current level;
- total tests;
- average score;
- tổng số bài học hoàn thành;
- tổng thời lượng học;
- số lần tương tác với agent;
- lịch sử điểm theo tài liệu;
- lịch sử đăng nhập.

Nhờ profile này, hệ thống có thể cá nhân hóa không chỉ nội dung trả lời mà còn cả nhịp độ học, thứ tự ưu tiên tài liệu và mức độ đánh giá.

### 4.4.4 Planning và điều chỉnh lộ trình học tập

Kế hoạch học không phải một cấu trúc bất biến. Planning Agent cho phép:
- tái tạo kế hoạch mới khi sinh viên đăng nhập;
- dời một môn về học trước hoặc học sau;
- thêm số lượng tài liệu cần học trong ngày hoặc trong tuần;
- cập nhật deadline tương ứng.

Về mặt thiết kế, đây là bước biến roadmap dài hạn thành một lịch học ngắn hạn có thể thực thi trên thực tế. Sự tách biệt giữa roadmap và plan giúp hệ thống linh hoạt hơn: roadmap thể hiện chiến lược tổng thể, còn plan thể hiện lịch hành động cụ thể.

## 4.5 Thiết kế cơ sở dữ liệu và API

### 4.5.1 Thiết kế cơ sở dữ liệu PostgreSQL

Hệ thống sử dụng **PostgreSQL** làm cơ sở dữ liệu quan hệ trung tâm trong triển khai thực tế. PostgreSQL phù hợp với bài toán này vì hỗ trợ tốt:
- dữ liệu quan hệ phức tạp;
- transaction và tính nhất quán;
- mở rộng theo số lượng người dùng;
- kiểu dữ liệu JSON/JSONB cho một số trường linh hoạt như roadmap data, metadata hoặc debug payload.

Các nhóm bảng chính gồm:

**Nhóm người dùng và tổ chức học tập**
- `users`
- `subjects`
- `classrooms`
- `enrollments`

**Nhóm học liệu**
- `documents`
- `document_publications`
- `chunks`

**Nhóm cá nhân hóa học tập**
- `learner_profiles`
- `learning_roadmaps`
- `student_learning_progress`
- `student_learning_plans`
- `student_learning_plan_steps`
- `study_sessions`
- `user_login_sessions`

**Nhóm đánh giá và question bank**
- `question_bank`
- `assessment_history`
- `assessment_results`
- `student_document_evaluations`
- `student_document_score_history`

**Nhóm thông báo**
- `notifications`

**Nhóm OCR/OMR**
- `test_ocr_exam_batches`
- `test_ocr_grading_runs`
- `test_ocr_grading_results`

Việc tách theo nhóm như trên giúp hệ thống dễ bảo trì, dễ tối ưu chỉ mục và hỗ trợ phát triển thêm tính năng trong tương lai.

### 4.5.2 Thiết kế dữ liệu learning analytics

Learning analytics trong hệ thống không dồn vào một bảng duy nhất mà được hình thành từ sự kết hợp của nhiều bảng theo góc nhìn khác nhau.

- `assessment_history` ghi lịch sử điểm theo bài kiểm tra;
- `student_document_score_history` ghi lịch sử điểm theo từng tài liệu;
- `student_document_evaluations` ghi trạng thái gần nhất của một tài liệu đối với một sinh viên;
- `student_learning_progress` tổng hợp số buổi học, số lần làm bài, tổng phút học;
- `user_login_sessions` ghi thời gian vào/ra để tính effort score;
- `student_learning_plan_steps` cung cấp thông tin đúng hạn, trễ hạn và ưu tiên học.

Thiết kế này giúp hệ thống trả lời được nhiều loại câu hỏi phân tích khác nhau mà không cần nhồi quá nhiều thuộc tính vào một cấu trúc dữ liệu duy nhất.

### 4.5.3 Thiết kế REST API

Hệ thống backend được xây dựng bằng FastAPI và tổ chức thành nhiều router theo nhóm nghiệp vụ. Một số nhóm API chính gồm:
- `/api/auth`: xác thực người dùng;
- `/api/classroom`: quản lý lớp học;
- `/api/subjects`: quản lý môn học;
- `/api/upload` và `/api/documents`: quản lý tài liệu;
- `/api/assessment`: bài kiểm tra và câu hỏi;
- `/api/evaluation`: đánh giá học tập;
- `/api/adaptive`: gia sư AI cá nhân hóa;
- `/api/planning`: kế hoạch học tập;
- `/api/teacher`: hỗ trợ giảng viên qua Nova Teacher Agent;
- `/api/test-ocr`: sinh đề OCR và chấm bài;
- `/api/ops`, `/api/health`: giám sát vận hành.

Thiết kế REST API theo module giúp frontend dễ tích hợp và cũng giúp tách biệt rõ ràng trách nhiệm từng nghiệp vụ.

### 4.5.4 Thiết kế API cho AI Agent và RAG

Khác với CRUD thông thường, API cho AI Agent và RAG cần truyền được nhiều ngữ cảnh hơn. Một request kiểu AI thường bao gồm:
- thông tin người dùng và vai trò;
- môn học hoặc lớp học hiện hành;
- tài liệu đang mở;
- nội dung câu hỏi;
- lịch sử ngắn của hội thoại;
- tùy chọn cấu hình như số câu hỏi hoặc số mã đề.

Phía backend, các endpoint AI không chỉ trả chuỗi văn bản mà còn có thể trả:
- suggested actions;
- generated exam payload;
- plan data;
- material summary;
- grading results;
- debug metadata nếu là OCR.

Thiết kế này làm cho API vừa phục vụ hiển thị UI, vừa phục vụ điều phối luồng tiếp theo trên frontend.

# Chương 5: Thiết kế hệ thống OCR và chấm thi tự động

## 5.1 Phân tích bài toán OCR và OMR

### 5.1.1 Bài toán sinh đề thi OCR

Bài toán đầu tiên là tạo ra một bộ đề thi giấy đủ chuẩn để máy có thể chấm được về sau. Điều này không chỉ là sinh nội dung đề, mà còn phải đồng thời sinh:
- nhiều mã đề khác nhau;
- đáp án tương ứng cho từng mã đề;
- phiếu trả lời có bố cục cố định, dễ căn chỉnh;
- vùng mã sinh viên, mã đề và các ô tròn tô đáp án.

Do đó, thiết kế đề OCR cần ràng buộc chặt giữa question bank, mã đề, đáp án và layout OMR.

### 5.1.2 Bài toán nhận diện phiếu trả lời

Sau khi thu bài thi giấy và scan thành PDF, hệ thống cần giải quyết bài toán nhận diện phiếu trả lời trong điều kiện thực tế như:
- ảnh scan bị lệch góc;
- ánh sáng và độ tương phản không đồng đều;
- sinh viên tô ô quá đậm hoặc quá nhạt;
- có trường hợp tô nhiều ô hoặc bỏ trống;
- mã sinh viên và mã đề có thể ghi sai hoặc không tô rõ.

Bài toán này đòi hỏi kết hợp giữa xử lý ảnh cổ điển và các quy tắc hình học thay vì chỉ dùng OCR văn bản thuần túy.

### 5.1.3 Bài toán chấm thi tự động

Sau khi nhận diện được mã đề và đáp án tô, hệ thống cần đối chiếu với answer key, tính điểm, lưu kết quả và cho phép tra soát. Bài toán chấm thi tự động phải giải quyết thêm:
- chọn đúng bộ đáp án theo exam code;
- đánh dấu trạng thái như thiếu mã đề, thiếu mã sinh viên, đáp án mơ hồ;
- lưu ảnh crop và debug score để phục vụ kiểm tra sau này.

## 5.2 Thiết kế hệ thống sinh đề OCR

### 5.2.1 Thiết kế question bank

Question bank là đầu vào cho sinh đề OCR. Hệ thống ưu tiên lấy câu hỏi theo đúng subject và tập tài liệu của lớp học. Nếu số lượng câu hỏi chưa đủ, hệ thống lấy bổ sung từ question bank cùng môn; nếu vẫn thiếu thì sinh fallback questions từ học liệu đã có.

Thiết kế này bảo đảm ba mục tiêu:
- đề thi bám sát nội dung học của lớp;
- vẫn sinh được đề trong điều kiện ngân hàng câu hỏi chưa hoàn chỉnh;
- tái sử dụng cùng nguồn dữ liệu với các luồng đánh giá trực tuyến.

### 5.2.2 Thiết kế file Word đề thi

Bộ đề được xuất thành file Word, trong đó:
- mỗi mã đề có header riêng;
- câu hỏi được xáo trộn;
- thứ tự đáp án A/B/C/D cũng được xáo trộn lại;
- cuối tài liệu có phần hướng dẫn chấm và đáp án cho từng mã đề.

Thiết kế xuất Word có lợi thế là giảng viên dễ kiểm tra, chỉnh sửa và in ấn trong môi trường thực tế của nhà trường.

### 5.2.3 Thiết kế file Excel đáp án

Song song với file Word, hệ thống sinh file Excel đáp án. Mỗi mã đề có một answer key riêng, được dùng làm đầu vào chấm tự động khi giảng viên tải bài scan lên. Việc tách answer key ra file Excel giúp thuận tiện khi kiểm tra độc lập với file đề và cũng hỗ trợ trường hợp giảng viên muốn thay answer key ở bước chấm.

### 5.2.4 Thiết kế phiếu trả lời OMR

Phiếu trả lời OMR được dựng bằng ảnh raster theo layout cố định. Các thành phần chính của phiếu gồm:
- marker căn chỉnh ở bốn góc;
- vùng họ tên;
- vùng tô mã sinh viên theo cột số;
- vùng tô mã đề;
- vùng đáp án A/B/C/D theo từng câu.

Layout được tham số hóa theo số câu hỏi, số cột mã sinh viên và số cột hiển thị đáp án, giúp hệ thống mở rộng từ đề ngắn đến đề dài.

## 5.3 Thiết kế pipeline OCR và OMR

### 5.3.1 PDF Rasterization bằng PyMuPDF

Bài làm scan được nộp lên dưới dạng PDF. Hệ thống sử dụng PyMuPDF để rasterize từng trang PDF thành ảnh RGB ở độ phân giải phù hợp (ví dụ 200 DPI). Đây là bước biến dữ liệu tài liệu thành đầu vào xử lý ảnh cho các bước OMR tiếp theo.

Ưu điểm của PyMuPDF là tốc độ tốt, khả năng xử lý PDF ổn định và phù hợp cho pipeline backend trong Docker.

### 5.3.2 Alignment Marker và Perspective Correction

Sau khi có ảnh trang scan, hệ thống tìm các marker đen ở bốn góc phiếu. Nếu tìm đủ marker, hệ thống tính ma trận biến đổi phối cảnh (perspective transform) để đưa phiếu về kích thước chuẩn. Nếu không đủ marker, hệ thống dùng phương án fallback là resize về kích thước template.

Bước này cực kỳ quan trọng vì các tọa độ ô tô, ô mã sinh viên và ô mã đề đều được xác định theo layout chuẩn. Nếu không căn chỉnh tốt, toàn bộ pipeline OMR phía sau sẽ sai lệch.

### 5.3.3 Bubble Detection bằng OpenCV

Sau khi căn chỉnh, hệ thống chuyển ảnh sang grayscale, làm mờ Gaussian và nhị phân hóa bằng Otsu threshold. Với mỗi ô tròn cần kiểm tra, hệ thống tính tỷ lệ pixel được tô trong vùng tròn nhỏ ở tâm bubble. Dựa trên fill ratio, hệ thống xác định:
- ô được tô rõ;
- ô bỏ trống;
- nhiều ô được tô cùng lúc;
- trường hợp mơ hồ cần gắn nhãn `MULTI` hoặc trạng thái lỗi.

Cách tiếp cận này phù hợp với OMR truyền thống vì đơn giản, dễ tối ưu và dễ giải thích kết quả.

### 5.3.4 Student ID Recognition

Mã sinh viên không được OCR trực tiếp từ chữ viết tay mà được nhận từ vùng bubble theo từng cột số. Với mỗi cột, hệ thống so sánh điểm tô của 10 hàng số từ 0 đến 9, lấy giá trị có điểm cao nhất nếu vượt ngưỡng và đủ khác biệt với lựa chọn đứng thứ hai.

Cơ chế này cho độ ổn định cao hơn so với việc nhận diện ký tự viết tay của mã sinh viên.

### 5.3.5 OCR nhận diện thông tin sinh viên bằng Tesseract

Khác với mã sinh viên, vùng họ tên là văn bản tự do nên cần OCR văn bản. Hệ thống crop vùng name box, tiền xử lý ảnh bằng grayscale, blur, threshold và phóng to, sau đó dùng Tesseract OCR để nhận diện tên.

Trong thực tế, OCR tên chỉ mang tính hỗ trợ hiển thị và tra soát, còn khóa nhận dạng chính của bài làm vẫn là mã sinh viên và mã đề.

## 5.4 Thiết kế quy trình chấm thi tự động

### 5.4.1 Nhận diện mã đề và đáp án

Khi chấm một trang bài làm, hệ thống thực hiện theo chuỗi:
1. căn chỉnh phiếu;
2. đọc mã sinh viên;
3. đọc mã đề;
4. đọc danh sách đáp án A/B/C/D;
5. xác định trạng thái ban đầu của phiếu.

Nếu thiếu mã đề hoặc mã sinh viên, hệ thống vẫn lưu kết quả nhưng gắn trạng thái lỗi để người dùng tra soát.

### 5.4.2 So khớp đáp án và tính điểm

Sau khi có exam code, hệ thống truy xuất answer key tương ứng. Mỗi đáp án được so sánh với lựa chọn sinh viên tô. Điểm số có thể tính theo thang 10 dựa trên tỷ lệ số câu đúng trên tổng số câu.

Việc chấm được thiết kế tách riêng khỏi phần OMR để hỗ trợ các tình huống thay answer key từ file Excel khác mà không cần chạy lại pipeline nhận diện ảnh.

### 5.4.3 Lưu trữ kết quả OCR grading

Kết quả chấm được lưu vào PostgreSQL qua các bảng:
- `test_ocr_grading_runs` lưu một đợt chấm;
- `test_ocr_grading_results` lưu kết quả từng trang/bài;
- `debug_json` lưu thông tin score theo bubble, marker alignment, tên nhận diện OCR và các dữ liệu phục vụ debug.

Ngoài dữ liệu bảng, hệ thống còn lưu:
- ảnh trang đã căn chỉnh;
- ảnh crop vùng tên;
- file PDF đầu vào.

Thiết kế này giúp việc truy vết và sửa sai trở nên khả thi trong môi trường vận hành thực tế.

### 5.4.4 Xử lý lỗi và debugging OCR

Một hệ thống OCR dùng thật không thể tránh lỗi hoàn toàn, vì vậy khâu debug phải được thiết kế ngay từ đầu. Các trường hợp được gắn nhãn gồm:
- `missing_exam_code`;
- `missing_student_id`;
- `ambiguous_answers`;
- `unknown_exam_code`;
- `graded`.

Nhờ lưu các score chi tiết và ảnh crop, người vận hành có thể xem lại nguyên nhân của từng lỗi thay vì chỉ thấy “chấm sai”. Đây là khác biệt quan trọng giữa một demo OCR và một hệ thống chấm thi có khả năng vận hành.

## 5.5 Đánh giá hệ thống OCR

### 5.5.1 Đánh giá độ chính xác nhận diện bubble

Độ chính xác nhận diện bubble phụ thuộc mạnh vào chất lượng scan, độ đậm nét tô, căn chỉnh marker và ngưỡng fill ratio. Hệ thống hiện dùng chiến lược nhận diện dựa trên tỉ lệ lấp đầy nên hoạt động tốt với phiếu in chuẩn và scan đủ rõ. Với các bài tô mờ, tô lệch hoặc quệt nhiều lần, hệ thống có thể gắn trạng thái mơ hồ thay vì cố chấm sai.

### 5.5.2 Đánh giá OCR nhận diện văn bản

Nhận diện văn bản bằng Tesseract chủ yếu hỗ trợ tên sinh viên. Trong thực tế, chất lượng OCR tên thường thấp hơn OMR do phụ thuộc vào chữ viết và ảnh scan. Vì vậy, hệ thống chỉ dùng trường tên như dữ liệu phụ trợ, không dùng làm khóa đối chiếu chính.

### 5.5.3 Đánh giá hiệu năng pipeline OCR

Hiệu năng pipeline OCR bao gồm:
- thời gian rasterize PDF;
- thời gian căn chỉnh từng trang;
- thời gian đọc bubble;
- thời gian OCR vùng tên;
- thời gian ghi dữ liệu và lưu ảnh debug.

Do pipeline làm việc theo từng trang độc lập, hệ thống có khả năng song song hóa về sau khi quy mô bài thi tăng lên.

### 5.5.4 Đánh giá khả năng mở rộng hệ thống

Kiến trúc OCR hiện đã tách tương đối rõ giữa:
- sinh đề;
- lưu answer key;
- rasterize PDF;
- xử lý OMR;
- OCR tên;
- chấm điểm;
- lưu kết quả.

Vì vậy, hệ thống có khả năng mở rộng theo các hướng như đa luồng, worker queue, hoặc triển khai service OCR riêng khi lượng bài quét tăng lớn.

# Chương 6: Cài đặt, thử nghiệm và đánh giá hệ thống

## 6.1 Công nghệ và môi trường triển khai

### 6.1.1 Backend và API framework

Backend được xây dựng bằng **FastAPI** trên nền Python 3.11. FastAPI phù hợp vì:
- hỗ trợ xây REST API nhanh và rõ kiểu dữ liệu;
- tích hợp tốt với Pydantic;
- tương thích với SQLAlchemy;
- dễ triển khai qua Gunicorn/Uvicorn trong Docker.

Tầng ORM sử dụng **SQLAlchemy** để ánh xạ dữ liệu giữa các model Python và PostgreSQL.

### 6.1.2 Frontend framework

Frontend được phát triển bằng **Next.js** kết hợp **React** và **TypeScript**. Cách lựa chọn này mang lại:
- cấu trúc route rõ ràng theo App Router;
- khả năng tổ chức dashboard, trang quản trị, trang học tập và trang OCR trong cùng một web app;
- dễ triển khai production bằng build tĩnh/SSR trong container Docker.

### 6.1.3 AI/LLM và RAG framework

Hệ thống AI sử dụng các thành phần chính:
- các LLM backend linh hoạt như Groq, OpenAI-compatible API, Gemini hoặc Ollama tùy tác vụ;
- LangChain-compatible loaders và Chroma integration;
- **ChromaDB** làm vector store;
- các prompt/task-specific agent ở tầng ứng dụng.

Điểm đáng chú ý là hệ thống không phụ thuộc cứng vào một nhà cung cấp duy nhất, nhờ đó linh hoạt trong thử nghiệm và tối ưu chi phí.

### 6.1.4 OCR và image processing framework

Phần OCR/OMR sử dụng:
- **PyMuPDF** để render PDF thành ảnh;
- **OpenCV** để nhị phân hóa, căn chỉnh, phát hiện bubble;
- **Pillow** để dựng form OMR và xử lý ảnh phụ trợ;
- **Tesseract OCR** để nhận diện vùng họ tên sinh viên.

Tập công nghệ này phù hợp cho bài toán xử lý ảnh tài liệu trong môi trường máy chủ Linux/Docker.

## 6.2 Triển khai hệ thống

### 6.2.1 Triển khai Backend FastAPI

Trong môi trường production, backend được đóng gói bằng Docker image riêng. Container backend cài sẵn:
- Python runtime;
- dependency từ `requirements.txt`;
- Tesseract OCR;
- các thư viện hệ thống cần cho OpenCV/PyMuPDF.

Ứng dụng được chạy bằng **Gunicorn** với cấu hình worker/thread phù hợp cho production thay vì dùng dev server. Thiết kế này giúp backend đáp ứng tốt hơn khi có nhiều request đồng thời.

### 6.2.2 Triển khai Frontend Next.js

Frontend cũng được build thành Docker image riêng. Quy trình triển khai gồm:
- copy package manifest;
- cài dependency;
- build production;
- chạy `next start` trên cổng nội bộ của container.

Frontend giao tiếp với backend thông qua biến môi trường `NEXT_PUBLIC_API_BASE_URL`, cho phép thay đổi địa chỉ API dễ dàng giữa các môi trường.

### 6.2.3 Triển khai PostgreSQL và ChromaDB

Trong triển khai thực tế, **PostgreSQL** chạy dưới dạng service riêng trong Docker Compose và đóng vai trò nguồn dữ liệu quan hệ trung tâm. Cơ sở dữ liệu được mount volume bền vững để bảo toàn dữ liệu khi container khởi động lại.

**ChromaDB** trong hệ thống được lưu theo kiểu persistent directory và mount volume dùng chung vào thư mục dữ liệu vector. Nhờ đó, nhiều backend instance có thể dùng chung một tập embedding.

Bên cạnh đó, **Redis** được triển khai như một service riêng để hỗ trợ conversation memory phân tán và/hoặc cache khi mở rộng ngang hệ thống.

### 6.2.4 Triển khai AI Service và OCR Service

Trong kiến trúc hiện tại, AI Agent và OCR Service được chạy bên trong container backend, nhưng được tách module rõ ràng theo service và agent. Điều này phù hợp ở giai đoạn triển khai một cụm web thực tế quy mô vừa.

Về sau, có thể tách riêng OCR worker hoặc AI worker nếu tải tăng cao. Tuy nhiên ở phiên bản hiện tại, việc đồng nhất trong một backend service giúp triển khai đơn giản hơn và giảm chi phí vận hành ban đầu.

## 6.3 Thử nghiệm hệ thống

### 6.3.1 Thử nghiệm AI Agent

Việc thử nghiệm AI Agent được thực hiện theo từng nhóm nghiệp vụ:
- Nova Teacher Agent: thử hỏi thông tin lớp, tài liệu, sinh viên, sinh đề;
- Adaptive Learning Agent: thử hỏi nội dung dựa trên tài liệu đang mở, yêu cầu tóm tắt, giải thích khái niệm;
- Planning Agent: thử tạo kế hoạch mới và điều chỉnh thứ tự ưu tiên;
- Evaluation Agent: thử hỏi môn yếu, tài liệu quá hạn, xu hướng điểm.

Các tiêu chí đánh giá gồm:
- hiểu đúng intent;
- dùng đúng dữ liệu ngữ cảnh;
- phản hồi có ích cho người dùng;
- không trả lời quá chung chung.

### 6.3.2 Thử nghiệm Retrieval-Augmented Generation

RAG được thử nghiệm qua các tình huống:
- truy vấn đúng tài liệu đang mở;
- truy vấn theo môn học;
- truy vấn khi chỉ một phần học liệu có trong vector store;
- truy vấn khi vector store tạm thời không sẵn sàng.

Mục tiêu là kiểm tra xem hệ thống có thực sự dùng học liệu để trả lời hay chỉ phản hồi theo tri thức nền của mô hình. Ngoài ra cần kiểm tra mức độ loại bỏ nhiễu hành chính khỏi context injection.

### 6.3.3 Thử nghiệm OCR và OMR

Phần OCR/OMR được thử nghiệm theo nhiều kịch bản:
- sinh đề Word + Excel + test sheet;
- scan một bài làm chuẩn;
- scan nhiều bài làm trong một PDF;
- bài bị lệch góc;
- bài tô nhiều ô hoặc bỏ trống;
- bài có mã đề không khớp answer key.

Các chỉ tiêu quan sát bao gồm tính đúng của mã sinh viên, mã đề, đáp án, điểm số và khả năng lưu ảnh/debug phục vụ tra soát.

### 6.3.4 Thử nghiệm tải và hiệu năng hệ thống

Thử nghiệm tải tập trung vào:
- thời gian phản hồi API cơ bản;
- khả năng xử lý đồng thời nhiều request frontend/backend;
- khả năng chia tải qua nhiều instance backend/frontend sau Nginx;
- thời gian xử lý các tác vụ nặng như generate exam, retrieval lớn và OCR chấm PDF nhiều trang.

Kết quả thử nghiệm tải giúp xác định điểm nghẽn tiềm năng như I/O file, PostgreSQL connection pool, vector retrieval hoặc thời gian gọi LLM.

## 6.4 Đánh giá hệ thống

### 6.4.1 Đánh giá khả năng hỗ trợ học tập cá nhân hóa

Hệ thống cho thấy khả năng hỗ trợ cá nhân hóa ở ba mức:
- cá nhân hóa theo dữ liệu quá khứ của sinh viên;
- cá nhân hóa theo tài liệu đang học;
- cá nhân hóa theo kế hoạch và tiến độ hiện tại.

Điểm mạnh là các đề xuất không chỉ dựa trên mô hình AI mà còn dựa trên dữ liệu nghiệp vụ đã lưu trong PostgreSQL. Điều này giúp khuyến nghị có tính thực thi cao hơn.

### 6.4.2 Đánh giá chất lượng phản hồi AI

Chất lượng phản hồi AI được cải thiện đáng kể khi có RAG và context routing. Nova Teacher Agent cho phản hồi tốt trong các truy vấn quản trị học thuật; Adaptive Agent hiệu quả hơn khi sinh viên hỏi bám tài liệu. Tuy vậy, chất lượng vẫn phụ thuộc vào chất lượng học liệu đầu vào, vector retrieval và mức độ ổn định của LLM backend.

### 6.4.3 Đánh giá độ chính xác OCR

Độ chính xác OMR thường cao khi biểu mẫu chuẩn và scan đủ rõ. OCR tên sinh viên có độ ổn định thấp hơn nhưng vẫn hữu ích ở vai trò hỗ trợ hiển thị. Việc lưu debug score và ảnh crop là một ưu điểm lớn vì tăng khả năng tin cậy khi vận hành thực tế.

### 6.4.4 Đánh giá khả năng mở rộng hệ thống

Hệ thống có nền tảng mở rộng tốt nhờ:
- tách frontend/backend;
- dùng PostgreSQL làm nguồn dữ liệu trung tâm;
- dùng Redis cho memory phân tán;
- dùng ChromaDB cho retrieval;
- triển khai Docker Compose với nhiều instance backend/frontend và Nginx cân bằng tải.

Điểm cần tiếp tục tối ưu là tách worker cho các tác vụ nặng và chuẩn hóa sâu hơn khả năng scale của vector store và OCR pipeline.

# Chương 7: Kết luận và hướng phát triển

## 7.1 Kết luận

Đề tài đã xây dựng được một nền tảng học tập cá nhân hóa tích hợp nhiều lớp công nghệ: quản trị học liệu, AI agent chuyên biệt, retrieval-augmented generation, đánh giá học tập, planning cá nhân hóa và OCR/OMR chấm thi tự động. So với một hệ thống LMS thông thường, sản phẩm này tạo ra giá trị ở khả năng gắn dữ liệu học tập với suy luận AI để hỗ trợ ra quyết định cho cả giảng viên và sinh viên.

Về mặt kiến trúc, hệ thống có những điểm nổi bật sau:
- tổ chức theo mô hình multi-agent rõ vai trò;
- sử dụng PostgreSQL làm dữ liệu lõi, ChromaDB làm dữ liệu ngữ nghĩa và Redis hỗ trợ phân tán session/memory;
- hỗ trợ triển khai web thực tế bằng Docker với khả năng nhân bản backend/frontend;
- có thêm lớp OCR/OMR phục vụ bài toán số hóa kiểm tra trên giấy.

Từ góc nhìn ứng dụng, hệ thống không chỉ dừng ở trình diễn AI mà đã tiến gần mô hình một nền tảng edtech có khả năng triển khai trong môi trường vận hành thật.

## 7.2 Hướng phát triển tương lai

### 7.2.1 Mở rộng Multi-Agent System

Trong tương lai có thể mở rộng hệ thống theo hướng bổ sung thêm các agent chuyên trách hơn như:
- agent tư vấn học tập theo mục tiêu nghề nghiệp;
- agent hỗ trợ phát hiện lỗ hổng kiến thức theo kỹ năng;
- agent dành cho quản trị viên để giám sát hệ thống học tập toàn trường;
- agent phân tích lớp học theo thời gian thực.

Việc mở rộng multi-agent sẽ giúp tăng tính mô-đun và giảm tải cho từng agent hiện tại.

### 7.2.2 Tối ưu hóa Conversational Memory

Conversation memory hiện đã hỗ trợ Redis và context routing cơ bản, nhưng vẫn có thể phát triển thêm theo hướng:
- tóm tắt hội thoại dài thành memory ngắn hạn/ dài hạn;
- lưu memory theo từng người dùng và từng tác vụ;
- kết hợp memory với learner profile để tạo phản hồi ổn định hơn giữa nhiều phiên đăng nhập.

Đây là hướng quan trọng nếu hệ thống muốn phát triển thành một trợ lý học tập liên tục thay vì chatbot theo phiên rời rạc.

### 7.2.3 Tích hợp Multimodal AI

Hiện tại hệ thống chủ yếu xử lý văn bản và ảnh tài liệu. Trong tương lai có thể tích hợp multimodal AI để:
- hiểu slide có biểu đồ/phương trình tốt hơn;
- phân tích ảnh chụp bài tập tự luận;
- hỗ trợ giảng viên bằng cách hiểu cả văn bản, hình ảnh và sơ đồ;
- mở rộng khả năng OCR sang các bài làm viết tay phức tạp hơn.

Multimodal AI sẽ đặc biệt hữu ích trong các môn kỹ thuật, toán học và khoa học tự nhiên.

### 7.2.4 Tối ưu hóa triển khai phân tán và autoscaling

Hướng phát triển hạ tầng trong tương lai gồm:
- tách backend API, OCR worker, AI worker thành các service độc lập;
- đưa hàng đợi tác vụ vào pipeline cho generate exam, OCR và warmup question bank;
- triển khai trên Kubernetes hoặc nền tảng container orchestration tương đương;
- bổ sung autoscaling cho backend/frontend theo CPU, RAM hoặc số request;
- bổ sung cơ chế sao lưu và phục hồi dữ liệu cho PostgreSQL và vector store.

Khi đó, hệ thống sẽ tiến gần hơn tới một nền tảng giáo dục thông minh có khả năng phục vụ quy mô lớn, ổn định và bền vững.
