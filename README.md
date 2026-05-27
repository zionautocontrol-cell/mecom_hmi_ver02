# MECOM HMI ver02

Streamlit 기반 HMI/모니터링 앱과 Modbus RTU 데이터 수집 워커입니다.

## ver02 변경사항 (vs mecom_hmi)

| 항목 | mecom_hmi (기존) | mecom_hmi_ver02 (신규) |
|------|-----------------|----------------------|
| 데이터 저장 | CSV + SQLite (이중) | **SQLite 단일** |
| 저장기간 | 무제한 | **3년 초과 자동삭제** |
| 읽기 비트 | 38개 | **39개 (bit 38=운전피드백 추가)** |
| 운전/정지 버튼 | 로컬 UI 상태 | **PLC 피드백 (bit 38) 기반** |

## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행

1. API 서버 시작
```powershell
python api_server.py
```

2. Modbus 수집 워커 시작 (별도 터미널)
```powershell
python modbus_worker.py
```

3. Streamlit 앱 실행 (별도 터미널)
```powershell
streamlit run app.py
```

## Docker 배포

```powershell
docker build -t mecom-hmi .
docker run -p 8501:8501 mecom-hmi
```

## 로그

- 워커 로그: `mecom_hmi.log`

## 기본 구조

- `config.py`: 공통 설정과 경로 정의
- `data_provider.py`: JSON/SQLite 읽기/쓰기 로직
- `modbus_worker.py`: PLC/Modbus 데이터 수집
- `api_server.py`: FastAPI 기반 REST API + 자동 리포트 + 데이터 클린업
- `app.py`: Streamlit UI
- `realtime_data.json`: 실시간 상태 데이터 저장
