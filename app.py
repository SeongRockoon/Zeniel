import io
import re

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Zeniel 물류 생산성 시스템",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


REQUIRED_MASTER_COLUMNS = {
    "상품존": ["상품존", "피킹존"],
    "로케이션": ["로케이션"],
    "상품코드": ["상품코드", "SKU"],
    "상품명": ["상품명", "상품명칭"],
    "박스입수량": ["박스입수량", "박스입수", "입수량"],
}

OPTIONAL_MASTER_COLUMNS = {
    "개별중량(kg)": ["개별중량(kg)", "개별중량", "낱개중량"],
    "작업유형": ["작업유형"],
    "파레트입수량": ["파레트입수량", "파렛트입수량"],
    "라인중요도계수": ["라인중요도계수"],
    "상품복잡도계수": ["상품복잡도계수"],
}


def inject_css():
    st.markdown(
        """
        <style>
        :root { --nav:#102c46; --teal:#078a98; --mint:#17a77b; --ink:#162433; }
        .stApp { background:#f4f7fb; color:var(--ink); }
        [data-testid="stSidebar"] { background:linear-gradient(180deg,#112f4a 0%,#0c263e 100%); }
        [data-testid="stSidebar"] * { color:#f4fbff; }
        [data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.12); }
        .brand { padding:8px 4px 22px; }
        .brand-title { font-size:20px; font-weight:800; line-height:1.25; }
        .brand-sub { font-size:11px; opacity:.72; margin-top:4px; }
        .page-title { font-size:28px; font-weight:850; margin:2px 0 4px; }
        .page-sub { color:#66788a; margin-bottom:18px; }
        .stepper { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; background:white;
                   border:1px solid #dce4ec; border-radius:13px; padding:14px; margin-bottom:18px; }
        .step { text-align:center; color:#8493a3; font-size:12px; font-weight:700; }
        .step b { display:inline-flex; width:30px; height:30px; border-radius:50%; align-items:center;
                  justify-content:center; border:1px solid #c9d3dd; margin-bottom:6px; background:#fff; }
        .step.active { color:#087f8e; }.step.active b { color:#fff; background:#087f8e; border-color:#087f8e; }
        .panel { background:white; border:1px solid #dce4ec; border-radius:13px; padding:18px; margin-bottom:14px;
                 box-shadow:0 2px 8px rgba(22,36,51,.035); }
        .panel-title { font-size:16px; font-weight:800; margin-bottom:4px; }
        .panel-note { color:#6d7d8d; font-size:13px; margin-bottom:10px; }
        .metric-card { background:#fff; border:1px solid #dce4ec; border-radius:12px; padding:16px; min-height:112px; }
        .metric-label { font-size:13px; font-weight:750; color:#487080; }
        .metric-value { font-size:29px; font-weight:850; color:#087f8e; margin-top:8px; }
        .metric-unit { font-size:13px; font-weight:600; color:#6f7e8b; }
        .ok { color:#16875f; font-weight:750; }.warn { color:#d07316; font-weight:750; }
        div[data-testid="stFileUploader"] { background:#fbfdff; border-radius:12px; padding:6px; }
        div[data-testid="stDataFrame"] { border:1px solid #e1e8ef; border-radius:10px; overflow:hidden; }
        .stButton > button { border-radius:8px; font-weight:750; }
        @media(max-width:900px){.stepper{grid-template-columns:1fr;}.step{text-align:left}.page-title{font-size:23px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def clean_header(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def flatten_headers(top, bottom):
    top = pd.Series(top).ffill().fillna("")
    result = []
    for a, b in zip(top, bottom):
        a, b = str(a).strip(), str(b).strip()
        if b.startswith("Unnamed") or b == "nan":
            b = ""
        if a.startswith("Unnamed") or a == "nan":
            a = ""
        result.append(f"{a}_{b}" if a and b and a != b else (b or a))
    return result


@st.cache_data(show_spinner=False)
def read_uploaded_file(file_bytes, filename, header_rows):
    bio = io.BytesIO(file_bytes)
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "csv":
        for encoding in ("utf-8-sig", "cp949", "utf-8"):
            try:
                bio.seek(0)
                return pd.read_csv(bio, encoding=encoding, header=0)
            except UnicodeDecodeError:
                continue
        raise ValueError("CSV 문자 인코딩을 확인할 수 없습니다.")
    if header_rows == 2:
        raw = pd.read_excel(bio, header=[0, 1])
        raw.columns = flatten_headers(
            [x[0] for x in raw.columns], [x[1] for x in raw.columns]
        )
        return raw
    return pd.read_excel(bio, header=0)


def find_column(columns, aliases):
    normalized = {clean_header(c): c for c in columns}
    for alias in aliases:
        if clean_header(alias) in normalized:
            return normalized[clean_header(alias)]
    for alias in aliases:
        key = clean_header(alias)
        for norm, original in normalized.items():
            if norm.endswith("_" + key) or norm == key:
                return original
    return None


def map_master_columns(df):
    mapping, missing = {}, []
    for standard, aliases in REQUIRED_MASTER_COLUMNS.items():
        found = find_column(df.columns, aliases)
        if found is None:
            missing.append(standard)
        else:
            mapping[standard] = found
    for standard, aliases in OPTIONAL_MASTER_COLUMNS.items():
        found = find_column(df.columns, aliases)
        if found is not None:
            mapping[standard] = found
    return mapping, missing


def analysis_zone(zone):
    z = str(zone).strip().upper()
    if not z or z == "NAN":
        return ""
    if z in {"J", "J01", "D", "W"}:
        return "J01"
    if z == "M01":
        return "L01"
    if z == "M02":
        return "L06"
    match = re.fullmatch(r"L(\d{1,2})", z)
    if match:
        number = int(match.group(1))
        if 1 <= number <= 5:
            return "L01"
        if 6 <= number <= 13:
            return "L06"
    match = re.fullmatch(r"K(\d+)", z)
    if match:
        number = int(match.group(1))
        if 12 <= number <= 16:
            return "K12"
        if number == 22:
            return "K22"
        if number >= 23:
            return "K23"
    return z


def normalize_master(df, mapping):
    out = pd.DataFrame()
    for standard, original in mapping.items():
        out[standard] = df[original]
    out = out.dropna(how="all")
    out["상품코드"] = out["상품코드"].astype(str).str.strip()
    out = out[~out["상품코드"].isin(["", "nan", "None"])]
    out["분석피킹존"] = out["상품존"].apply(analysis_zone)
    for col in ["박스입수량", "개별중량(kg)", "파레트입수량", "라인중요도계수", "상품복잡도계수"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "개별중량(kg)" in out:
        out["박스무게(kg)"] = out["박스입수량"] * out["개별중량(kg)"]
    return out


def stepper(active=1):
    labels = ["상품마스터", "주문 업로드", "작업배정", "분석 실행", "결과 확인"]
    html = '<div class="stepper">'
    for i, label in enumerate(labels, 1):
        cls = "step active" if i == active else "step"
        html += f'<div class="{cls}"><b>{i}</b><br>{label}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def sidebar():
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="brand-title">📦 물류 생산성 시스템</div>'
            '<div class="brand-sub">Warehouse Productivity</div></div>',
            unsafe_allow_html=True,
        )
        page = st.radio(
            "메뉴",
            ["대시보드", "상품마스터", "주문 업로드", "작업배정", "인원계수", "분석결과"],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("관리자 · Zeniel")
    return page


def empty_page(title, description, step):
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">{description}</div>', unsafe_allow_html=True)
    stepper(step)
    st.info("화면 골격을 먼저 구성했습니다. 상품마스터 검증 후 다음 단계에서 실제 기능을 연결합니다.")


def master_page():
    st.markdown('<div class="page-title">상품마스터 관리</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">상품 기준정보를 업로드하고 작업량 분석에 필요한 열을 검증합니다.</div>', unsafe_allow_html=True)
    stepper(1)

    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.markdown('<div class="panel-title">1. 상품마스터 업로드</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-note">Excel 또는 CSV 파일을 선택하세요. 파일은 GitHub에 저장하지 않습니다.</div>', unsafe_allow_html=True)
        header_rows = st.radio("헤더 형태", ["1행 제목", "2행 병합 제목"], horizontal=True)
        uploaded = st.file_uploader("상품마스터 파일", type=["xlsx", "xls", "csv"])
    with right:
        st.markdown('<div class="panel-title">필수 기준열</div>', unsafe_allow_html=True)
        st.markdown(
            "상품존 · 로케이션 · 상품코드 · 상품명 · 박스입수량<br>"
            "<span style='color:#6d7d8d;font-size:13px'>개별중량과 작업유형은 선택 항목이며 이후 직접 보완할 수 있습니다.</span>",
            unsafe_allow_html=True,
        )
        st.caption("존 통합: J01/D/W→J01 · L01~05/M01→L01 · L06~13/M02→L06 · K12~16→K12 · K22→K22 · K23 이상→K23")

    if not uploaded:
        st.markdown("---")
        st.subheader("업로드 미리보기")
        st.caption("파일을 올리면 열 인식 결과와 상위 10개 행이 여기에 표시됩니다.")
        return

    try:
        df = read_uploaded_file(uploaded.getvalue(), uploaded.name, 2 if header_rows.startswith("2") else 1)
        mapping, missing = map_master_columns(df)
    except Exception as exc:
        st.error(f"파일을 읽지 못했습니다: {exc}")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="metric-card"><div class="metric-label">전체 행</div><div class="metric-value">{len(df):,}<span class="metric-unit"> 행</span></div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-card"><div class="metric-label">전체 열</div><div class="metric-value">{len(df.columns):,}<span class="metric-unit"> 개</span></div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="metric-card"><div class="metric-label">인식된 기준열</div><div class="metric-value">{len(mapping):,}<span class="metric-unit"> 개</span></div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-card"><div class="metric-label">미등록 필수열</div><div class="metric-value">{len(missing):,}<span class="metric-unit"> 개</span></div></div>', unsafe_allow_html=True)

    st.markdown("### 열 인식 결과")
    if missing:
        st.warning("자동 인식하지 못한 필수열: " + ", ".join(missing))
        st.caption("다음 버전에서 열 직접 연결 기능을 추가합니다. 현재는 원본 열 제목을 확인해 주세요.")
    else:
        st.success("작업량 분석에 필요한 필수열을 모두 확인했습니다.")
        master = normalize_master(df, mapping)
        st.session_state["product_master"] = master
        duplicates = int(master["상품코드"].duplicated().sum())
        if duplicates:
            st.warning(f"중복 상품코드가 {duplicates:,}행 있습니다. 같은 상품이 여러 로케이션에 존재하는지 확인이 필요합니다.")
        st.dataframe(master.head(10), use_container_width=True, hide_index=True)
        st.download_button(
            "정리된 상품마스터 CSV 다운로드",
            master.to_csv(index=False).encode("utf-8-sig"),
            file_name="정리된_상품마스터.csv",
            mime="text/csv",
            type="primary",
        )
    with st.expander("원본 열과 인식 결과 보기"):
        st.write(pd.DataFrame({"분석 기준열": list(mapping.keys()), "원본 열": list(mapping.values())}))
        st.write("원본 열:", list(map(str, df.columns)))


def dashboard_page():
    st.markdown('<div class="page-title">분석 대시보드</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">존별 작업부하와 인원별 생산성을 한눈에 확인합니다.</div>', unsafe_allow_html=True)
    cards = [("총 출고수량", "—", "낱개"), ("총 보정작업량", "—", "점"), ("평균 작업강도", "—", ""), ("인원별 생산성", "—", "점/인")]
    cols = st.columns(4)
    for col, (label, value, unit) in zip(cols, cards):
        col.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}<span class="metric-unit"> {unit}</span></div></div>', unsafe_allow_html=True)
    st.markdown("### 분석 준비 상태")
    if "product_master" in st.session_state:
        st.success(f"상품마스터 {len(st.session_state['product_master']):,}개 행이 준비되었습니다.")
    else:
        st.info("먼저 상품마스터 메뉴에서 기준정보를 업로드해 주세요.")


inject_css()
page = sidebar()
if page == "상품마스터":
    master_page()
elif page == "대시보드":
    dashboard_page()
elif page == "주문 업로드":
    empty_page("주문리스트 업로드", "Excel 업로드와 복사·붙여넣기로 출고 원본을 입력합니다.", 2)
elif page == "작업배정":
    empty_page("작업배정", "피킹존별 담당자와 배분율을 설정합니다.", 3)
elif page == "인원계수":
    empty_page("인원계수", "작업자의 숙련도·업무조건·근무시간을 관리합니다.", 3)
else:
    empty_page("분석결과", "존별 부하와 인원별 생산성 결과를 비교합니다.", 5)
