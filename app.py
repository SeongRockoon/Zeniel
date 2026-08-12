import io
import re

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Zeniel 작업량 분석", page_icon="📦", layout="wide")


MASTER_SAMPLE = """상품코드\t상품명\t존\t박스입수\t개별중량
100001\t생수 500ml\tJ01\t20\t0.5
100002\t참치캔\tL01\t12\t0.2
100003\t식용유\tK22\t6\t1.0"""

ORDER_SAMPLE = """상품코드\t확정수량
100001\t45
100002\t25
100003\t12"""

MASTER_COLUMNS = ["상품코드", "상품명", "존", "박스입수", "개별중량"]
ORDER_COLUMNS = ["상품코드", "확정수량"]


def clean_name(value: object) -> str:
    return re.sub(r"[\s_()\[\]/.-]", "", str(value)).lower()


ALIASES = {
    "상품코드": {"상품코드", "품목코드", "sku", "skucode", "productcode"},
    "상품명": {"상품명", "상품명칭", "품목명", "productname"},
    "존": {"존", "zone", "피킹존", "상품존", "재고위치"},
    "박스입수": {"박스입수", "입수", "박스당수량", "casepack", "boxqty"},
    "개별중량": {"개별중량", "중량", "단위중량", "unitweight"},
    "확정수량": {"확정수량", "출고수량", "지시수량", "주문수량", "수량", "qty"},
}


def parse_paste(raw: str, required: list[str]) -> pd.DataFrame:
    text = raw.strip()
    if not text:
        raise ValueError("붙여넣은 내용이 없습니다.")

    first = text.splitlines()[0]
    separator = "\t" if "\t" in first else "," if "," in first else None
    if separator is None:
        raise ValueError("엑셀에서 열 제목을 포함해 복사한 뒤 그대로 붙여넣어 주세요.")

    frame = pd.read_csv(io.StringIO(text), sep=separator, dtype=str).dropna(how="all")
    normalized = {clean_name(column): column for column in frame.columns}
    rename = {}
    for target in required:
        candidates = {clean_name(name) for name in ALIASES[target]}
        source = next((normalized[name] for name in candidates if name in normalized), None)
        if source is None:
            raise ValueError(f"필수 열 ‘{target}’을 찾지 못했습니다.")
        rename[source] = target

    frame = frame.rename(columns=rename)[required].copy()
    frame = frame.dropna(how="all")
    frame["상품코드"] = frame["상품코드"].fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
    frame = frame[frame["상품코드"] != ""]
    return frame


def grouped_zone(zone: object) -> str:
    value = str(zone).strip().upper()
    if value in {"L01", "L02", "L03", "L04", "L05", "M01"}:
        return "L01"
    if value in {"L06", "L07", "L08", "L09", "L10", "L11", "L12", "L13", "M02"}:
        return "L06"
    if value in {"J", "J01", "D", "W"}:
        return "J01"
    if value == "K22":
        return "K22"
    match = re.fullmatch(r"K(\d+)", value)
    if match and int(match.group(1)) >= 23:
        return "K23"
    return value or "미지정"


