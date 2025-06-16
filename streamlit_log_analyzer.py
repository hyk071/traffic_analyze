import streamlit as st
import os
import re
import pandas as pd
from datetime import datetime
import plotly.express as px

# ------------------ 설정 ------------------
LIMIT_SPEED = 50         # 제한속도
OVER_SPEED = 61          # 단속 기준
SECTION_LENGTH = 0.8     # 구간 길이 (km)

# ------------------ 로그 파싱 ------------------
def parse_log_file(file_path):
    vehicle_data = []
    filename = os.path.basename(file_path)
    date_str = re.search(r'(\d{8})(\d{2})', filename)
    if not date_str:
        return []
    base_date = f"20{date_str.group(1)}"
    hour = int(date_str.group(2))
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.search(r"\[(\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):(\d{3})\].*Plate=([가-힣A-Za-z0-9]+)", line)
            if m:
                time_str = f"20{m.group(1)}.{m.group(2)}"
                time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                plate = m.group(3).strip()
                vehicle_data.append((plate, time_obj, hour))
    return vehicle_data

# ------------------ 폴더에서 로그 수집 ------------------
def collect_logs(folder_path, prefix):
    vehicle_dict = {}
    for fname in os.listdir(folder_path):
        if fname.startswith(prefix) and fname.endswith(".txt"):
            entries = parse_log_file(os.path.join(folder_path, fname))
            for plate, t, hour in entries:
                if plate not in vehicle_dict or t < vehicle_dict[plate][0]:
                    vehicle_dict[plate] = (t, hour)
    return vehicle_dict

# ------------------ 분석 함수 ------------------
def analyze_logs(start_logs, end_logs):
    start_df = pd.DataFrame([(k, v[0], v[1]) for k, v in start_logs.items()], columns=["plate", "start_time", "start_hour"])
    end_df = pd.DataFrame([(k, v[0], v[1]) for k, v in end_logs.items()], columns=["plate", "end_time", "end_hour"])
    df = pd.merge(start_df, end_df, on="plate", how="inner")
    df["time_diff_sec"] = (df["end_time"] - df["start_time"]).dt.total_seconds()
    df["avg_speed"] = SECTION_LENGTH / (df["time_diff_sec"] / 3600)
    df["over_speed"] = (df["avg_speed"] >= OVER_SPEED)
    return start_df, end_df, df

# ------------------ Streamlit UI ------------------
st.set_page_config(layout="wide")
st.title("🚗 구간단속 로그 분석기")

col1, col2 = st.columns(2)
with col1:
    start_folder = st.text_input("시점 로그 폴더", value="./시점로그")
with col2:
    end_folder = st.text_input("종점 로그 폴더", value="./종점로그")

if st.button("🔍 분석 시작"):
    with st.spinner("분석 중입니다..."):
        start_logs = collect_logs(start_folder, "S0056")
        end_logs = collect_logs(end_folder, "S0052")
        start_df, end_df, result_df = analyze_logs(start_logs, end_logs)

        # ------- 요약 통계 -------
        st.subheader("📊 요약 통계")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("시점 통과 대수", f"{len(start_df)} 대")
        col2.metric("종점 통과 대수", f"{len(end_df)} 대")
        col3.metric("공통 차량 수", f"{len(result_df)} 대")
        col4.metric("통과율", f"{len(result_df)/len(start_df)*100:.2f} %")

        st.metric("평균 통과 시간(초)", f"{result_df['time_diff_sec'].mean():.2f}")
        st.metric("평균 구간 속도(km/h)", f"{result_df['avg_speed'].mean():.2f}")

        # ------- 필터 옵션 -------
        st.subheader("🔍 필터 옵션")
        col1, col2 = st.columns(2)
        with col1:
            show_over = st.checkbox("과속 차량만 보기")
        with col2:
            search_plate = st.text_input("번호판 일부 검색")

        filtered_df = result_df.copy()
        if show_over:
            filtered_df = filtered_df[filtered_df["over_speed"] == True]
        if search_plate:
            filtered_df = filtered_df[filtered_df["plate"].str.contains(search_plate)]

        # ------- 테이블 출력 -------
        st.subheader("📋 차량별 통과 정보")
        st.dataframe(filtered_df[["plate", "start_time", "end_time", "time_diff_sec", "avg_speed", "over_speed"]])

        # ------- 그래프 시각화 -------
        st.subheader("📈 시간대별 통과량 분석")
        hourly_stats = result_df.groupby("start_hour").size().reset_index(name="시점 통과")
        hourly_stats["종점 통과"] = result_df.groupby("end_hour").size().values
        hourly_stats["시간대"] = hourly_stats["start_hour"].astype(str) + "시"

        fig = px.bar(hourly_stats, x="시간대", y=["시점 통과", "종점 통과"], barmode="group")
        st.plotly_chart(fig, use_container_width=True)

        # ------- 엑셀 다운로드 -------
        st.subheader("⬇️ 엑셀 다운로드")
        to_download = filtered_df.copy()
        to_download["start_time"] = to_download["start_time"].astype(str)
        to_download["end_time"] = to_download["end_time"].astype(str)
        excel = to_download.to_excel(index=False, engine="openpyxl")
        st.download_button("엑셀 파일 다운로드", data=excel, file_name="구간단속_결과.xlsx")
