import streamlit as st
import re
import pandas as pd
from datetime import datetime
import plotly.express as px
import io
import zipfile

# ------------------ 설정 ------------------
LIMIT_SPEED = 50         # 제한속도
OVER_SPEED = 61          # 단속 기준
SECTION_LENGTH = 0.8     # 구간 길이 (km)

# ------------------ 로그 파싱 ------------------
def parse_log_file(filename, text):
    vehicle_data = {}
    date_str = re.search(r'(\d{8})(\d{2})', filename)
    if not date_str:
        return {}

    lines = text.splitlines()
    for i, line in enumerate(lines):
        # 실제 통과 시각으로 "차량번호:" 로그 기준 사용
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
                        vehicle_dict[plate] = (t, speed)  # 가장 마지막 시간으로 덮어씀
    return vehicle_dict

# ------------------ 분석 함수 ------------------
def analyze_logs(start_logs, end_logs):
    start_df = pd.DataFrame([(k, v[0], v[1]) for k, v in start_logs.items()], columns=["번호판", "시점 통과시간", "시점 통과속도"])
    end_df = pd.DataFrame([(k, v[0], v[1]) for k, v in end_logs.items()], columns=["번호판", "종점 통과시간", "종점 통과속도"])
    df = pd.merge(start_df, end_df, on="번호판", how="inner")
    df["구간 통과시간"] = (df["종점 통과시간"] - df["시점 통과시간"]).dt.total_seconds()
    df["평균 구간속도"] = SECTION_LENGTH / (df["구간 통과시간"] / 3600)
    df["과속 여부"] = (df["평균 구간속도"] >= OVER_SPEED)
    return start_df, end_df, df

# ------------------ Streamlit UI ------------------
st.set_page_config(layout="wide")
st.title("🚗 구간단속 로그 분석기 (Zip 업로드)")

col1, col2 = st.columns(2)
with col1:
    start_zip = st.file_uploader("시점 로그 Zip 파일 (S0056...)", type="zip")
with col2:
    end_zip = st.file_uploader("종점 로그 Zip 파일 (S0052...)", type="zip")

if st.button("🔍 분석 시작") and start_zip and end_zip:
    with st.spinner("Zip 압축 해제 및 로그 분석 중..."):
        start_logs = collect_logs_from_zip(start_zip, "S0056")
        end_logs = collect_logs_from_zip(end_zip, "S0052")
        start_df, end_df, result_df = analyze_logs(start_logs, end_logs)

        # ------- 요약 통계 -------
        st.subheader("📊 요약 통계")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("시점 통과 대수", f"{len(start_df)} 대")
        col2.metric("종점 통과 대수", f"{len(end_df)} 대")
        col3.metric("공통 차량 수", f"{len(result_df)} 대")
        col4.metric("통과율", f"{len(result_df)/len(start_df)*100:.2f} %")

        st.metric("평균 통과 시간(초)", f"{result_df['구간 통과시간'].mean():.2f}")
        st.metric("평균 구간 속도(km/h)", f"{result_df['평균 구간속도'].mean():.2f}")

        # ------- 필터 옵션 -------
        st.subheader("🔍 필터 옵션")
        col1, col2 = st.columns(2)
        with col1:
            show_over = st.checkbox("과속 차량만 보기")
        with col2:
            search_plate = st.text_input("번호판 일부 검색")

        filtered_df = result_df.copy()
        if show_over:
            filtered_df = filtered_df[filtered_df["과속 여부"] == True]
        if search_plate:
            filtered_df = filtered_df[filtered_df["번호판"].str.contains(search_plate)]

        # ------- 테이블 출력 -------
        st.subheader("📋 차량별 통과 정보")
        st.dataframe(filtered_df[["번호판", "시점 통과시간", "시점 통과속도", "종점 통과시간", "종점 통과속도", "구간 통과시간", "평균 구간속도", "과속 여부"]])

        # ------- 그래프 시각화 -------
        st.subheader("📈 통과 시간 분포 분석")
        filtered_df["시점 시간대"] = filtered_df["시점 통과시간"].dt.hour.astype(str) + "시"
        hourly_stats = filtered_df.groupby("시점 시간대").size().reset_index(name="통과 차량 수")
        fig = px.bar(hourly_stats, x="시점 시간대", y="통과 차량 수")
        st.plotly_chart(fig, use_container_width=True)

        # ------- 엑셀 다운로드 -------
        st.subheader("⬇️ 엑셀 다운로드")
        to_download = filtered_df.drop(columns=["시점 시간대"], errors='ignore').copy()
        to_download["시점 통과시간"] = to_download["시점 통과시간"].astype(str)
        to_download["종점 통과시간"] = to_download["종점 통과시간"].astype(str)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            to_download.to_excel(writer, index=False)
        st.download_button("엑셀 파일 다운로드", data=buffer.getvalue(), file_name="구간단속_결과.xlsx")
