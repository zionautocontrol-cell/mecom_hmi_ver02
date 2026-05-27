import json
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from config import CONTROL_ENABLED, CONTROL_FEEDBACK_BIT, ADMIN_PASSWORD, PASSWORD_FILE
from data_provider import (
    load_control_command,
    load_history_data,
    load_realtime_data,
    save_control_command,
)

st.set_page_config(page_title="MECOM 히트펌프 감시", layout="wide")

# ── 전체 레이아웃 여백 조정 ──────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 0.3rem !important; padding-bottom: 0 !important; }
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0.05rem !important; }
    section[data-testid="stSidebar"] hr { margin: 0.1rem 0 !important; }
    div[data-testid="stSidebarUserContent"] { gap: 0.02rem !important; }
    h1 { margin-top: 0 !important; padding-top: 0 !important; }
    .login-title { margin-top: 3rem !important; }
    thead tr th:first-child, tbody tr th:first-child { display: none !important; }
    thead tr th:only-child { display: table-cell !important; }
    thead tr th button { display: none !important; }
    @media print {
        section[data-testid="stSidebar"] { display: none !important; }
        header { display: none !important; }
        .stAppDeployButton { display: none !important; }
        footer { display: none !important; }
        #MainMenu { display: none !important; }
        .main > div { padding: 0 !important; max-width: 100% !important; }
        button { display: none !important; }
        .report-container { display: block !important; }
    }
