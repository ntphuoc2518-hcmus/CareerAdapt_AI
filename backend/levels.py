"""The 0-3 skill scale: one name, career stage and proof rule per level, shared by every result."""
from __future__ import annotations

# The exam tier that proves a level is the rule in engine/exam_grader.verified_level.
LEVELS = (
    {"level": 0, "name": "Chưa bắt đầu", "stage": "Chưa có bằng chứng", "meaning": "Chưa làm được bài ở độ khó Cơ bản, hoặc bỏ trống.", "proof": "Chưa có bài làm nào chứng minh kỹ năng này."},
    {"level": 1, "name": "Nền tảng", "stage": "Đang học", "meaning": "Làm được các thao tác cơ bản khi có hướng dẫn.", "proof": "Đạt từ 70/100 ở câu độ khó Cơ bản, hoặc đạt một phần ở câu Trung bình."},
    {"level": 2, "name": "Sẵn sàng thực tập", "stage": "Intern", "meaning": "Tự làm được việc thường gặp của thực tập sinh trên dữ liệu thật.", "proof": "Đạt từ 70/100 ở câu độ khó Trung bình, hoặc đạt một phần ở câu Khó."},
    {"level": 3, "name": "Sẵn sàng đầu nghề", "stage": "Fresher", "meaning": "Xử lý được bài toán khó hơn và giải thích được cách làm.", "proof": "Đạt từ 70/100 ở câu độ khó Khó."},
)
LEVEL_NAMES = {item["level"]: item["name"] for item in LEVELS}
MAX_LEVEL = 3
