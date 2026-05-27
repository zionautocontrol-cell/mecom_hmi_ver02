"""
PLC Modbus 연결 테스트 스크립트
사용법: python test_plc.py
"""
import sys
import time
from config import MODBUS_PORT, MODBUS_BAUDRATE, MODBUS_SLAVE_ID

print("=" * 50)
print("MECOM PLC 연결 테스트")
print("=" * 50)
print(f"  PORT:     {MODBUS_PORT}")
print(f"  BAUDRATE: {MODBUS_BAUDRATE}")
print(f"  SLAVE ID: {MODBUS_SLAVE_ID}")
print("=" * 50)

# Step 1: 포트 존재 확인
try:
    import serial.tools.list_ports
    ports = [p.device for p in serial.tools.list_ports.comports()]
    print(f"\n[1/4] 사용 가능한 COM 포트: {ports}")
    if any(p.upper() == MODBUS_PORT.upper() for p in ports):
        print(f"  ✅ {MODBUS_PORT} 발견")
    else:
        print(f"  ⚠️  {MODBUS_PORT} 목록에 없음! 사용 가능: {ports}")
except Exception as e:
    print(f"  ⚠️  포트 스캔 실패: {e}")

# Step 2: pymodbus 연결 시도
print(f"\n[2/4] Modbus 연결 시도 중... ({MODBUS_PORT})")
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient(
    port=MODBUS_PORT,
    baudrate=MODBUS_BAUDRATE,
    timeout=2,
    parity='N',
    stopbits=1,
    bytesize=8,
)

try:
    connected = client.connect()
    if connected:
        print(f"  ✅ 연결 성공! (client.connected = {client.connected})")
    else:
        print(f"  ❌ 연결 실패 (client.connected = {client.connected})")
        print(f"     → 케이블 연결 확인, config.py의 PORT={MODBUS_PORT} 확인")
        client.close()
        sys.exit(1)
except Exception as e:
    print(f"  ❌ 연결 예외: {e}")
    print(f"     → COM 포트 충돌 또는 케이블 문제")
    client.close()
    sys.exit(1)

# Step 3: 데이터 읽기 테스트
print(f"\n[3/4] 데이터 읽기 시도...")
try:
    # Discrete Inputs (비트)
    print("  - Discrete Inputs(FC02) address=0, count=38 읽는 중...")
    bit_resp = client.read_discrete_inputs(address=0, count=38, slave=MODBUS_SLAVE_ID)
    if bit_resp and not hasattr(bit_resp, 'isError'):
        bits = getattr(bit_resp, "bits", [])
        print(f"    ✅ 비트 읽기 성공: {len(bits)}개")
        print(f"       앞 16비트: {''.join(str(int(b)) for b in bits[:16])}")
    else:
        print(f"    ⚠️  Discrete Inputs 실패, Coils(FC01)로 재시도...")
        bit_resp = client.read_coils(address=0, count=38, slave=MODBUS_SLAVE_ID)
        if bit_resp and not hasattr(bit_resp, 'isError'):
            bits = getattr(bit_resp, "bits", [])
            print(f"    ✅ Coil 읽기 성공: {len(bits)}개")
        else:
            print(f"    ❌ 비트 읽기 실패 (PLC 미지원 기능일 수 있음)")

    # Holding Registers (워드)
    print("  - Holding Registers(FC03) address=0, count=13 읽는 중...")
    word_resp = client.read_holding_registers(address=0, count=13, slave=MODBUS_SLAVE_ID)
    if word_resp and not hasattr(word_resp, 'isError'):
        regs = getattr(word_resp, "registers", [])
        print(f"    ✅ 워드 읽기 성공: {len(regs)}개")
        if len(regs) >= 11:
            words = [r / 10.0 for r in regs[:11]]
            print(f"       값(Temp): {words[:4]}")
    else:
        print(f"    ⚠️  Holding Registers 실패, Input Registers(FC04)로 재시도...")
        word_resp = client.read_input_registers(address=0, count=13, slave=MODBUS_SLAVE_ID)
        if word_resp and not hasattr(word_resp, 'isError'):
            regs = getattr(word_resp, "registers", [])
            print(f"    ✅ Input Register 읽기 성공: {len(regs)}개")
        else:
            print(f"    ❌ 워드 읽기 실패")

except Exception as e:
    print(f"  ❌ 읽기 예외: {e}")

# Step 4: 연결 종료
print(f"\n[4/4] 연결 종료")
client.close()
print("  ✅ 종료 완료")
print("=" * 50)