</style>
""", unsafe_allow_html=True)

if "current_menu" not in st.session_state:
    st.session_state.current_menu = "📡 감시"

# ── 비밀번호 초기화 ─────────────────────────────
if "admin_password" not in st.session_state:
    if PASSWORD_FILE.exists():
        with open(str(PASSWORD_FILE), "r") as f:
            st.session_state.admin_password = json.load(f).get("password", ADMIN_PASSWORD)
    else:
        st.session_state.admin_password = ADMIN_PASSWORD


def save_password(new_pw: str) -> None:
    with open(str(PASSWORD_FILE), "w") as f:
        json.dump({"password": new_pw}, f)
    st.session_state.admin_password = new_pw

def load_history_from_api():
    """API 서버로부터 이력 데이터를 가져와서 판다스 데이터프레임으로 변환"""
    try:
        # API 서버 주소 (FastAPI가 실행 중인 포트 8000)
        url = "http://localhost:8000/history?limit=100"
        response = requests.get(url, timeout=5) # 타임아웃 설정으로 무한 대기 방지
        
        if response.status_code == 200:
            data = response.json()
            if not data:
                return pd.DataFrame()
                
            # JSON 데이터를 DataFrame으로 변환
            df = pd.DataFrame(data)
            
            # DB의 timestamp 컬럼을 시계열 데이터로 변환 (트렌드 그래프용)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # 보기 좋게 정렬
                df = df.sort_values('timestamp')
            
            return df
        else:
            st.error(f"API 응답 에러: {response.status_code}")
            return pd.DataFrame()
            
    except requests.exceptions.ConnectionError:
        st.error("API 서버가 실행 중이지 않습니다. api_server.py를 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()



def render_sidebar() -> None:
    """렌더 사이드바 메뉴와 제어 버튼"""
    st.sidebar.markdown("## 📊 MECOM")
    st.sidebar.markdown("---")

    menu_options = ["📡 감시", "📈 이력", "📊 트렌드", "🔑 비밀번호 변경"]
    # menu_options = ["📡 감시", "📈 이력", "⚠️ 알람", "📊 트렌드"]
    for option in menu_options:
        is_active = st.session_state.current_menu == option
        if st.sidebar.button(
            option,
            key=f"menu_{option}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.current_menu = option
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 제어")

    realtime = load_realtime_data()
    bits = realtime.get("bits", [False] * 39)
    fb_bit = CONTROL_FEEDBACK_BIT
    is_running = bits[fb_bit] if fb_bit < len(bits) else False

    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button(
            "시작",
            key="btn_start",
            use_container_width=True,
            type="primary" if is_running else "secondary",
            disabled=not CONTROL_ENABLED,
        ):
            save_control_command(
                command="start",
                status="requested",
                message="UI 요청",
                requested_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            st.rerun()

    with col2:
        if st.button(
            "정지",
            key="btn_stop",
            use_container_width=True,
            type="primary" if not is_running else "secondary",
            disabled=not CONTROL_ENABLED,
        ):
            save_control_command(
                command="stop",
                status="requested",
                message="UI 요청",
                requested_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            st.rerun()

    # 운전 상태 메시지 (PLC 피드백 기반)
    if is_running:
        st.sidebar.success("🟢 시스템 운전중")
    else:
        st.sidebar.info("⚫ 시스템 정지중")

    st.sidebar.markdown("---")
    st.sidebar.metric(
        label="순시 열량 (kW)", value=f"{realtime.get('words', [0]*11)[10]:,.1f}"
    )
    st.sidebar.metric(
        label="누적 열량 (kW/h)", value=f"{realtime.get('accum_heat', 0.0):,.0f}"
    )

    st.sidebar.markdown("---")
    st.sidebar.info("🕐 자동 일일리포트\n매일 01:00 자동 생성 중")


@st.cache_data(ttl=3600)
def _get_hmi_html():
    import urllib.request
    try:
        return urllib.request.urlopen("http://localhost:8000/hmi", timeout=5).read().decode("utf-8")
    except Exception:
        return None


def render_hmi_dashboard() -> None:
    realtime = load_realtime_data()
    current_ts = realtime.get("timestamp", "")
    status = realtime.get("status", "disconnected")

    st.title("🎯 MECOM 히트펌프 감시")
    st.markdown(f"**마지막 업데이트:** {current_ts}  |  **통신 상태:** {status}")
    st.markdown("---")

    hmi_html = _get_hmi_html()
    if hmi_html:
        components.html(hmi_html, height=700, scrolling=False)
    else:
        st.error("HMI 다이어그램을 불러올 수 없습니다. API 서버(localhost:8000)가 실행 중인지 확인하세요.")


def _make_report_pdf(df: pd.DataFrame, rpt_type: str, interval: str) -> bytes:
    rpt_labels = {"daily": "일일", "weekly": "주간", "monthly": "월간", "custom": "사용자지정"}
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_font("Nanum", "", "C:/Windows/Fonts/malgun.ttf", uni=True)
    pdf.add_page()
    pdf.set_font("Nanum", size=12)
    pdf.cell(0, 8, text=f"MECOM {rpt_labels[rpt_type]}리포트 ({interval})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    cols = list(df.columns)
    col_w = max(20, int(270 / len(cols))) if cols else 270
    pdf.set_font("Nanum", size=7)
    for c in cols:
        pdf.cell(col_w, 6, text=c, border=1)
    pdf.ln()
    for _, row in df.iterrows():
        for c in cols:
            v = str(row[c]) if pd.notna(row[c]) else ""
            pdf.cell(col_w, 5, text=v, border=1)
        pdf.ln()
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _report_filename(rpt_type: str) -> str:
    rpt_labels = {"daily": "일일", "weekly": "주간", "monthly": "월간", "custom": "사용자지정"}
    now = datetime.now()
    if rpt_type == "weekly":
        monday = (now - timedelta(days=now.weekday())).strftime("%m%d")
        date_str = f"{monday}~"
    elif rpt_type == "monthly":
        date_str = now.strftime("%Y-%m")
    elif rpt_type == "daily":
        date_str = now.strftime("%Y-%m-%d")
    else:
        date_str = now.strftime("%Y%m%d_%H%M%S")
    return f"{rpt_labels[rpt_type]}리포트_{date_str}.pdf"


def _save_report_pdf(df: pd.DataFrame, rpt_type: str, interval: str) -> str:
    folder_map = {"daily": "일일리포트", "weekly": "주간리포트", "monthly": "월간리포트", "custom": "사용자지정"}
    save_dir = Path.home() / "Desktop" / "리포트" / folder_map[rpt_type]
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / _report_filename(rpt_type)
    filepath.write_bytes(_make_report_pdf(df, rpt_type, interval))
    return str(filepath)


def render_history_page() -> None:
    st.title("운전 이력")
    raw = load_history_data()
    if raw.empty:
        st.warning("데이터가 없습니다.")
        return
    raw["날짜"] = pd.to_datetime(raw["날짜"], format="%y/%m/%d %H:%M", errors="coerce")
    raw = raw.dropna(subset=["날짜"]).sort_values("날짜", ascending=False)
    display_df = raw.copy()

    merge_pairs = [
        ("지중공급온도", ["지중공급온도(1동)", "지중공급온도(2동)"]),
        ("지중환수온도", ["지중환수온도(1동)", "지중환수온도(2동)"]),
        ("2차공급온도",   ["2차공급온도(1동)", "2차공급온도(2동)"]),
        ("2차환수온도",   ["2차환수온도(1동)", "2차환수온도(2동)"]),
        ("유량",          ["1동유량", "2동유량"]),
    ]
    out = display_df[["날짜"]].copy()
    for label, (a, b) in merge_pairs:
        if a in display_df and b in display_df:
            out[label] = display_df[a].round(1).astype(str) + " / " + display_df[b].round(1).astype(str)
    if "생산열량" in display_df:
        out["순시열량"] = display_df["생산열량"].round(1)
    if "누적열량" in display_df:
        out["누적열량"] = display_df["누적열량"].round(1)
    st.dataframe(out.head(15), use_container_width=True, hide_index=True)

    # ── 리포트 ─────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 리포트")

    numeric_cols = [c for c in raw.columns if c != "날짜"]
    now = pd.Timestamp.now()

    r1, r2, r3, r4 = st.columns(4)
    with r1:
        if st.button("📅 일일 리포트", key="rpt_daily", use_container_width=True):
            st.session_state.rpt_type = "daily"
            st.session_state.pop("rpt_result", None)
    with r2:
        if st.button("📆 주간 리포트", key="rpt_weekly", use_container_width=True):
            st.session_state.rpt_type = "weekly"
            st.session_state.pop("rpt_result", None)
    with r3:
        if st.button("📆 월간 리포트", key="rpt_monthly", use_container_width=True):
            st.session_state.rpt_type = "monthly"
            st.session_state.pop("rpt_result", None)
    with r4:
        if st.button("📅 사용자 지정", key="rpt_custom", use_container_width=True):
            st.session_state.rpt_type = "custom"
            st.session_state.pop("rpt_result", None)

    rpt_type = st.session_state.get("rpt_type")
    if not rpt_type:
        return

    selected_cols = st.multiselect(
        "항목 선택", options=numeric_cols,
        default=numeric_cols[:3], key="rpt_cols"
    )

    interval_map = {
        "daily":     ["1분", "10분", "30분", "1시간"],
        "weekly":    ["10분", "30분", "1시간", "1일"],
        "monthly":   ["1시간", "1일"],
        "custom":    ["1분", "10분", "30분", "1시간", "1일"],
    }
    rule_map = {"1분": "1min", "10분": "10min", "30분": "30min", "1시간": "1H", "1일": "1D"}
    interval = st.selectbox("주기", options=interval_map[rpt_type], key="rpt_interval")

    start_date = end_date = None
    if rpt_type == "daily":
        start_date = now.normalize()
        end_date = now
    elif rpt_type == "weekly":
        start_date = now - pd.Timedelta(days=7)
        end_date = now
    elif rpt_type == "monthly":
        start_date = now - pd.Timedelta(days=30)
        end_date = now
    else:
        dc1, dc2 = st.columns(2)
        with dc1:
            d1 = st.date_input("시작일", value=now.date() - pd.Timedelta(days=7), key="rpt_start")
        with dc2:
            d2 = st.date_input("종료일", value=now.date(), key="rpt_end")
        start_date = pd.Timestamp(d1)
        end_date = pd.Timestamp(d2) + pd.Timedelta(days=1)

    if st.button("조회", key="rpt_generate", use_container_width=True):
        if not selected_cols:
            st.warning("항목을 하나 이상 선택하세요.")
        else:
            data = raw.copy().sort_values("날짜")
            mask = (data["날짜"] >= start_date) & (data["날짜"] <= end_date)
            filtered = data.loc[mask].set_index("날짜")

            if filtered.empty:
                st.info("선택한 기간에 데이터가 없습니다.")
            else:
                rule = rule_map[interval]
                agg = {col: "mean" for col in selected_cols}
                if "누적열량" in selected_cols:
                    agg["누적열량"] = "last"

                report = filtered[selected_cols].resample(rule).agg(agg)
                report = report.dropna(how="all").reset_index()
                for c in selected_cols:
                    report[c] = report[c].round(1)

                pdf_bytes = _make_report_pdf(report, rpt_type, interval)
                chart_data = report.set_index("날짜")
                report["날짜"] = report["날짜"].dt.strftime("%y/%m/%d %H:%M")

                st.session_state.rpt_result = {
                    "report": report, "chart_data": chart_data,
                    "pdf_bytes": pdf_bytes, "rpt_type": rpt_type,
                    "interval": interval,
                }

    rpt = st.session_state.get("rpt_result")
    if rpt:
        st.markdown('<div class="report-container">', unsafe_allow_html=True)
        st.dataframe(rpt["report"], use_container_width=True, hide_index=True)
        if not rpt["chart_data"].empty:
            st.line_chart(rpt["chart_data"].astype(float))
        st.markdown("</div>", unsafe_allow_html=True)

        pdf_name = _report_filename(rpt["rpt_type"])
        if st.download_button(
            "📄 PDF 저장", data=rpt["pdf_bytes"],
            file_name=pdf_name, mime="application/pdf",
            use_container_width=True,
        ):
            saved = _save_report_pdf(rpt["report"], rpt["rpt_type"], rpt["interval"])
            st.success(f"✅ 저장 완료: {saved}")


# def render_alarm_page() -> None:
#     st.title("알람 이력")
#     df = load_alarm_history()
#     if df.empty:
#         st.info("기록된 알람이 없습니다.")
#         return
#     st.dataframe(df.tail(50), use_container_width=True, hide_index=True)


def render_trend_page() -> None:
    st.title("트렌드")
    df = load_history_data()
    if df.empty:
        st.warning("데이터가 없습니다.")
        return

    columns_to_plot = [col for col in df.columns if col != "날짜"]

    if "trend_saved" not in st.session_state:
        st.session_state.trend_saved = columns_to_plot[:2]

    # 복원: widget key가 없을 때만 session_state에서 복원
    if "trend_multi" not in st.session_state:
        st.session_state.trend_multi = st.session_state.trend_saved

    selected = st.multiselect("항목 선택:", options=columns_to_plot, key="trend_multi")
    st.session_state.trend_saved = selected

    if selected:
        chart_data = df.set_index("날짜")[selected]
        st.line_chart(chart_data)

def render_password_page() -> None:
    st.title("🔑 비밀번호 변경")
    with st.form("password_change_form", clear_on_submit=True):
        current_pw = st.text_input("현재 비밀번호", type="password")
        new_pw = st.text_input("새 비밀번호", type="password")
        confirm_pw = st.text_input("새 비밀번호 확인", type="password")
        submitted = st.form_submit_button("변경", use_container_width=True)
        if submitted:
            if current_pw != st.session_state.admin_password:
                st.error("현재 비밀번호가 일치하지 않습니다.")
            elif len(new_pw) < 4:
                st.error("새 비밀번호는 최소 4자 이상이어야 합니다.")
            elif new_pw != confirm_pw:
                st.error("새 비밀번호가 일치하지 않습니다.")
            elif new_pw == current_pw:
                st.warning("현재 비밀번호와 동일합니다. 다른 비밀번호를 입력하세요.")
            else:
                save_password(new_pw)
                st.success("비밀번호가 변경되었습니다.")


def check_password():
    """비밀번호 확인 함수"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown('<h1 class="login-title">🔒 시스템 접근 제한</h1>', unsafe_allow_html=True)
        pwd = st.text_input("접근 비밀번호를 입력하세요", type="password")
        if st.button("접속"):
            if pwd == st.session_state.admin_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        return False
    return True




def main() -> None:
    if not check_password():
        return

    render_sidebar()

    # 120초 간격 자동 갱신 (감시화면 iframe 재로딩 최소화)
    st_autorefresh(interval=120000, key="auto_refresh")

    if st.session_state.current_menu == "📡 감시":
        render_hmi_dashboard()
    elif st.session_state.current_menu == "📈 이력":
        render_history_page()
    # elif st.session_state.current_menu == "⚠️ 알람":
    #     render_alarm_page()
    elif st.session_state.current_menu == "📊 트렌드":
        render_trend_page()
    elif st.session_state.current_menu == "🔑 비밀번호 변경":
        render_password_page()


if __name__ == "__main__":
    main()