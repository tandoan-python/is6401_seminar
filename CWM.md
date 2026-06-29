# Phân tích Chuyên sâu Kiến trúc Chat with MES (CWM)

Tài liệu này cung cấp cái nhìn chi tiết và chuyên sâu về kiến trúc lõi của hệ thống **Chat with MES (CWM)** được đề xuất trong bài báo và cách kiến trúc này được hiện thực hóa (implemented) bên trong mã nguồn `app.py`.

---

## 1. Tổng quan Kiến trúc (Overview)
Kiến trúc CWM giải quyết hai thách thức cốt lõi khi ứng dụng LLM vào hệ thống sản xuất (Manufacturing):
1. **Sự mơ hồ của ngôn ngữ tự nhiên (Ambiguity)**: Người dùng có thể nhập sai tên công ty, tên sản phẩm so với dữ liệu gốc lưu trong database.
2. **Tính phức tạp và toàn vẹn dữ liệu (Complexity & Atomicity)**: Việc sửa đổi dữ liệu MES đòi hỏi các quy tắc nghiệp vụ khắt khe (ví dụ: tạo task cắt/may thì phải trừ nguyên liệu trong kho). Mô hình không được phép viết SQL tùy tiện để sửa dữ liệu.

Để giải quyết, kiến trúc CWM chia quy trình xử lý thành **3 giai đoạn (Stages)** tương ứng với **3 lần gọi LLM (Listings)**.

---

## 2. Phân tích 3 Giai đoạn Cốt lõi (The 3 Stages)

### Giai đoạn 1: Request Rewriting (Tiền xử lý & Chuẩn hóa Query)
* **Vấn đề**: Người dùng nhập "PolyU" thay vì tên đầy đủ "Hong Kong Polytechnic University" có trong Database. Nếu đưa trực tiếp "PolyU" vào truy vấn SQL, hệ thống sẽ trả về lỗi không tìm thấy (0 results).
* **Cách giải quyết trong Bài báo (Listing 1)**: Sử dụng một LLM phụ đóng vai trò là *Entity Disambiguation* (Khử nhầm lẫn thực thể).
* **Cách thực thi trong `app.py`**:
  1. **Nhúng (Embedding) và Vector Database (ChromaDB)**: 
     - Đầu tiên, hệ thống `app.py` trích xuất trước toàn bộ các tên khách hàng, tên đơn hàng, tên sản phẩm... hợp lệ từ database MySQL. 
     - Sử dụng mô hình HuggingFace (`all-MiniLM-L6-v2`) để chuyển hóa các chuỗi văn bản này thành các chuỗi số học (Vector Embeddings) đa chiều. Các vector này biểu diễn ý nghĩa ngữ nghĩa (semantic meaning) của từ ngữ.
     - Các vector được lưu vào cơ sở dữ liệu vector cục bộ ChromaDB.
  2. **Tìm kiếm tương đồng (Similarity Search)**: 
     - Khi người dùng nhập một câu hỏi (ví dụ: "Cho xem đơn hàng của PolyU"), câu hỏi này cũng được "nhúng" (embed) thành một vector tương tự.
     - ChromaDB sẽ dùng các thuật toán đo khoảng cách (như Cosine Similarity) để tìm ra các vector trong database có không gian gần nhất với vector câu hỏi. Qua đó, hệ thống nhận diện được từ "PolyU" có ngữ nghĩa cực kỳ gần với thực thể "Hong Kong Polytechnic University" đã lưu sẵn.
  3. **Chuyển đổi bởi LLM**: Truyền danh sách thực thể vừa tìm được vào Prompt của **Listing 1**. LLM sẽ dùng suy luận để bóc tách câu hỏi, loại bỏ từ sai ("PolyU") và thay bằng đúng định dạng thẻ được quy định: `<tên_bảng.tên_cột = 'Tên chuẩn'>`.
  *Ví dụ:* `Orders of PolyU` -> `<customers.customer_name = 'Hong Kong Polytechnic University'> orders`.

### Giai đoạn 2: Multi-Step Dynamical Operations Planning (Lên kế hoạch đa bước)
* **Vấn đề**: Các model Text2SQL truyền thống chỉ sinh ra được một câu lệnh SQL duy nhất, không thể xử lý các logic chuỗi (Ví dụ: "Tìm mã đơn hàng -> Cấp phát task -> Nhập vật liệu").
* **Cách giải quyết trong Bài báo (Listing 2)**: Sử dụng kỹ thuật lập kế hoạch trước khi thực thi (Pre-execution planning) mang hơi hướng của *Chain-of-Thought (CoT)*.
* **Cách thực thi kỹ thuật Chain-of-Thought (CoT) trong `app.py`**:
  Chain-of-Thought (Chuỗi tư duy) là kỹ thuật mô phỏng cách con người suy nghĩ từng bước một trước khi hành động. Khác với Text2SQL truyền thống (cố gắng nhồi nhét mọi thứ vào 1 câu SQL), hệ thống CWM yêu cầu LLM phải "nghĩ lớn rồi chia nhỏ":
  1. **Cung cấp ngữ cảnh**: Hệ thống bơm (inject) toàn bộ Lược đồ Database (Schema) và Danh sách Tools vào Prompt **Listing 2**.
  2. **Tư duy từng bước (Step-by-step Reasoning)**: 
     - Thay vì đưa ra đáp án ngay, LLM được yêu cầu phân rã yêu cầu phức tạp thành một chuỗi (Chain) các hành động tuyến tính. 
     - Mỗi một "mắt xích" trong chuỗi này được LLM gán cho 1 trong 3 nhãn hành động (Operations):
       - **SQL**: Dùng để truy vấn dữ liệu thô (ví dụ: "Tìm mã đơn hàng").
       - **Tool**: Dùng để thao tác an toàn với các nghiệp vụ (ví dụ: "Phân bổ công việc cho đơn hàng vừa tìm được").
       - **Thought (Tư duy)**: Nếu bài toán yêu cầu tổng hợp hoặc tính toán (ví dụ: "tổng lượng vải đã dùng"), LLM sinh ra một bước `Thought`. Ở bước này, LLM sẽ nhận dữ liệu từ các bước trước đó, tự dùng khả năng suy luận nội tại để cộng trừ nhân chia và sinh ra kết quả trung gian.
  3. **Lợi ích của CoT**: Việc buộc LLM phải diễn giải "Step 1 làm gì, Step 2 lấy kết quả Step 1 làm gì tiếp" giúp giảm thiểu tối đa hiện tượng "Ảo giác" (Hallucination) do LLM không phải xử lý một lượng lớn logic nghiệp vụ cùng một lúc. Kế hoạch (Plan) định dạng Markdown được sinh ra giống hệt cách một chuyên gia hệ thống lập trình.

