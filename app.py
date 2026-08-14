import pandas as pd
import streamlit as st
import base64
import json
from datetime import date, datetime, timezone

import requests


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

MASTER_STORAGE_PATH = "data/product_master.json"


def empty_frame(columns: list[str], rows: int = 50) -> pd.DataFrame:
    return pd.DataFrame("", index=range(rows), columns=columns)


def repository_storage_config() -> tuple[str, str, str] | None:
    try:
        config = st.secrets.get("github", {})
        token = str(config.get("token", "")).strip()
        repository = str(config.get("repo", "")).strip()
        branch = str(config.get("branch", "main")).strip() or "main"
    except Exception:
        return None
    if not token or not repository:
        return None
    return token, repository, branch


def repository_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def padded_master(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.reindex(columns=MASTER_COLUMNS, fill_value="").fillna("").astype(str)
    if len(normalized) < 50:
        normalized = pd.concat(
            [normalized, empty_frame(MASTER_COLUMNS, 50 - len(normalized))],
            ignore_index=True,
        )
    return normalized.reset_index(drop=True)


def load_master_from_repository() -> tuple[pd.DataFrame | None, str]:
    config = repository_storage_config()
    if config is None:
        return None, "저장 연동이 설정되지 않았습니다."
    token, repository, branch = config
    url = f"https://api.github.com/repos/{repository}/contents/{MASTER_STORAGE_PATH}"
    try:
        response = requests.get(
            url,
            headers=repository_headers(token),
            params={"ref": branch},
            timeout=15,
        )
        if response.status_code == 404:
            return None, "아직 저장된 상품마스터가 없습니다."
        response.raise_for_status()
        encoded = response.json()["content"].replace("\n", "")
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        frame = pd.DataFrame(payload.get("rows", []))
        return padded_master(frame), f"저장된 상품마스터 {len(frame):,}행을 불러왔습니다."
    except Exception as error:
        return None, f"상품마스터를 불러오지 못했습니다: {error}"


def save_master_to_repository(frame: pd.DataFrame) -> tuple[bool, str]:
    config = repository_storage_config()
    if config is None:
        return False, "저장 연동 설정이 필요합니다."
    token, repository, branch = config
    clean = frame.reindex(columns=MASTER_COLUMNS, fill_value="").fillna("").astype(str)
    mask = clean.apply(lambda column: column.str.strip()).ne("").any(axis=1)
    clean = clean.loc[mask].reset_index(drop=True)
    if clean.empty:
        return False, "빈 상품마스터는 저장할 수 없습니다."

    url = f"https://api.github.com/repos/{repository}/contents/{MASTER_STORAGE_PATH}"
    headers = repository_headers(token)
    try:
        current = requests.get(url, headers=headers, params={"ref": branch}, timeout=15)
        sha = current.json().get("sha") if current.status_code == 200 else None
        if current.status_code not in {200, 404}:
            current.raise_for_status()
        document = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "columns": MASTER_COLUMNS,
            "rows": clean.to_dict(orient="records"),
        }
        content = base64.b64encode(
            json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("ascii")
        body = {
            "message": f"상품마스터 저장 ({len(clean)}행)",
            "content": content,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        saved = requests.put(url, headers=headers, json=body, timeout=30)
        saved.raise_for_status()
        return True, f"상품마스터 {len(clean):,}행을 저장했습니다."
    except Exception as error:
        return False, f"상품마스터를 저장하지 못했습니다: {error}"


def filled_rows(frame: pd.DataFrame) -> int:
    normalized = frame.fillna("").astype(str).apply(lambda col: col.str.strip())
    return int(normalized.ne("").any(axis=1).sum())


def initialize_state() -> None:
    defaults = {
        "workload_view": "자료 입력·검증",
        "master_data": empty_frame(MASTER_COLUMNS),
        "destinations": [{"id": 1, "name": "도착지 1", "data": empty_frame(ORDER_COLUMNS)}],
        "destination_seq": 1,
        "validation_result": None,
        "analysis_detail": None,
        "master_storage_checked": False,
        "master_storage_message": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.master_storage_checked:
        stored, message = load_master_from_repository()
        if stored is not None:
            st.session_state.master_data = stored
        st.session_state.master_storage_message = message
        st.session_state.master_storage_checked = True


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
    st.markdown(
        '<div class="section-kicker">WORKLOAD ANALYSIS · STEP 01</div>',
        unsafe_allow_html=True,
    )
    st.subheader("상품마스터")
    st.caption("원본 31개 열을 유지합니다. 엑셀의 데이터 행만 복사해 첫 번째 셀에 붙여넣으세요.")

    storage_configured = repository_storage_config() is not None
    if storage_configured:
        st.success(st.session_state.master_storage_message or "상품마스터 저장소가 연결되어 있습니다.")
    else:
        st.warning(
            "상품마스터 영구 저장을 사용하려면 앱 비밀정보에 GitHub 저장 설정이 필요합니다. "
            "실제 업무자료는 비공개 저장소에서만 사용하세요."
        )

    st.info(
        "표의 첫 번째 셀을 선택한 뒤 Ctrl+V 하세요. 열 제목은 붙여넣지 않습니다. "
        "원본의 2단 헤더는 Streamlit 표에서 ‘상위항목 | 하위항목’ 형태로 표시합니다."
    )
    edited = st.data_editor(
        st.session_state.master_data,
        key="master_editor",
        num_rows="dynamic",
        height=330,
        use_container_width=True,
        hide_index=False,
        column_config={column: st.column_config.TextColumn(column, width="medium") for column in MASTER_COLUMNS},
    )
    st.session_state.master_data = edited

    save_col, reload_col, reset_col, spacer = st.columns([1.25, 1.25, 1, 3.5])
    with save_col:
        if st.button(
            "상품마스터 저장",
            type="primary",
            use_container_width=True,
            disabled=not storage_configured,
        ):
            success, message = save_master_to_repository(edited)
            st.session_state.master_storage_message = message
            if success:
                st.success(message)
            else:
                st.error(message)
    with reload_col:
        if st.button("저장본 다시 불러오기", use_container_width=True, disabled=not storage_configured):
            stored, message = load_master_from_repository()
            st.session_state.master_storage_message = message
            if stored is not None:
                st.session_state.master_data = stored
                st.session_state.pop("master_editor", None)
                st.rerun()
            st.error(message)
    with reset_col:
        st.button("화면 초기화", on_click=reset_master, use_container_width=True)

    left, middle, right = st.columns(3)
    left.metric("입력 행", f"{filled_rows(edited):,}")
    middle.metric("기준 열", "31")
    right.metric("현재 단계", "상품마스터 입력")
    st.caption("※ 화면에서 열 이름이 길어 보일 수 있으나 원본 열의 순서와 개수는 유지됩니다.")


def render_destination_card(destination: dict, position: int) -> None:
    destination_id = destination["id"]
    input_count = filled_rows(destination["data"])
    label = destination["name"] or f"도착지 {destination_id}"
    with st.expander(f"{label}  ·  입력 {input_count:,}행", expanded=False):
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
            height=300,
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
    st.markdown(
        '<div class="section-kicker">WORKLOAD ANALYSIS · STEP 02</div>',
        unsafe_allow_html=True,
    )
    title, action = st.columns([5, 1])
    with title:
        st.subheader("도착지별 주문자료")
        st.caption("도착지마다 별도의 입력표를 만들고, 각 원본 자료를 서로 섞지 않고 붙여넣습니다.")
    with action:
        st.button("＋ 도착지 추가", on_click=add_destination, type="primary", use_container_width=True)

    st.info("각 표의 첫 번째 셀을 선택하고 엑셀의 데이터 행을 Ctrl+V 하세요. 열 제목은 제외합니다.")
    for position, destination in enumerate(st.session_state.destinations):
        render_destination_card(destination, position)


def normalized_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.fillna("").astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def compact_frame(frame: pd.DataFrame) -> pd.DataFrame:
    clean = frame.fillna("").copy()
    mask = clean.astype(str).apply(lambda col: col.str.strip()).ne("").any(axis=1)
    return clean.loc[mask].reset_index(drop=True)


def grouped_zone(value: object) -> str:
    zone = str(value).strip().upper()
    if zone in {"L01", "L02", "L03", "L04", "L05", "M01"}:
        return "L01"
    if zone in {"L06", "L07", "L08", "L09", "L10", "L11", "L12", "L13", "M02"}:
        return "L06"
    if zone in {"J", "J01", "D", "W"}:
        return "J01"
    if zone == "K22":
        return "K22"
    if zone.startswith("K") and zone[1:].isdigit() and int(zone[1:]) >= 23:
        return "K23"
    return zone or "미지정"


def validate_and_analyze() -> tuple[pd.DataFrame, pd.DataFrame]:
    issues: list[dict] = []
    master = compact_frame(st.session_state.master_data)
    if master.empty:
        issues.append({"구분": "상품마스터", "위치": "전체", "오류": "상품마스터가 비어 있습니다."})
        return pd.DataFrame(issues), pd.DataFrame()

    master["상품코드_키"] = normalized_text(master["상품코드"])
    master["박스입수_숫자"] = numeric_series(master["박스입수"])
    for index, row in master.iterrows():
        excel_row = index + 1
        if not row["상품코드_키"]:
            issues.append({"구분": "상품마스터", "위치": f"{excel_row}행", "오류": "상품코드 누락"})
        if pd.isna(row["박스입수_숫자"]) or row["박스입수_숫자"] <= 0:
            issues.append({"구분": "상품마스터", "위치": f"{excel_row}행", "오류": "박스입수가 숫자가 아니거나 0 이하"})
        if not str(row["피킹존"]).strip():
            issues.append({"구분": "상품마스터", "위치": f"{excel_row}행", "오류": "피킹존 누락"})

    duplicates = master.loc[master["상품코드_키"].ne("") & master["상품코드_키"].duplicated(False), "상품코드_키"].unique()
    for code in duplicates:
        candidates = master.loc[master["상품코드_키"].eq(code), ["피킹존", "박스입수_숫자"]].drop_duplicates()
        if len(candidates) > 1:
            issues.append({
                "구분": "상품마스터", "위치": code,
                "오류": "동일 상품코드에 피킹존 또는 박스입수가 여러 개입니다 — 첫 번째 행을 사용",
            })

    # 엑셀의 일반적인 XLOOKUP/VLOOKUP 첫 일치 방식과 동일하게 첫 번째 상품을 사용한다.
    master_lookup = master.drop_duplicates("상품코드_키", keep="first")
    detail_parts = []
    for destination in st.session_state.destinations:
        orders = compact_frame(destination["data"])
        if orders.empty:
            continue
        name = destination["name"] or f"도착지 {destination['id']}"
        orders["상품코드_키"] = normalized_text(orders["상품정보 | 상품코드"])
        orders["확정수량_숫자"] = numeric_series(orders["수량정보 | 확정수량"])
        orders["처리물량KG_숫자"] = numeric_series(orders["처리물량(KG)"])
        orders["주문단위_키"] = normalized_text(orders["주문단위"]).str.upper()
        for index, row in orders.iterrows():
            excel_row = index + 1
            if not row["상품코드_키"]:
                issues.append({"구분": name, "위치": f"{excel_row}행", "오류": "상품코드 누락"})
            elif row["상품코드_키"] not in set(master_lookup["상품코드_키"]):
                issues.append({"구분": name, "위치": f"{excel_row}행", "오류": f"상품마스터 미등록: {row['상품코드_키']}"})
            if pd.isna(row["확정수량_숫자"]) or row["확정수량_숫자"] < 0:
                issues.append({"구분": name, "위치": f"{excel_row}행", "오류": "확정수량이 숫자가 아니거나 음수"})
            if row["주문단위_키"] not in {"EA", "BOX", "박스", "CASE", "CS"}:
                issues.append({"구분": name, "위치": f"{excel_row}행", "오류": f"확인되지 않은 주문단위: {row['주문단위_키'] or '공란'}"})

        merged = orders.merge(
            master_lookup[["상품코드_키", "상품명칭", "피킹존", "박스입수_숫자"]],
            on="상품코드_키", how="left",
        )
        valid = merged[
            merged["상품코드_키"].ne("")
            & merged["박스입수_숫자"].notna()
            & merged["박스입수_숫자"].gt(0)
            & merged["확정수량_숫자"].notna()
            & merged["확정수량_숫자"].ge(0)
            & merged["주문단위_키"].isin({"EA", "BOX", "박스", "CASE", "CS"})
        ].copy()
        if valid.empty:
            continue
        valid["도착지"] = name
        valid["도착지ID"] = destination["id"]
        valid["묶음존"] = valid["피킹존"].map(grouped_zone)
        box_order = valid["주문단위_키"].isin({"BOX", "박스", "CASE", "CS"})
        valid["박스수"] = 0
        valid["낱개수"] = 0
        valid.loc[box_order, "박스수"] = valid.loc[box_order, "확정수량_숫자"]
        valid.loc[~box_order, "박스수"] = (
            valid.loc[~box_order, "확정수량_숫자"] // valid.loc[~box_order, "박스입수_숫자"]
        )
        valid.loc[~box_order, "낱개수"] = (
            valid.loc[~box_order, "확정수량_숫자"] % valid.loc[~box_order, "박스입수_숫자"]
        )
        valid[["박스수", "낱개수"]] = valid[["박스수", "낱개수"]].astype(int)
        # 기준 엑셀과 동일: 낱개가 있는 행을 1회로 보지 않고 실제 낱개 수량을 모두 접촉으로 계산한다.
        valid["접촉횟수"] = valid["박스수"] + valid["낱개수"]
        detail_parts.append(valid)

    if not detail_parts:
        return pd.DataFrame(issues), pd.DataFrame()
    detail = pd.concat(detail_parts, ignore_index=True)
    return pd.DataFrame(issues), detail


def run_validation() -> None:
    issues, detail = validate_and_analyze()
    st.session_state.validation_result = issues
    st.session_state.analysis_detail = detail


def render_validation() -> None:
    st.markdown('<div class="section-kicker">WORKLOAD ANALYSIS · STEP 03</div>', unsafe_allow_html=True)
    st.subheader("데이터 검증")
    st.caption("상품마스터와 모든 도착지 주문자료의 상품코드·박스입수·피킹존·확정수량을 확인합니다.")
    st.button("검증 실행", on_click=run_validation, type="primary")
    result = st.session_state.validation_result
    if result is None:
        st.info("검증 실행을 누르면 오류 위치와 원인을 표시합니다.")
        return
    if result.empty:
        st.success("검증이 완료되었습니다. 분석 가능한 오류가 없습니다.")
    else:
        st.warning(f"확인할 항목이 {len(result):,}건 있습니다. 오류가 있는 행은 분석에서 제외됩니다.")
        st.dataframe(result, use_container_width=True, hide_index=True, height=380)
    if st.session_state.analysis_detail is not None and not st.session_state.analysis_detail.empty:
        st.caption(f"현재 분석 가능 주문행: {len(st.session_state.analysis_detail):,}행")


def render_analysis(
    detail: pd.DataFrame,
    title: str,
    destination_label: str,
    source_rows: int,
    show_destination_comparison: bool,
) -> None:
    st.markdown('<div class="section-kicker">WORKLOAD ANALYSIS · DASHBOARD</div>', unsafe_allow_html=True)
    st.subheader(title)
    if detail.empty:
        st.warning("분석 가능한 주문자료가 없습니다. 검증 결과를 확인해주세요.")
        return

    by_zone = detail.groupby("묶음존", as_index=False).agg(
        SKU수=("상품코드_키", "nunique"),
        주문행수=("상품코드_키", "size"),
        확정수량=("확정수량_숫자", "sum"),
        박스수=("박스수", "sum"),
        낱개수=("낱개수", "sum"),
        접촉횟수=("접촉횟수", "sum"),
        처리물량KG=("처리물량KG_숫자", "sum"),
    ).sort_values("접촉횟수", ascending=False)
    total_touches = by_zone["접촉횟수"].sum()
    by_zone["접촉비중"] = by_zone["접촉횟수"].div(total_touches).fillna(0)
    top_zone = by_zone.iloc[0]

    st.markdown(
        f'<div class="analysis-meta"><b>분석일자</b> {date.today().isoformat()}<span></span>'
        f'<b>주문자료</b> {destination_label}</div>',
        unsafe_allow_html=True,
    )
    excluded_rows = max(source_rows - len(detail), 0)
    a, b, c, d, e = st.columns(5)
    a.metric("원본 라인수", f"{source_rows:,}")
    b.metric("분석 라인수", f"{len(detail):,}")
    c.metric("제외 라인수", f"{excluded_rows:,}")
    d.metric("총 출고수량", f"{detail['확정수량_숫자'].sum():,.0f}")
    e.metric("총 접촉횟수", f"{total_touches:,.0f}")

    st.warning(
        "보정작업량 계수가 현재 앱에 확인되지 않아 보정작업량·강도지수·작업강도는 계산하지 않습니다. "
        "확정되지 않은 임시값을 표시하지 않도록 수정했습니다."
    )

    table_view = by_zone[[
        "묶음존", "주문행수", "확정수량", "박스수", "낱개수", "접촉횟수",
        "처리물량KG", "접촉비중",
    ]].copy()
    table_view.columns = [
        "분석피킹존", "라인수", "총출고수량", "박스수", "낱개수", "접촉횟수",
        "총중량(kg)", "접촉비중",
    ]
    table_view["접촉비중"] = table_view["접촉비중"].map(lambda value: f"{value:.1%}")
    for column in ["총중량(kg)"]:
        table_view[column] = table_view[column].map(lambda value: f"{value:,.1f}")

    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.markdown("#### 존별 작업부하 상세")
        st.dataframe(table_view, use_container_width=True, hide_index=True, height=480)
    with right:
        st.markdown("#### 존별 접촉횟수")
        st.bar_chart(by_zone.set_index("묶음존")["접촉횟수"], color="#168a58", height=420)

    interpretation = (
        f"접촉횟수가 가장 많은 존은 **{top_zone['묶음존']}**이며, 전체 접촉횟수의 "
        f"**{top_zone['접촉비중']:.1%}**를 차지합니다. 보정작업량 계수 적용 전 결과입니다."
    )
    st.markdown("#### 자동 분석")
    st.info(interpretation)

    if show_destination_comparison:
        by_destination = detail.groupby("도착지", as_index=False).agg(
            SKU수=("상품코드_키", "nunique"),
            주문행수=("상품코드_키", "size"),
            확정수량=("확정수량_숫자", "sum"),
            박스수=("박스수", "sum"),
            낱개수=("낱개수", "sum"),
            접촉횟수=("접촉횟수", "sum"),
            처리물량KG=("처리물량KG_숫자", "sum"),
        ).sort_values("접촉횟수", ascending=False)
        tab_destination, tab_detail = st.tabs(["주문지 비교", "상품별 상세"])
        with tab_destination:
            st.bar_chart(by_destination.set_index("도착지")["접촉횟수"], color="#0b5d3b")
            st.dataframe(by_destination, use_container_width=True, hide_index=True)
        detail_holder = tab_detail
    else:
        st.markdown("#### 상품별 상세")
        detail_holder = st.container()

    with detail_holder:
        detail_view = detail[["도착지", "상품코드_키", "상품명칭", "피킹존", "묶음존", "확정수량_숫자", "박스입수_숫자", "박스수", "낱개수", "접촉횟수", "처리물량KG_숫자"]].copy()
        detail_view.columns = ["도착지", "상품코드", "상품명칭", "피킹존", "묶음존", "확정수량", "박스입수", "박스수", "낱개수", "접촉횟수", "처리물량(KG)"]
        st.dataframe(detail_view, use_container_width=True, hide_index=True, height=520)

    st.caption("접촉횟수 = 박스수 + 실제 낱개수입니다. 보정작업량과 작업강도는 계수가 확인된 뒤 적용합니다.")


def render_input_and_validation() -> None:
    st.markdown("### 입력자료")
    master_rows = filled_rows(st.session_state.master_data)
    order_rows = sum(filled_rows(item["data"]) for item in st.session_state.destinations)
    a, b, c = st.columns(3)
    a.metric("상품마스터", f"{master_rows:,}행")
    b.metric("등록 도착지", f"{len(st.session_state.destinations):,}개")
    c.metric("주문자료", f"{order_rows:,}행")

    with st.expander("상품마스터 관리", expanded=master_rows == 0):
        render_master()
    st.markdown("#### 도착지별 주문자료")
    render_orders()

    st.markdown("### 검증 및 분석")
    button_col, note_col = st.columns([1, 4])
    with button_col:
        st.button("검증하고 분석하기", on_click=run_validation, type="primary", use_container_width=True)
    with note_col:
        st.caption("상품코드·피킹존·박스입수·확정수량을 검증한 뒤 정상 행으로 대시보드를 갱신합니다.")

    result = st.session_state.validation_result
    if result is not None:
        if result.empty:
            st.success("검증이 완료되었습니다. 분석 가능한 오류가 없습니다.")
        else:
            st.warning(f"확인할 항목이 {len(result):,}건 있습니다. 해당 행은 분석에서 제외했습니다.")
            with st.expander("검증 오류 상세 보기"):
                st.dataframe(result, use_container_width=True, hide_index=True, height=260)
        st.info("검증이 끝났습니다. 위 메뉴에서 ‘주문지별 대시보드’ 또는 ‘당일 최종분석’을 선택하세요.")


def render_destination_dashboard() -> None:
    detail = st.session_state.analysis_detail
    if detail is None or detail.empty:
        st.info("먼저 ‘자료 입력·검증’ 화면에서 검증하고 분석하기를 실행해주세요.")
        return

    available = []
    for destination in st.session_state.destinations:
        destination_id = destination["id"]
        if destination_id in set(detail["도착지ID"]):
            available.append((destination_id, destination["name"] or f"도착지 {destination_id}"))
    if not available:
        st.warning("분석 가능한 주문지가 없습니다.")
        return

    label_by_id = {destination_id: label for destination_id, label in available}
    selected_id = st.selectbox(
        "분석할 주문지 선택",
        options=[destination_id for destination_id, _ in available],
        format_func=lambda value: label_by_id[value],
    )
    selected_detail = detail.loc[detail["도착지ID"].eq(selected_id)].copy()
    destination = next(item for item in st.session_state.destinations if item["id"] == selected_id)
    render_analysis(
        selected_detail,
        f"{label_by_id[selected_id]} 작업부하 대시보드",
        label_by_id[selected_id],
        filled_rows(destination["data"]),
        False,
    )


def render_daily_dashboard() -> None:
    detail = st.session_state.analysis_detail
    if detail is None or detail.empty:
        st.info("먼저 ‘자료 입력·검증’ 화면에서 검증하고 분석하기를 실행해주세요.")
        return
    destinations = [d["name"] or f"도착지 {d['id']}" for d in st.session_state.destinations if filled_rows(d["data"])]
    render_analysis(
        detail,
        "당일 최종 작업부하 대시보드",
        " + ".join(destinations),
        sum(filled_rows(item["data"]) for item in st.session_state.destinations),
        True,
    )


def render_workload_page() -> None:
    views = ["자료 입력·검증", "주문지별 대시보드", "당일 최종분석"]
    selected = st.segmented_control(
        "작업량 분석 화면",
        views,
        default=st.session_state.workload_view,
        selection_mode="single",
        label_visibility="collapsed",
    )
    if selected:
        st.session_state.workload_view = selected
    st.divider()

    if st.session_state.workload_view == "자료 입력·검증":
        render_input_and_validation()
    elif st.session_state.workload_view == "주문지별 대시보드":
        render_destination_dashboard()
    else:
        render_daily_dashboard()


def render_placeholder(title: str, message: str) -> None:
    st.subheader(title)
    st.info(message)
    st.caption("현재 버전에서는 상품마스터와 도착지별 주문자료 입력 구조까지만 구현했습니다.")


initialize_state()

st.markdown(
    """
    <style>
    :root {
        --forest: #0b5d3b;
        --forest-dark: #073f2a;
        --leaf: #168a58;
        --mint: #eaf6f0;
        --canvas: #f4f7f5;
        --line: #d8e5de;
        --ink: #17211c;
        --muted: #66736c;
    }
    html, body, [class*="css"] {font-family: "Pretendard", "Noto Sans KR", sans-serif;}
    .stApp {background: var(--canvas); color: var(--ink);}
    .block-container {max-width: 1800px; padding-top: 1.35rem; padding-bottom: 3rem;}
    header[data-testid="stHeader"] {background: transparent;}
    #MainMenu, footer {visibility: hidden;}

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--forest-dark) 0%, var(--forest) 100%);
        border-right: 0;
    }
    section[data-testid="stSidebar"] * {color: #fff;}
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color: #c9e2d6;}
    section[data-testid="stSidebar"] hr {border-color: rgba(255,255,255,.15);}
    section[data-testid="stSidebar"] div[role="radiogroup"] {gap: .35rem;}
    section[data-testid="stSidebar"] label[data-baseweb="radio"] {
        padding: .72rem .8rem; border-radius: .65rem; transition: .15s ease;
    }
    section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
        background: rgba(255,255,255,.10);
    }
    section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
        background: #fff; box-shadow: 0 8px 20px rgba(0,0,0,.13);
    }
    section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) * {
        color: var(--forest-dark) !important; font-weight: 750;
    }

    h1 {font-size: 2rem !important; letter-spacing: -.04em; color: var(--ink);}
    h2, h3 {letter-spacing: -.025em; color: var(--ink);}
    .section-kicker {font-size:.72rem;font-weight:800;letter-spacing:.13em;color:var(--leaf);margin-bottom:.25rem;}
    .hero-panel {
        background: linear-gradient(120deg, #0b5d3b 0%, #168a58 72%, #36a875 100%);
        color:#fff; border-radius: 1.15rem; padding: 1.35rem 1.55rem; margin: .2rem 0 1.25rem;
        box-shadow: 0 12px 30px rgba(11,93,59,.18); position:relative; overflow:hidden;
    }
    .hero-panel:after {content:"";position:absolute;width:210px;height:210px;border:42px solid rgba(255,255,255,.08);border-radius:50%;right:-70px;top:-95px;}
    .hero-eyebrow {font-size:.72rem;font-weight:800;letter-spacing:.16em;opacity:.8;}
    .hero-title {font-size:1.65rem;font-weight:850;margin:.25rem 0 .25rem;letter-spacing:-.035em;}
    .hero-copy {font-size:.88rem;color:#d9efe5;}

    div[data-testid="stMetric"] {
        background:#fff;border:1px solid var(--line);padding:15px 17px;border-radius:14px;
        box-shadow:0 4px 14px rgba(24,64,45,.045);
    }
    div[data-testid="stMetric"] label {color:var(--muted);}
    div[data-testid="stMetricValue"] {color:var(--forest-dark);font-weight:800;}
    div[data-testid="stDataEditor"] {
        border:1px solid #cddfd5;border-radius:12px;overflow:hidden;background:#fff;
        box-shadow:0 8px 24px rgba(24,64,45,.06);
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background:#fff;border-color:var(--line) !important;border-radius:16px !important;
        box-shadow:0 6px 20px rgba(24,64,45,.05);
    }
    div[data-testid="stAlert"] {border-radius:12px;border-color:#b9dfcb;background:var(--mint);color:var(--forest-dark);}

    .stButton > button {border-radius:9px;border-color:#b8cec2;font-weight:700;min-height:2.55rem;}
    .stButton > button:hover {border-color:var(--leaf);color:var(--forest);background:#f1faf5;}
    .stButton > button[kind="primary"] {background:var(--forest);border-color:var(--forest);color:#fff;}
    .stButton > button[kind="primary"]:hover {background:var(--forest-dark);border-color:var(--forest-dark);color:#fff;}
    div[data-testid="stSegmentedControl"] {background:#e7eee9;padding:.35rem;border-radius:12px;width:fit-content;}
    div[data-testid="stSegmentedControl"] button {border:0;border-radius:8px;color:#526158;font-weight:700;}
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {background:#fff;color:var(--forest);box-shadow:0 3px 9px rgba(30,70,48,.12);}
    .stTextInput input {border-color:#cddfd5;border-radius:9px;background:#fbfdfc;}
    .stTextInput input:focus {border-color:var(--leaf);box-shadow:0 0 0 1px var(--leaf);}
    .analysis-meta {
        display:flex;align-items:center;gap:.65rem;background:#fff;border:1px solid var(--line);
        border-radius:10px;padding:.7rem .9rem;margin:.4rem 0 1rem;color:var(--muted);font-size:.86rem;
    }
    .analysis-meta b {color:var(--forest-dark);}.analysis-meta span{width:1px;height:18px;background:var(--line);}
    .grade-guide {background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;}
    .grade-guide div {display:flex;justify-content:space-between;padding:.7rem .9rem;border-bottom:1px solid var(--line);}
    .grade-guide div:last-child {border-bottom:0;}.grade-guide b{color:var(--forest-dark);}.grade-guide span{color:var(--muted);}

    @media (max-width: 760px) {
        .block-container {padding-left:.7rem;padding-right:.7rem;padding-top:.7rem;}
        .hero-panel {padding:1.1rem;border-radius:.9rem}.hero-title{font-size:1.35rem;}
        div[data-testid="stSegmentedControl"] {width:100%;overflow-x:auto;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## ZENIEL OPS")
    st.caption("LOGISTICS OPERATION SYSTEM")
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
    st.markdown(
        """
        <div class="hero-panel">
            <div class="hero-eyebrow">ZENIEL LOGISTICS</div>
            <div class="hero-title">작업량 분석</div>
            <div class="hero-copy">상품마스터와 도착지별 주문자료를 준비하고, 검증을 거쳐 작업 부하를 분석합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_workload_page()
