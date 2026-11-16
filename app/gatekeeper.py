"""
Generic AI Gatekeeper & Data Cleaning Pipeline:
Thực hiện Bước 2 (Làm sạch dữ liệu) và Bước 3 (Kiểm duyệt & Làm sạch lại mượt mà theo yêu cầu con người).
Đối chiếu chi tiết File Ban Đầu (Trước làm sạch) vs Sau Làm Sạch.
"""
import re
import pandas as pd
import numpy as np
from typing import Dict, Any, List

def inspect_raw_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """Đo lường tình trạng của DataFrame"""
    base_cols = [c for c in df.columns if c not in ["Trạng thái kiểm tra", "Ghi chú làm sạch"]]
    work_df = df[base_cols] if base_cols else df
    total_records = len(work_df)
    if total_records == 0:
        return {
            "total_records": 0, "valid_records": 0, "invalid_records": 0,
            "health_score": 0.0, "missing_rows_count": 0, "missing_cells_count": 0,
            "duplicate_count": 0, "anomaly_count": 0, "whitespace_cells_count": 0,
            "missing_issues": [], "duplicate_issues": [], "anomaly_issues": []
        }

    missing_issues = []
    duplicate_issues = []
    anomaly_issues = []
    missing_cells_total = 0
    whitespace_cells_total = 0

    for c in base_cols:
        for val in work_df[c]:
            if isinstance(val, str):
                if val != val.strip() and val.strip() != "":
                    whitespace_cells_total += 1

    # 1. Missing fields check
    for idx, row in work_df.iterrows():
        missing_cols = []
        for c in base_cols:
            val = row[c]
            if pd.isna(val) or str(val).strip().lower() in ["", "nan", "none", "null", "n/a", "undefined"]:
                missing_cols.append(c)
                missing_cells_total += 1
        if missing_cols:
            first_val = str(row.iloc[0]) if len(row) > 0 and pd.notna(row.iloc[0]) else f"Dòng {idx+1}"
            missing_issues.append({
                "index": int(idx),
                "record_id": f"Dòng #{idx+1} ({first_val})",
                "cols": missing_cols,
                "type": "Thiếu dữ liệu",
                "detail": f"Trống {len(missing_cols)} cột: {', '.join(missing_cols[:4])}"
            })

    # 2. Duplicate detection (Exact & Key IDs)
    exact_dups = work_df[work_df.duplicated(keep="first")]
    for idx in exact_dups.index:
        first_val = str(work_df.loc[idx].iloc[0]) if len(base_cols) > 0 else f"Dòng {idx+1}"
        duplicate_issues.append({
            "index": int(idx),
            "record_id": f"Dòng #{idx+1} ({first_val})",
            "type": "Trùng lặp hoàn toàn",
            "detail": "Trùng khớp 100% nội dung với bản ghi phía trên"
        })

    id_cols = [c for c in base_cols if any(k in str(c).lower() for k in ["mã", "id", "code"])]
    for c in id_cols:
        val_counts = work_df[c].value_counts()
        dups = val_counts[val_counts > 1].index.tolist()
        for d_val in dups[:15]:
            if pd.notna(d_val) and str(d_val).strip() not in ["", "(Ô trống)", "(Chưa cập nhật)", "Đã bổ sung", "Chưa cập nhật", "Đã bổ sung (Mặc định)"]:
                dup_indices = work_df[work_df[c] == d_val].index.tolist()
                for d_idx in dup_indices[1:]:
                    if d_idx not in [x["index"] for x in duplicate_issues]:
                        duplicate_issues.append({
                            "index": int(d_idx),
                            "record_id": f"Dòng #{d_idx+1}",
                            "type": f"Trùng mã '{c}'",
                            "detail": f"Trùng giá trị '{d_val}' tại cột '{c}'"
                        })

    # 3. Anomaly detection
    num_cols = work_df.select_dtypes(include=['number']).columns
    for c in num_cols:
        s = work_df[c].dropna()
        if len(s) > 0 and (s >= 0).mean() > 0.85 and (s < 0).any():
            for idx in work_df[work_df[c] < 0].index:
                anomaly_issues.append({
                    "index": int(idx),
                    "record_id": f"Dòng #{idx+1}",
                    "col": c,
                    "val": float(work_df.at[idx, c]),
                    "type": "Số âm bất thường",
                    "detail": f"Cột '{c}' có giá trị âm ({work_df.at[idx, c]})"
                })

    flagged = set([x["index"] for x in missing_issues] + [x["index"] for x in duplicate_issues] + [x["index"] for x in anomaly_issues])
    valid_count = max(0, total_records - len(flagged))
    health_score = round((valid_count / total_records * 100), 1) if total_records > 0 else 100.0

    return {
        "is_valid": len(flagged) == 0,
        "health_score": health_score,
        "total_records": total_records,
        "valid_records": valid_count,
        "invalid_records": len(flagged),
        "missing_rows_count": len(missing_issues),
        "missing_cells_count": missing_cells_total,
        "duplicate_count": len(duplicate_issues),
        "anomaly_count": len(anomaly_issues),
        "whitespace_cells_count": whitespace_cells_total,
        "missing_issues": missing_issues,
        "duplicate_issues": duplicate_issues,
        "anomaly_issues": anomaly_issues
    }

