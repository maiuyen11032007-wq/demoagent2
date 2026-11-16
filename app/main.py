"""
FastAPI application for SphereAI Data Processing Agent (Human-in-the-Loop).
Compatible with both Local Uvicorn and Vercel Serverless Python runtime.
"""
import sys
import os
import io
import json
import math
import pickle
import tempfile
import asyncio

# Đảm bảo thư mục gốc luôn nằm trong sys.path khi chạy trên Vercel Serverless
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from app.sample_data import generate_sample_crm_data
from app.gatekeeper import run_ai_gatekeeper, reclean_dataframe_with_options
from app.gemini_service import analyze_generic_data_with_gemini, call_gemini
from app.report_generator import generate_excel_report, generate_word_report

app = FastAPI(title="SphereAI - Human-in-the-Loop Data Processing Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_CACHE_FILE = os.path.join(tempfile.gettempdir(), "sphereai_session_state.pkl")

# Global in-memory storage for current session
session_state = {
    "raw_df": None,
    "cleaned_df": None,
    "gatekeeper": None,
    "gemini_analysis": None,
    "last_source": None,
    "business_context": "",
    "stage": "idle",  # idle | awaiting_human_gatekeeper | awaiting_human_evaluation | completed
    "cleaning_loop_count": 0,
    "analysis_loop_count": 0,
    "last_human_feedback": "",
    "workflow_execution": None
}


def save_session_state():
    """Lưu trạng thái phiên vào /tmp để duy trì qua các lần gọi hàm Serverless trên Vercel."""
    try:
        with open(SESSION_CACHE_FILE, "wb") as f:
            pickle.dump(session_state, f)
    except Exception:
        pass


def restore_session_state_if_needed(auto_fallback_sample: bool = False):
    """Khôi phục trạng thái phiên từ /tmp nếu container Serverless vừa khởi tạo."""
    if session_state["cleaned_df"] is not None:
        return
    try:
        if os.path.exists(SESSION_CACHE_FILE):
            with open(SESSION_CACHE_FILE, "rb") as f:
                loaded = pickle.load(f)
                if isinstance(loaded, dict) and loaded.get("cleaned_df") is not None:
                    session_state.update(loaded)
                    return
    except Exception:
        pass

    if auto_fallback_sample and session_state["cleaned_df"] is None:
        df = generate_sample_crm_data(52)
        default_ctx = "Phân tích hiệu quả vận hành, cơ cấu chi phí và lợi nhuận theo từng phân nhóm để trình Ban Giám đốc."
        start_step1_and_step2(df, "Dữ liệu Doanh nghiệp mẫu", default_ctx)


# Disable browser caching on static files
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Đường dẫn thư mục static (Không gọi os.makedirs vì hệ thống file /var/task trên Vercel là Read-Only)
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>SphereAI Agent Running</h1>"


@app.get("/static/{file_path:path}")
async def serve_static_fallback(file_path: str):
    full_path = os.path.join(static_dir, file_path)
    if os.path.isfile(full_path):
        return FileResponse(full_path)
    raise HTTPException(status_code=404, detail="Static file not found")


def clean_dataframe_to_safe_records(df: pd.DataFrame, max_rows: int = 50):
    records = []
    subset = df.head(max_rows)
    for row in subset.to_dict(orient="records"):
        clean_row = {}
        for k, v in row.items():
            k_str = str(k)
            if v is None or pd.isna(v):
                clean_row[k_str] = ""
            elif isinstance(v, (pd.Timestamp, np.datetime64)):
                clean_row[k_str] = str(v)
            elif isinstance(v, (float, np.floating)):
                if np.isnan(v) or np.isinf(v) or math.isnan(v) or math.isinf(v):
                    clean_row[k_str] = ""
                else:
                    clean_row[k_str] = round(float(v), 4)
            elif isinstance(v, (int, np.integer)):
                clean_row[k_str] = int(v)
            else:
                clean_row[k_str] = str(v).strip()
        records.append(clean_row)
    return records


def load_dataframe_from_bytes(contents: bytes, filename: str) -> pd.DataFrame:
    filename_lower = filename.lower()
    df = None

    if filename_lower.endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
        try:
            df = pd.read_excel(io.BytesIO(contents))
        except Exception:
            try:
                df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
            except Exception:
                pass

    if df is None:
        encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252", "utf-16"]
        separators = [None, ",", ";", "\t", "|"]
        for enc in encodings:
            for sep in separators:
                try:
                    if sep:
                        df = pd.read_csv(io.BytesIO(contents), encoding=enc, sep=sep)
                    else:
                        df = pd.read_csv(io.BytesIO(contents), encoding=enc)
                    if df is not None and len(df.columns) > 1 and not df.empty:
                        break
                except Exception:
                    continue
            if df is not None and len(df.columns) > 1 and not df.empty:
                break

    if df is None or df.empty:
        try:
            df = pd.read_excel(io.BytesIO(contents))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(contents))
            except Exception as e:
                raise ValueError(f"Không thể giải mã nội dung file: {str(e)}")

    if df is None or df.empty:
        raise ValueError("File tải lên bị rỗng hoặc không có dữ liệu bảng hợp lệ.")

    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    clean_cols = []
    for i, col in enumerate(df.columns):
        c_str = str(col).strip()
        if not c_str or c_str.lower().startswith("unnamed:"):
            clean_cols.append(f"Cột_{i+1}")
        else:
            clean_cols.append(c_str)
    df.columns = clean_cols

    return df


