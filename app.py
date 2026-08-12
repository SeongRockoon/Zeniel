import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Zeniel 물류 운영 시스템",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


MASTER_COLUMNS = [
    "No.", "물류센터", "창고", "재고위치", "재고속성", "피킹존", "로케이션",
    "로케이션유형", "렉타입", "상품코드", "상품명칭", "저장조건", "박스입수",
    "현재고 | 수량", "현재고 | 단위", "재고정보 | 수량", "재고정보 | 단위①",
    "재고정보 | 단위②", "재고정보 | 현재고수량", "재고정보 | 가용재고수량",
    "재고정보 | 재고할당수량", "재고정보 | 피킹재고", "재고정보 | 단가",
    "소비기한임박여부", "제조일자", "소비일자", "소비기간(잔여/전체)",
    "소비기한잔여(%)", "상품이력정보 | 이력번호", "중량 | 현재고",
    "중량 | 이동가능중량",
]

ORDER_COLUMNS = [
    "No.", "출고일자", "주문번호", "고객 | 관리처코드", "고객 | 배송인도처명",
    "상품정보 | 상품코드", "상품정보 | 상품명칭", "수량정보 | 지시건수",
    "수량정보 | 진행예정량", "수량정보 | 처리량", "수량정보 | 검수량",
    "수량정보 | 확정수량", "주문단위", "처리물량(KG)",
    "고객(하나로마트 경로만) | 고객코드", "고객(하나로마트 경로만) | 고객명",
]


def empty_frame(columns: list[str], rows: int = 50) -> pd.DataFrame:
    return pd.DataFrame("", index=range(rows), columns=columns)


def filled_rows(frame: pd.DataFrame) -> int:
    normalized = frame.fillna("").astype(str).apply(lambda col: col.str.strip())
    return int(normalized.ne("").any(axis=1).sum())


