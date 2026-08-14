# Zeniel 작업량 분석

엑셀 파일을 업로드하지 않고, 필요한 표를 복사해 붙여넣어 분석하는 Streamlit 앱입니다.

## 현재 기능

- 상품마스터와 주문자료 붙여넣기
- 필수 열 자동 인식
- 박스수, 낱개수, 접촉횟수, 총중량 계산
- 묶음 존별 요약과 차트
- 입력 내용 초기화
- 상품마스터 저장 및 앱 시작 시 자동 불러오기

## 상품마스터 저장 설정

상품마스터는 `data/product_master.json`에 저장됩니다. 실제 업무자료를 저장할 경우
GitHub 저장소와 Streamlit 앱을 모두 비공개로 운영하세요.

1. GitHub에서 `SeongRockoon/Zeniel` 저장소만 접근 가능한 Fine-grained token을 만듭니다.
2. 토큰 권한은 `Contents: Read and write`만 부여합니다.
3. Streamlit Community Cloud의 앱 설정에서 `Secrets`에 아래 내용을 입력합니다.

```toml
[github]
token = "발급받은_토큰"
repo = "SeongRockoon/Zeniel"
branch = "main"
```

토큰을 `app.py`, `README.md`, `secrets.toml` 또는 GitHub 저장소 파일에 직접 올리지 마세요.

## 로컬 실행

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포

- Repository: `SeongRockoon/Zeniel`
- Branch: `main`
- Main file path: `app.py`

배포 후 앱을 Private으로 유지하고 허용된 계정만 Viewer로 추가하세요.