def build_workflow_trace():
    stage = session_state["stage"]
    gk = session_state["gatekeeper"]
    analysis = session_state["gemini_analysis"]
    c_loops = session_state["cleaning_loop_count"]
    a_loops = session_state["analysis_loop_count"]
    total_rows = gk["summary"]["total_records"] if gk else 0
    health = gk["summary"]["health_score"] if gk else 100.0

    step1 = {
        "step": 1,
        "name": "Nhập dữ liệu",
        "detail": f"Đã tiếp nhận dữ liệu từ {session_state['last_source']}",
        "status": "done"
    }
    step2 = {
        "step": 2,
        "name": "Làm sạch dữ liệu",
        "detail": f"Đã chuẩn hóa dữ liệu ({total_rows} dòng)" + (f" — Đã làm sạch lại {c_loops} lần theo yêu cầu người duyệt" if c_loops > 0 else ""),
        "status": "done"
    }

    if stage == "awaiting_human_gatekeeper":
        dec1 = {
            "step": "decision_1",
            "name": "Kiểm duyệt dữ liệu (Con người duyệt)",
            "question": "Có hợp lệ?",
            "decision": "Chờ duyệt",
            "had_loop": c_loops > 0,
            "loop_message": f"⏳ Đang chờ bạn kiểm duyệt dữ liệu (Điểm chất lượng: {health}%). Hãy chọn [Có] để phân tích hoặc [Không] để làm sạch lại."
        }
        step4 = {"step": 4, "name": "Phân tích dữ liệu", "detail": "Chờ người dùng duyệt Kiểm duyệt dữ liệu", "status": "waiting"}
        dec2 = {
            "step": "decision_2",
            "name": "Đánh giá kết quả (Con người duyệt)",
            "question": "Đạt yêu cầu?",
            "decision": "Chờ",
            "had_loop": False,
            "loop_message": "Chờ hoàn tất Bước 4"
        }
        step5 = {"step": 5, "name": "Xuất báo cáo", "detail": "Chờ người dùng đánh giá kết quả đạt yêu cầu", "status": "waiting"}
    elif stage == "awaiting_human_evaluation":
        dec1 = {
            "step": "decision_1",
            "name": "Kiểm duyệt dữ liệu (Con người duyệt)",
            "question": "Có hợp lệ?",
            "decision": "Có",
            "had_loop": c_loops > 0,
            "loop_message": f"Người dùng đã duyệt: Hợp lệ [Có]" + (f" (sau {c_loops} lần làm sạch lại)" if c_loops > 0 else "")
        }
        domain_str = analysis.get("domain_detected", "") if analysis else ""
        step4 = {
            "step": 4,
            "name": "Phân tích dữ liệu",
            "detail": f"Đã tạo insight lĩnh vực '{domain_str}'" + (f" — Đã điều chỉnh & phân tích lại {a_loops} lần" if a_loops > 0 else ""),
            "status": "done"
        }
        dec2 = {
            "step": "decision_2",
            "name": "Đánh giá kết quả (Con người duyệt)",
            "question": "Đạt yêu cầu?",
            "decision": "Chờ duyệt",
            "had_loop": a_loops > 0,
            "loop_message": "⏳ Đang chờ bạn đánh giá kết quả phân tích. Hãy chọn [Có] để xuất báo cáo hoặc [Không] để yêu cầu điều chỉnh & phân tích lại."
        }
        step5 = {"step": 5, "name": "Xuất báo cáo", "detail": "Chờ người dùng xác nhận Đạt yêu cầu [Có]", "status": "waiting"}
    else:  # completed
        dec1 = {
            "step": "decision_1",
            "name": "Kiểm duyệt dữ liệu (Con người duyệt)",
            "question": "Có hợp lệ?",
            "decision": "Có",
            "had_loop": c_loops > 0,
            "loop_message": f"Người dùng đã duyệt: Hợp lệ [Có]" + (f" (sau {c_loops} lần làm sạch lại)" if c_loops > 0 else "")
        }
        domain_str = analysis.get("domain_detected", "") if analysis else ""
        step4 = {
            "step": 4,
            "name": "Phân tích dữ liệu",
            "detail": f"Đã tạo insight lĩnh vực '{domain_str}'" + (f" (điều chỉnh {a_loops} lần)" if a_loops > 0 else ""),
            "status": "done"
        }
        dec2 = {
            "step": "decision_2",
            "name": "Đánh giá kết quả (Con người duyệt)",
            "question": "Đạt yêu cầu?",
            "decision": "Có",
            "had_loop": a_loops > 0,
            "loop_message": f"Người dùng đã duyệt: Đạt yêu cầu [Có]" + (f" (sau {a_loops} lần điều chỉnh & phân tích lại)" if a_loops > 0 else "")
        }
        step5 = {
            "step": 5,
            "name": "Xuất báo cáo",
            "detail": "Đã mở khóa & hoàn tất 3 định dạng: File Excel, Dashboard, Báo cáo Word",
            "status": "done"
        }

    trace = [step1, step2, dec1, step4, dec2, step5]
    session_state["workflow_execution"] = trace
    return trace


