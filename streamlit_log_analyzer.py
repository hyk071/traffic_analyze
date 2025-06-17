import streamlit as st
import re
import pandas as pd
from datetime import datetime
import plotly.express as px
import io
import zipfile
from jinja2 import Template
from weasyprint import HTML

# ------------------ 설정 ------------------
LIMIT_SPEED = 50
OVER_SPEED = 61
SECTION_LENGTH = 0.8
MAX_TIME_DIFF = 3600

# ------------------ 로그 파싱 ------------------
def parse_log_file(filename, text):
    vehicle_data = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "차량번호:" in line:
            time_match = re.search(r"\[(\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):(\d{3})\]", line)
            plate_match = re.search(r"차량번호[:=\s]?([가-힣A-Za-z0-9]+)", line)
            speed_match = re.search(r"속도[:=\s]?([0-9.]+)", line)
            if time_match and plate_match:
                time_str = f"20{time_match.group(1)}.{time_match.group(2)}"
                try:
                    time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    continue
                plate = plate_match.group(1).strip()
                speed = float(speed_match.group(1)) if speed_match else None
                vehicle_data[plate] = (time_obj, speed)
    return vehicle_data

# ------------------ 압축에서 로그 수집 ------------------
def collect_logs_from_zip(zip_file, prefix):
    vehicle_dict = {}
    with zipfile.ZipFile(zip_file) as zf:
        for fname in zf.namelist():
            if fname.startswith(prefix) and fname.endswith(".txt"):
                with zf.open(fname) as file:
                    raw_bytes = file.read()
                    try:
                        text = raw_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            text = raw_bytes.decode('cp949')
                        except UnicodeDecodeError:
                            text = raw_bytes.decode('euc-kr', errors='replace')
                    entries = parse_log_file(fname, text)
                    for plate, (t, speed) in entries.items():
                        vehicle_dict[plate] = (t, speed)
    return vehicle_dict

# ------------------ 분석 함수 ------------------
def analyze_logs(start_logs, end_logs):
    start_df = pd.DataFrame([(k, v[0], v[1]) for k, v in start_logs.items()], columns=["번호판", "시점 통과시간", "시점 통과속도"])
    end_df = pd.DataFrame([(k, v[0], v[1]) for k, v in end_logs.items()], columns=["번호판", "종점 통과시간", "종점 통과속도"])
    df = pd.merge(start_df, end_df, on="번호판", how="inner")
    df["구간 통과시간"] = (df["종점 통과시간"] - df["시점 통과시간"]).dt.total_seconds()
    df = df[df["구간 통과시간"] >= 0]
    df = df[df["구간 통과시간"] <= MAX_TIME_DIFF]
    df["평균 구간속도"] = SECTION_LENGTH / (df["구간 통과시간"] / 3600)
    df["과속 여부"] = (df["평균 구간속도"] >= OVER_SPEED)
    return start_df, end_df, df

# ------------------ Streamlit UI ------------------
st.set_page_config(layout="wide")

if "result_df" not in st.session_state:
    st.session_state.result_df = None

st.title("🚗 구간단속 로그 분석기")

if st.button("🔁 초기화"):
    st.session_state.result_df = None

if st.session_state.result_df is None:
    col1, col2 = st.columns(2)
    with col1:
        start_zip = st.file_uploader("시점 로그 Zip 파일 (S0056...)", type="zip")
    with col2:
        end_zip = st.file_uploader("종점 로그 Zip 파일 (S0052...)", type="zip")

    sort_option = st.selectbox("정렬 기준을 선택하세요", ["시점 통과시간", "평균 구간속도"])

    if st.button("🔍 분석 시작") and start_zip and end_zip:
        with st.spinner("Zip 압축 해제 및 로그 분석 중..."):
            start_logs = collect_logs_from_zip(start_zip, "S0056")
            end_logs = collect_logs_from_zip(end_zip, "S0052")
            start_df, end_df, result_df = analyze_logs(start_logs, end_logs)

            if sort_option == "평균 구간속도":
                result_df = result_df.sort_values(by="평균 구간속도", ascending=False)
            else:
                result_df = result_df.sort_values(by="시점 통과시간")

            st.session_state.result_df = result_df

