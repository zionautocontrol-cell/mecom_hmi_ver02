"""
Modbus RTU worker for collecting PLC data and saving to JSON and SQLite.
Requires: pip install pymodbus
Run: python modbus_worker.py
"""

import logging
import os
import time

from pymodbus.client import ModbusSerialClient

from config import (
    BIT_READ_COUNT,
    BIT_READ_START,
    COIL_ADDRESS,
    CONTROL_ENABLED,
    LOG_FILE,
    MODBUS_BAUDRATE,
    MODBUS_PORT,
    MODBUS_SLAVE_ID,
    POLL_INTERVAL,
    WORD_READ_START,
)
from data_provider import (
    append_alarm_history,
    evaluate_alarms,
    get_default_realtime_data,
    load_control_command,
    save_control_command,
    save_realtime_data,
    save_history_to_db,  # 새로 만든 DB 저장 함수 추가
    init_db             # DB 초기화 함수 추가
)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("mecom_hmi")


def format_timestamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def create_modbus_client() -> ModbusSerialClient:
    return ModbusSerialClient(
        port=MODBUS_PORT,
        baudrate=MODBUS_BAUDRATE,
        timeout=1,
        parity='N',
        stopbits=1,
        bytesize=8,
    )


def _modbus_read_call(client: ModbusSerialClient, method_name: str, address: int, count: int):
    """Modbus 읽기 메서드에 대해 slave 파라미터로 시도합니다."""
    method = getattr(client, method_name)
    try:
        return method(address=address, count=count, slave=MODBUS_SLAVE_ID)
    except TypeError:
        try:
            return method(address=address, count=count)
        except Exception as exc:
            logger.warning(f"Modbus {method_name} failed without slave param: {exc}")
            return None
    except Exception as exc:
        logger.warning(f"Modbus {method_name} failed with slave param: {exc}")
        return None


def process_control_request(client: ModbusSerialClient, control: dict) -> dict:
    command = control.get("command", "none")
    status = control.get("status", "idle")

    if status != "requested" or command not in {"start", "stop"}:
        return control

    if not CONTROL_ENABLED:
        control["status"] = "disabled"
        control["message"] = "Control write disabled in config.py."
        return control

    if not client.connected:
        control["message"] = "Waiting for PLC connection to execute command."
        return control

    try:
        coil_value = command == "start"
        # LS PLC Modbus 서버는 블록 내 상대 주소 사용: 1번 코일 = P0 (블록 시작)
        target_address = max(0, COIL_ADDRESS - 1)

        try:
            response = client.write_coil(target_address, coil_value, slave=MODBUS_SLAVE_ID)
        except TypeError:
            response = client.write_coil(target_address, coil_value)

        if response is None:
            success = False
        elif hasattr(response, "isError"):
            try:
                success = not response.isError()
            except Exception:
                success = False
        else:
            success = bool(response)

        if success:
            control["status"] = "executed"
            bit_value = 1 if coil_value else 0
            status_msg = "시스템 운전중" if coil_value else "시스템 정지중"
            control["message"] = f"{status_msg} - Coil {COIL_ADDRESS} set to {bit_value}"
            control["executed_at"] = format_timestamp()
            control["command"] = "none"
            logger.info(f"Control command '{command}' executed: {status_msg} (Coil {COIL_ADDRESS} = {bit_value})")
        else:
            control["status"] = "failed"
            control["message"] = "Modbus write failed or returned error."
            logger.warning(f"Write coil returned non-success response: {response}")
    except Exception as exc:
        logger.exception(f"Exception during control command write: {exc}")
        control["status"] = "failed"
        control["message"] = f"Control write exception: {exc}"
    except Exception as exc:
        logger.exception(f"Exception during control command write: {exc}")
        control["status"] = "failed"
        control["message"] = f"Control write exception: {exc}"

    return control