def build_session_payload():
    cleaned_df = session_state["cleaned_df"]
    gk = session_state["gatekeeper"]
    safe_preview = clean_dataframe_to_safe_records(cleaned_df, max_rows=50) if cleaned_df is not None else []
    cols = [str(c) for c in cleaned_df.columns] if cleaned_df is not None else []
    total_rows = len(cleaned_df) if cleaned_df is not None else 0

    return {
        "stage": session_state["stage"],
        "source": session_state["last_source"],
        "business_context": session_state["business_context"],
        "cleaning_loop_count": session_state["cleaning_loop_count"],
        "analysis_loop_count": session_state["analysis_loop_count"],
        "gatekeeper": {
            "summary": gk["summary"],
            "comparison": gk.get("comparison", {}),
            "issues": gk["issues"],
            "had_loop": session_state["cleaning_loop_count"] > 0,
            "actions_taken": gk.get("actions_taken", [])
        } if gk else None,
        "gemini_analysis": session_state["gemini_analysis"],
        "workflow_trace": build_workflow_trace(),
        "preview": safe_preview,
        "columns": cols,
        "total_rows": total_rows
    }


def start_step1_and_step2(df: pd.DataFrame, source_name: str, business_context: str = ""):
    ctx_clean = business_context.strip() if business_context else ""
    gatekeeper_result = run_ai_gatekeeper(df)

    session_state["raw_df"] = df
    session_state["cleaned_df"] = gatekeeper_result["cleaned_df"]
    session_state["gatekeeper"] = gatekeeper_result
    session_state["gemini_analysis"] = None
    session_state["last_source"] = source_name
    session_state["business_context"] = ctx_clean
    session_state["stage"] = "awaiting_human_gatekeeper"
    session_state["cleaning_loop_count"] = 0
    session_state["analysis_loop_count"] = 0
    session_state["last_human_feedback"] = ""

    save_session_state()
    return build_session_payload()


class SampleRequest(BaseModel):
    business_context: Optional[str] = ""


@app.post("/api/load-sample")
async def load_sample_data(req: Optional[SampleRequest] = None):
    if not req or not req.business_context or not req.business_context.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ Bối cảnh doanh nghiệp trước khi bấm Bắt đầu phân tích!")
    try:
        ctx = req.business_context.strip()
        df = await asyncio.to_thread(generate_sample_crm_data, 52)
        res = await asyncio.to_thread(start_step1_and_step2, df, "Dữ liệu Doanh nghiệp mẫu", ctx)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi nạp mẫu: {str(e)}")


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    business_context: str = Form("")
):
    if not business_context or not business_context.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ Bối cảnh doanh nghiệp trước khi bấm Bắt đầu phân tích!")
    filename = file.filename or "uploaded_data.xlsx"
    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File tải lên bị rỗng. Vui lòng chọn file có dữ liệu.")

    try:
        df = await asyncio.to_thread(load_dataframe_from_bytes, contents, filename)
        res = await asyncio.to_thread(start_step1_and_step2, df, f"File: {filename}", business_context)
        return {"status": "success", "data": res}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý file: {str(e)}")


