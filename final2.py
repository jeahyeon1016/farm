import subprocess #변경된 파일입니다
import json
import requests
from datetime import datetime, timedelta
import pytz
import time
import re

# ✅ 설정
IPERF_SERVER = "15.164.194.31"
SERVER_URL = "http://15.164.194.31/upload"
SENSOR_MAC = "2c:cf:67:d0:5c:c2"
KST = pytz.timezone('Asia/Seoul')

# ✅ 인터넷 연결 상태 확인 함수
def is_connected():
    try:
        subprocess.check_call(["ping", "-c", "1", "-W", "2", "8.8.8.8"], stdout=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

# ✅ ping 측정 (1회)
def get_ping(host="8.8.8.8"):
    try:
        output = subprocess.check_output(["ping", "-c", "1", host], universal_newlines=True)
        for line in output.split("\n"):
            if "time=" in line:
                time_ms = float(line.split("time=")[1].split(" ")[0])
                return round(time_ms, 2)
    except Exception:
        return 0

# ✅ RSSI 측정
def get_rssi():
    try:
        output = subprocess.check_output(["iwconfig"], universal_newlines=True)
        for line in output.split("\n"):
            if "Signal level=" in line:
                match = re.search(r"Signal level=(-?\d+)", line)
                if match:
                    return int(match.group(1))
    except Exception:
        return 0

# ✅ iperf3 측정 (11초, 1초 단위 → 첫값 제외)
def get_bps_list():
    try:
        result = subprocess.run(
            ["iperf3", "-c", IPERF_SERVER, "-t", "11", "-i", "1"],
            capture_output=True,
            text=True,
            timeout=50
        )
        output = result.stdout
        print("📋 iperf3 원본 출력:\n", output)  # 디버깅 출력

        mbps_list = []
        for line in output.splitlines():
            if "Mbits/sec" in line and "sender" not in line and "receiver" not in line:
                match = re.search(r"([\d\.]+)\s+Mbits/sec", line)
                if match:
                    mbps_list.append(float(match.group(1)))

        print(f"📊 수집된 측정값: {len(mbps_list)}개 → {mbps_list}")  # 디버깅 출력

        if len(mbps_list) < 11:
            print("⚠️ 측정 줄 부족, iperf3 결과 파싱 실패 가능성")
            return []
        return mbps_list[1:]  # 첫 번째 값 제외

    except Exception as e:
        print("[iperf3 오류]", e)
        return []

# ✅ 종합 센서 측정 + 전송
def collect_and_send():
    retry_count = 3
    for attempt in range(retry_count):
        bps_list = get_bps_list()
        if len(bps_list) == 10:
            break
        print(f"❌ 측정 실패, 재시도 {attempt + 1}/{retry_count}")
        time.sleep(3)
    else:
        print("❌ 최종 측정 실패")
        return

    base_time = datetime.now(KST)
    data_payload = []

    for i, bps in enumerate(bps_list):
        timestamp = base_time + timedelta(seconds=i + 1)
        ping = get_ping()
        rssi = get_rssi()

        data = {
            "sensor_mac": SENSOR_MAC,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "rssi": rssi,
            "ping": ping,
            "speed": round(bps, 2),
            "ping_timeout": (ping == 0) or (ping >= 300.0)
        }
        data_payload.append(data)
        time.sleep(0.2)

    print("📡 전송 데이터:", json.dumps(data_payload, indent=2, ensure_ascii=False))

    try:
        response = requests.post(SERVER_URL, json=data_payload, timeout=40)
        print("✅ 서버 응답 코드:", response.status_code)
        try:
            print("✅ 응답 내용:", response.json())
        except json.JSONDecodeError:
            print("⚠️ JSON 파싱 실패. 텍스트 응답:\n", response.text)
    except Exception as e:
        print("❌ 전송 실패:", str(e))

# ✅ 실행 루프
if __name__ == "__main__":
    disconnected_logged = False

    while True:
        if not is_connected():
            if not disconnected_logged:
                print("🚫 인터넷 연결 끊김. 연결될 때까지 대기 중...")
                disconnected_logged = True
            time.sleep(5)
            continue
        else:
            if disconnected_logged:
                print("✅ 인터넷 다시 연결됨. 측정 재개")
                disconnected_logged = False

        start_time = time.time()
        print("\n📡 측정 시작:", datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"))

        collect_and_send()

        elapsed_time = time.time() - start_time
        sleep_time = max(0, 60 - elapsed_time)
        print(f"⏳ 다음 측정을 위해 {sleep_time:.2f}초 대기...\n")
        time.sleep(sleep_time)