if st.session_state.result_df is not None:
    result_df = st.session_state.result_df

    st.subheader("📊 요약 통계")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("시점 통과 대수", f"{len(result_df)} 대")
    col2.metric("종점 통과 대수", f"{len(result_df)} 대")
    col3.metric("공통 차량 수", f"{len(result_df)} 대")
    col4.metric("통과율", f"100.00 %")
    st.metric("평균 통과 시간(초)", f"{result_df['구간 통과시간'].mean():.2f}")
    st.metric("평균 구간 속도(km/h)", f"{result_df['평균 구간속도'].mean():.2f}")

    # 월별 통계
    st.subheader("📅 월별 통과량 통계")
    result_df["월"] = result_df["시점 통과시간"].dt.to_period("M").astype(str)
    monthly_stats = result_df.groupby("월").size().reset_index(name="통과 차량 수")
    st.dataframe(monthly_stats)

    # 요일+시간 통과량 상위 3개
    st.subheader("📌 요일+시간 기준 통과량 상위 3개")
    result_df["요일"] = result_df["시점 통과시간"].dt.day_name()
    result_df["시"] = result_df["시점 통과시간"].dt.hour
    result_df["요일_시간"] = result_df["요일"] + " " + result_df["시"].astype(str) + "시"
    top3 = result_df.groupby("요일_시간").size().reset_index(name="통과 차량 수").sort_values(by="통과 차량 수", ascending=False).head(3)
    st.table(top3)

    # 시간대별 통과량
    st.subheader("📈 시간대별 통과량")
    hourly_stats = result_df.groupby("시").size().reset_index(name="통과 차량 수")
    hourly_stats = hourly_stats.sort_values("시")
    fig = px.bar(hourly_stats, x="시", y="통과 차량 수")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 시간대별 통과량 표")
    st.table(hourly_stats)

    st.subheader("📋 차량별 통과 정보")
    st.dataframe(result_df[["번호판", "시점 통과시간", "시점 통과속도", "종점 통과시간", "종점 통과속도", "구간 통과시간", "평균 구간속도", "과속 여부"]])

    # 엑셀 다운로드
    st.subheader("⬇️ 엑셀 다운로드")
    df_to_download = result_df.copy()
    df_to_download = df_to_download.sort_values("시점 통과시간")
    df_to_download["시점 통과시간"] = df_to_download["시점 통과시간"].astype(str)
    df_to_download["종점 통과시간"] = df_to_download["종점 통과시간"].astype(str)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_to_download.to_excel(writer, index=False)
    st.download_button("엑셀 파일 다운로드", data=buffer.getvalue(), file_name="구간단속_결과.xlsx")

    # PDF 보고서 다운로드
    st.subheader("📄 PDF 보고서 다운로드")
    report_html = Template("""
    <html>
    <head>
        <meta charset='utf-8'>
        <style>
            body { font-family: sans-serif; padding: 30px; }
            h1, h2 { color: #2c3e50; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h1>구간단속 분석 보고서</h1>
        <h2>요약 통계</h2>
        <p>시점 통과 대수: {{ start_count }} 대</p>
        <p>종점 통과 대수: {{ end_count }} 대</p>
        <p>공통 차량 수: {{ match_count }} 대</p>
        <p>통과율: {{ ratio }}%</p>
        <p>평균 통과 시간(초): {{ avg_time }} 초</p>
        <p>평균 구간 속도(km/h): {{ avg_speed }} km/h</p>

        <h2>월별 통계</h2>
        <table>
            <tr><th>월</th><th>통과 차량 수</th></tr>
            {% for row in monthly %}
            <tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>
            {% endfor %}
        </table>

        <h2>요일 + 시간대 상위 3</h2>
        <table>
            <tr><th>요일+시간</th><th>통과 차량 수</th></tr>
            {% for row in top3 %}
            <tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """)

    html_out = report_html.render(
        start_count=len(result_df),
        end_count=len(result_df),
        match_count=len(result_df),
        ratio="100.00",
        avg_time=f"{result_df['구간 통과시간'].mean():.2f}",
        avg_speed=f"{result_df['평균 구간속도'].mean():.2f}",
        monthly=monthly_stats.values.tolist(),
        top3=top3.values.tolist()
    )

    pdf_buffer = io.BytesIO()
    HTML(string=html_out).write_pdf(pdf_buffer)
    st.download_button("PDF 보고서 다운로드", data=pdf_buffer.getvalue(), file_name="구간단속_보고서.pdf")