# ==================== HUMAN DECISION 1: KIỂM DUYỆT DỮ LIỆU (CÓ / KHÔNG) ====================

class RecleanRequest(BaseModel):
    drop_duplicates: bool = True
    fill_missing: bool = True
    drop_missing_rows: bool = False
    fix_anomalies: bool = True
    custom_instruction: Optional[str] = ""


@app.post("/api/gatekeeper/reclean")
async def human_reject_and_reclean(req: RecleanRequest):
    restore_session_state_if_needed(auto_fallback_sample=True)
    source_df = session_state["raw_df"] if session_state["raw_df"] is not None else session_state["cleaned_df"]
    if source_df is None:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu để làm sạch lại.")
    try:
        reclean_res = await asyncio.to_thread(
            reclean_dataframe_with_options,
            source_df,
            req.drop_duplicates,
            req.fill_missing,
            req.drop_missing_rows,
            req.fix_anomalies,
            req.custom_instruction or ""
        )
        session_state["cleaned_df"] = reclean_res["cleaned_df"]
        session_state["gatekeeper"] = reclean_res
        session_state["cleaning_loop_count"] += 1
        session_state["stage"] = "awaiting_human_gatekeeper"
        save_session_state()
        return {"status": "success", "data": build_session_payload()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi làm sạch lại: {str(e)}")


class ApproveGatekeeperRequest(BaseModel):
    business_context: Optional[str] = None


@app.post("/api/gatekeeper/approve")
async def human_approve_gatekeeper(req: Optional[ApproveGatekeeperRequest] = None):
    restore_session_state_if_needed(auto_fallback_sample=True)
    if session_state["cleaned_df"] is None:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu để phân tích.")
    try:
        if req and req.business_context is not None and req.business_context.strip():
            session_state["business_context"] = req.business_context.strip()

        session_state["gatekeeper"]["summary"]["decision"] = "Có (Đã được người dùng duyệt)"
        gemini_result = await asyncio.to_thread(
            analyze_generic_data_with_gemini,
            session_state["cleaned_df"],
            session_state["gatekeeper"]["summary"],
            session_state["business_context"],
            "",
            session_state["last_source"] or "Dữ liệu Doanh nghiệp mẫu"
        )
        session_state["gemini_analysis"] = gemini_result
        session_state["stage"] = "awaiting_human_evaluation"
        save_session_state()
        return {"status": "success", "data": build_session_payload()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi phân tích dữ liệu: {str(e)}")


# ==================== HUMAN DECISION 2: ĐÁNH GIÁ KẾT QUẢ (CÓ / KHÔNG) ====================

class RefineAnalysisRequest(BaseModel):
    feedback: str = ""
    business_context: Optional[str] = None


@app.post("/api/evaluation/refine")
async def human_reject_and_refine_analysis(req: RefineAnalysisRequest):
    restore_session_state_if_needed(auto_fallback_sample=True)
    if session_state["cleaned_df"] is None:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu trong hệ thống.")
    try:
        if req.business_context is not None and req.business_context.strip():
            session_state["business_context"] = req.business_context.strip()

        session_state["analysis_loop_count"] += 1
        session_state["last_human_feedback"] = req.feedback.strip()

        gemini_result = await asyncio.to_thread(
            analyze_generic_data_with_gemini,
            session_state["cleaned_df"],
            session_state["gatekeeper"]["summary"],
            session_state["business_context"],
            req.feedback.strip(),
            session_state["last_source"] or "Dữ liệu Doanh nghiệp mẫu"
        )
        session_state["gemini_analysis"] = gemini_result
        session_state["stage"] = "awaiting_human_evaluation"
        save_session_state()
        return {"status": "success", "data": build_session_payload()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi điều chỉnh phân tích: {str(e)}")


@app.post("/api/evaluation/approve")
async def human_approve_evaluation():
    restore_session_state_if_needed(auto_fallback_sample=True)
    if session_state["gemini_analysis"] is None:
        gemini_result = await asyncio.to_thread(
            analyze_generic_data_with_gemini,
            session_state["cleaned_df"],
            session_state["gatekeeper"]["summary"],
            session_state["business_context"],
            "",
            session_state["last_source"] or "Dữ liệu Doanh nghiệp mẫu"
        )
        session_state["gemini_analysis"] = gemini_result
    session_state["stage"] = "completed"
    save_session_state()
    return {"status": "success", "data": build_session_payload()}


@app.post("/api/reset")
async def reset_data():
    session_state["raw_df"] = None
    session_state["cleaned_df"] = None
    session_state["gatekeeper"] = None
    session_state["gemini_analysis"] = None
    session_state["last_source"] = None
    session_state["business_context"] = ""
    session_state["stage"] = "idle"
    session_state["cleaning_loop_count"] = 0
    session_state["analysis_loop_count"] = 0
    session_state["last_human_feedback"] = ""
    session_state["workflow_execution"] = None
    try:
        if os.path.exists(SESSION_CACHE_FILE):
            os.remove(SESSION_CACHE_FILE)
    except Exception:
        pass
    return {"status": "success", "message": "Đã xóa dữ liệu hiện tại"}


class ChatRequest(BaseModel):
    query: str


@app.post("/api/chat")
async def chat_with_agent(req: ChatRequest):
    restore_session_state_if_needed(auto_fallback_sample=False)
    if session_state["cleaned_df"] is None:
        return {
            "response": "⚠️ **Chưa có dữ liệu trong hệ thống.**\n\nBạn vui lòng tải file lên và nhập bối cảnh doanh nghiệp ở khu vực trung tâm để bắt đầu quy trình nhé!"
        }

    analysis = session_state["gemini_analysis"] or {}
    gatekeeper = session_state["gatekeeper"]
    df = session_state["cleaned_df"]
    biz_ctx = session_state.get("business_context", "")

    prompt = f"""
Bạn là AI Agent phân tích dữ liệu SphereAI thông minh.
BỐI CẢNH DOANH NGHIỆP: {biz_ctx or 'Theo dữ liệu thực tế'}
TẬP DỮ LIỆU HIỆN TẠI:
- Lĩnh vực: {analysis.get('domain_detected', 'Đang trong quá trình kiểm duyệt')}
- Tóm tắt: {analysis.get('dataset_summary', '')}
- Số dòng: {len(df) if df is not None else 0}
- Chỉ số KPI chính: {json.dumps(analysis.get('kpis', []), ensure_ascii=False)}
- Tình trạng Gatekeeper: Sức khỏe {gatekeeper['summary']['health_score']}%, Lỗi thiếu: {gatekeeper['summary']['missing_fields_count']}, Trùng: {gatekeeper['summary']['duplicate_count']}

CÂU HỎI CỦA NGƯỜI DÙNG:
"{req.query}"

Hãy trả lời một cách tự nhiên, chuyên sâu, bám sát bối cảnh doanh nghiệp và tập dữ liệu thực tế này bằng tiếng Việt. Định dạng markdown rõ ràng.
"""
    try:
        answer = await asyncio.to_thread(call_gemini, prompt, False)
        return {"response": answer}
    except Exception:
        return {"response": f"Hệ thống đã ghi nhận {len(df)} dòng dữ liệu với điểm chất lượng {gatekeeper['summary']['health_score']}%. Hãy hoàn tất các bước duyệt trên quy trình để xem báo cáo đầy đủ."}


@app.get("/api/export/excel")
async def export_excel():
    restore_session_state_if_needed(auto_fallback_sample=True)
    if session_state["cleaned_df"] is None:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu để xuất")

    excel_stream = await asyncio.to_thread(
        generate_excel_report,
        session_state["cleaned_df"],
        session_state["gemini_analysis"] or {},
        session_state["gatekeeper"]
    )

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SphereAI_Cleaned_Data.xlsx"}
    )


@app.get("/api/export/word")
async def export_word():
    restore_session_state_if_needed(auto_fallback_sample=True)
    if session_state["gemini_analysis"] is None:
        gemini_result = await asyncio.to_thread(
            analyze_generic_data_with_gemini,
            session_state["cleaned_df"],
            session_state["gatekeeper"]["summary"],
            session_state["business_context"],
            "",
            session_state["last_source"] or "Dữ liệu Doanh nghiệp mẫu"
        )
        session_state["gemini_analysis"] = gemini_result
        save_session_state()

    word_stream = await asyncio.to_thread(
        generate_word_report,
        session_state["gemini_analysis"],
        session_state["gatekeeper"]
    )

    return StreamingResponse(
        word_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=SphereAI_Executive_Report.docx"}
    )


@app.get("/api/status")
async def get_status():
    restore_session_state_if_needed(auto_fallback_sample=False)
    has_data = session_state["cleaned_df"] is not None
    return {
        "has_data": has_data,
        "stage": session_state["stage"],
        "source": session_state["last_source"],
        "business_context": session_state["business_context"],
        "domain": session_state["gemini_analysis"].get("domain_detected") if session_state["gemini_analysis"] else None,
        "data": build_session_payload() if has_data else None
    }