def initialize_state() -> None:
    defaults = {
        "workload_page": "상품마스터",
        "master_data": empty_frame(MASTER_COLUMNS),
        "destinations": [{"id": 1, "name": "도착지 1", "data": empty_frame(ORDER_COLUMNS)}],
        "destination_seq": 1,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_master() -> None:
    st.session_state.master_data = empty_frame(MASTER_COLUMNS)
    st.session_state.pop("master_editor", None)


def add_destination() -> None:
    st.session_state.destination_seq += 1
    number = st.session_state.destination_seq
    st.session_state.destinations.append(
        {"id": number, "name": f"도착지 {number}", "data": empty_frame(ORDER_COLUMNS)}
    )


def render_master() -> None:
    title, action = st.columns([5, 1])
    with title:
        st.subheader("상품마스터")
        st.caption("원본 31개 열을 유지합니다. 엑셀의 데이터 행만 복사해 첫 번째 셀에 붙여넣으세요.")
    with action:
        st.button("전체 초기화", on_click=reset_master, use_container_width=True)

    st.info(
        "표의 첫 번째 셀을 선택한 뒤 Ctrl+V 하세요. 열 제목은 붙여넣지 않습니다. "
        "원본의 2단 헤더는 Streamlit 표에서 ‘상위항목 | 하위항목’ 형태로 표시합니다."
    )
    edited = st.data_editor(
        st.session_state.master_data,
        key="master_editor",
        num_rows="dynamic",
        height=570,
        use_container_width=True,
        hide_index=False,
        column_config={column: st.column_config.TextColumn(column, width="medium") for column in MASTER_COLUMNS},
    )
    st.session_state.master_data = edited
    left, middle, right = st.columns(3)
    left.metric("입력 행", f"{filled_rows(edited):,}")
    middle.metric("기준 열", "31")
    right.metric("현재 단계", "상품마스터 입력")
    st.caption("※ 화면에서 열 이름이 길어 보일 수 있으나 원본 열의 순서와 개수는 유지됩니다.")


def render_destination_card(destination: dict, position: int) -> None:
    destination_id = destination["id"]
    with st.container(border=True):
        name_col, clear_col, delete_col = st.columns([5, 1, 1])
        with name_col:
            destination["name"] = st.text_input(
                "도착지 또는 주문자료 이름",
                value=destination["name"],
                key=f"destination_name_{destination_id}",
            )
        with clear_col:
            st.write("")
            st.write("")
            if st.button("이 표 초기화", key=f"clear_destination_{destination_id}", use_container_width=True):
                destination["data"] = empty_frame(ORDER_COLUMNS)
                st.session_state.pop(f"order_editor_{destination_id}", None)
                st.rerun()
        with delete_col:
            st.write("")
            st.write("")
            disabled = len(st.session_state.destinations) == 1
            if st.button("삭제", key=f"delete_destination_{destination_id}", disabled=disabled, use_container_width=True):
                st.session_state.destinations.pop(position)
                st.rerun()

        st.caption("16개 열 · 원본 순서 유지 · 다른 도착지 자료와 분리")
        edited = st.data_editor(
            destination["data"],
            key=f"order_editor_{destination_id}",
            num_rows="dynamic",
            height=430,
            use_container_width=True,
            hide_index=False,
            column_config={column: st.column_config.TextColumn(column, width="medium") for column in ORDER_COLUMNS},
        )
        destination["data"] = edited
        a, b, c = st.columns(3)
        a.metric("입력 행", f"{filled_rows(edited):,}")
        b.metric("기준 열", "16")
        c.metric("자료 구분", destination["name"] or f"도착지 {destination_id}")


def render_orders() -> None:
    title, action = st.columns([5, 1])
    with title:
        st.subheader("도착지별 주문자료")
        st.caption("도착지마다 별도의 입력표를 만들고, 각 원본 자료를 서로 섞지 않고 붙여넣습니다.")
    with action:
        st.button("＋ 도착지 추가", on_click=add_destination, type="primary", use_container_width=True)

    st.info("각 표의 첫 번째 셀을 선택하고 엑셀의 데이터 행을 Ctrl+V 하세요. 열 제목은 제외합니다.")
    for position, destination in enumerate(st.session_state.destinations):
        render_destination_card(destination, position)


def render_placeholder(title: str, message: str) -> None:
    st.subheader(title)
    st.info(message)
    st.caption("현재 버전에서는 상품마스터와 도착지별 주문자료 입력 구조까지만 구현했습니다.")


initialize_state()

st.markdown(
    """
    <style>
    .block-container {max-width: 1800px; padding-top: 1.7rem; padding-bottom: 3rem;}
    div[data-testid="stMetric"] {background:#f6f8fb;border:1px solid #e1e7ef;padding:14px;border-radius:12px;}
    div[data-testid="stDataEditor"] {border:1px solid #d9e0e8;border-radius:10px;overflow:hidden;}
    @media (max-width: 760px) {.block-container {padding-left:.7rem;padding-right:.7rem;}}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("ZENIEL OPS")
    st.caption("물류 운영 통합 시스템")
    main_menu = st.radio(
        "전체 메뉴",
        ["종합 업무상황판", "작업량 분석", "로스 분석", "재고 관리", "인원·근무 관리", "기준정보·설정"],
        index=1,
    )
    st.divider()
    st.caption("🔒 입력 데이터는 GitHub에 저장하지 않습니다.")

if main_menu != "작업량 분석":
    st.title(main_menu)
    st.info("준비 중인 메뉴입니다. 현재는 작업량 분석의 입력 구조를 먼저 만들고 있습니다.")
else:
    st.title("작업량 분석")
    st.caption("상품마스터와 도착지별 주문자료를 준비한 뒤 검증과 분석으로 진행합니다.")

    pages = ["상품마스터", "도착지별 주문자료", "데이터 검증", "분석 결과"]
    selected = st.segmented_control(
        "작업 단계",
        pages,
        default=st.session_state.workload_page,
        key="workload_navigation",
        selection_mode="single",
        label_visibility="collapsed",
    )
    if selected:
        st.session_state.workload_page = selected
    st.divider()

    if st.session_state.workload_page == "상품마스터":
        render_master()
    elif st.session_state.workload_page == "도착지별 주문자료":
        render_orders()
    elif st.session_state.workload_page == "데이터 검증":
        render_placeholder("데이터 검증", "다음 단계에서 상품코드 대조와 필수값 검증을 연결합니다.")
    else:
        render_placeholder("분석 결과", "검증 기준과 작업량 계산식을 확정한 뒤 연결합니다.")
