"""
Mô-đun quản lý cấu hình và thiết lập môi trường hệ thống.
Tuân thủ tiêu chuẩn kỹ nghệ phần mềm (Software Engineering).
"""
import os
import warnings
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Tải cấu hình từ biến môi trường
load_dotenv()

# Tắt cảnh báo symlink của hệ thống bộ nhớ đệm HuggingFace trên Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Bỏ qua các cảnh báo không ảnh hưởng đến logic cốt lõi nhằm đảm bảo giao diện terminal sạch (Clean Code)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_community")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")

class Config:
    """Lớp quản lý các tham số cấu hình toàn cục của hệ thống MES Agent."""
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "mes_database")
    
    # Định dạng chuỗi kết nối SQLAlchemy (URI) với mã hóa để hỗ trợ các ký tự đặc biệt
    _encoded_user = quote_plus(DB_USER)
    _encoded_password = quote_plus(DB_PASSWORD)
    DB_URI = f"mysql+pymysql://{_encoded_user}:{_encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # Hệ số quy mô cho quá trình sinh dữ liệu giả định
    SCALE_FACTOR = int(os.getenv("SCALE_FACTOR", 50))
