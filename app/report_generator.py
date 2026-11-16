"""
Report Generator module:
1. Generates Cleaned Excel (.xlsx)
2. Renders a high-resolution Blue-Tone Visual Dashboard PNG using Pillow (with automatic text-fitting so numbers never overflow boxes and full Vietnamese Unicode font support) and embeds it directly into the Word Report (.docx).
3. Sets standard Vietnamese font (Times New Roman / Arial) across all Word styles, paragraphs, runs, and tables.
"""
from datetime import datetime
import io
import math
import os
import pandas as pd
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
from openpyxl.styles import Font, PatternFill, Alignment
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from typing import Dict, Any, Tuple


def _sanitize_vn_text(text: Any) -> str:
    """Chuẩn hóa chuỗi tiếng Việt, thay thế các ký tự đặc biệt dễ gây lỗi ô vuông trên font hệ thống."""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("<strong>", "").replace("</strong>", "")
    s = s.replace("<em>", "").replace("</em>", "")
    s = s.replace("➔", "->").replace("➜", "->").replace("⟶", "->")
    s = s.replace("•", "-").replace("·", "-")
    return s.strip()


def _load_vn_font(size: int, bold: bool = False):
    """Tải font hỗ trợ đầy đủ tiếng Việt Unicode (Ưu tiên font đóng gói sẵn trong app/fonts cho cả Vercel Linux & Windows)."""
    local_fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    local_candidates = ["arialbd.ttf"] if bold else ["arial.ttf"]
    for fn in local_candidates:
        fp = os.path.join(local_fonts_dir, fn)
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue

    windir = os.environ.get("WINDIR", "C:/Windows")
    fonts_dir = os.path.join(windir, "Fonts")
    candidates = (
        ["segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf", "timesbd.ttf", "calibrib.ttf"]
        if bold else
        ["segoeui.ttf", "arial.ttf", "tahoma.ttf", "times.ttf", "calibri.ttf"]
    )
    for fn in candidates:
        fp = os.path.join(fonts_dir, fn)
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{fn}", size)
        except Exception:
            continue

    linux_candidates = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    )
    for lfp in linux_candidates:
        if os.path.exists(lfp):
            try:
                return ImageFont.truetype(lfp, size)
            except Exception:
                continue

    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _measure_text(draw: Any, text: str, font) -> float:
    try:
        return float(draw.textlength(text, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return float(bbox[2] - bbox[0])


def _fit_text_and_font(
    draw: Any,
    raw_text: Any,
    max_width: int,
    base_size: int,
    bold: bool = False,
    min_size: int = 11
) -> Tuple[str, Any]:
    """
    Tự động thu nhỏ cỡ chữ hoặc cắt gọn có dấu '...' nếu chuỗi số/chữ quá dài,
    đảm bảo 100% KHÔNG BAO GIỜ tràn ra ngoài khung ô (max_width).
    """
    text = _sanitize_vn_text(raw_text)
    if not text:
        return "", _load_vn_font(base_size, bold=bold)

    for sz in range(base_size, min_size - 1, -1):
        font = _load_vn_font(sz, bold=bold)
        if _measure_text(draw, text, font) <= max_width:
            return text, font

    # Nếu ở cỡ chữ nhỏ nhất vẫn dài hơn max_width thì cắt gọn kèm '...'
    font = _load_vn_font(min_size, bold=bold)
    trimmed = text
    while len(trimmed) > 3 and _measure_text(draw, trimmed + "...", font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "..." if trimmed != text else trimmed), font


def _fmt_compact_axis(val: float) -> str:
    """Định dạng số trục Y gọn gàng để không tràn vào biểu đồ."""
    v = abs(float(val))
    sign = "-" if val < 0 else ""
    if v == 0:
        return "0"
    if v >= 1e9:
        return f"{sign}{v/1e9:.1f} Tỷ".replace(".", ",")
    if v >= 1e6:
        return f"{sign}{v/1e6:.0f} Tr" if v >= 1e7 else f"{sign}{v/1e6:.1f} Tr".replace(".", ",")
    if v >= 1e3:
        return f"{sign}{v/1e3:.0f} N"
    return f"{sign}{v:.0f}"


def render_dashboard_image_png(dash: Dict[str, Any], active_view: Dict[str, Any]) -> io.BytesIO:
    """
    Vẽ hình ảnh trực quan toàn bộ Dashboard (Tone Xanh Dương) độ phân giải cao (1440x1040)
    để nhúng trực tiếp vào Báo cáo Word (.docx) trình cấp trên.
    Tất cả chữ và số đều được đo độ rộng tự động để KHÔNG BAO GIỜ tràn khỏi ô.
    """
    W, H = 1440, 1040
    img = Image.new("RGB", (W, H), (240, 246, 255))
    draw = ImageDraw.Draw(img)

    # 1. Header
    title_raw = dash.get("dashboard_title", "Dashboard Phân Tích Quản Trị Doanh Nghiệp")
    sub_raw = active_view.get("header_subtitle", "")
    title_str, f_title = _fit_text_and_font(draw, title_raw, W - 64, 25, bold=True, min_size=18)
    sub_str, f_sub = _fit_text_and_font(draw, sub_raw, W - 64, 14, bold=False, min_size=11)
    draw.text((32, 22), title_str, fill=(15, 23, 42), font=f_title)
    draw.text((32, 58), sub_str, fill=(71, 85, 105), font=f_sub)

    # 2. Row of 4 KPI Cards (Blue Top Border #2563EB, Blue Numbers #1D4ED8)
    kpis = active_view.get("kpis", [])[:4]
    gap = 18
    start_x = 32
    card_w = (W - 64 - 3 * gap) // 4  # 330px each
    card_h = 152
    y_kpi = 92
    inner_kpi_w = card_w - 32  # 298px max text width inside card

    for i, k in enumerate(kpis):
        x0 = start_x + i * (card_w + gap)
        x1 = x0 + card_w
        y1 = y_kpi + card_h
        draw.rounded_rectangle([x0, y_kpi, x1, y1], radius=12, fill=(255, 255, 255), outline=(191, 219, 254), width=2)
        draw.rounded_rectangle([x0, y_kpi, x1, y_kpi + 6], radius=3, fill=(37, 99, 235))

        lbl_txt, f_lbl = _fit_text_and_font(draw, k.get("label", ""), inner_kpi_w, 14, bold=True, min_size=11)
        val_txt, f_val = _fit_text_and_font(draw, k.get("value", ""), inner_kpi_w, 24, bold=True, min_size=14)
        sub_txt, f_unit = _fit_text_and_font(draw, k.get("sub", ""), inner_kpi_w, 12, bold=False, min_size=10)
        cmp_txt, f_cmp = _fit_text_and_font(draw, k.get("comparison_html", ""), inner_kpi_w, 13, bold=True, min_size=10)

        draw.text((x0 + 16, y_kpi + 16), lbl_txt, fill=(30, 41, 59), font=f_lbl)
        draw.text((x0 + 16, y_kpi + 46), val_txt, fill=(29, 78, 216), font=f_val)
        draw.text((x0 + 16, y_kpi + 92), sub_txt, fill=(100, 116, 139), font=f_unit)
        draw.text((x0 + 16, y_kpi + 116), cmp_txt, fill=(37, 99, 235), font=f_cmp)

    # 3. 2x2 Grid of 4 Visual Cards
    grid_gap = 20
    grid_w = (W - 64 - grid_gap) // 2  # 678px each
    grid_h = 365
    row1_y = 264
    row2_y = 648
    col1_x = 32
    col2_x = 32 + grid_w + grid_gap
    card_inner_w = grid_w - 40

    # --- CARD 1 (Top-Left): Trend Line/Area Chart ---
    draw.rounded_rectangle([col1_x, row1_y, col1_x + grid_w, row1_y + grid_h], radius=14, fill=(255, 255, 255), outline=(191, 219, 254), width=2)
    trend = dash.get("trend_chart", {})
    t_title, f_ct1 = _fit_text_and_font(draw, trend.get("title", "Diễn biến theo kỳ"), card_inner_w, 17, bold=True, min_size=13)
    t_sub, f_cs1 = _fit_text_and_font(draw, trend.get("subtitle", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col1_x + 20, row1_y + 16), t_title, fill=(15, 23, 42), font=f_ct1)
    draw.text((col1_x + 20, row1_y + 42), t_sub, fill=(100, 116, 139), font=f_cs1)

    t_labels = trend.get("labels", [])
    t_vals = [float(v) for v in trend.get("values", [])] if trend.get("values") else [0.0]
    max_tv = max(t_vals + [1.0])
    plot_x0, plot_y0 = col1_x + 92, row1_y + 82
    plot_x1, plot_y1 = col1_x + grid_w - 32, row1_y + grid_h - 48
    f_axis = _load_vn_font(12, bold=False)

    for g_i in range(4):
        gy = plot_y0 + int((plot_y1 - plot_y0) * g_i / 3)
        draw.line([(plot_x0, gy), (plot_x1, gy)], fill=(226, 232, 240), width=1)
        g_val = max_tv * (1 - g_i / 3)
        lbl_v = _fmt_compact_axis(g_val)
        lbl_w = _measure_text(draw, lbl_v, f_axis)
        draw.text((max(col1_x + 14, plot_x0 - 10 - lbl_w), gy - 8), lbl_v, fill=(71, 85, 105), font=f_axis)

    if len(t_vals) >= 1:
        pts = []
        for idx, v in enumerate(t_vals):
            px = plot_x0 + int((plot_x1 - plot_x0) * idx / max(1, len(t_vals) - 1)) if len(t_vals) > 1 else (plot_x0 + plot_x1) // 2
            py = plot_y1 - int((plot_y1 - plot_y0) * (max(0.0, v) / max_tv))
            pts.append((px, py))
        if len(pts) >= 2:
            poly = [(pts[0][0], plot_y1)] + pts + [(pts[-1][0], plot_y1)]
            draw.polygon(poly, fill=(219, 234, 254))
            draw.line(pts, fill=(37, 99, 235), width=4)
        for idx, (px, py) in enumerate(pts):
            draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(29, 78, 216))
            if idx < len(t_labels):
                xlbl = _sanitize_vn_text(t_labels[idx])[:10]
                xw = _measure_text(draw, xlbl, f_axis)
                draw.text((px - xw / 2, plot_y1 + 10), xlbl, fill=(51, 65, 85), font=f_axis)

    # --- CARD 2 (Top-Right): Doughnut Chart + Legend ---
    draw.rounded_rectangle([col2_x, row1_y, col2_x + grid_w, row1_y + grid_h], radius=14, fill=(255, 255, 255), outline=(191, 219, 254), width=2)
    cost_st = active_view.get("cost_structure", {})
    c_title, f_ct2 = _fit_text_and_font(draw, cost_st.get("title", "Cơ cấu tỷ trọng"), card_inner_w, 17, bold=True, min_size=13)
    c_sub, f_cs2 = _fit_text_and_font(draw, cost_st.get("subtitle", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col2_x + 20, row1_y + 16), c_title, fill=(15, 23, 42), font=f_ct2)
    draw.text((col2_x + 20, row1_y + 42), c_sub, fill=(100, 116, 139), font=f_cs2)

    c_items = cost_st.get("items", [])[:5]
    pie_box = [col2_x + 24, row1_y + 90, col2_x + 224, row1_y + 290]
    start_ang = -90.0
    rgb_palette = [(30, 58, 138), (37, 99, 235), (59, 130, 246), (96, 165, 250), (147, 197, 253)]
    for idx, item in enumerate(c_items):
        sweep = max(4.0, float(item.get("pct", 0)) * 3.6)
        col_rgb = rgb_palette[idx % len(rgb_palette)]
        draw.pieslice(pie_box, start=start_ang, end=start_ang + sweep, fill=col_rgb, outline=(255, 255, 255), width=2)
        start_ang += sweep
    draw.ellipse([col2_x + 74, row1_y + 140, col2_x + 174, row1_y + 240], fill=(255, 255, 255))

    leg_x = col2_x + 248
    leg_max_w = (col2_x + grid_w - 20) - (leg_x + 20)  # ~390px
    leg_y = row1_y + 78
    for idx, item in enumerate(c_items):
        cy = leg_y + idx * 52
        col_rgb = rgb_palette[idx % len(rgb_palette)]
        draw.ellipse([leg_x, cy + 4, leg_x + 12, cy + 16], fill=col_rgb)
        top_line_raw = f"{item.get('label', '')} ({item.get('pct_str', '')})"
        top_line_txt, f_leg_top = _fit_text_and_font(draw, top_line_raw, leg_max_w, 13, bold=False, min_size=10)
        val_line_txt, f_leg_val = _fit_text_and_font(draw, item.get("formatted_value", ""), leg_max_w, 14, bold=True, min_size=11)
        draw.text((leg_x + 20, cy), top_line_txt, fill=(51, 65, 85), font=f_leg_top)
        draw.text((leg_x + 20, cy + 20), val_line_txt, fill=(29, 78, 216), font=f_leg_val)

    # --- CARD 3 (Bottom-Left): Horizontal Contribution Bars (2-line safe layout so numbers never overflow) ---
    draw.rounded_rectangle([col1_x, row2_y, col1_x + grid_w, row2_y + grid_h], radius=14, fill=(255, 255, 255), outline=(191, 219, 254), width=2)
    rev_st = active_view.get("revenue_contribution", {})
    r_title, f_ct3 = _fit_text_and_font(draw, rev_st.get("title", "Đóng góp theo nhóm"), card_inner_w, 17, bold=True, min_size=13)
    r_sub, f_cs3 = _fit_text_and_font(draw, rev_st.get("subtitle", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col1_x + 20, row2_y + 16), r_title, fill=(15, 23, 42), font=f_ct3)
    draw.text((col1_x + 20, row2_y + 42), r_sub, fill=(100, 116, 139), font=f_cs3)

    r_items = rev_st.get("items", [])[:5]
    bar_left = col1_x + 20
    bar_right = col1_x + grid_w - 20
    bar_total_w = bar_right - bar_left
    for idx, item in enumerate(r_items):
        by = row2_y + 72 + idx * 45
        val_txt, f_v = _fit_text_and_font(draw, item.get("formatted_value", ""), int(bar_total_w * 0.48), 13, bold=True, min_size=10)
        val_w = _measure_text(draw, val_txt, f_v)
        lbl_max_w = int(bar_total_w - val_w - 16)
        lbl_txt, f_l = _fit_text_and_font(draw, item.get("label", ""), lbl_max_w, 13, bold=False, min_size=10)

        draw.text((bar_left, by), lbl_txt, fill=(30, 41, 59), font=f_l)
        draw.text((bar_right - val_w, by), val_txt, fill=(29, 78, 216), font=f_v)

        track_y0, track_y1 = by + 22, by + 34
        draw.rounded_rectangle([bar_left, track_y0, bar_right, track_y1], radius=6, fill=(219, 234, 254))
        fill_w = int(bar_total_w * (min(100.0, max(4.0, float(item.get("bar_pct", 10)))) / 100.0))
        draw.rounded_rectangle([bar_left, track_y0, bar_left + max(12, fill_w), track_y1], radius=6, fill=(37, 99, 235))

    foot3_txt, f_foot3 = _fit_text_and_font(draw, rev_st.get("footer", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col1_x + 20, row2_y + grid_h - 28), foot3_txt, fill=(100, 116, 139), font=f_foot3)

    # --- CARD 4 (Bottom-Right): Horizontal Delta / Variance Bars (2-line safe layout) ---
    draw.rounded_rectangle([col2_x, row2_y, col2_x + grid_w, row2_y + grid_h], radius=14, fill=(255, 255, 255), outline=(191, 219, 254), width=2)
    delta_st = active_view.get("revenue_delta", {})
    d_title, f_ct4 = _fit_text_and_font(draw, delta_st.get("title", "Nhóm làm thay đổi kết quả"), card_inner_w, 17, bold=True, min_size=13)
    d_sub, f_cs4 = _fit_text_and_font(draw, delta_st.get("subtitle", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col2_x + 20, row2_y + 16), d_title, fill=(15, 23, 42), font=f_ct4)
    draw.text((col2_x + 20, row2_y + 42), d_sub, fill=(100, 116, 139), font=f_cs4)

    d_items = delta_st.get("items", [])[:5]
    d_left = col2_x + 20
    d_right = col2_x + grid_w - 20
    d_total_w = d_right - d_left
    for idx, item in enumerate(d_items):
        by = row2_y + 72 + idx * 45
        val_txt, f_v = _fit_text_and_font(draw, item.get("formatted_delta", ""), int(d_total_w * 0.48), 13, bold=True, min_size=10)
        val_w = _measure_text(draw, val_txt, f_v)
        lbl_max_w = int(d_total_w - val_w - 16)
        lbl_txt, f_l = _fit_text_and_font(draw, item.get("label", ""), lbl_max_w, 13, bold=False, min_size=10)

        is_neg = bool(item.get("is_negative"))
        val_color = (124, 58, 237) if is_neg else (29, 78, 216)
        bar_col = (124, 58, 237) if is_neg else (37, 99, 235)

        draw.text((d_left, by), lbl_txt, fill=(30, 41, 59), font=f_l)
        draw.text((d_right - val_w, by), val_txt, fill=val_color, font=f_v)

        track_y0, track_y1 = by + 22, by + 34
        draw.rounded_rectangle([d_left, track_y0, d_right, track_y1], radius=6, fill=(219, 234, 254))
        fill_w = int(d_total_w * (min(100.0, max(4.0, float(item.get("bar_pct", 10)))) / 100.0))
        draw.rounded_rectangle([d_left, track_y0, d_left + max(12, fill_w), track_y1], radius=6, fill=bar_col)

    foot4_txt, f_foot4 = _fit_text_and_font(draw, delta_st.get("footer", ""), card_inner_w, 12, bold=False, min_size=10)
    draw.text((col2_x + 20, row2_y + grid_h - 28), foot4_txt, fill=(100, 116, 139), font=f_foot4)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _set_run_vn_font(run, font_name: str = "Times New Roman", size_pt: float = 11.0, bold: bool = False, italic: bool = False, color_rgb: Tuple[int, int, int] = None):
    """Đặt phông chữ chuẩn tiếng Việt (Times New Roman) cho mọi bảng mã XML (ascii, hAnsi, eastAsia, cs) trong Word."""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color_rgb:
        run.font.color.rgb = RGBColor(*color_rgb)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:eastAsia"), font_name)
    rFonts.set(qn("w:cs"), font_name)


def _configure_docx_vn_styles(doc: Document, font_name: str = "Times New Roman"):
    """Thiết lập phông chữ mặc định toàn bộ văn bản Word là Times New Roman chuẩn tiếng Việt."""
    for style_name in ["Normal", "Heading 1", "Heading 2", "Heading 3", "List Bullet"]:
        if style_name in doc.styles:
            st = doc.styles[style_name]
            st.font.name = font_name
            rPr = st.element.get_or_add_rPr()
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is None:
                rFonts = OxmlElement("w:rFonts")
                rPr.insert(0, rFonts)
            rFonts.set(qn("w:ascii"), font_name)
            rFonts.set(qn("w:hAnsi"), font_name)
            rFonts.set(qn("w:eastAsia"), font_name)
            rFonts.set(qn("w:cs"), font_name)


def _style_docx_table(table, col_widths_inches: list):
    """Cố định độ rộng từng cột bảng trong Word, đặt padding ô và phông chữ tiếng Việt để số liệu không bao giờ tràn ô."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Header shading
    for c_idx, cell in enumerate(table.rows[0].cells):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "1E3A8A")
        tcPr.append(shd)
        for p in cell.paragraphs:
            for r in p.runs:
                _set_run_vn_font(r, size_pt=10.5, bold=True, color_rgb=(255, 255, 255))

    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            if c_idx < len(col_widths_inches):
                cell.width = Inches(col_widths_inches[c_idx])
            if r_idx > 0:
                for p in cell.paragraphs:
                    for r in p.runs:
                        is_b = bool(r.bold)
                        col_rgb = None
                        if r.font.color and r.font.color.rgb:
                            rgb_val = r.font.color.rgb
                            col_rgb = (rgb_val[0], rgb_val[1], rgb_val[2])
                        _set_run_vn_font(r, size_pt=10.5, bold=is_b, color_rgb=col_rgb)


def generate_excel_report(cleaned_df: pd.DataFrame, gemini_analysis: Dict[str, Any], gatekeeper: Dict[str, Any]) -> io.BytesIO:
    output = io.BytesIO()
    dash = gemini_analysis.get("dashboard_model", {})
    default_p = dash.get("default_period", "all")
    active_view = dash.get("by_period", {}).get(default_p, {})
    deep = gemini_analysis.get("report_deep_analysis", {})
    kpi_analyses = deep.get("kpi_deep_analysis", [])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        cleaned_df.to_excel(writer, sheet_name="Dữ liệu đã làm sạch", index=False)

        kpi_rows = []
        for idx, k in enumerate(active_view.get("kpis", [])):
            cmp_clean = _sanitize_vn_text(k.get("comparison_html", ""))
            analysis_txt = _sanitize_vn_text(kpi_analyses[idx] if idx < len(kpi_analyses) else "")
            kpi_rows.append({
                "Chỉ số KPI": _sanitize_vn_text(k.get("label")),
                "Giá trị kỳ báo cáo": _sanitize_vn_text(k.get("value")),
                "Đơn vị / Mô tả": _sanitize_vn_text(k.get("sub")),
                "Đối chiếu": cmp_clean,
                "Phân tích chuyên sâu": analysis_txt
            })
        if kpi_rows:
            pd.DataFrame(kpi_rows).to_excel(writer, sheet_name="4 KPIs Dashboard", index=False)

        monthly_rows = dash.get("trend_chart", {}).get("monthly_table", [])
        if monthly_rows:
            pd.DataFrame(monthly_rows).to_excel(writer, sheet_name="Diễn biến theo kỳ", index=False)

        cat_rows = []
        rev_items = active_view.get("revenue_contribution", {}).get("items", [])
        cost_map = {x["label"]: x for x in active_view.get("cost_structure", {}).get("items", [])}
        delta_map = {x["label"]: x for x in active_view.get("revenue_delta", {}).get("items", [])}
        for r_item in rev_items:
            lbl = r_item["label"]
            c_item = cost_map.get(lbl, {})
            d_item = delta_map.get(lbl, {})
            cat_rows.append({
                "Phân nhóm": _sanitize_vn_text(lbl),
                "Đóng góp quy mô": _sanitize_vn_text(r_item.get("formatted_value", "")),
                "Tỷ trọng đóng góp (%)": f"{r_item.get('share_pct', 0)}%",
                "Cơ cấu nguồn lực / Chi phí": _sanitize_vn_text(c_item.get("formatted_value", "")),
                "Tỷ trọng cơ cấu (%)": _sanitize_vn_text(c_item.get("pct_str", "")),
                "Biến động / Độ lệch": _sanitize_vn_text(d_item.get("formatted_delta", ""))
            })
        if cat_rows:
            pd.DataFrame(cat_rows).to_excel(writer, sheet_name="Phân tích theo Nhóm", index=False)

        wb = writer.book
        header_fill = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        body_font = Font(name="Arial", size=10.5)

        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    cell.font = body_font
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.row_dimensions[1].height = 26
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_len = max(max_len, len(str(cell.value)))
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max(max_len + 5, 16), 55)

    output.seek(0)
    return output


def generate_word_report(gemini_analysis: Dict[str, Any], gatekeeper: Dict[str, Any]) -> io.BytesIO:
    """
    Tạo Báo cáo Word (.docx) trình Cấp trên:
    - Sử dụng phông chữ chuẩn tiếng Việt (Times New Roman) cho toàn bộ văn bản & bảng biểu.
    - Nhúng trực tiếp hình ảnh Dashboard (đã căn chỉnh kích thước số không tràn ô).
    - Định dạng độ rộng các cột bảng hợp lý để không bị tràn số.
    """
    doc = Document()
    _configure_docx_vn_styles(doc, "Times New Roman")

    for section in doc.sections:
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    summary = gatekeeper.get("summary", {}) if gatekeeper else {}
    cmp = gatekeeper.get("comparison", {}) if gatekeeper else {}
    report_title = _sanitize_vn_text(gemini_analysis.get("report_title", "BÁO CÁO PHÂN TÍCH SÂU DASHBOARD & ĐỊNH HƯỚNG PHÁT TRIỂN TRÌNH CẤP TRÊN"))
    biz_context = _sanitize_vn_text(gemini_analysis.get("business_context", ""))
    exec_summary = _sanitize_vn_text(gemini_analysis.get("dataset_summary", ""))

    dash = gemini_analysis.get("dashboard_model", {})
    default_p = dash.get("default_period", "all")
    active_view = dash.get("by_period", {}).get(default_p, {})
    trend_chart = dash.get("trend_chart", {})
    deep = gemini_analysis.get("report_deep_analysis", {})
    roadmap = gemini_analysis.get("strategic_roadmap", {})
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Header hành chính
    header_table = doc.add_table(rows=1, cols=2)
    header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_left = header_table.rows[0].cells[0].paragraphs[0]
    c_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_l1 = c_left.add_run("HỆ THỐNG PHÂN TÍCH QUẢN TRỊ SPHEREAI\n")
    _set_run_vn_font(r_l1, size_pt=10, bold=True, color_rgb=(29, 78, 216))
    r_l2 = c_left.add_run("BỘ PHẬN PHÂN TÍCH DỮ LIỆU & CHIẾN LƯỢC")
    _set_run_vn_font(r_l2, size_pt=9.5, bold=False)

    c_right = header_table.rows[0].cells[1].paragraphs[0]
    c_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_r1 = c_right.add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n")
    _set_run_vn_font(r_r1, size_pt=10, bold=True)
    r_r2 = c_right.add_run("Độc lập - Tự do - Hạnh phúc\n")
    _set_run_vn_font(r_r2, size_pt=10, bold=True)
    r_r3 = c_right.add_run(f"Ngày lập báo cáo: {now_str}")
    _set_run_vn_font(r_r3, size_pt=9.5, italic=True)

    doc.add_paragraph()

    # Title
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(report_title.upper())
    _set_run_vn_font(title_run, size_pt=14.5, bold=True, color_rgb=(29, 78, 216))

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub_p.add_run(
        f"Kính trình: Ban Giám đốc / Cấp Lãnh đạo có thẩm quyền phê duyệt\n"
        f"Chiều phân tích trọng tâm: {_sanitize_vn_text(active_view.get('dimension_col', ''))} - Kỳ: {_sanitize_vn_text(active_view.get('period_display', ''))}"
    )
    _set_run_vn_font(sub_run, size_pt=10.5, bold=True)

    def add_vn_heading(text_str: str, level: int = 1):
        h = doc.add_heading("", level=level)
        run = h.add_run(_sanitize_vn_text(text_str))
        sz = 12.5 if level == 1 else 11.5
        col = (29, 78, 216) if level == 1 else (15, 23, 42)
        _set_run_vn_font(run, size_pt=sz, bold=True, color_rgb=col)
        return h

    def add_vn_label_val_paragraph(label_str: str, val_str: str):
        p = doc.add_paragraph()
        r1 = p.add_run(_sanitize_vn_text(label_str))
        _set_run_vn_font(r1, size_pt=11, bold=True)
        r2 = p.add_run(" " + _sanitize_vn_text(val_str))
        _set_run_vn_font(r2, size_pt=11, bold=False)
        return p

    # ==================== PHẦN I: BỐI CẢNH & TÓM TẮT ĐIỀU HÀNH ====================
    add_vn_heading("I. BỐI CẢNH DOANH NGHIỆP & TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)", level=1)
    add_vn_label_val_paragraph("1. Bối cảnh & Vấn đề doanh nghiệp đang gặp phải:", biz_context)
    add_vn_label_val_paragraph("2. Tóm tắt kết quả điều hành trình Lãnh đạo:", exec_summary)
    add_vn_label_val_paragraph(
        "3. Kết quả làm sạch & Kiểm duyệt dữ liệu đầu vào (So với file gốc):",
        f"Từ {cmp.get('before_rows', summary.get('total_records', 0))} dòng ban đầu "
        f"(Độ sạch {cmp.get('before_health_score', 100)}%) -> Sau làm sạch đạt "
        f"{summary.get('total_records', 0)} dòng hợp lệ (Độ sạch {summary.get('health_score', 100)}%, "
        f"đã lọc {cmp.get('removed_duplicates', 0)} dòng trùng và xử lý {cmp.get('filled_missing_cells', 0)} ô trống)."
    )

    # ==================== PHẦN II: TRỰC QUAN HÓA TOÀN BỘ DASHBOARD & PHÂN TÍCH 4 CHỈ SỐ KPI ====================
    add_vn_heading("II. TỔNG QUAN DASHBOARD TRỰC QUAN & PHÂN TÍCH SÂU 4 CHỈ SỐ KPI", level=1)
    add_vn_label_val_paragraph("Hình ảnh trực quan Dashboard KPI:", "Được kết xuất trực tiếp từ bộ dữ liệu sạch và bối cảnh doanh nghiệp:")

    try:
        dash_img_stream = render_dashboard_image_png(dash, active_view)
        pic_p = doc.add_paragraph()
        pic_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pic_p.add_run().add_picture(dash_img_stream, width=Inches(6.9))
    except Exception:
        pass

    add_vn_label_val_paragraph("Bảng phân tích chuyên sâu 4 chỉ số KPI trọng tâm trên Dashboard:", "")
    kpis = active_view.get("kpis", [])
    kpi_analyses = deep.get("kpi_deep_analysis", [])
    if kpis:
        t_kpi = doc.add_table(rows=len(kpis) + 1, cols=4)
        t_kpi.style = 'Table Grid'
        t_kpi.rows[0].cells[0].paragraphs[0].add_run("Chỉ số KPI")
        t_kpi.rows[0].cells[1].paragraphs[0].add_run("Giá trị đạt được")
        t_kpi.rows[0].cells[2].paragraphs[0].add_run("So sánh kỳ trước")
        t_kpi.rows[0].cells[3].paragraphs[0].add_run("Phân tích chuyên sâu & Ý nghĩa quản trị")

        for i, k in enumerate(kpis):
            r_cells = t_kpi.rows[i + 1].cells
            r_cells[0].paragraphs[0].add_run(_sanitize_vn_text(k.get("label", ""))).bold = True
            v_run = r_cells[1].paragraphs[0].add_run(_sanitize_vn_text(k.get("value", "")))
            v_run.bold = True
            v_run.font.color.rgb = RGBColor(29, 78, 216)
            r_cells[2].paragraphs[0].add_run(_sanitize_vn_text(k.get("comparison_html", "")))
            detail_str = kpi_analyses[i] if i < len(kpi_analyses) else k.get("sub", "")
            r_cells[3].paragraphs[0].add_run(_sanitize_vn_text(detail_str))
        _style_docx_table(t_kpi, [1.4, 1.4, 1.35, 2.75])
        doc.add_paragraph()

    # ==================== PHẦN III: PHÂN TÍCH SÂU 4 KHỐI BIỂU ĐỒ TRÊN DASHBOARD ====================
    add_vn_heading("III. PHÂN TÍCH CHUYÊN SÂU 4 KHỐI BIỂU ĐỒ TRÊN DASHBOARD", level=1)

    # 3.1 Biểu đồ 1
    add_vn_heading(f"1. Phân tích '{trend_chart.get('title', 'Diễn biến theo kỳ')}'", level=2)
    add_vn_label_val_paragraph("- Phân tích chuyên sâu xu hướng:", deep.get("trend_analysis", ""))

    m_table = trend_chart.get("monthly_table", [])
    if m_table:
        t_m = doc.add_table(rows=len(m_table) + 1, cols=5)
        t_m.style = 'Table Grid'
        headers_m = [
            "Kỳ dữ liệu",
            _sanitize_vn_text(dash.get("m_count", {}).get("label", "Số lượng")),
            _sanitize_vn_text(dash.get("m_primary", {}).get("label", "Chỉ số chính")),
            _sanitize_vn_text(dash.get("m_secondary", {}).get("label", "Chỉ số phụ")),
            _sanitize_vn_text(dash.get("m_tertiary", {}).get("label", "Hiệu quả"))
        ]
        for c_i, col_title in enumerate(headers_m):
            t_m.rows[0].cells[c_i].paragraphs[0].add_run(col_title)
        for r_i, m_row in enumerate(m_table, 1):
            t_m.rows[r_i].cells[0].paragraphs[0].add_run(_sanitize_vn_text(m_row.get("month_display", ""))).bold = True
            t_m.rows[r_i].cells[1].paragraphs[0].add_run(_sanitize_vn_text(m_row.get("orders", "")))
            v_r = t_m.rows[r_i].cells[2].paragraphs[0].add_run(_sanitize_vn_text(m_row.get("revenue", "")))
            v_r.bold = True
            v_r.font.color.rgb = RGBColor(29, 78, 216)
            t_m.rows[r_i].cells[3].paragraphs[0].add_run(_sanitize_vn_text(m_row.get("cost", "")))
            t_m.rows[r_i].cells[4].paragraphs[0].add_run(_sanitize_vn_text(m_row.get("profit", "")))
        _style_docx_table(t_m, [1.25, 1.05, 1.55, 1.50, 1.55])
        doc.add_paragraph()

    # 3.2 Biểu đồ 2
    cost_st = active_view.get("cost_structure", {})
    add_vn_heading(f"2. Phân tích '{cost_st.get('title', 'Cơ cấu tỷ trọng')}' ({cost_st.get('subtitle', '')})", level=2)
    add_vn_label_val_paragraph("- Phân tích chuyên sâu cơ cấu:", deep.get("cost_structure_analysis", ""))

    cost_items = cost_st.get("items", [])
    if cost_items:
        t_c = doc.add_table(rows=len(cost_items) + 1, cols=3)
        t_c.style = 'Table Grid'
        t_c.rows[0].cells[0].paragraphs[0].add_run("Phân nhóm")
        t_c.rows[0].cells[1].paragraphs[0].add_run("Giá trị phân bổ")
        t_c.rows[0].cells[2].paragraphs[0].add_run("Tỷ trọng (%)")
        for r_i, c_item in enumerate(cost_items, 1):
            t_c.rows[r_i].cells[0].paragraphs[0].add_run(_sanitize_vn_text(c_item.get("label", ""))).bold = True
            t_c.rows[r_i].cells[1].paragraphs[0].add_run(_sanitize_vn_text(c_item.get("formatted_value", ""))).bold = True
            t_c.rows[r_i].cells[2].paragraphs[0].add_run(_sanitize_vn_text(c_item.get("pct_str", "")))
        _style_docx_table(t_c, [2.6, 2.3, 2.0])
        doc.add_paragraph()

    # 3.3 Biểu đồ 3
    rev_st = active_view.get("revenue_contribution", {})
    add_vn_heading(f"3. Phân tích '{rev_st.get('title', 'Đóng góp quy mô')}' ({rev_st.get('subtitle', '')})", level=2)
    add_vn_label_val_paragraph("- Phân tích chuyên sâu đóng góp:", deep.get("revenue_contribution_analysis", ""))

    rev_items = rev_st.get("items", [])
    if rev_items:
        t_r = doc.add_table(rows=len(rev_items) + 1, cols=3)
        t_r.style = 'Table Grid'
        t_r.rows[0].cells[0].paragraphs[0].add_run("Phân nhóm (Xếp hạng giảm dần)")
        t_r.rows[0].cells[1].paragraphs[0].add_run("Giá trị đóng góp")
        t_r.rows[0].cells[2].paragraphs[0].add_run("Tỷ trọng đóng góp (%)")
        for r_i, r_item in enumerate(rev_items, 1):
            t_r.rows[r_i].cells[0].paragraphs[0].add_run(_sanitize_vn_text(r_item.get("label", ""))).bold = True
            vr = t_r.rows[r_i].cells[1].paragraphs[0].add_run(_sanitize_vn_text(r_item.get("formatted_value", "")))
            vr.bold = True
            vr.font.color.rgb = RGBColor(29, 78, 216)
            t_r.rows[r_i].cells[2].paragraphs[0].add_run(f"{r_item.get('share_pct', 0)}%")
        _style_docx_table(t_r, [2.6, 2.3, 2.0])
        doc.add_paragraph()

    # 3.4 Biểu đồ 4
    delta_st = active_view.get("revenue_delta", {})
    add_vn_heading(f"4. Phân tích '{delta_st.get('title', 'Nhóm làm thay đổi kết quả')}' ({delta_st.get('subtitle', '')})", level=2)
    add_vn_label_val_paragraph("- Tổng hợp biến động / Độ lệch:", delta_st.get("summary_line", ""))
    add_vn_label_val_paragraph("- Phân tích sâu nguyên nhân tăng/giảm & điểm nghẽn:", deep.get("revenue_delta_analysis", ""))

    delta_items = delta_st.get("items", [])
    if delta_items:
        t_d = doc.add_table(rows=len(delta_items) + 1, cols=3)
        t_d.style = 'Table Grid'
        t_d.rows[0].cells[0].paragraphs[0].add_run("Phân nhóm")
        t_d.rows[0].cells[1].paragraphs[0].add_run("Mức biến động / Độ lệch")
        t_d.rows[0].cells[2].paragraphs[0].add_run("Đánh giá tác động")
        for r_i, d_item in enumerate(delta_items, 1):
            t_d.rows[r_i].cells[0].paragraphs[0].add_run(_sanitize_vn_text(d_item.get("label", ""))).bold = True
            d_run = t_d.rows[r_i].cells[1].paragraphs[0].add_run(_sanitize_vn_text(d_item.get("formatted_delta", "")))
            d_run.bold = True
            if d_item.get("is_negative"):
                d_run.font.color.rgb = RGBColor(124, 58, 237)
                t_d.rows[r_i].cells[2].paragraphs[0].add_run("Dưới chuẩn / Sụt giảm (Thanh tím - Điểm nghẽn cần xử lý)")
            else:
                d_run.font.color.rgb = RGBColor(29, 78, 216)
                t_d.rows[r_i].cells[2].paragraphs[0].add_run("Vượt chuẩn / Tăng trưởng dương (Thanh xanh dương)")
        _style_docx_table(t_d, [2.1, 2.0, 2.8])
        doc.add_paragraph()

    # ==================== PHẦN IV: ĐỊNH HƯỚNG PHÁT TRIỂN TIẾP THEO & KIẾN NGHỊ TRÌNH CẤP TRÊN ====================
    add_vn_heading("IV. ĐỊNH HƯỚNG PHÁT TRIỂN TIẾP THEO & KIẾN NGHỊ TRÌNH CẤP TRÊN PHÊ DUYỆT", level=1)

    bottlenecks = roadmap.get("bottlenecks_and_risks", [])
    if bottlenecks:
        add_vn_label_val_paragraph("1. Các điểm nghẽn & rủi ro trọng yếu đúc kết từ Dashboard:", "")
        for b in bottlenecks:
            p = doc.add_paragraph(style='List Bullet')
            r = p.add_run(_sanitize_vn_text(b))
            _set_run_vn_font(r, size_pt=11)

    short_term = roadmap.get("short_term_actions", [])
    if short_term:
        add_vn_label_val_paragraph("2. Giải pháp hành động ngắn hạn (30 ngày tới):", "")
        for s_item in short_term:
            p = doc.add_paragraph(style='List Bullet')
            r = p.add_run(_sanitize_vn_text(s_item))
            _set_run_vn_font(r, size_pt=11)

    long_term = roadmap.get("medium_long_term_orientation", [])
    if long_term:
        add_vn_label_val_paragraph("3. Định hướng phát triển trung và dài hạn (Quý tới / 6 - 12 tháng):", "")
        for l_item in long_term:
            p = doc.add_paragraph(style='List Bullet')
            r = p.add_run(_sanitize_vn_text(l_item))
            _set_run_vn_font(r, size_pt=11)

    proposals = roadmap.get("proposals_for_upper_management", [])
    if proposals:
        add_vn_label_val_paragraph("4. Kiến nghị & Đề xuất trình Cấp trên / Ban Giám đốc phê duyệt:", "")
        for prop in proposals:
            p = doc.add_paragraph(style='List Bullet')
            r = p.add_run(_sanitize_vn_text(prop))
            _set_run_vn_font(r, size_pt=11, bold=True)

    doc.add_paragraph()
    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_left = sig_table.rows[0].cells[0].paragraphs[0]
    sig_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rl_s1 = sig_left.add_run("NGƯỜI LẬP BÁO CÁO / ĐƠN VỊ TRÌNH\n")
    _set_run_vn_font(rl_s1, size_pt=10.5, bold=True)
    rl_s2 = sig_left.add_run("(Ký và ghi rõ họ tên)\n\n\n\n")
    _set_run_vn_font(rl_s2, size_pt=10, italic=True)

    sig_right = sig_table.rows[0].cells[1].paragraphs[0]
    sig_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr_s1 = sig_right.add_run("Ý KIẾN PHÊ DUYỆT CỦA CẤP TRÊN / BAN GIÁM ĐỐC\n")
    _set_run_vn_font(rr_s1, size_pt=10.5, bold=True)
    rr_s2 = sig_right.add_run("(Phê duyệt định hướng & giao chỉ tiêu thực hiện)\n\n\n\n")
    _set_run_vn_font(rr_s2, size_pt=10, italic=True)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output
