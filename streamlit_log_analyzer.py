... # 정확한 통과율 계산 start_count = len(start_df) end_count = len(end_df) match_count = len(result_df) ratio = round((match_count / start_count * 100), 2) if start_count else 0

st.subheader("📊 요약 통계")
col1, col2, col3, col4 = st.columns(4)
col1.metric("시점 통과 대수", f"{start_count} 대")
col2.metric("종점 통과 대수", f"{end_count} 대")
col3.metric("공통 차량 수", f"{match_count} 대")
col4.metric("통과율", f"{ratio:.2f} %")
st.metric("평균 통과 시간(초)", f"{result_df['구간 통과시간'].mean():.2f}")
st.metric("평균 구간 속도(km/h)", f"{result_df['평균 구간속도'].mean():.2f}")

# PDF 템플릿 개선
report_html = Template("""
<html>
<head>
    <meta charset='utf-8'>
    <style>
        body { font-family: Arial, sans-serif; padding: 40px; line-height: 1.6; }
        h1, h2 { color: #2c3e50; }
        .section { margin-bottom: 30px; }
        table { border-collapse: collapse; width: 100%; margin-top: 10px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
        th { background-color: #f7f7f7; }
        .summary-box { background-color: #f0f8ff; padding: 10px; border: 1px solid #ccc; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>구간단속 분석 보고서</h1>

    <div class="section">
        <h2>📊 요약 통계</h2>
        <div class="summary-box">
            <p><strong>시점 통과 대수:</strong> {{ start_count }} 대</p>
            <p><strong>종점 통과 대수:</strong> {{ end_count }} 대</p>
            <p><strong>공통 차량 수:</strong> {{ match_count }} 대</p>
            <p><strong>통과율:</strong> {{ ratio }}%</p>
            <p><strong>평균 통과 시간:</strong> {{ avg_time }} 초</p>
            <p><strong>평균 구간 속도:</strong> {{ avg_speed }} km/h</p>
        </div>
    </div>

    <div class="section">
        <h2>📅 월별 통과량 통계</h2>
        <table>
            <tr><th>월</th><th>통과 차량 수</th></tr>
            {% for row in monthly %}
            <tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>📌 요일 + 시간대 상위 3</h2>
        <table>
            <tr><th>요일+시간</th><th>통과 차량 수</th></tr>
            {% for row in top3 %}
            <tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
""")

html_out = report_html.render(
    start_count=start_count,
    end_count=end_count,
    match_count=match_count,
    ratio=ratio,
    avg_time=f"{result_df['구간 통과시간'].mean():.2f}",
    avg_speed=f"{result_df['평균 구간속도'].mean():.2f}",
    monthly=monthly_stats.values.tolist(),
    top3=top3.values.tolist()
)

pdf_buffer = io.BytesIO()
HTML(string=html_out).write_pdf(pdf_buffer)
st.download_button("PDF 보고서 다운로드", data=pdf_buffer.getvalue(), file_name="구간단속_보고서.pdf")

