"""
Sample Enterprise Dataset generator for SphereAI.
Contains 54 raw rows (52 valid after removing 2 duplicates) with rich dimensions:
- Kỳ báo cáo (2026-01, 2026-02, 2026-03)
- Kênh tiếp cận (Website, Đối tác, Trực tiếp B2B, Hội thảo)
- Giai đoạn (Prospecting, Qualification, Proposal, Negotiation, Closed Won, Closed Lost)
- Phụ trách (4 nhân sự)
- Giá trị dự kiến (VNĐ), Chi phí triển khai (VNĐ), Lợi nhuận kỳ vọng (VNĐ)
- Intentional dirty data (2 duplicates, 5 missing cells, 2 whitespace cells, 1 negative value) for Step 2 & Step 3 Cleaning review.
"""
from datetime import datetime, timedelta
import random
import pandas as pd

def generate_sample_crm_data(count: int = 52) -> pd.DataFrame:
    random.seed(42)
    now = datetime.now()

    companies = [
        "Công ty TNHH Công Nghệ Thiên Hà",
        "Tập đoàn Bán lẻ Viễn Đông",
        "Công ty CP Giải pháp Số NextWave",
        "Chuỗi Nhà hàng & Khách sạn Sài Gòn Star",
        "Công ty Logistics Toàn Cầu Apex",
        "Ngân hàng TMCP Phương Đông",
        "Công ty Dược phẩm & Y tế Hoa Sen",
        "Tập đoàn Xây dựng Minh Phát",
        "Công ty FinTech PayFast Việt Nam",
        "Công ty Giáo dục Trực tuyến EduSmart",
        "Tổng công ty May mặc Thời Trang Việt",
        "Công ty Năng lượng Xanh SolarEco",
        "Chuỗi Siêu thị Thực phẩm GreenMart",
        "Công ty Phần mềm Trí tuệ Nhân tạo V-AI",
        "Tập đoàn Sản xuất Công nghiệp An Phú"
    ]

    channels = ["Website & Inbound", "Đối tác chiến lược", "Đội ngũ B2B Trực tiếp", "Hội thảo & Sự kiện"]
    stages = [
        ("Prospecting", 0.20),
        ("Qualification", 0.35),
        ("Proposal", 0.55),
        ("Negotiation", 0.80),
        ("Closed Won", 1.00),
        ("Closed Lost", 0.00),
    ]
    sales_reps = ["Lê Hữu Đạt", "Nguyễn Thu Trang", "Trần Đình Trọng", "Phạm Hải Yến"]
    solutions = [
        "Hệ thống Quản trị ERP Cloud",
        "Nền tảng Phân tích Dữ liệu AI",
        "Hạ tầng Điện toán Đám mây",
        "Giải pháp Tự động hóa Quy trình",
        "Gói Bảo mật & Quản trị Dữ liệu"
    ]
    months = ["2026-01", "2026-02", "2026-03"]

    rows = []
    for i in range(1, count + 1):
        company = random.choice(companies)
        solution = random.choice(solutions)
        channel = random.choice(channels)
        stage, prob = random.choice(stages)
        rep = random.choice(sales_reps)
        ym = months[0] if i <= 15 else (months[1] if i <= 33 else months[2])

        amount = random.randint(4, 90) * 10_000_000
        cost = int(round(amount * random.uniform(0.45, 0.68), -5))
        expected_profit = amount - cost

        # Cố ý tạo các lỗi dữ liệu thực tế để Bước 2 làm sạch và Bước 3 kiểm duyệt lại:
        if i in [5, 18]:
            company = f"   {company}   "
        if i in [7, 23]:
            channel = ""
        if i in [14, 38]:
            rep = ""
        if i == 31:
            amount = None
        if i == 42:
            amount = -180_000_000

        rows.append({
            "Mã hồ sơ": f"HS-{1000 + i}",
            "Kỳ dữ liệu": ym,
            "Khách hàng / Đơn vị": company,
            "Hạng mục / Giải pháp": f"{solution} - {company.split()[-1]}",
            "Kênh / Nguồn": channel,
            "Giai đoạn / Trạng thái": stage,
            "Nhân sự phụ trách": rep,
            "Giá trị (VNĐ)": amount,
            "Chi phí (VNĐ)": cost,
            "Lợi nhuận dự kiến (VNĐ)": expected_profit
        })

    # Thêm 2 dòng trùng lặp cố ý
    dup1 = dict(rows[3])
    rows.append(dup1)

    dup2 = dict(rows[10])
    dup2["Hạng mục / Giải pháp"] = dup2["Hạng mục / Giải pháp"] + " (Bản nhập trùng mã)"
    rows.append(dup2)

    return pd.DataFrame(rows)
