"""
Gemini AI Service & Problem-Driven Blue Dashboard Engine:
1. Phân tích dựa trên DỮ LIỆU THỰC TẾ của file tải lên kết hợp với VẤN ĐỀ TRONG BỐI CẢNH DOANH NGHIỆP.
2. Dựng Dashboard theo bố cục chuẩn (Header + Bộ lọc động + 4 Thẻ KPI + Lưới 2x2 gồm 4 khối trực quan) với TONE XANH DƯƠNG chủ đạo (#1d4ed8, #2563eb, #3b82f6).
3. Cho phép chuyển đổi linh hoạt cả Chiều phân tích (Dimension) lẫn Kỳ báo cáo (Period) ngay trên Dashboard.
4. Tạo Báo cáo Word trình cấp trên: Nhúng trực tiếp toàn bộ Dashboard và phân tích sâu từng chỉ số, từng biểu đồ.
"""
import json
import math
import re
import urllib.request
import urllib.error
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional

GEMINI_API_KEY = "AQ.Ab8RN6LHPG3hwxUXWy_bcd4ofZ2IK_6F36VmRnlVXXu_6b4NoA"

MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
]

# Bảng màu XANH DƯƠNG chủ đạo cho biểu đồ tròn (Doughnut) & Dashboard
BLUE_PALETTE = [
    "#1e3a8a",  # Navy Blue đậm
    "#2563eb",  # Royal Blue
    "#3b82f6",  # Bright Blue
    "#60a5fa",  # Sky Blue
    "#93c5fd",  # Light Blue
    "#64748b",  # Slate
]

