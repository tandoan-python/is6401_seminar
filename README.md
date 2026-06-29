# Hướng dẫn Cài đặt và Chạy Ứng dụng MES Agent

Hệ thống MES Agent tích hợp trí tuệ nhân tạo (LLM Agent) giúp hỗ trợ truy vấn, tương tác với cơ sở dữ liệu hệ thống điều hành sản xuất (MES) bằng ngôn ngữ tự nhiên và thực hiện các tác vụ quản lý.

---

## 📌 Các tính năng cốt lõi của dự án

1. **Quản lý Cấu hình**: Hệ thống đọc các thiết lập kết nối cơ sở dữ liệu (MySQL) và hệ số quy mô sinh dữ liệu từ file `.env` thông qua module `config.py`.
2. **Khởi tạo và Mô phỏng Dữ liệu**: Module `database_init.py` thiết lập 16 bảng thực thể liên quan đến quy trình sản xuất (đơn hàng, kho bãi, vật liệu, nhiệm vụ may/cắt...) và tự động sinh dữ liệu kiểm thử thực tế dựa trên thư viện Faker kết hợp hệ số quy mô (`SCALE_FACTOR`).
3. **Chuẩn hóa Thực thể (Request Rewriter)**: Sử dụng HuggingFace Embeddings (`all-MiniLM-L6-v2`) và cơ sở dữ liệu vector Chroma để chuẩn hóa các tên thực thể không đồng nhất trong câu truy vấn của người dùng nhằm giảm thiểu sai lệch thông tin trước khi đưa vào LLM.
4. **Các Công cụ Tích hợp (Custom Tools)**: Hệ thống cung cấp các công cụ nội bộ cho Agent để trực tiếp tương tác với dữ liệu MES, bao gồm:
   - `find_order_details`: Tra cứu thông tin chi tiết của đơn hàng.
   - `allocate_task`: Tự động phân bổ nhiệm vụ cắt và may cho các nhóm làm việc.
   - `store_materials`: Tự động nhập kho vật liệu.
   - `complete_task`: Báo cáo hoàn thành các nhiệm vụ sản xuất.
   - `get_busy_workers`: Truy xuất trạng thái các nhóm làm việc và số lượng nhiệm vụ đang thực hiện.
5. **Điều phối Tác tử (Agent Orchestration)**: Xây dựng quy trình xử lý đa bước (Multi-step Dynamical Operations Planner) sử dụng mô hình LLM từ Ollama (`llama3`). Agent có khả năng lên kế hoạch sử dụng các công cụ (tools) hoặc sinh câu truy vấn SQL trực tiếp để giải quyết yêu cầu của người dùng.
6. **Giao diện Người dùng (Web UI)**: Cung cấp giao diện tương tác qua trình duyệt sử dụng thư viện Gradio, hỗ trợ trực quan hóa quy trình suy nghĩ (Streaming Thought Process) và tải về dữ liệu báo cáo dạng CSV.

---

## 🛠️ Yêu cầu Hệ thống

- **Hệ điều hành**: Windows, macOS hoặc Linux.
- **Python**: Phiên bản 3.10 trở lên.
- **MySQL Server**: Đã cài đặt phần mềm và đang chạy dịch vụ MySQL.
- **Ollama**: Đã cài đặt phần mềm Ollama và tải sẵn mô hình `llama3`.
  - Lệnh tải mô hình: `ollama run llama3`

---

## 🚀 Hướng dẫn Cài đặt

### Bước 1: Tạo môi trường ảo (Virtual Environment)
Mở Terminal hoặc Command Prompt tại thư mục gốc của dự án và chạy lệnh sau:

- **Windows**:
  ```cmd
  python -m venv venv
  ```
- **macOS/Linux**:
  ```bash
  python3 -m venv venv
  ```

### Bước 2: Kích hoạt môi trường ảo
- **Windows (Command Prompt)**:
  ```cmd
  venv\Scripts\activate
  ```
- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **macOS/Linux**:
  ```bash
  source venv/bin/activate
  ```
*(Lưu ý: Sau khi kích hoạt thành công, bạn sẽ thấy tiền tố `(venv)` xuất hiện ở đầu dòng lệnh).*

### Bước 3: Cài đặt thư viện
Với môi trường ảo đã được kích hoạt, cài đặt các gói phụ thuộc cần thiết từ file `requirements.txt`:
```bash
pip install -r requirements.txt
```

### Bước 4: Cấu hình Cơ sở dữ liệu
1. Mở công cụ quản lý MySQL của bạn và tạo một cơ sở dữ liệu mới (ví dụ `mes_database`):
   ```sql
   CREATE DATABASE mes_database;
   ```
2. Tạo file `.env` tại thư mục gốc của dự án (hoặc đổi tên từ file `env_sample`) và thiết lập các thông số cấu hình:
   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=mật_khẩu_mysql_của_bạn
   DB_NAME=mes_database
   SCALE_FACTOR=50
   ```
   *(Tham số `SCALE_FACTOR` quy định số lượng bản ghi giả lập được sinh ra. Tùy chỉnh theo tài nguyên phần cứng của bạn).*

---

## 🏃 Hướng dẫn Khởi chạy Hệ thống

### Bước 1: Khởi tạo Cơ sở dữ liệu
Chạy script `database_init.py` để tạo các bảng thực thể và sinh dữ liệu giả lập. Việc này chỉ cần thực hiện một lần khi thiết lập hệ thống ban đầu hoặc khi cần đặt lại dữ liệu gốc.
```bash
python database_init.py
```
*(Đợi hệ thống chạy hoàn tất và hiển thị thông báo thành công trên màn hình console).*

### Bước 2: Chạy ứng dụng MES Agent
Khởi động giao diện người dùng bằng cách chạy script `app.py`:
```bash
python app.py
```
Sau khi khởi động thành công, Terminal sẽ hiển thị đường dẫn truy cập cục bộ (thường là `http://0.0.0.0:7860` hoặc `http://127.0.0.0:7860`). Mở đường dẫn này trên trình duyệt web của bạn để bắt đầu sử dụng Hệ thống MES Agent Assistant.
