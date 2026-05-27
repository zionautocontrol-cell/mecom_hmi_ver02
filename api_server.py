import json
import base64
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import sqlite3
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fpdf import FPDF

from config import (
    DB_PATH,
    HISTORY_COLUMNS,
    REALTIME_JSON,
    CONTROL_COMMAND_JSON,
    DIAGRAM_HTML,
    BACKGROUND_IMAGE,
)
from data_provider import cleanup_old_history

app = FastAPI(title="MECOM API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_background_base64() -> str:
    if not BACKGROUND_IMAGE.exists():
        return ""
    try:
        with open(BACKGROUND_IMAGE, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


@app.get("/realtime")
def get_realtime():
    try:
        return json.loads(REALTIME_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "disconnected", "bits": [False] * 39, "words": [0.0] * 11, "accum_heat": 0.0}


@app.get("/control")
def get_control():
    try:
        return json.loads(CONTROL_COMMAND_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"command": "none", "status": "idle", "message": ""}


@app.get("/history")
def get_history(limit: int = 100):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM history_logs ORDER BY timestamp DESC LIMIT {limit}")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/hmi", response_class=HTMLResponse)
def get_hmi():
    try:
        data = json.loads(REALTIME_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {"bits": [False] * 38, "words": [0.0] * 11, "accum_heat": 0.0}

    bits = data.get("bits", [False] * 38)
    words = data.get("words", [0.0] * 11)

    if not DIAGRAM_HTML.exists():
        return HTMLResponse("<h2>diagram.html not found</h2>", status_code=404)

    html = DIAGRAM_HTML.read_text(encoding="utf-8")

    bg = load_background_base64()
    if bg:
        html = html.replace("{{BACKGROUND_IMAGE}}", bg)

    for i in range(min(38, len(bits))):
        val = bits[i] if i < len(bits) else False
        if i < 30:
            cls = "running" if val else "paused"
        else:
            cls = "on" if val else "off"
        html = html.replace(f"{{{{B{i}}}}}", cls)

    for i in range(11):
        val = words[i] if i < len(words) else 0.0
        html = html.replace(f"{{{{W{i}}}}}", f"{val:.1f}")

    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _auto_daily_report():
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    date_label = yesterday.strftime("%Y-%m-%d")
    yesterday_start = yesterday.strftime("%y/%m/%d") + " 00:00"
    yesterday_end = yesterday.strftime("%y/%m/%d") + " 23:59"

    try:
        with sqlite3.connect(DB_PATH) as conn:
            query = ("SELECT * FROM history_logs "
                     "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp")
            rows = conn.execute(query, (yesterday_start, yesterday_end)).fetchall()
        if not rows:
            return
    except Exception:
        return

    col_map = {
        "timestamp": "날짜",
        "w0": "지중공급온도(1동)", "w1": "지중환수온도(1동)",
        "w2": "지중공급온도(2동)", "w3": "지중환수온도(2동)",
        "w4": "2차공급온도(1동)", "w5": "2차환수온도(1동)",
        "w6": "2차공급온도(2동)", "w7": "2차환수온도(2동)",
        "w8": "1동유량", "w9": "2동유량",
        "w10": "생산열량",
        "accum_heat": "누적열량",
    }
    with sqlite3.connect(DB_PATH) as conn:
        db_cols = [d[0] for d in conn.execute("PRAGMA table_info(history_logs)").fetchall()]
    data = []
    for row in rows:
        record = {}
        for i, col in enumerate(db_cols):
            mapped = col_map.get(col, col)
            record[mapped] = row[i]
        data.append(record)
    if not data:
        return
    df = pd.DataFrame(data, columns=HISTORY_COLUMNS)
    df["날짜"] = pd.to_datetime(df["날짜"], format="%y/%m/%d %H:%M", errors="coerce")
    df = df.dropna(subset=["날짜"]).sort_values("날짜")
    filtered = df.set_index("날짜")
    if filtered.empty:
        return

    numeric_cols = [c for c in HISTORY_COLUMNS if c != "날짜"]
    report = filtered[numeric_cols].resample("10min").mean()
    report = report.dropna(how="all").reset_index()
    report["날짜"] = report["날짜"].dt.strftime("%y/%m/%d %H:%M")

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_font("Nanum", "", "C:/Windows/Fonts/malgun.ttf", uni=True)
    pdf.add_page()
    pdf.set_font("Nanum", size=12)
    pdf.cell(0, 8, text=f"MECOM 일일리포트 ({date_label})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    cols = list(report.columns)
    col_w = max(20, int(270 / len(cols))) if cols else 270
    pdf.set_font("Nanum", size=7)
    for c in cols:
        pdf.cell(col_w, 6, text=c, border=1)
    pdf.ln()
    for _, row in report.iterrows():
        for c in cols:
            v = str(row[c]) if pd.notna(row[c]) else ""
            pdf.cell(col_w, 5, text=v, border=1)
        pdf.ln()

    save_dir = Path.home() / "Desktop" / "리포트" / "일일리포트"
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / f"일일리포트_{date_label}.pdf"
    pdf.output(str(filepath))
    print(f"[Auto Report] 일일리포트 생성 완료: {filepath}")


scheduler = BackgroundScheduler()
scheduler.add_job(_auto_daily_report, "cron", hour=1, minute=0)
scheduler.add_job(cleanup_old_history, "cron", day=1, hour=3, minute=0)
scheduler.start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