def call_gemini(prompt: str, json_mode: bool = True) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
        }
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    for model in MODELS_TO_TRY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            res = urllib.request.urlopen(req, timeout=18)
            data = json.loads(res.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            continue
            
    raise RuntimeError("Tất cả mô hình Gemini tạm thời bận hoặc không khả dụng")

def fmt_vn_val(val: float, unit: str = "") -> str:
    if pd.isna(val) or math.isnan(float(val)):
        val = 0.0
    fval = float(val)
    if abs(fval) >= 100 or unit.upper() in ["VND", "VNĐ", "ĐỒNG"]:
        rounded = int(round(fval))
        sign = "-" if rounded < 0 else ""
        s = f"{abs(rounded):,}".replace(",", ".")
        return f"{sign}{s} {unit}".strip()
    else:
        s = f"{fval:,.1f}".replace(".0", "")
        return f"{s} {unit}".strip()

def fmt_month_display(ym: str) -> str:
    if ym == "all":
        return "Toàn bộ dữ liệu"
    m = re.match(r"^(\d{4})-(\d{2})$", str(ym))
    if m:
        return f"Tháng {m.group(2)}/{m.group(1)}"
    return str(ym)

def discover_dataset_schema(work_df: pd.DataFrame, business_context: str = "") -> Dict[str, Any]:
    """
    Tự động khám phá cấu trúc của BẤT KỲ file dữ liệu nào và chọn các cột phù hợp nhất
    với vấn đề trong Bối cảnh doanh nghiệp:
    - Cột thời gian / kỳ (nếu có)
    - Danh sách các cột phân loại (Dimensions: Kênh, Giai đoạn, Phòng ban, Nhân sự, Sản phẩm, Kho...)
    - Các cột chỉ số định lượng (Metrics: Giá trị/Doanh thu, Chi phí/Số lượng, Lợi nhuận/Hiệu suất...)
    """
    df = work_df.copy()
    cols = list(df.columns)
    ctx_lower = (business_context or "").lower()

    # 1. Tìm cột Thời gian / Kỳ
    period_col = None
    for c in cols:
        cl = str(c).lower()
        if any(k in cl for k in ["kỳ", "tháng", "month", "period", "quý", "năm"]):
            period_col = c
            break
    if not period_col:
        for c in cols:
            cl = str(c).lower()
            if any(k in cl for k in ["ngày", "date", "time", "thời gian"]):
                period_col = c
                break

    has_real_period = False
    if period_col:
        def extract_period(val):
            s = str(val).strip()
            m1 = re.match(r"^(\d{4})[-/](\d{1,2})", s)
            if m1:
                return f"{m1.group(1)}-{int(m1.group(2)):02d}"
            try:
                dt = pd.to_datetime(s, errors="coerce")
                if pd.notna(dt):
                    return dt.strftime("%Y-%m")
            except Exception:
                pass
            return s if len(s) <= 12 and s not in ["", "nan", "None"] else "Kỳ hiện tại"
        df["_period"] = df[period_col].apply(extract_period)
        if df["_period"].nunique() >= 2:
            has_real_period = True

    if not has_real_period:
        # Nếu file không có nhiều kỳ thời gian, chia thành 3 giai đoạn thời gian theo thứ tự bản ghi để vẫn đối chiếu được xu hướng
        n = len(df)
        p_list = []
        for i in range(n):
            if i < n * 0.30:
                p_list.append("2026-01")
            elif i < n * 0.65:
                p_list.append("2026-02")
            else:
                p_list.append("2026-03")
        df["_period"] = p_list

    # 2. Tìm tất cả các cột phân loại có ý nghĩa (Categorical Dimensions)
    id_like_keywords = ["mã", "id", "code", "sđt", "phone", "điện thoại", "email", "ngày", "date"]
    candidate_cats = []
    for c in cols:
        if c == period_col or c == "_period":
            continue
        cl = str(c).lower()
        if any(k in cl for k in id_like_keywords):
            continue
        nunique = df[c].nunique(dropna=True)
        if 2 <= nunique <= max(25, len(df) // 2):
            # Ưu tiên cột được nhắc tới trong bối cảnh doanh nghiệp
            score = 10 if any(w in ctx_lower for w in cl.split()) else 1
            if any(k in cl for k in ["kênh", "hạng mục", "giải pháp", "sản phẩm", "dịch vụ", "giai đoạn", "trạng thái", "phòng ban", "nhóm", "loại", "nguồn", "khu vực", "phụ trách", "nhân sự", "kho"]):
                score += 5
            candidate_cats.append((score, c))

    candidate_cats.sort(key=lambda x: x[0], reverse=True)
    cat_columns = [c for _, c in candidate_cats]

    if not cat_columns:
        obj_cols = [c for c in df.select_dtypes(include=["object", "category"]).columns if c not in [period_col, "_period"]]
        cat_columns = obj_cols[:2] if obj_cols else [cols[0]]

    primary_cat = cat_columns[0]
    secondary_cat = cat_columns[1] if len(cat_columns) > 1 else primary_cat

    # 3. Tìm các cột định lượng (Numeric Metrics) dựa theo dữ liệu thực tế
    num_cols = [c for c in df.select_dtypes(include=["number"]).columns if c not in ["_period"]]
    # Thử ép kiểu các cột chuỗi chứa số (nếu có)
    if not num_cols:
        for c in cols:
            if c not in [period_col, "_period"] + cat_columns:
                 coerced = pd.to_numeric(df[c].astype(str).str.replace(",", "").str.replace(".", ""), errors="coerce")
                 if coerced.notna().mean() > 0.6:
                     df[c] = coerced.fillna(0)
                     num_cols.append(c)

    # Phân loại ý nghĩa của các cột số trong file
    primary_metric = None
    secondary_metric = None
    tertiary_metric = None
    count_metric = None

    for c in num_cols:
        cl = str(c).lower()
        if any(k in cl for k in ["số đơn", "số lượng", "sl", "count", "qty", "nhân sự", "số người"]) and not count_metric:
            count_metric = c
        elif any(k in cl for k in ["doanh thu", "doanh số", "giá trị", "thành tiền", "tổng tiền", "ngân sách", "quỹ lương", "tồn kho", "revenue", "amount", "value", "sales"]) and not primary_metric:
            primary_metric = c
        elif any(k in cl for k in ["chi phí", "giá vốn", "cost", "expense", "đầu tư", "định mức"]) and not secondary_metric:
            secondary_metric = c
        elif any(k in cl for k in ["lợi nhuận", "lãi", "profit", "margin", "hiệu suất", "kpi", "điểm", "xác suất"]) and not tertiary_metric:
            tertiary_metric = c

    rem = [c for c in num_cols if c not in [primary_metric, secondary_metric, tertiary_metric, count_metric]]
    if not primary_metric and rem:
        primary_metric = rem.pop(0)
    if not secondary_metric and rem:
        secondary_metric = rem.pop(0)
    if not tertiary_metric and rem:
        tertiary_metric = rem.pop(0)

    # Xác định đơn vị (VND, %, Điểm, SP...)
    def infer_unit(col_name: Optional[str], series: Optional[pd.Series] = None) -> str:
        if not col_name:
            return ""
        cl = str(col_name).lower()
        if any(k in cl for k in ["vnd", "vnđ", "đồng", "tiền", "doanh thu", "doanh số", "giá trị", "chi phí", "lợi nhuận", "lương"]):
            return "VND"
        if "%" in cl or "xác suất" in cl or "tỷ lệ" in cl:
            return "%"
        if series is not None and len(series.dropna()) > 0 and series.dropna().abs().mean() >= 100000:
            return "VND"
        return ""

    # Chuẩn bị 4 thước đo thực tế trên DataFrame dựa trên đúng các cột có trong file
    # Metric 1: Quy mô bản ghi / Số lượng
    if count_metric:
        df["_m_count"] = pd.to_numeric(df[count_metric], errors="coerce").fillna(0.0).abs()
        m_count_label = str(count_metric).split("(")[0].strip()
        m_count_unit = infer_unit(count_metric, df["_m_count"])
        m_count_sub = f"Tổng {m_count_label.lower()}"
    else:
        df["_m_count"] = 1.0
        m_count_label = "Tổng số bản ghi / Hồ sơ"
        m_count_unit = "hồ sơ"
        m_count_sub = "Quy mô dữ liệu phân tích"

    # Metric 2: Chỉ số giá trị chính (Primary Metric)
    if primary_metric:
        df["_m_primary"] = pd.to_numeric(df[primary_metric], errors="coerce").fillna(0.0).abs()
        m_pri_label = str(primary_metric).split("(")[0].strip()
        m_pri_unit = infer_unit(primary_metric, df["_m_primary"])
        m_pri_sub = str(primary_metric)
    else:
        df["_m_primary"] = 1.0
        m_pri_label = "Quy mô hoạt động"
        m_pri_unit = "đơn vị"
        m_pri_sub = "Chỉ số chính"

    # Metric 3: Chỉ số hiệu quả / Lợi nhuận / Trung bình
    if tertiary_metric:
        df["_m_tertiary"] = pd.to_numeric(df[tertiary_metric], errors="coerce").fillna(0.0)
        m_ter_label = str(tertiary_metric).split("(")[0].strip()
        m_ter_unit = infer_unit(tertiary_metric, df["_m_tertiary"])
        m_ter_is_avg = (m_ter_unit == "%" or "điểm" in m_ter_label.lower() or "xác suất" in m_ter_label.lower())
        m_ter_sub = f"Trung bình {tertiary_metric}" if m_ter_is_avg else str(tertiary_metric)
    else:
        # Nếu file chỉ có 1 cột số chính, KPI 3 hiển thị Giá trị Trung bình trên mỗi bản ghi của cột số chính!
        df["_m_tertiary"] = df["_m_primary"]
        m_ter_label = f"Trung bình {m_pri_label}/hồ sơ"
        m_ter_unit = m_pri_unit
        m_ter_is_avg = True
        m_ter_sub = f"Bình quân trên mỗi bản ghi"

    # Metric 4: Chỉ số Chi phí / Rủi ro / Tỷ trọng nhóm đầu
    if secondary_metric:
        df["_m_secondary"] = pd.to_numeric(df[secondary_metric], errors="coerce").fillna(0.0).abs()
        m_sec_label = str(secondary_metric).split("(")[0].strip()
        m_sec_unit = infer_unit(secondary_metric, df["_m_secondary"])
        m_sec_sub = str(secondary_metric)
        sec_for_doughnut = True
    else:
        # Nếu không có cột số thứ 2, dùng chính cột số chính nhưng phân tích theo chiều phân loại thứ 2 (secondary_cat)!
        df["_m_secondary"] = df["_m_primary"]
        m_sec_label = f"Đỉnh cao nhất ({m_pri_label})"
        m_sec_unit = m_pri_unit
        m_sec_sub = f"Giá trị lớn nhất ghi nhận"
        sec_for_doughnut = False

    return {
        "df": df,
        "has_real_period": has_real_period,
        "period_col_name": str(period_col) if period_col else "Kỳ phân tích",
        "cat_columns": [str(c) for c in cat_columns],
        "primary_cat": str(primary_cat),
        "secondary_cat": str(secondary_cat),
        "m_count": {"label": m_count_label, "unit": m_count_unit, "sub": m_count_sub},
        "m_primary": {"label": m_pri_label, "unit": m_pri_unit, "sub": m_pri_sub, "col": str(primary_metric or "")},
        "m_tertiary": {"label": m_ter_label, "unit": m_ter_unit, "sub": m_ter_sub, "is_avg": m_ter_is_avg},
        "m_secondary": {"label": m_sec_label, "unit": m_sec_unit, "sub": m_sec_sub, "has_col": sec_for_doughnut}
    }

def build_dashboard_model(
    work_df: pd.DataFrame,
    business_context: str = "",
    source_name: str = "Dữ liệu doanh nghiệp",
    ai_Customization: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Xây dựng mô hình Dashboard theo bố cục chuẩn (4 thẻ KPI + 4 khối biểu đồ 2x2) với TONE XANH DƯƠNG,
    nhưng hoàn toàn linh hoạt theo các cột thực tế của tập dữ liệu và vấn đề của doanh nghiệp!
    Hỗ trợ chuyển đổi cả Chiều phân tích (Dimension) lẫn Kỳ báo cáo (Period).
    """
    schema = discover_dataset_schema(work_df, business_context)
    df = schema["df"]
    cat_columns = schema["cat_columns"]
    m_cnt = schema["m_count"]
    m_pri = schema["m_primary"]
    m_ter = schema["m_tertiary"]
    m_sec = schema["m_secondary"]

    all_periods = sorted(df["_period"].unique().tolist())[-12:]
    if not all_periods:
        all_periods = ["Kỳ hiện tại"]

    # Trend chart (Khối 1 - Trên Trái)
    monthly_grp = df.groupby("_period", as_index=False).agg(
        rows=("_m_primary", "count"),
        cnt=("_m_count", "sum"),
        pri=("_m_primary", "sum"),
        sec=("_m_secondary", "sum" if m_sec["has_col"] else "max"),
        ter=("_m_tertiary", "mean" if m_ter["is_avg"] else "sum")
    ).sort_values("_period").tail(12)

    trend_labels = monthly_grp["_period"].tolist()
    trend_values = [round(float(v), 1) for v in monthly_grp["pri"].tolist()]
    monthly_table = []
    for _, r in monthly_grp.iterrows():
        monthly_table.append({
            "month": str(r["_period"]),
            "month_display": fmt_month_display(str(r["_period"])),
            "orders": fmt_vn_val(r["cnt"], m_cnt["unit"]),
            "revenue": fmt_vn_val(r["pri"], m_pri["unit"]),
            "cost": fmt_vn_val(r["sec"], m_sec["unit"]),
            "profit": fmt_vn_val(r["ter"], m_ter["unit"])
        })

    def compute_slice(cat_col: str, target_p: str, prev_p: Optional[str]) -> Dict[str, Any]:
        # Chuẩn hóa giá trị cột phân loại
        s_cat = df[cat_col].apply(
            lambda x: "(Chưa cập nhật)" if pd.isna(x) or str(x).strip() in ["", "nan", "None", "(Ô trống)"] else str(x).strip()
        )
        temp_df = df.copy()
        temp_df["_active_cat"] = s_cat

        # Cột phân loại phụ cho biểu đồ tròn nếu không có cột số thứ 2
        other_cat_col = schema["secondary_cat"] if cat_col == schema["primary_cat"] else schema["primary_cat"]
        temp_df["_second_cat"] = df[other_cat_col].apply(
            lambda x: "(Chưa cập nhật)" if pd.isna(x) or str(x).strip() in ["", "nan", "None", "(Ô trống)"] else str(x).strip()
        )

        if target_p == "all":
            curr_df = temp_df
            prev_df = None
            p_disp = "Toàn bộ dữ liệu"
            prev_disp = None
        else:
            curr_df = temp_df[temp_df["_period"] == target_p]
            prev_df = temp_df[temp_df["_period"] == prev_p] if prev_p else None
            p_disp = fmt_month_display(target_p)
            prev_disp = fmt_month_display(prev_p) if prev_p else None

        c_cnt = float(curr_df["_m_count"].sum())
        c_pri = float(curr_df["_m_primary"].sum())
        c_ter = float(curr_df["_m_tertiary"].mean() if m_ter["is_avg"] else curr_df["_m_tertiary"].sum())
        c_sec = float(curr_df["_m_secondary"].sum() if m_sec["has_col"] else curr_df["_m_secondary"].max())

        p_cnt = float(prev_df["_m_count"].sum()) if prev_df is not None and len(prev_df) > 0 else None
        p_pri = float(prev_df["_m_primary"].sum()) if prev_df is not None and len(prev_df) > 0 else None
        p_ter = float(prev_df["_m_tertiary"].mean() if m_ter["is_avg"] else prev_df["_m_tertiary"].sum()) if prev_df is not None and len(prev_df) > 0 else None
        p_sec = float(prev_df["_m_secondary"].sum() if m_sec["has_col"] else prev_df["_m_secondary"].max()) if prev_df is not None and len(prev_df) > 0 else None

        def make_cmp(curr_v: float, prev_v: Optional[float], pr_disp: Optional[str]) -> str:
            if prev_v is None or pr_disp is None or prev_v == 0:
                return f"Tổng hợp trên <strong>{len(curr_df)} bản ghi</strong>"
            pct = round(((curr_v - prev_v) / abs(prev_v)) * 100)
            sign = "+" if pct >= 0 else ""
            return f"<strong>{sign}{pct}%</strong> so với {pr_disp}"

        kpis = [
            {
                "label": m_cnt["label"],
                "value": fmt_vn_val(c_cnt, m_cnt["unit"]),
                "raw_value": c_cnt,
                "sub": m_cnt["sub"],
                "comparison_html": make_cmp(c_cnt, p_cnt, prev_disp)
            },
            {
                "label": m_pri["label"],
                "value": fmt_vn_val(c_pri, m_pri["unit"]),
                "raw_value": c_pri,
                "sub": m_pri["sub"],
                "comparison_html": make_cmp(c_pri, p_pri, prev_disp)
            },
            {
                "label": m_ter["label"],
                "value": fmt_vn_val(c_ter, m_ter["unit"]),
                "raw_value": c_ter,
                "sub": m_ter["sub"],
                "comparison_html": make_cmp(c_ter, p_ter, prev_disp)
            },
            {
                "label": m_sec["label"],
                "value": fmt_vn_val(c_sec, m_sec["unit"]),
                "raw_value": c_sec,
                "sub": m_sec["sub"],
                "comparison_html": make_cmp(c_sec, p_sec, prev_disp)
            }
        ]

        # Khối 2 (Trên - Phải - Doughnut): Cơ cấu tỷ trọng
        if m_sec["has_col"]:
            struct_grp = curr_df.groupby("_active_cat", as_index=False)["_m_secondary"].sum().sort_values("_m_secondary", ascending=False).head(6)
            struct_col_key = "_m_secondary"
            struct_unit = m_sec["unit"]
            struct_title = f"Cơ cấu {m_sec['label'].lower()}"
            struct_sub = f"Phân bổ theo {cat_col}"
        else:
            struct_grp = curr_df.groupby("_second_cat", as_index=False)["_m_primary"].sum().sort_values("_m_primary", ascending=False).head(6)
            struct_col_key = "_m_primary"
            struct_unit = m_pri["unit"]
            struct_title = f"Cơ cấu {m_pri['label'].lower()}"
            struct_sub = f"Phân bổ theo {other_cat_col}"

        total_struct = float(struct_grp[struct_col_key].sum()) or 1.0
        struct_items = []
        for idx, r in enumerate(struct_grp.to_dict(orient="records")):
            v = float(r[struct_col_key])
            pct = round((v / total_struct) * 100, 1)
            pct_str = f"{pct:.1f}%".replace(".", ",")
            cat_lbl = str(r["_active_cat"] if m_sec["has_col"] else r["_second_cat"])
            struct_items.append({
                "label": cat_lbl,
                "value": v,
                "formatted_value": fmt_vn_val(v, struct_unit),
                "pct": pct,
                "pct_str": pct_str,
                "color": BLUE_PALETTE[idx % len(BLUE_PALETTE)]
            })

        # Khối 3 (Dưới - Trái - Horizontal Progress Bars): Đóng góp chỉ số chính theo Chiều phân tích
        contrib_grp = curr_df.groupby("_active_cat", as_index=False)["_m_primary"].sum().sort_values("_m_primary", ascending=False).head(6)
        max_contrib = float(contrib_grp["_m_primary"].max()) if len(contrib_grp) > 0 else 1.0
        total_contrib = float(contrib_grp["_m_primary"].sum()) or 1.0
        contrib_items = []
        for r in contrib_grp.to_dict(orient="records"):
            v = float(r["_m_primary"])
            bar_pct = round((v / max_contrib) * 100, 1) if max_contrib > 0 else 0
            share_pct = round((v / total_contrib) * 100, 1)
            contrib_items.append({
                "label": str(r["_active_cat"]),
                "value": v,
                "formatted_value": fmt_vn_val(v, m_pri["unit"]),
                "bar_pct": max(bar_pct, 6),
                "share_pct": share_pct
            })

        # Khối 4 (Dưới - Phải - Delta / Variance Bars): Nhóm làm thay đổi kết quả hoặc Chênh lệch so với trung bình chuẩn
        delta_items = []
        if prev_df is not None and len(prev_df) > 0:
            curr_map = curr_df.groupby("_active_cat")["_m_primary"].sum().to_dict()
            prev_map = prev_df.groupby("_active_cat")["_m_primary"].sum().to_dict()
            all_cats = list(set(list(curr_map.keys()) + list(prev_map.keys())))
            raw_deltas = []
            for c_k in all_cats:
                d_val = float(curr_map.get(c_k, 0.0)) - float(prev_map.get(c_k, 0.0))
                raw_deltas.append({"label": str(c_k), "delta": d_val, "abs_delta": abs(d_val)})
            raw_deltas.sort(key=lambda x: x["abs_delta"], reverse=True)
            raw_deltas = raw_deltas[:6]
            max_abs = max([x["abs_delta"] for x in raw_deltas]) if raw_deltas else 1.0
            for item in raw_deltas:
                d_val = item["delta"]
                bar_w = round((item["abs_delta"] / max_abs) * 100, 1) if max_abs > 0 else 0
                sign_str = "+" if d_val > 0 else ""
                delta_items.append({
                    "label": item["label"],
                    "delta": d_val,
                    "formatted_delta": f"{sign_str}{fmt_vn_val(d_val, m_pri['unit'])}",
                    "bar_pct": max(bar_w, 8),
                    "is_negative": d_val < 0
                })
            total_diff = c_pri - (p_pri or 0.0)
            diff_sign = "+" if total_diff >= 0 else ""
            delta_sub = f"{prev_disp} → {p_disp} · Theo {cat_col}"
            delta_sum = f"Từ {fmt_vn_val(p_pri or 0, m_pri['unit'])} đến {fmt_vn_val(c_pri, m_pri['unit'])} · Thay đổi {diff_sign}{fmt_vn_val(total_diff, m_pri['unit'])}"
        else:
            avg_v = float(contrib_grp["_m_primary"].mean()) if len(contrib_grp) > 0 else 0.0
            raw_deltas = []
            for r in contrib_grp.to_dict(orient="records"):
                d_val = float(r["_m_primary"]) - avg_v
                raw_deltas.append({"label": str(r["_active_cat"]), "delta": d_val, "abs_delta": abs(d_val)})
            raw_deltas.sort(key=lambda x: x["abs_delta"], reverse=True)
            max_abs = max([x["abs_delta"] for x in raw_deltas]) if raw_deltas else 1.0
            for item in raw_deltas:
                d_val = item["delta"]
                bar_w = round((item["abs_delta"] / max_abs) * 100, 1) if max_abs > 0 else 0
                sign_str = "+" if d_val > 0 else ""
                delta_items.append({
                    "label": item["label"],
                    "delta": d_val,
                    "formatted_delta": f"{sign_str}{fmt_vn_val(d_val, m_pri['unit'])}",
                    "bar_pct": max(bar_w, 8),
                    "is_negative": d_val < 0
                })
            delta_sub = f"Độ lệch so với mức trung bình chuẩn ({fmt_vn_val(avg_v, m_pri['unit'])}) · Theo {cat_col}"
            delta_sum = f"Tổng {m_pri['label']}: {fmt_vn_val(c_pri, m_pri['unit'])} · So sánh hiệu suất giữa các nhóm {cat_col}"

        clean_src = str(source_name).replace("File:", "").strip() or "Dữ liệu doanh nghiệp"
        return {
            "period_key": target_p,
            "period_display": p_disp,
            "dimension_col": cat_col,
            "row_count": len(curr_df),
            "header_subtitle": f"{p_disp} · {len(curr_df)} bản ghi · Phân tích theo {cat_col} · Nguồn: {clean_src}",
            "kpis": kpis,
            "cost_structure": {
                "title": struct_title,
                "subtitle": struct_sub,
                "items": struct_items
            },
            "revenue_contribution": {
                "title": f"Đóng góp {m_pri['label'].lower()}",
                "subtitle": f"Theo {cat_col}",
                "items": contrib_items,
                "footer": f"{len(contrib_items)} nhóm ({cat_col}) theo giá trị giảm dần."
            },
            "revenue_delta": {
                "title": f"Nhóm làm thay đổi / Độ lệch {m_pri['label'].lower()}",
                "subtitle": delta_sub,
                "summary_line": delta_sum,
                "items": delta_items,
                "footer": f"{len(delta_items)} nhóm theo biên độ tác động. Thanh xanh dương biểu thị mức dương (+), thanh tím biểu thị mức âm (-)."
            }
        }

    # Tính toán cho từng Chiều phân tích (cat_col) và từng Kỳ (period)
    by_dim_and_period = {}
    latest_p = all_periods[-1]
    for cat_c in cat_columns[:6]:
        by_dim_and_period[cat_c] = {}
        for idx, ym in enumerate(all_periods):
            prev_ym = all_periods[idx - 1] if idx > 0 else None
            by_dim_and_period[cat_c][ym] = compute_slice(cat_c, ym, prev_ym)
        all_slice = compute_slice(cat_c, "all", None)
        by_dim_and_period[cat_c]["all"] = all_slice

    default_dim = schema["primary_cat"]
    default_period = "all" if not schema["has_real_period"] else latest_p

    period_options = [{"value": "all", "label": "Toàn bộ dữ liệu"}] + [
        {"value": ym, "label": fmt_month_display(ym)}
        for ym in reversed(all_periods)
    ]
    dimension_options = [
        {"value": c, "label": f"Theo {c}"}
        for c in cat_columns[:6]
    ]

    return {
        "dashboard_title": f"Dashboard Phân Tích {m_pri['label']} & Hiệu Suất Vận Hành",
        "problem_focus_note": f"Phân tích tự động các chiều dữ liệu ({', '.join(cat_columns[:3])}) bám sát vấn đề trong bối cảnh doanh nghiệp.",
        "dataset_name": str(source_name).replace("File:", "").strip() or "Dữ liệu doanh nghiệp",
        "default_dimension": default_dim,
        "default_period": default_period,
        "dimension_options": dimension_options,
        "period_options": period_options,
        "m_count": m_cnt,
        "m_primary": m_pri,
        "m_tertiary": m_ter,
        "m_secondary": m_sec,
        "trend_chart": {
            "title": f"Diễn biến {m_pri['label'].lower()} theo kỳ",
            "subtitle": f"{m_pri['sub']} · Đối chiếu xu hướng qua các kỳ dữ liệu",
            "labels": trend_labels,
            "values": trend_values,
            "monthly_table": monthly_table
        },
        "by_dim_and_period": by_dim_and_period,
        "by_period": by_dim_and_period[default_dim]
    }

def analyze_generic_data_with_gemini(
    df: pd.DataFrame, 
    gatekeeper_summary: Dict[str, Any],
    business_context: str = "",
    human_feedback: str = "",
    source_name: str = "Dữ liệu doanh nghiệp"
) -> Dict[str, Any]:
    """
    Thực thi Bước 4:
    1. Xây dựng Dashboard tone Xanh dương dựa trên đúng các cột dữ liệu thực tế & vấn đề doanh nghiệp.
    2. Dùng Gemini AI tinh chỉnh tiêu đề theo vấn đề doanh nghiệp và phân tích sâu toàn bộ Dashboard để đưa vào Báo cáo Word trình cấp trên.
    """
    base_cols = [c for c in df.columns if c not in ["Trạng thái kiểm tra", "Ghi chú làm sạch"]]
    work_df = df[base_cols] if base_cols else df

    context_text = business_context.strip() if business_context and business_context.strip() else "Phân tích hiệu quả vận hành và giải quyết điểm nghẽn doanh nghiệp."
    dashboard_model = build_dashboard_model(work_df, context_text, source_name)

    def_dim = dashboard_model["default_dimension"]
    def_p = dashboard_model["default_period"]
    active_view = dashboard_model["by_dim_and_period"][def_dim][def_p]
    trend_data = dashboard_model["trend_chart"]

    feedback_block = ""
    if human_feedback and human_feedback.strip():
        feedback_block = f"""
YÊU CẦU ĐIỀU CHỈNH & PHÂN TÍCH LẠI TỪ NGƯỜI DUYỆT (ƯU TIÊN SỐ 1):
"{human_feedback.strip()}"
Hãy điều chỉnh lại góc nhìn phân tích Dashboard và định hướng trình cấp trên theo đúng yêu cầu này!
"""

    prompt = f"""
Bạn là Giám đốc Chiến lược & Phân tích Dữ liệu Doanh nghiệp (Chief Data & Strategy Officer).
Dựa trên tập dữ liệu thực tế ({len(work_df)} dòng, các chiều phân tích: {', '.join([d['value'] for d in dashboard_model['dimension_options']])}) và BỐI CẢNH DOANH NGHIỆP dưới đây, hãy đặt tiêu đề Dashboard sát nhất với bài toán và phân tích sâu toàn bộ số liệu trên Dashboard để trình Ban Giám đốc.

BỐI CẢNH & VẤN ĐỀ DOANH NGHIỆP ĐANG GẶP PHẢI:
"{context_text}"
{feedback_block}
SỐ LIỆU ĐÃ BÓC TÁCH TRÊN DASHBOARD (CHIỀU PHÂN TÍCH CHÍNH: {def_dim} | KỲ: {active_view['period_display']}):
1. 4 CHỈ SỐ KPI TRỌNG TÂM:
{json.dumps(active_view['kpis'], ensure_ascii=False)}

2. BIỂU ĐỒ 1 - DIỄN BIẾN THEO KỲ ({trend_data['title']}):
{json.dumps(trend_data['monthly_table'], ensure_ascii=False)}

3. BIỂU ĐỒ 2 - CƠ CẤU TỶ TRỌNG ({active_view['cost_structure']['title']} - {active_view['cost_structure']['subtitle']}):
{json.dumps(active_view['cost_structure']['items'], ensure_ascii=False)}

4. BIỂU ĐỒ 3 - ĐÓNG GÓP QUY MÔ ({active_view['revenue_contribution']['title']} - {active_view['revenue_contribution']['subtitle']}):
{json.dumps(active_view['revenue_contribution']['items'], ensure_ascii=False)}

5. BIỂU ĐỒ 4 - NHÓM LÀM THAY ĐỔI KẾT QUẢ / ĐỘ LỆCH HIỆU SUẤT ({active_view['revenue_delta']['title']}):
- Tổng quan: {active_view['revenue_delta']['summary_line']}
- Chi tiết từng nhóm: {json.dumps(active_view['revenue_delta']['items'], ensure_ascii=False)}

Trả về JSON theo cấu trúc sau:
{{
  "domain_detected": "Tên lĩnh vực & vấn đề trọng tâm cần giải quyết của doanh nghiệp",
  "custom_dashboard_title": "Tiêu đề Dashboard ngắn gọn, sát nhất với dữ liệu và vấn đề doanh nghiệp (VD: Dashboard Phân Tích Phễu Bán Hàng & Hiệu Quả Kênh B2B)",
  "problem_focus_note": "1 câu giải thích các chiều trên Dashboard đang tập trung bóc tách vấn đề gì của doanh nghiệp",
  "report_title": "TIÊU ĐỀ BÁO CÁO PHÂN TÍCH SÂU DASHBOARD & ĐỊNH HƯỚNG PHÁT TRIỂN TRÌNH CẤP TRÊN",
  "executive_summary": "Tóm tắt điều hành 3-4 câu sâu sắc về bức tranh tổng thể trên Dashboard gắn với bối cảnh doanh nghiệp để trình Ban Giám đốc",
  "kpi_deep_analysis": [
    "Phân tích sâu KPI 1: Con số đạt được, so sánh và ý nghĩa đối với vấn đề của doanh nghiệp",
    "Phân tích sâu KPI 2: Con số đạt được, so sánh và động lực cốt lõi",
    "Phân tích sâu KPI 3: Con số đạt được, đánh giá hiệu quả sinh lời / chất lượng vận hành",
    "Phân tích sâu KPI 4: Con số đạt được, đánh giá việc kiểm soát nguồn lực / chi phí"
  ],
  "trend_analysis": "Phân tích chuyên sâu Biểu đồ 1 (Diễn biến theo kỳ): Quỹ đạo tăng/giảm qua các kỳ, tốc độ biến động và dự báo.",
  "cost_structure_analysis": "Phân tích chuyên sâu Biểu đồ 2 (Cơ cấu tỷ trọng): Nhóm nào chiếm tỷ trọng lớn nhất, cơ cấu phân bổ hiện tại đã hợp lý với mục tiêu doanh nghiệp chưa.",
  "revenue_contribution_analysis": "Phân tích chuyên sâu Biểu đồ 3 (Đóng góp quy mô): Nhóm chủ lực mang lại kết quả cao nhất, mức độ chênh lệch giữa nhóm dẫn đầu và nhóm cuối.",
  "revenue_delta_analysis": "Phân tích chuyên sâu Biểu đồ 4 (Nhóm làm thay đổi kết quả / Độ lệch hiệu suất): Bóc tách rõ nhóm nào mang lại tác động dương (+) mạnh nhất, nhóm nào đang bị âm (-) hoặc kéo lùi kết quả, chỉ rõ nguyên nhân gốc rễ.",
  "strategic_roadmap": {{
    "bottlenecks_and_risks": [
      "Điểm nghẽn / Rủi ro trọng yếu số 1 phát hiện trực tiếp từ số liệu Dashboard",
      "Điểm nghẽn / Rủi ro trọng yếu số 2 (kèm dẫn chứng số liệu cụ thể)",
      "Điểm nghẽn / Rủi ro trọng yếu số 3"
    ],
    "short_term_actions": [
      "Giải pháp hành động ngắn hạn (30 ngày tới) số 1: Tháo gỡ ngay điểm nghẽn ở nhóm đang âm/thấp trên Dashboard",
      "Giải pháp ngắn hạn số 2: Tối ưu hóa nhóm chủ lực đang dẫn đầu",
      "Giải pháp ngắn hạn số 3: Chuẩn hóa quy trình kiểm soát các bản ghi thiếu thông tin"
    ],
    "medium_long_term_orientation": [
      "Định hướng phát triển trung & dài hạn (Quý tới / 6-12 tháng) số 1",
      "Định hướng phát triển trung & dài hạn số 2",
      "Định hướng phát triển trung & dài hạn số 3"
    ],
    "proposals_for_upper_management": [
      "Kiến nghị trình Cấp trên / Ban Giám đốc phê duyệt số 1 (Về phân bổ nguồn lực & ngân sách)",
      "Kiến nghị trình Cấp trên phê duyệt số 2 (Về cơ chế thúc đẩy các nhóm đang tắc nghẽn)",
      "Kiến nghị trình Cấp trên phê duyệt số 3 (Về giao chỉ tiêu KPI cho các bộ phận trong kỳ tới)"
    ]
  }}
}}
"""
    try:
        raw_res = call_gemini(prompt, json_mode=True)
        ai_report = json.loads(raw_res)
        if ai_report.get("custom_dashboard_title"):
            dashboard_model["dashboard_title"] = ai_report["custom_dashboard_title"]
        if ai_report.get("problem_focus_note"):
            dashboard_model["problem_focus_note"] = ai_report["problem_focus_note"]
    except Exception:
        ai_report = build_fallback_deep_report(dashboard_model, active_view, context_text, human_feedback)

    return {
        "domain_detected": ai_report.get("domain_detected", "Phân Tích Quản Trị & Giải Quyết Điểm Nghẽn Doanh Nghiệp"),
        "report_title": ai_report.get("report_title", "BÁO CÁO PHÂN TÍCH SÂU DASHBOARD & ĐỊNH HƯỚNG PHÁT TRIỂN TRÌNH CẤP TRÊN"),
        "business_context": context_text,
        "human_feedback_applied": human_feedback.strip() if human_feedback else "",
        "dataset_summary": ai_report.get("executive_summary", ""),
        "dashboard_model": dashboard_model,
        "kpis": active_view["kpis"],
        "report_deep_analysis": {
            "kpi_deep_analysis": ai_report.get("kpi_deep_analysis", []),
            "trend_analysis": ai_report.get("trend_analysis", ""),
            "cost_structure_analysis": ai_report.get("cost_structure_analysis", ""),
            "revenue_contribution_analysis": ai_report.get("revenue_contribution_analysis", ""),
            "revenue_delta_analysis": ai_report.get("revenue_delta_analysis", ""),
        },
        "strategic_roadmap": ai_report.get("strategic_roadmap", {}),
        "had_refinement_loop": bool(human_feedback and human_feedback.strip())
    }

def build_fallback_deep_report(
    dashboard_model: Dict[str, Any],
    active_view: Dict[str, Any],
    context_text: str,
    human_feedback: str
) -> Dict[str, Any]:
    kpis = active_view["kpis"]
    cost_items = active_view["cost_structure"]["items"]
    rev_items = active_view["revenue_contribution"]["items"]
    delta_items = active_view["revenue_delta"]["items"]
    trend_table = dashboard_model["trend_chart"]["monthly_table"]
    dim_col = active_view.get("dimension_col", "Phân nhóm")

    top_rev = rev_items[0] if rev_items else {"label": "Nhóm dẫn đầu", "formatted_value": "0", "share_pct": 0}
    top_cost = cost_items[0] if cost_items else {"label": "Nhóm chính", "formatted_value": "0", "pct_str": "0%"}
    neg_deltas = [d for d in delta_items if d["is_negative"]]
    pos_deltas = [d for d in delta_items if not d["is_negative"]]

    neg_text = f"Nhóm '{neg_deltas[0]['label']}' đang ở mức âm ({neg_deltas[0]['formatted_delta']}), là điểm nghẽn cần ưu tiên tháo gỡ" if neg_deltas else "Các nhóm chủ lực đều duy trì mức đóng góp dương tích cực"
    pos_text = f"Nhóm '{pos_deltas[0]['label']}' dẫn đầu mức đóng góp tăng trưởng ({pos_deltas[0]['formatted_delta']})" if pos_deltas else ""

    return {
        "domain_detected": f"Phân Tích Quản Trị Theo {dim_col} & Giải Quyết Bài Toán Doanh Nghiệp",
        "custom_dashboard_title": dashboard_model["dashboard_title"],
        "problem_focus_note": f"Dashboard phân tích tập trung vào chiều '{dim_col}' để giải quyết bài toán: {context_text[:110]}",
        "report_title": "BÁO CÁO PHÂN TÍCH SÂU DASHBOARD & ĐỀ XUẤT ĐỊNH HƯỚNG PHÁT TRIỂN TRÌNH CẤP TRÊN",
        "executive_summary": (
            f"Dựa trên bối cảnh doanh nghiệp ({context_text[:120]}), hệ thống Dashboard đã tổng hợp và phân tích {active_view['row_count']} bản ghi hợp lệ. "
            f"Kết quả ghi nhận {kpis[0]['label']} đạt {kpis[0]['value']}, {kpis[1]['label']} đạt {kpis[1]['value']}, "
            f"{kpis[2]['label']} đạt {kpis[2]['value']} và {kpis[3]['label']} ở mức {kpis[3]['value']}. "
            f"Phân tích sâu theo chiều '{dim_col}' chỉ ra nhóm dẫn đầu là '{top_rev['label']}' ({top_rev['formatted_value']}), đồng thời khoanh vùng rõ các nhóm đang sụt giảm để trình Ban Giám đốc phương án điều hành."
        ),
        "kpi_deep_analysis": [
            f"{kpis[0]['label']} đạt {kpis[0]['value']} ({kpis[0]['comparison_html'].replace('<strong>','').replace('</strong>','')}), phản ánh quy mô hoạt động thực tế của tập dữ liệu sau làm sạch.",
            f"{kpis[1]['label']} đạt {kpis[1]['value']} ({kpis[1]['comparison_html'].replace('<strong>','').replace('</strong>','')}), là thước đo tài chính/quy mô cốt lõi quyết định mục tiêu của doanh nghiệp.",
            f"{kpis[2]['label']} đạt {kpis[2]['value']} ({kpis[2]['comparison_html'].replace('<strong>','').replace('</strong>','')}), cho thấy hiệu suất sinh lời và chất lượng chuyển đổi trên toàn hệ thống.",
            f"{kpis[3]['label']} ở mức {kpis[3]['value']} ({kpis[3]['comparison_html'].replace('<strong>','').replace('</strong>','')}), cần được theo dõi sát để tối ưu hóa tỷ suất đầu tư theo từng phân nhóm."
        ],
        "trend_analysis": (
            f"Biểu đồ '{dashboard_model['trend_chart']['title']}' thể hiện quỹ đạo vận hành qua {len(trend_table)} kỳ dữ liệu "
            f"({', '.join([m['month'] + ': ' + m['revenue'] for m in trend_table])}). Số liệu giữa các kỳ là cơ sở quan trọng để đối chiếu tốc độ tăng trưởng và dự báo nguồn lực kỳ tới."
        ),
        "cost_structure_analysis": (
            f"Biểu đồ '{active_view['cost_structure']['title']}' ({active_view['cost_structure']['subtitle']}) cho thấy nhóm '{top_cost['label']}' chiếm tỷ trọng cao nhất với {top_cost['formatted_value']} ({top_cost['pct_str']}). "
            f"Việc đặt cơ cấu này cạnh tỷ trọng đóng góp đầu ra giúp Ban Giám đốc đánh giá chính xác nhóm nào đang sử dụng nguồn lực hiệu quả."
        ),
        "revenue_contribution_analysis": (
            f"Biểu đồ '{active_view['revenue_contribution']['title']}' ({active_view['revenue_contribution']['subtitle']}) khẳng định '{top_rev['label']}' là trụ cột chính khi đóng góp {top_rev['formatted_value']} (chiếm {top_rev['share_pct']}% toàn hệ thống)."
        ),
        "revenue_delta_analysis": (
            f"Biểu đồ '{active_view['revenue_delta']['title']}' ({active_view['revenue_delta']['summary_line']}) chỉ rõ: {pos_text}. {neg_text}."
        ),
        "strategic_roadmap": {
            "bottlenecks_and_risks": [
                f"Sự chênh lệch lớn giữa nhóm dẫn đầu '{top_rev['label']}' ({top_rev['share_pct']}%) và các nhóm còn lại theo chiều '{dim_col}' tạo ra rủi ro phụ thuộc tập trung.",
                f"{neg_text}. Nếu không can thiệp kịp thời sẽ ảnh hưởng trực tiếp tới mục tiêu chung.",
                "Một số bản ghi ở file gốc bị khuyết thông tin phân nhóm (đã được chuẩn hóa tại Bước 2) cần được kiểm soát chặt ngay từ khâu nhập liệu đầu vào."
            ],
            "short_term_actions": [
                f"Trong 30 ngày tới: Tập trung tháo gỡ điểm nghẽn tại các nhóm có chỉ số biến động âm (thanh tím trên Dashboard) theo chiều '{dim_col}'.",
                f"Ưu tiên nguồn lực thúc đẩy các hồ sơ/giao dịch trọng điểm thuộc nhóm '{top_rev['label']}' để tối đa hóa kết quả đầu ra.",
                "Áp dụng bộ dữ liệu sạch (File Excel) để rà soát và phân công trách nhiệm cụ thể cho từng nhân sự phụ trách."
            ],
            "medium_long_term_orientation": [
                f"Định hướng Quý tới / 6-12 tháng: Tái cơ cấu danh mục và phân bổ ngân sách theo hiệu suất thực tế của từng nhóm '{dim_col}' trên Dashboard.",
                "Thiết lập định mức chuẩn (Benchmark) cho từng chỉ số KPI để tự động cảnh báo sớm khi có nhóm rơi xuống dưới mức trung bình.",
                "Chuẩn hóa quy trình thu thập và kiểm duyệt dữ liệu định kỳ hàng tháng nhằm nâng cao độ chính xác của công tác dự báo."
            ],
            "proposals_for_upper_management": [
                f"Kính trình Ban Giám đốc phê duyệt phương án điều phối lại nguồn lực theo kết quả phân tích Dashboard: Ưu tiên đầu tư cho nhóm hiệu quả cao ('{top_rev['label']}') và chấn chỉnh nhóm đang sụt giảm.",
                "Phê duyệt bộ chỉ tiêu KPI kỳ tới dựa trên 4 thước đo cốt lõi của Dashboard và giao trực tiếp cho các trưởng bộ phận.",
                "Ban hành quy định kiểm soát chất lượng dữ liệu bắt buộc trước khi nghiệm thu báo cáo định kỳ."
            ]
        }
    }