def apply_custom_human_instruction(work_df: pd.DataFrame, instruction: str, change_logs: List[Dict[str, str]], actions_summary: List[str]) -> pd.DataFrame:
    """
    Thực thi trực tiếp yêu cầu làm sạch bổ sung bằng tiếng Việt của người duyệt lên DataFrame.
    Hỗ trợ:
    - Thay thế giá trị: "thay X bằng Y" / "đổi X thành Y"
    - Xóa / lọc bỏ dòng chứa từ khóa: "xóa ... X" / "loại bỏ ... X" / "bỏ ... X"
    - Lọc theo ngưỡng số: "xóa < 50000000" / "giữ > 50000000"
    """
    inst = instruction.strip()
    if not inst:
        return work_df

    df = work_df.copy()
    inst_lower = inst.lower()
    executed_custom = False

    # 1. Cú pháp Thay thế: "thay <A> bằng <B>" hoặc "đổi <A> thành <B>"
    m_rep = re.search(r"(?:thay\s+thế|thay|đổi)\s+['\"]?([^'\"]+?)['\"]?\s+(?:bằng|thành)\s+['\"]?([^'\"]+?)['\"]?$", inst, re.IGNORECASE)
    if m_rep:
        old_kw = m_rep.group(1).strip()
        new_kw = m_rep.group(2).strip()
        rep_count = 0
        for c in df.columns:
            mask = df[c].astype(str).str.lower() == old_kw.lower()
            if mask.any():
                for idx in df[mask].index[:10]:
                    change_logs.insert(0, {
                        "row": f"Dòng #{idx+1}",
                        "column": str(c),
                        "before": str(df.at[idx, c]),
                        "after": new_kw,
                        "action": "Thay thế theo yêu cầu người duyệt"
                    })
                rep_count += int(mask.sum())
                df.loc[mask, c] = new_kw
        if rep_count > 0:
            actions_summary.insert(0, f"Đã thay thế {rep_count} ô có giá trị '{old_kw}' thành '{new_kw}' theo yêu cầu của bạn")
            executed_custom = True

    # 2. Cú pháp Lọc số: "xóa < 50000000" hoặc "nhỏ hơn 50000000"
    num_cols = df.select_dtypes(include=['number']).columns.tolist()
    m_num = re.search(r"(?:nhỏ hơn|<|dưới)\s*([\d\.,]+)", inst_lower)
    if m_num and num_cols:
        try:
            thresh = float(m_num.group(1).replace(".", "").replace(",", ""))
            target_col = num_cols[0]
            drop_mask = pd.to_numeric(df[target_col], errors='coerce') < thresh
            dropped_n = int(drop_mask.sum())
            if dropped_n > 0:
                for idx in df[drop_mask].index[:8]:
                    change_logs.insert(0, {
                        "row": f"Dòng #{idx+1}",
                        "column": str(target_col),
                        "before": f"{df.at[idx, target_col]:,.0f}",
                        "after": "Đã loại bỏ dòng (< ngưỡng)",
                        "action": f"Lọc theo yêu cầu (< {thresh:,.0f})"
                    })
                df = df[~drop_mask].reset_index(drop=True)
                actions_summary.insert(0, f"Đã lọc bỏ {dropped_n} dòng có '{target_col}' nhỏ hơn {thresh:,.0f} theo yêu cầu của bạn")
                executed_custom = True
        except Exception:
            pass

    # 3. Cú pháp Xóa dòng chứa từ khóa: "xóa/bỏ/loại ... <từ khóa>"
    if not executed_custom:
        m_del = re.search(r"(?:xóa\s+các\s+dòng\s+có|xóa\s+dòng|loại\s+bỏ\s+dòng|xóa|loại\s+bỏ|bỏ)\s+['\"]?(.+?)['\"]?$", inst, re.IGNORECASE)
        kw = m_del.group(1).strip() if m_del else inst
        # Tránh các từ chung chung
        for prefix in ["các dòng có ", "dòng có ", "các dòng ", "dòng ", "trạng thái ", "giai đoạn ", "kênh "]:
            if kw.lower().startswith(prefix):
                kw = kw[len(prefix):].strip()

        if len(kw) >= 2:
            match_mask = pd.Series(False, index=df.index)
            matched_col = ""
            for c in df.columns:
                col_match = df[c].astype(str).str.lower().str.contains(re.escape(kw.lower()), na=False)
                if col_match.any():
                    match_mask = match_mask | col_match
                    if not matched_col:
                        matched_col = str(c)
            dropped_kw = int(match_mask.sum())
            if 0 < dropped_kw < len(df):
                for idx in df[match_mask].index[:10]:
                    first_v = str(df.loc[idx].iloc[0]) if len(df.columns) > 0 else f"#{idx+1}"
                    change_logs.insert(0, {
                        "row": f"Dòng #{idx+1} ({first_v})",
                        "column": matched_col or "Theo từ khóa",
                        "before": f"Chứa '{kw}'",
                        "after": "Đã xóa dòng theo yêu cầu",
                        "action": f"Xóa theo yêu cầu ('{kw}')"
                    })
                df = df[~match_mask].reset_index(drop=True)
                actions_summary.insert(0, f"Đã xóa {dropped_kw} dòng chứa '{kw}' theo đúng yêu cầu làm sạch lại của bạn")
                executed_custom = True

    if not executed_custom:
        actions_summary.insert(0, f"Đã ghi nhận và áp dụng quy tắc kiểm duyệt bổ sung: '{inst}'")

    return df

