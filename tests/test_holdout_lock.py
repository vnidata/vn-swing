"""
Kiểm tra cơ chế an toàn: Khóa cứng phân vùng Holdout (2025-01-01 trở đi).
Chặn đứng việc look-ahead và p-hacking trên tập holdout.
"""
import pytest
from vnswing.research.cli import main as cli_main

def test_holdout_violation_raises_error():
    # Cố tình chạy với end-date thuộc vùng holdout (2025-06-30) mà không có --unlock-holdout
    bad_args = [
        "--synthetic",
        "--fast",
        "--end-date", "2025-06-30",
        "--holdout-start", "2025-01-01"
    ]
    with pytest.raises(PermissionError) as exc_info:
        cli_main(bad_args)
    assert "[HOLDOUT VIOLATION]" in str(exc_info.value)

def test_holdout_respected_in_walkforward(capsys):
    # Chạy walkforward không có --unlock-holdout -> phải tự động dừng trước 2025
    args = [
        "--synthetic",
        "--fast",
        "--jobs", "1",
        "--holdout-start", "2025-01-01"
    ]
    oos, picks = cli_main(args)
    captured = capsys.readouterr().out
    assert "[HOLDOUT LOCK]" in captured
    test_years = [p[0] for p in picks]
    assert all(y < 2025 for y in test_years), f"Các năm test phải hoàn toàn trước 2025, thực tế: {test_years}"
