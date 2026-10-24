# Hướng dẫn chạy và kiểm thử Backend CareerAdapt AI (TV3)

Phần mềm Backend do **Hà Xuân Tỉnh (TV3 - Backend Developer + Tech Lead)** triển khai.

## 1. Yêu cầu môi trường
- Python 3.12+ (đã tích hợp trong `.venv`)
- Các thư viện liệt kê trong `requirements.txt`:
  - `fastapi`
  - `uvicorn`
  - `pydantic`
  - `pytest`
  - `httpx`
  - `python-multipart`
  - `psycopg2-binary`
  - `python-dotenv`

## 2. Cài đặt và kích hoạt môi trường

```powershell
# Kích hoạt virtualenv (PowerShell)
.\.venv\Scripts\Activate.ps1

# Cài đặt phụ thuộc
pip install -r requirements.txt
```

## 3. Khởi chạy Backend Server (FastAPI)

```powershell
# Chạy uvicorn server ở cổng 8000
python src/main.py

# Hoặc dùng uvicorn trực tiếp
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Sau khi chạy:
- **Tài liệu Swagger UI tương tác:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Tài liệu ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Kiểm tra sức khỏe:** [http://localhost:8000/health](http://localhost:8000/health)

## 4. Chạy kiểm thử tự động (Unit & Integration Tests)

```powershell
.\.venv\Scripts\pytest.exe -v
```

Bộ kiểm thử bao gồm:
1. `tests/test_evaluation_algorithms.py`: Kiểm thử toán học thuần (Gap, Coverage, Priority, Division-by-zero, Gate 80% + core skill).
2. `tests/test_scheduler_dag.py`: Kiểm thử đồ thị DAG (Phát hiện chu trình, thiếu tiền quyết, vượt ngân sách giờ tuần).
3. `tests/test_api_endpoints.py`: Kiểm thử toàn bộ các API F01 đến F10, kiểm tra quyền sở hữu (IDOR protection) và chống nộp trùng (Idempotency).
4. Các kiểm thử an toàn lưu trữ tệp và vòng đời dữ liệu từ TV5.