def main() -> None:
    logger.info(f"Starting Modbus worker on port {MODBUS_PORT} with slave ID {MODBUS_SLAVE_ID}. PID={os.getpid()}")

    init_db()  # DB 초기화

    client = create_modbus_client()
    current_data = get_default_realtime_data()
    last_valid_data = current_data.copy()
    last_logged_minute = ""
    last_alarm_log_minute = ""

    try:
        while True:
            # 1️⃣ 먼저 명령 처리 (우선순위 높음)
            if client.connected:
                control = load_control_command()
                if control.get("status") == "requested":
                    updated_control = process_control_request(client, control)
                    save_control_command(
                        command=updated_control.get("command"),
                        status=updated_control.get("status"),
                        message=updated_control.get("message"),
                        requested_at=updated_control.get("requested_at"),
                        executed_at=updated_control.get("executed_at"),
                    )
                    logger.info(f"Control processed: {updated_control}")
            
            # 2️⃣ 연결 확인
            if not client.connected:
                try:
                    client.connect()
                    logger.info(f"Modbus connected: {client.connected}")
                except Exception as exc:
                    logger.warning(f"Modbus connect failed: {exc}")

            read_success = False

            # 3️⃣ 데이터 읽기
            if client.connected:
                try:
                    # ─── 비트 읽기 (Discrete Input만 사용, 폴백 없음) ──────────────
                    # coil 폴백 시 다른 주소의 데이터를 읽어와 HP 상태가 깜빡이는 현상 방지
                    bit_resp = _modbus_read_call(client, "read_discrete_inputs", address=0, count=BIT_READ_COUNT)

                    # ─── 워드 읽기 (Holding Register → Input Register 순으로 폴백) ─────
                    # 모드버스맵 기준: 40001~40013 = Holding Registers (Modbus FC 03)
                    # offset = 40001 - 40001 = 0
                    word_resp = _modbus_read_call(client, "read_holding_registers", address=WORD_READ_START, count=13)
                    if word_resp is None or (hasattr(word_resp, "isError") and word_resp.isError()):
                        logger.warning("Holding register read failed, trying input register fallback.")
                        word_resp = _modbus_read_call(client, "read_input_registers", address=WORD_READ_START, count=13)
                    if word_resp is None or (hasattr(word_resp, "isError") and word_resp.isError()):
                        logger.warning("Input register read also failed, trying count=11 fallback.")
                        word_resp = _modbus_read_call(client, "read_holding_registers", address=WORD_READ_START, count=11)

                    # ─── 비트 처리 (워드와 독립적으로 적용) ──────────────────────────────
                    bits_ok = False
                    if bit_resp is not None and not (hasattr(bit_resp, "isError") and bit_resp.isError()):
                        raw_bits = getattr(bit_resp, "bits", None)
                        if raw_bits is not None and len(raw_bits) >= BIT_READ_COUNT:
                            new_bits = list(raw_bits[:BIT_READ_COUNT])
                            current_data["bits"] = new_bits
                            bits_ok = True
                            bits_str = "".join(str(int(b)) for b in new_bits[:16])
                            logger.info(f"Bits[0:16]={bits_str}")
                        else:
                            logger.warning(f"Coil/Discrete response has insufficient bits: {raw_bits}")
                    else:
                        logger.warning("Bit read failed or returned error response.")

                    # ─── 워드 처리 (비트와 독립적으로 적용) ──────────────────────────────
                    words_ok = False
                    if word_resp is not None and not (hasattr(word_resp, "isError") and word_resp.isError()):
                        registers = getattr(word_resp, "registers", None)
                        if registers is not None and len(registers) >= 11:
                            words = [r / 10.0 for r in registers[:11]]
                            current_data["words"] = words
                            words_ok = True
                            # 누적 열량: 레지스터가 13개 이상일 때만 32비트 결합
                            if len(registers) >= 13:
                                current_data["accum_heat"] = (registers[12] << 16) | registers[11]
                            logger.info(f"Words[0:3]={words[:3]}")
                        else:
                            logger.warning(f"Register response has insufficient data: {registers}")
                    else:
                        logger.warning("Word read failed or returned error response.")

                    # ─── 전체 상태 갱신 ───────────────────────────────────────────────────
                    if bits_ok or words_ok:
                        current_data["status"] = "connected"
                        current_data["timestamp"] = format_timestamp()
                        last_valid_data = current_data.copy()
                        read_success = True
                        if not bits_ok:
                            logger.warning("Connected but bit read failed — using last known bit values.")
                        if not words_ok:
                            logger.warning("Connected but word read failed — using last known word values.")
                    else:
                        logger.warning("Both bit and word reads failed.")
                except Exception as exc:
                    logger.exception(f"Exception during Modbus read: {exc}")

            if not read_success:
                logger.warning("Real PLC read failed. Setting disconnected state.")
                if current_data["status"] != "disconnected":
                    logger.warning("Communication lost. Keeping last values.")
                current_data["status"] = "disconnected"
                current_data["timestamp"] = format_timestamp()
                current_data["bits"] = last_valid_data.get("bits", current_data["bits"])
                current_data["words"] = last_valid_data.get("words", current_data["words"])
                current_data["accum_heat"] = last_valid_data.get("accum_heat", current_data["accum_heat"])

            if not save_realtime_data(current_data):
                logger.error("Failed to save realtime JSON data.")

            if read_success:
                current_minute = time.strftime('%y/%m/%d %H:%M')
                if current_minute != last_logged_minute:
                    save_history_to_db(
                        current_data["words"][:11],
                        current_data.get("accum_heat", 0.0),
                        current_minute,
                    )
                    last_logged_minute = current_minute
                    logger.info(f"Appended history to DB for {current_minute}.")

            alarms = evaluate_alarms(current_data)
            if alarms:
                current_alarm_minute = time.strftime('%y/%m/%d %H:%M')
                if current_alarm_minute != last_alarm_log_minute:
                    if append_alarm_history(alarms):
                        last_alarm_log_minute = current_alarm_minute
                        logger.info(f"Appended alarm history for {current_alarm_minute}.")
                    else:
                        logger.error("Failed to append alarm history.")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Stopping Modbus worker.")
    finally:
        if client.connected:
            client.close()
            logger.info("Modbus client closed.")

if __name__ == '__main__':
    main()
