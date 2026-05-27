# MECOM HMI 변경 이력

## 2026-05-14 — v1.0 (master 최종 완성본)

### 문제 1: 감시화면 온도 위치가 PLC 신호와 맞지 않음

**증상:** Modbus 주소 0~7의 온도값이 감시화면의 표시 위치와 어긋나 있었음.
예를 들어 지중공급온도(1동)가 2차공급온도(1동) 자리에 표시되는 등 8개 온도값이 전반적으로 뒤섞임.

**원인:**
- 서버(`api_server.py`)에서 `{{W0}}`~`{{W7}}` 플레이스홀더를 단순히 `words[i]`로 치환했으나,
- `diagram.html`의 JavaScript(`pollData`, `applyData`)가 1초마다 API를 호출하여 `data-word` 속성 기준으로 값을 **덮어쓰고** 있었음.
- 즉, 서버 측 치환은 의미가 없었고, 실제 화면에 표시되는 값은 `data-word` 속성으로 결정됨.

**해결:**
- `diagram.html`의 `data-word` 속성값을 실제 PLC 신호 연결에 맞게 직접 수정.
- 불필요한 서버 측 `display_map` 로직은 제거.

**교훈:**
- JavaScript가 DOM을 직접 조작하는 경우 서버 측 템플릿 치환이 무력화될 수 있음.
- 디버깅 시 서버 응답(HTTP)과 브라우저 표시(DOM)를 분리해서 확인해야 함.

---

### 문제 2: 감시화면 주기적 멈춤 (프리징)

**증상:** 화면이 30초마다 멈췄다가 다시 돌아오는 현상 반복.
멈춰 있는 시간이 점점 길어지는 느낌.

**원인:**
- `app.py`의 `st_autorefresh(interval=30000)`가 30초마다 Streamlit 전체 페이지를 재실행.
- `components.html('<iframe src="http://localhost:8000/hmi"...')` 가 매 재실행 시 iframe을 새로 생성.
- iframe이 `src=`로 URL을 로드하면서 **HTTP 요청(200~500ms)** 동안 화면이 빈 상태로 멈춤.
- 게다가 기존 iframe이 제거되고 새 iframe이 생성되는 과정에서 브라우저가 깜빡임.

**시행착오:**
1. `st_autorefresh` 제거 → 화면 데이터 갱신 안 됨
2. `st.markdown`으로 변경 → 근본적 해결 안 됨
3. 별도 탭으로 분리 → 사용자 거부
4. **최종:** `@st.cache_data`로 HMI HTML을 **1시간 캐싱**하고 `components.html(html_content)`로 **인라인 삽입**
   → iframe 재생성 시 HTTP 요청 없이 즉시 표시되어 멈춤 현상 해결

**교훈:**
- iframe에 `src` 대신 인라인 콘텐츠를 사용하면 재생성 비용이 거의 없음.
- Streamlit의 `components.html(content)`는 iframe을 재생성하지만, 콘텐츠가 인라인이므로 깜빡임 최소화.

---

### 문제 3: 히트펌프 가동상태 깜빡임

**증상:** 1번 HP는 계속 돌지만 3번, 6번 HP가 멈췄다 돌았다를 반복.
나중에는 1번도 같이 깜빡이기 시작.

**원인:**
- `modbus_worker.py`가 비트 읽기에 실패하면 `read_coils`로 폴백(fallback)하는 로직이 있었음.
- 그런데 폴백 주소가 **완전히 다른 영역**을 가리키고 있었음:
  - `read_discrete_inputs(address=0)` → PLC 10001번지 (올바른 HP 상태)
  - `read_coils(address=500)` → PLC 00501번지 (엉뚱한 데이터!)
  - `read_coils(address=0)` → PLC 00001번지 (또 다른 데이터!)
- 통신이 불안정할 때 서로 다른 세 영역의 값이 번갈아 읽히면서 HP 상태가 깜빡임.

**해결:**
- Coil 폴백을 완전히 제거. `read_discrete_inputs`만 사용하고 실패 시 이전값 유지.

**교훈:**
- 폴백 로직은 "동일한 데이터를 다른 방식으로 읽는 경우"에만 유효.
- 서로 다른 주소 영역으로 폴백하면 데이터 일관성이 깨짐.
- Modbus 통신에서는 기능 코드(FC)별로 주소 체계가 완전히 다를 수 있음.

---

### 문제 4: 배포 시 이전 데이터가 남아 있음

**증상:** 새 PC에 설치했는데 개발 시 사용했던 온도값, 히스토리, 알람이 그대로 표시됨.

**해결:** `install.bat`에 데이터 초기화 단계 추가
- `realtime_data.json`, `history_data.csv`, `alarm_history.csv`,
  `control_command.json`, `mecom_data.db`, `mecom_hmi.log`, `password.json`
  → 설치 시 자동 삭제

---

### 문제 5: PLC 연결 테스트 실패

**증상 1:** `test_plc.py` 실행 시 "could not open port '14'" 에러
- **원인:** `config.py`에 `MODBUS_PORT = "14"`로 저장 (COM 누락)
- **해결:** `install.bat`에서 숫자만 입력해도 자동으로 `COM`을 앞에 붙이도록 수정

**증상 2:** `test_plc.py`에서 "포트 목록에 없음" 경고
- **원인:** `com14`(소문자)와 `COM14`(대문자) 비교 실패
- **해결:** 대소문자 구분 없이 비교하도록 수정

**증상 3:** `No module named 'serial'`
- **원인:** `requirements.txt`에 `pyserial` 누락
- **해결:** `pyserial` 추가

---

### 문제 6: 설치 시 COM 포트 변환 실패

**증상:** `install.bat`에서 COM 포트 입력 시 PowerShell 에러 발생 후 `"8"`로 저장됨

**원인:**
- `install.bat` 내 PowerShell 명령어에 `%{$_}` 구문이 포함되어 있었는데,
- batch 파일이 `%`를 변수 참조로 잘못 해석하여 PowerShell 구문이 깨짐.

**시행착오:**
1. PowerShell 복잡한 one-liner 시도 → batch의 `%` 해석 문제로 실패
2. **최종:** `echo %comport% | findstr /i "^COM"` → batch 내장 명령어로 간단히 해결

**교훈:**
- batch 파일 안에서 PowerShell을 호출할 때 `%` 문자는 반드시 `%%`로 이스케이프해야 함.
- 복잡한 PowerShell one-liner보다 batch 내장 명령어가 더 안정적.

---

### 의존성 추가 (requirements.txt)

| 추가된 패키지 | 이유 |
|---|---|
| `streamlit-autorefresh` | `app.py`에서 `st_autorefresh` import |
| `requests` | `app.py`에서 API 호출 |
| `fastapi` | `api_server.py`에서 사용 |
| `uvicorn` | `api_server.py` 실행 |
| `pyserial` | `test_plc.py` 포트 스캔 / ModbusSerialClient |
