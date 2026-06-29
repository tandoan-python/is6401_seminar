# Hướng dẫn Cài đặt và Chạy Ứng dụng MES Agent

Hệ thống **MES Agent** tích hợp Trí tuệ nhân tạo (LLM Agent) hỗ trợ quản lý, truy vấn thông tin cơ sở dữ liệu sản xuất (MES) và tự động hóa quy trình phân bổ nhiệm vụ.

---

## 📌 Các tính năng cốt lõi của Hệ thống

1. **Quản lý Cấu hình (Configuration)**: Tự động tải các thông số kết nối cơ sở dữ liệu MySQL và hệ số quy mô sinh dữ liệu từ file `.env`.
2. **Khởi tạo Lược đồ Cơ sở Dữ liệu (Database Schema Manager)**: Thiết lập 16 bảng thực thể chuẩn hóa phục vụ cho quy trình may mặc, cắt vá, kho bãi và nhiệm vụ sản xuất.
3. **Mô phỏng Dữ liệu Kiểm thử (Data Generator)**: Tự động sinh dữ liệu thực tế dựa trên thư viện Faker và hệ số quy mô `SCALE_FACTOR`.
4. **Chuẩn hóa Thực thể (Request Rewriter/RAG)**: Sử dụng HuggingFace Embeddings (`all-MiniLM-L6-v2`) kết hợp cơ sở dữ liệu vector Chroma để chuẩn hóa các tên thực thể không đồng nhất trước khi đưa vào LLM (ví dụ: chuyển "PolyU" thành "Hong Kong Polytechnic University").
5. **Định nghĩa API Nội bộ (Custom Tools)**: Cung cấp công cụ `allocate_task` cho phép Agent tương tác trực tiếp với các chức năng nghiệp vụ của hệ thống MES.
6. **Điều phối Tác tử (LLM Agent Manager)**: Sử dụng LangChain SQL Agent cùng mô hình ngôn ngữ lớn Ollama (`llama3`) chạy cục bộ để suy luận, lập kế hoạch, truy vấn SQL và thực thi nhiệm vụ theo thời gian thực.

---

## 🛠️ Yêu cầu Hệ thống & Tiền đề

* **Python**: Phiên bản 3.10 trở lên.
* **MySQL Server**: Đã cài đặt và đang chạy dịch vụ MySQL.
* **Ollama**: Đã cài đặt và tải sẵn mô hình `llama3`.
  * Lệnh chạy Ollama và tải model:
    ```bash
    ollama run llama3
    ```

---

## 🚀 Các Bước Cài đặt và Triển khai

### Bước 1: Tạo môi trường ảo (Virtual Environment)

Mở Terminal (hoặc Command Prompt) tại thư mục dự án và chạy lệnh sau để cô lập môi trường:

* **Đối với Windows:**
  ```bash
  python -m venv venv
  ```
* **Đối với macOS/Linux:**
  ```bash
  python3 -m venv venv
  ```

### Bước 2: Kích hoạt môi trường ảo

* **Đối với Windows (Command Prompt):**
  ```cmd
  venv\scripts\activate
  ```
* **Đối với Windows (PowerShell):**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
* **Đối với macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```
*(Lưu ý: Sau khi kích hoạt thành công, bạn sẽ thấy tiền tố `(venv)` xuất hiện ở đầu dòng lệnh).*

### Bước 3: Cài đặt các thư viện cần thiết

Đảm bảo file [requirements.txt](file:///c:/tandoan/dev/python/IS6101/requirements.txt) có sẵn trong thư mục dự án. Tiến hành chạy lệnh sau:

```bash
pip install -r requirements.txt

## update
pip install -U -r requirements.txt

```

*Các thư viện chính bao gồm: `pymysql`, `faker`, `SQLAlchemy`, `langchain`, `langchain-community`, `langchain-huggingface`, `chromadb`, `python-dotenv`.*

### Bước 4: Cấu hình Biến môi trường (`.env`)

Tạo hoặc chỉnh sửa file [.env](file:///c:/tandoan/dev/python/IS6101/.env) trong thư mục gốc của dự án với nội dung cấu hình kết nối MySQL và hệ số quy mô dữ liệu:

```env
# Cấu hình kết nối cơ sở dữ liệu MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=mes_database

# Cấu hình hệ số quy mô dữ liệu (Scale Factor)
SCALE_FACTOR=15000
```

*Lưu ý: Hãy chắc chắn cơ sở dữ liệu tương ứng với `DB_NAME` đã được tạo trước đó trong MySQL của bạn:*
```sql
CREATE DATABASE mes_database;
```

---

## 🏃 Hướng dẫn Chạy ứng dụng

Sau khi hoàn tất cấu hình và kích hoạt môi trường ảo, bạn thực thi ứng dụng theo 2 bước tách biệt nhằm bảo đảm tính toàn vẹn và độc lập của hệ thống (Clean Code & Separation of Concerns):

### Bước 1: Khởi tạo và Sinh dữ liệu Cơ sở dữ liệu (Chỉ chạy 1 lần)
Chạy lệnh sau để hệ thống tự động khởi tạo 16 bảng và sinh dữ liệu kiểm thử giả định:

```bash
python database_init.py
```

### Bước 2: Khởi động Hệ thống MES Agent Chat
Sau khi cơ sở dữ liệu đã sẵn sàng, bạn khởi chạy module điều phối AI:

```bash
python app.py
```

### Quy trình Xử lý nội tại:
1. **Tiền xử lý Truy vấn**: Hệ thống nhận câu lệnh gốc của người dùng, đưa qua bộ lọc của `RequestRewriter` sử dụng vector store Chroma để chuẩn hóa thực thể.
2. **Lập kế hoạch & Thực thi**: Tác tử SQL Agent (Ollama Llama3) nhận yêu cầu đã chuẩn hóa, sinh truy vấn SQL để lấy kết quả từ MySQL, và tự động gọi công cụ `allocate_task` khi cần thiết để trả lời người dùng bằng ngôn ngữ tự nhiên.