def analyze(master: pd.DataFrame, orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    master = master.copy()
    orders = orders.copy()
    for column in ["박스입수", "개별중량"]:
        master[column] = pd.to_numeric(master[column], errors="coerce")
    orders["확정수량"] = pd.to_numeric(orders["확정수량"], errors="coerce")

    invalid_master = master[master[["박스입수", "개별중량"]].isna().any(axis=1)]
    invalid_orders = orders[orders["확정수량"].isna()]
    if not invalid_master.empty or not invalid_orders.empty:
        raise ValueError("박스입수·개별중량·확정수량에는 숫자만 입력해 주세요.")
    if (master["박스입수"] <= 0).any() or (orders["확정수량"] < 0).any():
        raise ValueError("박스입수는 0보다 커야 하고 확정수량은 음수일 수 없습니다.")

    master = master.drop_duplicates("상품코드", keep="last")
    merged = orders.merge(master, on="상품코드", how="left", indicator=True)
    missing_count = int((merged["_merge"] == "left_only").sum())
    merged = merged[merged["_merge"] == "both"].drop(columns="_merge")
    if merged.empty:
        raise ValueError("주문자료와 상품마스터에서 일치하는 상품코드가 없습니다.")

    merged["박스수"] = (merged["확정수량"] // merged["박스입수"]).astype(int)
    merged["낱개수"] = (merged["확정수량"] % merged["박스입수"]).astype(int)
    merged["접촉횟수"] = merged["박스수"] + (merged["낱개수"] > 0).astype(int)
    merged["총중량(kg)"] = (merged["확정수량"] * merged["개별중량"]).round(2)
    merged["묶음존"] = merged["존"].map(grouped_zone)

    summary = (
        merged.groupby("묶음존", as_index=False)
        .agg(
            SKU수=("상품코드", "nunique"),
            총수량=("확정수량", "sum"),
            박스수=("박스수", "sum"),
            낱개수=("낱개수", "sum"),
            접촉횟수=("접촉횟수", "sum"),
            **{"총중량(kg)": ("총중량(kg)", "sum")},
        )
        .sort_values("접촉횟수", ascending=False)
    )
    summary["총중량(kg)"] = summary["총중량(kg)"].round(2)
    return merged, summary, missing_count


st.markdown(
    """
    <style>
    .block-container {max-width: 1280px; padding-top: 2rem;}
    div[data-testid="stMetric"] {background:#f6f8fb; border:1px solid #e5e9f0; padding:16px; border-radius:14px;}
    .notice {padding:14px 16px; border-radius:12px; background:#eef6ff; border:1px solid #cfe4ff; color:#164b7a;}
    textarea {font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📦 Zeniel 작업량 분석")
st.caption("엑셀의 열 제목과 데이터를 함께 복사해 붙여넣으세요. 파일 업로드 기능은 사용하지 않습니다.")
st.markdown('<div class="notice">입력 내용은 분석에만 사용되며 이 앱은 별도의 파일이나 데이터베이스에 저장하지 않습니다.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("사용 방법")
    st.write("1. 상품마스터 붙여넣기\n\n2. 주문자료 붙여넣기\n\n3. 분석 실행\n\n4. 결과 확인")
    sample = st.toggle("예시 데이터로 시험하기")
    if st.button("모든 입력 초기화", use_container_width=True):
        st.session_state.master_text = ""
        st.session_state.order_text = ""
        st.session_state.pop("result", None)
        st.rerun()

if "master_text" not in st.session_state:
    st.session_state.master_text = ""
if "order_text" not in st.session_state:
    st.session_state.order_text = ""
if sample and not st.session_state.master_text and not st.session_state.order_text:
    st.session_state.master_text = MASTER_SAMPLE
    st.session_state.order_text = ORDER_SAMPLE

left, right = st.columns(2, gap="large")
with left:
    st.subheader("1. 상품마스터")
    st.caption("필수 열: 상품코드, 상품명, 존, 박스입수, 개별중량(kg)")
    master_text = st.text_area("상품마스터 붙여넣기", key="master_text", height=250, label_visibility="collapsed", placeholder="상품코드\t상품명\t존\t박스입수\t개별중량")
with right:
    st.subheader("2. 주문자료")
    st.caption("필수 열: 상품코드, 확정수량")
    order_text = st.text_area("주문자료 붙여넣기", key="order_text", height=250, label_visibility="collapsed", placeholder="상품코드\t확정수량")

if st.button("분석 실행", type="primary", use_container_width=True):
    try:
        master = parse_paste(master_text, MASTER_COLUMNS)
        orders = parse_paste(order_text, ORDER_COLUMNS)
        st.session_state.result = analyze(master, orders)
    except ValueError as error:
        st.error(str(error))

if "result" in st.session_state:
    detail, summary, missing_count = st.session_state.result
    st.divider()
    st.subheader("3. 분석 결과")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 SKU", f"{detail['상품코드'].nunique():,}")
    c2.metric("총 출고수량", f"{detail['확정수량'].sum():,.0f}")
    c3.metric("총 접촉횟수", f"{detail['접촉횟수'].sum():,}")
    c4.metric("총 중량", f"{detail['총중량(kg)'].sum():,.1f} kg")
    if missing_count:
        st.warning(f"상품마스터에 없는 주문자료 {missing_count}행은 계산에서 제외했습니다.")

    tab1, tab2 = st.tabs(["존별 요약", "상품별 상세"])
    with tab1:
        st.bar_chart(summary.set_index("묶음존")["접촉횟수"], color="#2f6fed")
        st.dataframe(summary, use_container_width=True, hide_index=True)
    with tab2:
        columns = ["상품코드", "상품명", "존", "묶음존", "확정수량", "박스수", "낱개수", "접촉횟수", "총중량(kg)"]
        st.dataframe(detail[columns], use_container_width=True, hide_index=True)

st.caption("현재 버전은 기본 작업량 계산 화면입니다. 다음 단계에서 현장 계수와 인원 산정 기준을 연결합니다.")
