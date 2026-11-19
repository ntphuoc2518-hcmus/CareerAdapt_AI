"""Every pass mark and wait of the assessment rules, in one place (audit C-08).

Before 5.46 these numbers were defined in five modules (70 / 80 / 70 / 24 h / 6 h). The modules now take
them from here, and ``GET /me/assessment-policy`` shows the same values to the learner, so what the page
says is what the code applies. This module imports only ``backend.config`` to stay free of cycles; the
entry exam's pass mark also lives in the question bank file, and ``exam_grader.validate_bank`` reports a
mismatch.
"""
from __future__ import annotations

from backend import config

# Entry exam and final assessment: total score out of 100.
EXAM_PASS_SCORE = 70.0
# One question: share of its points that proves its difficulty tier, and share that proves one tier less.
QUESTION_PASS_RATIO = 0.7
QUESTION_PARTIAL_RATIO = 0.4
# Lesson completion check (closed questions).
LESSON_CHECK_PASS_SCORE = 80.0
LESSON_QUIZ_LEVEL_CEILING = 2
LESSON_RETRY_WAIT_HOURS = 6
# Spaced-review mini-test.
MINI_TEST_PASS_SCORE = 70.0
# Final assessment: share of the JD's weight that must be met, and the wait before a retake.
FINAL_COVERAGE_REQUIRED = float(config.MIN_COVERAGE_FOR_READINESS)
FINAL_RETAKE_HOURS = 24


def describe() -> list[dict]:
    """The rules as the learner reads them, each with the number the code uses."""
    return [
        {"key": "EXAM_PASS_SCORE", "value": EXAM_PASS_SCORE, "label": "Bài kiểm tra đầu vào và bài đánh giá tổng hợp đạt khi điểm tổng từ mức này (thang 100)."},
        {"key": "QUESTION_PASS_RATIO", "value": QUESTION_PASS_RATIO, "label": "Một câu chứng minh đúng độ khó của nó khi đạt từ tỉ lệ điểm này."},
        {"key": "QUESTION_PARTIAL_RATIO", "value": QUESTION_PARTIAL_RATIO, "label": "Đạt từ tỉ lệ này (nhưng chưa tới mức trên) thì câu chứng minh thấp hơn độ khó một mức."},
        {"key": "LESSON_CHECK_PASS_SCORE", "value": LESSON_CHECK_PASS_SCORE, "label": "Bài kiểm tra hoàn thành bài học đạt khi điểm từ mức này."},
        {"key": "LESSON_QUIZ_LEVEL_CEILING", "value": LESSON_QUIZ_LEVEL_CEILING, "label": "Câu hỏi đóng xác nhận được tối đa mức này; mức 3 cần bài thực hành."},
        {"key": "LESSON_RETRY_WAIT_HOURS", "value": LESSON_RETRY_WAIT_HOURS, "label": "Số giờ chờ trước khi làm lại bài kiểm tra hoàn thành đã trượt."},
        {"key": "MINI_TEST_PASS_SCORE", "value": MINI_TEST_PASS_SCORE, "label": "Bài ôn tập định kỳ đạt khi điểm từ mức này."},
        {"key": "FINAL_COVERAGE_REQUIRED", "value": FINAL_COVERAGE_REQUIRED, "label": "Bài đánh giá tổng hợp cần đáp ứng tỉ lệ trọng số JD này."},
        {"key": "FINAL_RETAKE_HOURS", "value": FINAL_RETAKE_HOURS, "label": "Số giờ chờ trước khi làm lại bài đánh giá tổng hợp chưa đạt."},
    ]