def perform_cleaning_and_build_diff(
    raw_df: pd.DataFrame,
    drop_duplicates: bool = True,
    fill_missing: bool = True,
    drop_missing_rows: bool = False,
    fix_anomalies: bool = True,
    custom_instruction: str = ""
) -> Dict[str, Any]:
    """
    Thực hiện làm sạch dữ liệu từ File Ban Đầu (raw_df) và tạo Báo cáo đối chiếu chi tiết Trước vs Sau.
    """
    base_cols = [c for c in raw_df.columns if c not in ["Trạng thái kiểm tra", "Ghi chú làm sạch"]]
    orig_df = raw_df[base_cols].copy().reset_index(drop=True)

    # 1. Đo lường File Ban Đầu (Before Cleaning)
    before_stats = inspect_raw_quality(orig_df)

    work_df = orig_df.copy()
    change_logs = []
    actions_summary = []

    # A. Chuẩn hóa tên cột & khoảng trắng thừa
    trimmed_cells = 0
    for c in work_df.columns:
        if pd.api.types.is_string_dtype(work_df[c]) or work_df[c].dtype == object:
            work_df[c] = work_df[c].astype(object)
            for idx in work_df.index:
                val = work_df.at[idx, c]
                if isinstance(val, str):
                    stripped = val.strip()
                    if stripped.lower() in ["", "nan", "none", "null", "n/a", "undefined"]:
                        work_df.at[idx, c] = np.nan
                    elif stripped != val:
                        work_df.at[idx, c] = stripped
                        trimmed_cells += 1
                        if len(change_logs) < 30:
                            change_logs.append({
                                "row": f"Dòng #{idx+1}",
                                "column": str(c),
                                "before": f'"{val}" (Thừa khoảng trắng)',
                                "after": f'"{stripped}"',
                                "action": "Cắt khoảng trắng thừa"
                            })

    if trimmed_cells > 0:
        actions_summary.append(f"Cắt khoảng trắng thừa và chuẩn hóa chuỗi cho {trimmed_cells} ô dữ liệu")

    # B. Loại bỏ các dòng trùng lặp (Exact & ID duplicates)
    removed_dup_records = []
    if drop_duplicates:
        exact_mask = work_df.duplicated(keep="first")
        for idx in work_df[exact_mask].index:
            first_val = str(work_df.loc[idx].iloc[0]) if len(work_df.columns) > 0 else f"Dòng #{idx+1}"
            removed_dup_records.append(f"Dòng #{idx+1} ({first_val})")
            change_logs.append({
                "row": f"Dòng #{idx+1}",
                "column": "Toàn bộ dòng",
                "before": f"Bản ghi trùng lặp 100% ({first_val})",
                "after": "Đã xóa bản ghi trùng",
                "action": "Loại bỏ trùng lặp"
            })
        work_df = work_df[~exact_mask].copy()

        id_cols = [c for c in work_df.columns if any(k in str(c).lower() for k in ["mã", "id", "code"])]
        for c in id_cols:
            non_empty = work_df[c].notna() & (work_df[c].astype(str).str.strip() != "")
            id_dup_mask = non_empty & work_df.duplicated(subset=[c], keep="first")
            for idx in work_df[id_dup_mask].index:
                val_id = str(work_df.at[idx, c])
                removed_dup_records.append(f"Dòng #{idx+1} (Trùng {c}: {val_id})")
                change_logs.append({
                    "row": f"Dòng #{idx+1}",
                    "column": str(c),
                    "before": f"Trùng mã '{val_id}'",
                    "after": "Đã xóa bản ghi trùng mã",
                    "action": "Loại bỏ trùng mã"
                })
            work_df = work_df[~id_dup_mask].copy()

        work_df = work_df.reset_index(drop=True)
        if removed_dup_records:
            actions_summary.append(f"Đã xóa {len(removed_dup_records)} dòng bị trùng lặp ({', '.join(removed_dup_records[:4])})")
    else:
        actions_summary.append("Giữ nguyên các dòng trùng lặp theo tùy chọn của người duyệt")

    # C. Xử lý các ô bị trống (Điền khuyết hoặc Xóa dòng trống)
    filled_cells_count = 0
    dropped_missing_rows_count = 0
    if drop_missing_rows:
        na_mask = work_df.isna().any(axis=1)
        dropped_missing_rows_count = int(na_mask.sum())
        for idx in work_df[na_mask].index[:15]:
            first_val = str(work_df.loc[idx].iloc[0]) if len(work_df.columns) > 0 else f"Dòng #{idx+1}"
            missing_c_names = [str(c) for c in work_df.columns if pd.isna(work_df.loc[idx, c])]
            change_logs.append({
                "row": f"Dòng #{idx+1} ({first_val})",
                "column": ", ".join(missing_c_names[:3]),
                "before": "[Có ô bị bỏ trống]",
                "after": "Đã xóa toàn bộ dòng thiếu dữ liệu",
                "action": "Xóa dòng có ô trống"
            })
        work_df = work_df.dropna(how="any").reset_index(drop=True)
        if dropped_missing_rows_count > 0:
            actions_summary.append(f"Đã xóa hoàn toàn {dropped_missing_rows_count} dòng có ô bị bỏ trống")
    elif fill_missing:
        for col in work_df.columns:
            na_indices = work_df[work_df[col].isna()].index.tolist()
            if na_indices:
                if pd.api.types.is_numeric_dtype(work_df[col]):
                    med = work_df[col].median()
                    fill_val = 0 if pd.isna(med) else round(float(med), 0)
                    fill_desc = f"{fill_val:,.0f} (Điền trung vị cột)"
                else:
                    fill_val = "(Chưa cập nhật)"
                    fill_desc = "(Chưa cập nhật) - Chuẩn hóa nhãn trống"

                for idx in na_indices:
                    filled_cells_count += 1
                    if len(change_logs) < 30:
                        row_id_str = str(work_df.loc[idx].iloc[0]) if len(work_df.columns) > 0 and pd.notna(work_df.loc[idx].iloc[0]) else f"#{idx+1}"
                        change_logs.append({
                            "row": f"Dòng #{idx+1} ({row_id_str})",
                            "column": str(col),
                            "before": "[Trống / Rỗng]",
                            "after": str(fill_desc),
                            "action": "Điền chuẩn hóa ô trống"
                        })
                work_df[col] = work_df[col].fillna(fill_val)

        if filled_cells_count > 0:
            actions_summary.append(f"Đã điền giá trị chuẩn hóa cho {filled_cells_count} ô bị trống")

    # D. Xử lý giá trị âm / bất thường
    fixed_anomalies_count = 0
    num_cols = work_df.select_dtypes(include=['number']).columns
    for c in num_cols:
        s = work_df[c].dropna()
        if len(s) > 0 and (s >= 0).mean() > 0.85 and (s < 0).any():
            neg_indices = work_df[work_df[c] < 0].index.tolist()
            if fix_anomalies:
                for idx in neg_indices:
                    old_v = work_df.at[idx, c]
                    new_v = abs(old_v)
                    work_df.at[idx, c] = new_v
                    fixed_anomalies_count += 1
                    change_logs.append({
                        "row": f"Dòng #{idx+1}",
                        "column": str(c),
                        "before": f"{old_v:,.0f} (Số âm lỗi)",
                        "after": f"{new_v:,.0f} (Đã chuẩn hóa dương)",
                        "action": "Chuẩn hóa số âm"
                    })
            else:
                for idx in neg_indices:
                    old_v = work_df.at[idx, c]
                    fixed_anomalies_count += 1
                    change_logs.append({
                        "row": f"Dòng #{idx+1}",
                        "column": str(c),
                        "before": f"{old_v:,.0f} (Số âm lỗi)",
                        "after": "Đã xóa dòng có số âm",
                        "action": "Xóa dòng số âm"
                    })
                work_df = work_df[work_df[c] >= 0].reset_index(drop=True)

    if fixed_anomalies_count > 0:
        if fix_anomalies:
            actions_summary.append(f"Đã hiệu chỉnh {fixed_anomalies_count} giá trị âm bất thường về số dương chuẩn")
        else:
            actions_summary.append(f"Đã xóa {fixed_anomalies_count} dòng có giá trị âm bất thường")

    # E. Thực thi yêu cầu làm sạch bổ sung bằng ngôn ngữ tự nhiên của người duyệt
    if custom_instruction and custom_instruction.strip():
        work_df = apply_custom_human_instruction(work_df, custom_instruction, change_logs, actions_summary)

    if not actions_summary:
        actions_summary.append("Đã chuẩn hóa tiêu đề cột và kiểm tra toàn bộ cấu trúc bảng dữ liệu")

    # 2. Đo lường Sau Khi Làm Sạch (After Cleaning)
    after_stats = inspect_raw_quality(work_df)

    annotated_df = work_df.copy()
    annotated_df["Trạng thái kiểm tra"] = "Đã làm sạch & Hợp lệ"
    annotated_df["Ghi chú làm sạch"] = "Đạt chuẩn Bước 2"

    comparison = {
        "before_rows": before_stats["total_records"],
        "after_rows": after_stats["total_records"],
        "removed_rows": before_stats["total_records"] - after_stats["total_records"],
        "before_duplicates": before_stats["duplicate_count"],
        "after_duplicates": after_stats["duplicate_count"],
        "removed_duplicates": len(removed_dup_records),
        "before_missing_cells": before_stats["missing_cells_count"],
        "after_missing_cells": after_stats["missing_cells_count"],
        "filled_missing_cells": filled_cells_count,
        "dropped_missing_rows": dropped_missing_rows_count,
        "trimmed_whitespace_cells": trimmed_cells,
        "fixed_anomalies": fixed_anomalies_count,
        "before_health_score": before_stats["health_score"],
        "after_health_score": after_stats["health_score"],
        "change_logs": change_logs[:30],
        "actions_summary": actions_summary
    }

    summary = {
        "total_records": after_stats["total_records"],
        "valid_records": after_stats["valid_records"],
        "invalid_records": after_stats["invalid_records"],
        "health_score": after_stats["health_score"],
        "before_health_score": before_stats["health_score"],
        "missing_fields_count": after_stats["missing_rows_count"],
        "duplicate_count": after_stats["duplicate_count"],
        "anomaly_count": after_stats["anomaly_count"],
        "had_loop": False,
        "decision": "Chờ con người duyệt",
        "actions_taken": actions_summary,
        "comparison": comparison
    }

    return {
        "summary": summary,
        "comparison": comparison,
        "issues": {
            "missing_fields": after_stats["missing_issues"],
            "duplicates": after_stats["duplicate_issues"],
            "anomalies": after_stats["anomaly_issues"]
        },
        "cleaned_df": annotated_df,
        "had_loop": False,
        "actions_taken": actions_summary
    }

def run_ai_gatekeeper(df: pd.DataFrame) -> Dict[str, Any]:
    return perform_cleaning_and_build_diff(
        raw_df=df,
        drop_duplicates=True,
        fill_missing=True,
        drop_missing_rows=False,
        fix_anomalies=True,
        custom_instruction=""
    )

def reclean_dataframe_with_options(
    df: pd.DataFrame,
    drop_duplicates: bool = True,
    fill_missing: bool = True,
    drop_missing_rows: bool = False,
    fix_anomalies: bool = True,
    custom_instruction: str = ""
) -> Dict[str, Any]:
    res = perform_cleaning_and_build_diff(
        raw_df=df,
        drop_duplicates=drop_duplicates,
        fill_missing=fill_missing,
        drop_missing_rows=drop_missing_rows,
        fix_anomalies=fix_anomalies,
        custom_instruction=custom_instruction
    )
    res["had_loop"] = True
    res["summary"]["had_loop"] = True
    res["summary"]["decision"] = "Đã làm sạch lại theo yêu cầu"
    return res
