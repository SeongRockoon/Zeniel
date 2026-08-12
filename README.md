# Zeniel 작업량 분석

엑셀 파일을 업로드하지 않고, 필요한 표를 복사해 붙여넣어 분석하는 Streamlit 앱입니다.

## 현재 기능

- 상품마스터와 주문자료 붙여넣기
- 필수 열 자동 인식
- 박스수, 낱개수, 접촉횟수, 총중량 계산
- 묶음 존별 요약과 차트
- 입력 내용 초기화
- 파일 및 업무 데이터의 GitHub 커밋 방지 규칙

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