### Giai đoạn 3: Parameter Identification & Execution (Trích xuất tham số & Thực thi)
* **Vấn đề**: Khi lên kế hoạch ở Giai đoạn 2, LLM không hề biết dữ liệu thực tế là gì (vì chưa query). Nó chỉ có thể tạo ra các tham số giữ chỗ (Placeholders), ví dụ: `Tool allocate_task, order_id=<order_id_step1>`. Làm sao để thay thế `<order_id_step1>` bằng một con số thực tế?
* **Cách giải quyết trong Bài báo (Listing 3)**: Sử dụng LLM phân tích ngữ cảnh lịch sử.
* **Cách thực thi trong `app.py`**:
  1. Vòng lặp *Executor* bắt đầu chạy từng Step một.
  2. Kết quả (Output) của mỗi Step được lưu vào một biến `Historical Context` (Ngữ cảnh lịch sử).
  3. Khi chuẩn bị chạy một Step mới, hệ thống dùng Regex quét xem câu lệnh có chứa dấu `< >` hay không.
  4. Nếu có, nó ném câu lệnh và `Historical Context` vào Prompt của **Listing 3**.
  5. LLM sẽ tự động tìm trong ngữ cảnh lịch sử xem kết quả SQL của bước 1 là số mấy, từ đó thay thế `<order_id_step1>` thành ID thật (ví dụ: `15`).
  6. Sau khi điền xong tham số, lệnh (SQL hoặc Tool) mới chính thức được đẩy xuống Database/Function để chạy.

---

## 3. Vai trò của Tools (Công cụ nghiệp vụ)
Tại sao không để LLM tự viết SQL `INSERT/UPDATE` luôn cho nhanh mà phải tạo ra Tools?
* MES là một môi trường sản xuất nghiêm ngặt (Serious scenario). Việc gán một nhiệm vụ cắt/may (cutting/sewing task) không chỉ đơn thuần là `INSERT` một dòng vào bảng `cutting_tasks`, mà nó còn kéo theo việc kiểm tra xem đơn hàng có tồn tại không, sản phẩm thuộc loại gì, và trạng thái mặc định phải là `0`.
* Việc cho phép LLM tự do viết lệnh `UPDATE/INSERT` rất dễ gây ra **Catastrophic Hallucinatory Data Editing** (Chỉnh sửa dữ liệu sinh ảo, phá hỏng toàn bộ logic CSDL).
* Do đó, `app.py` bọc (encapsulate) các thao tác nguy hiểm này vào 5 Tools an toàn (như Table 2 của paper):
  1. `find_order_details`
  2. `allocate_task`
  3. `store_materials`
  4. `complete_task`
  5. `get_busy_workers`
* LLM chỉ được phép gọi tên Tool truyền vào ID, phần thực thi an toàn phía dưới (Database Transactions) sẽ do Python lo liệu.

---

## 4. Response Generation (Tổng hợp và Phản hồi)
* Sau khi toàn bộ các bước được chạy xong, tất cả các dữ liệu thô (Raw Results) thường trông rất xấu và khó đọc (ví dụ: `[(4, 150), (5, 200)]`).
* Một Prompt cuối cùng được gọi để tổng hợp mớ dữ liệu thô này thành một báo cáo (Report) chuẩn văn phong doanh nghiệp, sử dụng Bảng (Markdown Table), loại bỏ hoàn toàn các thông số kỹ thuật (không in ra SQL hay Tool logs) để người dùng (Công nhân/Quản lý xưởng) dễ dàng đọc hiểu.

---

## 5. Tổng kết
Kiến trúc CWM là một sự chuyển dịch mô hình (Paradigm shift) cực kỳ thông minh:
- Nó hy sinh tốc độ (gọi LLM tới 3-4 lần) để đổi lấy **Sự an toàn** và **Độ chính xác (Accuracy)** trong môi trường nhà máy.
- Bằng cách phân rã (Decompose) một câu lệnh phức tạp thành nhiều bước nhỏ (CoT), kết hợp với kỹ thuật Parameter Identification, nó cho phép một LLM mã nguồn mở vừa phải như LLaMA3 cũng có thể xử lý thành công các nghiệp vụ MES phức tạp lên tới ~80% độ chính xác, bỏ xa các mô hình Text2SQL thuần túy.
