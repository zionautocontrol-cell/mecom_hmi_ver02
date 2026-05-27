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

### 일반 설치 (권장, 현장 PC용)

`install.bat`을 **관리자 권한으로 실행**하면 Python, 라이브러리, COM 포트 설정, 바탕화면 바로가기가 자동으로 설치됩니다.
```powershell
install.bat
```
> 설치 중 COM 포트 번호를 입력하라는 메시지가 나타나면 현장 PLC 연결 포트를 입력하세요.  
> (예: `COM6` 또는 숫자만 `6` → 자동으로 `COM6` 변환)

### 수동 설치
```powershell
python -m pip install -r requirements.txt
```

## 실행

### start_hmi.bat 실행 (권장)
설치 후 바탕화면의 **"MECOM HMI ver02"** 바로가기 또는 `start_hmi.bat`을 실행하면  
Modbus 워커 → API 서버 → Streamlit UI가 순서대로 시작됩니다.
```powershell
start_hmi.bat
```

### 수동 실행 (터미널 3개 필요)
```powershell
# 터미널 1: Modbus 수집 워커
python modbus_worker.py

# 터미널 2: API 서버 (FastAPI)
python api_server.py

# 터미널 3: Streamlit UI
streamlit run app.py
```

접속: http://localhost:8501

## Docker 배포 (본사 서버 테스트용)

Docker는 현장 PC의 Python 환경과 독립적으로 실행할 수 있는 컨테이너 방식입니다.  
설치 없이 빠르게 테스트해볼 때 사용합니다.

```powershell
# 이미지 빌드
docker build -t mecom-hmi .

# 컨테이너 실행 (8501 포트)
docker run -p 8501:8501 mecom-hmi
```

> ⚠️ Docker 배포 시에는 PLC 직렬 포트(COM) 연결이 필요하므로 `--device` 옵션 등 추가 설정이 필요할 수 있습니다.  
> 현장 PC에서는 `install.bat` 방식 사용을 권장합니다.

## 로그

- 워커 로그: `mecom_hmi.log`

## 기본 구조

- `config.py`: 공통 설정과 경로 정의
- `data_provider.py`: JSON/SQLite 읽기/쓰기 로직
- `modbus_worker.py`: PLC/Modbus 데이터 수집
- `api_server.py`: FastAPI 기반 REST API + 자동 리포트 + 데이터 클린업
- `app.py`: Streamlit UI
- `realtime_data.json`: 실시간 상태 데이터 저장
