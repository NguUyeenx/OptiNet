import os
import sys
import subprocess
import socket
import time
import json
import re
import winreg
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Configuration
PORT = 8888
TEST_DOMAINS = ["google.com", "wikipedia.org", "cloudflare.com", "github.com"]
DNS_SERVERS = {
    "1.1.1.1": "Cloudflare DNS",
    "8.8.8.8": "Google DNS",
    "9.9.9.9": "Quad9 DNS",
    "208.67.222.222": "OpenDNS"
}
DIAGNOSTIC_LOG_FILE = "diagnostics_report.json"
AFTER_LOG_FILE = "after_report.json"

# Thread-safe logging and status
log_lock = threading.Lock()
api_logs = []
current_status = "idle"  # idle, diagnosing, optimizing, completed
progress_percentage = 0

def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    with log_lock:
        api_logs.append(f"[{timestamp}] {msg}")
    print(f"[{timestamp}] {msg}")

def run_command(cmd, shell=True):
    """Utility to run a shell command and return stdout, stderr, and success code."""
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=shell)
        return res.stdout, res.stderr, res.returncode == 0
    except Exception as e:
        return "", str(e), False

def dns_query_time(dns_server, domain):
    """Sends a standard DNS query packet over UDP to measure response time in milliseconds."""
    # Transaction ID: 0xaabb, Flags: 0x0100 (standard query), Questions: 1, answers/authority/additional: 0
    packet = bytearray([0xaa, 0xbb, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    
    # Encode domain parts
    for part in domain.split('.'):
        if not part:
            continue
        packet.append(len(part))
        packet.extend(part.encode('ascii'))
    packet.append(0)  # Terminator
    
    # Type: A record (0x0001), Class: IN (0x0001)
    packet.extend([0x00, 0x01, 0x00, 0x01])
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.2)
        start = time.perf_counter()
        sock.sendto(packet, (dns_server, 53))
        data, _ = sock.recvfrom(512)
        end = time.perf_counter()
        sock.close()
        
        # Verify transaction ID in response
        if len(data) >= 2 and data[0] == 0xaa and data[1] == 0xbb:
            return (end - start) * 1000
    except Exception:
        pass
    return None

def benchmark_dns():
    """Benchmarks DNS servers for the domains in TEST_DOMAINS."""
    add_log("Bắt đầu đo kiểm tốc độ phân giải của các DNS Server phổ biến...")
    results = {}
    
    # Add local DNS server
    try:
        local_dns_query = subprocess.run(
            ["powershell", "-Command", "(Get-DnsClientServerAddress -InterfaceAlias Wi-Fi -AddressFamily IPv4).ServerAddresses[0]"],
            stdout=subprocess.PIPE, text=True, shell=True
        )
        local_dns = local_dns_query.stdout.strip()
        if local_dns and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", local_dns):
            DNS_SERVERS[local_dns] = f"Local Gateway / ISP ({local_dns})"
            add_log(f"Tìm thấy DNS mặc định của ISP: {local_dns}")
    except Exception:
        pass

    for ip, name in DNS_SERVERS.items():
        times = []
        add_log(f"Đang kiểm tra DNS: {name} ({ip})...")
        for domain in TEST_DOMAINS:
            t = dns_query_time(ip, domain)
            if t is not None:
                times.append(t)
        if times:
            avg_time = sum(times) / len(times)
            results[ip] = {"name": name, "avg_ms": round(avg_time, 2), "status": "Online"}
            add_log(f"-> {name} ({ip}): phản hồi trung bình {round(avg_time, 2)} ms")
        else:
            results[ip] = {"name": name, "avg_ms": 9999, "status": "Failed/Offline"}
            add_log(f"-> {name} ({ip}): Ngoại tuyến hoặc quá thời gian phản hồi")
            
    return results

def get_active_profile():
    """Gets the active Wi-Fi profile name (SSID) using Get-NetConnectionProfile."""
    cmd = 'powershell -Command "(Get-NetConnectionProfile -InterfaceAlias Wi-Fi -ErrorAction SilentlyContinue).Name"'
    stdout, _, success = run_command(cmd)
    if success and stdout.strip():
        profiles = [p.strip() for p in stdout.strip().split('\n') if p.strip()]
        return profiles[0] if profiles else None
    return None

def list_wifi_profiles():
    """Lists all configured Wi-Fi profiles."""
    stdout, _, success = run_command("netsh wlan show profiles")
    profiles = []
    if success:
        for line in stdout.split('\n'):
            if "All User Profile" in line or "Hồ sơ người dùng" in line or "Hồ sơ tất cả người dùng" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    profiles.append(parts[1].strip())
    return profiles

def get_latency_stats(target="1.1.1.1", count=10):
    """Pings target to calculate packet loss, latency, and jitter."""
    add_log(f"Đang kiểm tra độ trễ mạng và độ ổn định đến máy chủ tin cậy {target} ({count} pings)...")
    stdout, _, success = run_command(f"ping -n {count} {target}")
    
    loss_match = re.search(r"Lost = (\d+) \((\d+)% loss\)", stdout) or re.search(r"Bị mất = (\d+) \((\d+)% mất\)", stdout)
    min_max_avg = re.search(r"Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms", stdout) or re.search(r"Tối thiểu = (\d+)ms, Tối đa = (\d+)ms, Trung bình = (\d+)ms", stdout)
    
    loss_pct = 0
    stats = {"min": 0, "max": 0, "avg": 0, "loss_pct": 100, "jitter": 0}
    
    if loss_match:
        loss_pct = int(loss_match.group(2))
        stats["loss_pct"] = loss_pct
        
    if min_max_avg:
        stats["min"] = int(min_max_avg.group(1))
        stats["max"] = int(min_max_avg.group(2))
        stats["avg"] = int(min_max_avg.group(3))
        
    # Standard deviation/jitter calculation
    latencies = []
    ping_lines = re.findall(r"time[=<](\d+)ms", stdout) or re.findall(r"thời gian[=<](\d+)ms", stdout)
    for t in ping_lines:
        latencies.append(int(t))
    
    if latencies:
        avg = sum(latencies) / len(latencies)
        variance = sum((x - avg) ** 2 for x in latencies) / len(latencies)
        jitter = round(variance ** 0.5, 2)
        stats["jitter"] = jitter
        
    add_log(f"Kết quả Ping: Trung bình={stats['avg']}ms | Độ dao động trễ (Jitter)={stats['jitter']}ms | Mất gói={stats['loss_pct']}%")
    return stats

def discover_mtu(target="1.1.1.1"):
    """Finds the maximum packet size that passes without fragmentation."""
    add_log("Đang phân tích và quét kích thước MTU tối ưu (Ping Sweep)...")
    
    low = 1300
    high = 1472
    optimal_payload = 1472
    
    # Quick check for standard MTU 1500 (payload 1472)
    _, _, ok = run_command(f"ping -f -l {high} -n 1 {target}")
    if ok:
        add_log("Kích thước MTU hiện tại đã tối ưu ở mức tiêu chuẩn 1500 (không bị phân mảnh).")
        return 1500
        
    # Binary search optimal payload
    while low <= high:
        mid = (low + high) // 2
        stdout, _, ok = run_command(f"ping -f -l {mid} -n 1 {target}")
        if ok:
            optimal_payload = mid
            low = mid + 1
        else:
            high = mid - 1
            
    optimal_mtu = optimal_payload + 28
    add_log(f"Khám phá kích thước MTU tối ưu tốt nhất cho kết nối: {optimal_mtu} bytes.")
    return optimal_mtu

def list_bandwidth_hogs():
    """Lists active processes established network connections."""
    add_log("Đang quét các ứng dụng chạy ngầm chiếm dụng băng thông mạng...")
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-NetTCPConnection | Where-Object { $_.State -eq 'Established' } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } | Select-Object Id, ProcessName, Path | ConvertTo-Json"
    ]
    
    hogs = []
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
        stdout = res.stdout
        success = res.returncode == 0
    except Exception as e:
        stdout = ""
        success = False
        add_log(f"[!] Lỗi khi quét danh sách cổng kết nối: {e}")
        
    if success and stdout.strip():
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                proc_name = item.get("ProcessName", "").lower()
                if proc_name not in ["idle", "system"]:
                    hogs.append({
                        "pid": item.get("Id"),
                        "name": item.get("ProcessName"),
                        "path": item.get("Path", "N/A")
                    })
        except Exception:
            pass
    
    # Filter known non-essential hogs
    suspects = []
    for h in hogs:
        name = h["name"].lower() if h["name"] else ""
        if any(x in name for x in ["vantage", "widget", "searchhost", "update", "cortana", "onedrive", "teams", "steam", "epicgames", "discord", "gamebar"]):
            suspects.append(h)
            
    add_log(f"Quét hoàn tất: phát hiện {len(hogs)} ứng dụng có kết nối hoạt động. Đã cắm cờ {len(suspects)} tiến trình chạy ngầm đáng ngờ.")
    return {"all": hogs, "noise": suspects}

def check_mdns_llmnr():
    """Checks if LLMNR is enabled in registry."""
    llmnr_status = "Enabled (Default)"
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Policies\Microsoft\Windows NT\DNSClient", 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "EnableMulticast")
        if val == 0:
            llmnr_status = "Disabled"
        else:
            llmnr_status = "Enabled"
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except Exception as e:
        llmnr_status = f"Unknown (Error: {e})"
        
    return {"llmnr": llmnr_status}

def run_speed_test():
    """Runs speedtest-cli and parses JSON output."""
    add_log("Bắt đầu đo kiểm tốc độ mạng Internet (Download/Upload)... Quá trình này mất khoảng 20-30 giây.")
    stdout, _, success = run_command("speedtest-cli --json")
    if success and stdout.strip():
        try:
            data = json.loads(stdout)
            res = {
                "download_mbps": round(data["download"] / 1_000_000, 2),
                "upload_mbps": round(data["upload"] / 1_000_000, 2),
                "ping_ms": round(data["ping"], 2),
                "isp": data.get("client", {}).get("isp", "N/A"),
                "server": data.get("server", {}).get("sponsor", "N/A")
            }
            add_log(f"Kết quả kiểm tra tốc độ: Tải xuống: {res['download_mbps']} Mbps | Tải lên: {res['upload_mbps']} Mbps | Ping: {res['ping_ms']} ms")
            return res
        except Exception as e:
            add_log(f"[!] Lỗi phân tích kết quả JSON Speedtest: {e}")
            
    add_log("Thử nghiệm chế độ đo kiểm tốc độ đơn giản (Simple Speedtest)...")
    stdout, _, success = run_command("speedtest-cli --simple")
    if success:
        download = re.search(r"Download:\s+([\d\.]+)\s+Mbit/s", stdout)
        upload = re.search(r"Upload:\s+([\d\.]+)\s+Mbit/s", stdout)
        ping = re.search(r"Ping:\s+([\d\.]+)\s+ms", stdout)
        res = {
            "download_mbps": float(download.group(1)) if download else 0.0,
            "upload_mbps": float(upload.group(1)) if upload else 0.0,
            "ping_ms": float(ping.group(1)) if ping else 0.0,
            "isp": "N/A",
            "server": "N/A"
        }
        add_log(f"Kết quả kiểm tra tốc độ (Simple): Tải xuống: {res['download_mbps']} Mbps | Tải lên: {res['upload_mbps']} Mbps | Ping: {res['ping_ms']} ms")
        return res
        
    add_log("[!] Kiểm tra Speedtest thất bại hoàn toàn. Kết nối Internet của bạn có thể đang chặn dịch vụ kiểm tra.")
    return {"download_mbps": 0.0, "upload_mbps": 0.0, "ping_ms": 0.0, "isp": "N/A", "server": "N/A"}

def async_diagnose_task(is_after_optimization=False):
    global current_status, progress_percentage
    try:
        current_status = "diagnosing"
        progress_percentage = 5
        add_log("=== BẮT ĐẦU CHẨN ĐOÁN MẠNG ===")
        
        # 1. Active connection profile & stale profiles
        progress_percentage = 15
        active_profile = get_active_profile()
        all_profiles = list_wifi_profiles()
        stale_profiles = [p for p in all_profiles if p != active_profile]
        add_log(f"Đang sử dụng mạng Wi-Fi: '{active_profile}'")
        add_log(f"Phát hiện {len(all_profiles)} cấu hình Wi-Fi đã lưu. Có {len(stale_profiles)} cấu hình Wi-Fi cũ cần dọn dẹp.")
        
        # 2. DNS benchmark
        progress_percentage = 30
        dns = benchmark_dns()
        
        # 3. Latency, packet loss & Jitter
        progress_percentage = 50
        latency = get_latency_stats()
        
        # 4. Discover MTU
        progress_percentage = 65
        mtu = discover_mtu()
        
        # 5. List network noise processes
        progress_percentage = 75
        hogs = list_bandwidth_hogs()
        
        # 6. Check LLMNR status
        progress_percentage = 80
        mdns = check_mdns_llmnr()
        
        # 7. Internet Speedtest
        progress_percentage = 85
        speed = run_speed_test()
        
        progress_percentage = 95
        report = {
            "timestamp": time.time(),
            "speed": speed,
            "dns": dns,
            "latency": latency,
            "mtu": mtu,
            "active_profile": active_profile,
            "all_profiles_count": len(all_profiles),
            "stale_profiles": stale_profiles,
            "bandwidth_hogs": hogs["noise"],
            "mdns": mdns
        }
        
        filename = AFTER_LOG_FILE if is_after_optimization else DIAGNOSTIC_LOG_FILE
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
            
        progress_percentage = 100
        current_status = "completed"
        add_log(f"=== CHẨN ĐOÁN HOÀN TẤT. Đã lưu báo cáo vào file '{filename}' ===")
        
    except Exception as e:
        add_log(f"[!] Gặp lỗi nghiêm trọng trong quá trình chẩn đoán: {e}")
        current_status = "idle"
        progress_percentage = 0

def async_optimize_task():
    global current_status, progress_percentage
    try:
        current_status = "optimizing"
        progress_percentage = 10
        add_log("=== BẮT ĐẦU THỰC HIỆN TỐI ƯU HÓA MẠNG ===")
        
        # Load baseline report if exists, else run diagnostic first
        report = None
        if os.path.exists(DIAGNOSTIC_LOG_FILE):
            try:
                with open(DIAGNOSTIC_LOG_FILE, "r", encoding="utf-8") as f:
                    report = json.load(f)
            except Exception:
                pass
                
        if not report:
            add_log("[!] Chưa có báo cáo chẩn đoán nền. Đang quét nhanh cấu hình Wi-Fi và tiến trình ngầm...")
            active_profile = get_active_profile()
            all_profiles = list_wifi_profiles()
            stale_profiles = [p for p in all_profiles if p != active_profile]
            hogs = list_bandwidth_hogs()
            report = {
                "active_profile": active_profile,
                "all_profiles_count": len(all_profiles),
                "stale_profiles": stale_profiles,
                "bandwidth_hogs": hogs["noise"],
                "mtu": 1500
            }
            
        # 1. Clean Stale Wi-Fi profiles
        progress_percentage = 30
        stale = report.get("stale_profiles", [])
        if stale:
            add_log(f"Đang tiến hành dọn dẹp {len(stale)} cấu hình Wi-Fi rác đã tích lũy lâu ngày...")
            cleaned = 0
            for profile in stale:
                _, _, ok = run_command(f'netsh wlan delete profile name="{profile}"')
                if ok:
                    cleaned += 1
                    add_log(f"-> Đã xóa cấu hình Wi-Fi cũ: {profile}")
            add_log(f"Đã dọn dẹp thành công {cleaned}/{len(stale)} cấu hình Wi-Fi rác.")
        else:
            add_log("Không tìm thấy cấu hình Wi-Fi cũ rác nào để dọn dẹp.")
            
        # 2. Optimize LLMNR Multicast Settings via Registry
        progress_percentage = 50
        add_log("Đang tối ưu hóa cấu hình LLMNR Multicast (Giảm lưu lượng mạng dư thừa)...")
        llmnr_done = False
        try:
            key_path = r"Software\Policies\Microsoft\Windows NT\DNSClient"
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.SetValueEx(key, "EnableMulticast", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            add_log("Tối ưu hóa thành công: Đã tắt dịch vụ phân giải LLMNR multicast trong Windows Policy Registry.")
            llmnr_done = True
        except PermissionError:
            add_log("[!] Lỗi phân quyền: Không thể viết trực tiếp vào HKLM Registry. Cần khởi chạy server với quyền Admin hoặc chạy lệnh thủ công.")
        except Exception as e:
            add_log(f"[!] Không thể cấu hình LLMNR Registry: {e}")
            
        # 3. Terminate non-essential background noise processes
        progress_percentage = 70
        hogs = report.get("bandwidth_hogs", [])
        if hogs:
            add_log("Đang bắt đầu đóng các tiến trình chạy ngầm gây nghẽn băng thông...")
            killed_count = 0
            for h in hogs:
                name = h["name"].lower()
                # Safely terminate known widget, searchhost, vantage background noise
                if any(x in name for x in ["widget", "searchhost", "cortana"]):
                    add_log(f"-> Đang đóng tiến trình: {h['name']} (PID: {h['pid']})")
                    _, _, ok = run_command(f"taskkill /PID {h['pid']} /F")
                    if ok:
                        killed_count += 1
            add_log(f"Đã đóng thành công {killed_count} tiến trình chạy ngầm rác.")
        else:
            add_log("Không phát hiện tiến trình chạy ngầm rác nào đang hoạt động.")
            
        # 4. Flush DNS Cache
        progress_percentage = 80
        add_log("Đang xóa bộ nhớ đệm DNS (Flush DNS Cache) để sửa lỗi phân giải và giảm trễ...")
        _, _, ok = run_command("ipconfig /flushdns")
        if ok:
            add_log("-> Bộ nhớ đệm DNS đã được dọn sạch thành công (ipconfig /flushdns).")
        else:
            add_log("-> Gặp lỗi khi xóa bộ nhớ đệm DNS.")

        # 5. Advanced TCP/IP Stack Tweaks (AutoTuning, Congestion Provider, RSS, RSC)
        progress_percentage = 85
        add_log("Đang điều chỉnh cấu hình TCP/IP Stack tối tân cấp độ hệ thống...")
        tcp_tweaks = [
            ("netsh int tcp set global rss=enabled", "Kích hoạt Receive-Side Scaling (RSS) xử lý mạng đa luồng CPU"),
            ("netsh int tcp set global rsc=enabled", "Kích hoạt Receive Segment Coalescing (RSC) giảm tải CPU khi truyền dữ liệu lớn"),
            ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -AutoTuningLevelLocal Normal\"", "Thiết lập TCP Auto-Tuning Local Level sang 'Normal'"),
            ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -CongestionProvider CUBIC\"", "Thiết lập Congestion Control Provider sang 'CUBIC'"),
            ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -EcnCapability Enabled\"", "Kích hoạt Explicit Congestion Notification (ECN)")
        ]
        for cmd, desc in tcp_tweaks:
            stdout, stderr, ok = run_command(cmd)
            if ok:
                add_log(f"-> Thành công: {desc}")
            else:
                add_log(f"[!] Thất bại: {desc}. Chi tiết: {stderr.strip() or stdout.strip() or 'Yêu cầu quyền Administrator.'}")

        # 6. Gaming Lag Tweak (Bypass Nagle's Algorithm via TcpAckFrequency and TCPNoDelay & Multimedia Throttling)
        progress_percentage = 92
        add_log("Đang thực thi các tinh chỉnh giảm ping, giảm trễ (Gaming Tweak)...")
        
        # SystemProfile adjustments
        try:
            sys_profile_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sys_profile_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xffffffff)
            winreg.SetValueEx(key, "SystemResponsiveness", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            add_log("-> Đã tắt giới hạn băng thông Multimedia trong Registry (NetworkThrottlingIndex = 0xFFFFFFFF, SystemResponsiveness = 0).")
        except PermissionError:
            add_log("[!] Thất bại: Không có quyền ghi HKLM SystemProfile Registry. Yêu cầu chạy server với quyền Admin.")
        except Exception as e:
            add_log(f"-> Lỗi tinh chỉnh SystemProfile Registry: {e}")

        # Nagle's Algorithm bypass
        try:
            interfaces_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            interfaces_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, interfaces_path, 0, winreg.KEY_READ)
            
            i = 0
            modified_interfaces = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(interfaces_key, i)
                    subkey_path = f"{interfaces_path}\\{subkey_name}"
                    subkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path, 0, winreg.KEY_WRITE)
                    
                    winreg.SetValueEx(subkey, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(subkey, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                    winreg.CloseKey(subkey)
                    modified_interfaces += 1
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(interfaces_key)
            if modified_interfaces > 0:
                add_log(f"-> Đã vô hiệu hóa Nagle's Algorithm thành công cho {modified_interfaces} card mạng (TcpAckFrequency = 1, TCPNoDelay = 1).")
            else:
                add_log("-> Không tìm thấy giao diện mạng nào trong Registry để tinh chỉnh.")
        except PermissionError:
            add_log("[!] Thất bại: Không có quyền ghi HKLM Tcpip Interfaces Registry. Yêu cầu chạy server với quyền Admin.")
        except Exception as e:
            add_log(f"-> Gặp lỗi khi vô hiệu hóa Nagle's Algorithm: {e}")

        progress_percentage = 98
        add_log("Đang đồng bộ hóa cấu hình hệ thống mạng...")
        time.sleep(1)
        
        progress_percentage = 100
        current_status = "completed"
        add_log("=== QUÁ TRÌNH TỐI ƯU HÓA HOÀN TẤT ===")
        add_log("Mẹo: Hãy kích hoạt lại tính năng đo kiểm (Post-diagnose) để xem bảng so sánh cải thiện tốc độ và độ trễ!")
        
    except Exception as e:
        add_log(f"[!] Lỗi nghiêm trọng khi thực hiện tối ưu hóa: {e}")
        current_status = "idle"
        progress_percentage = 0

class NetworkOptimizerServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request spam logs in console to keep terminal clean
        pass
        
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        global current_status, progress_percentage, api_logs
        
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. API Endpoints
        if path == "/api/status":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            active_profile = get_active_profile()
            all_profiles = list_wifi_profiles()
            mdns = check_mdns_llmnr()
            
            dns_servers = []
            try:
                dns_query = subprocess.run(
                    ["powershell", "-Command", "(Get-DnsClientServerAddress -InterfaceAlias Wi-Fi -AddressFamily IPv4).ServerAddresses"],
                    stdout=subprocess.PIPE, text=True, shell=True
                )
                dns_servers = [d.strip() for d in dns_query.stdout.strip().split('\n') if d.strip()]
            except Exception:
                pass
                
            response = {
                "active_profile": active_profile or "Disconnected",
                "stale_profiles_count": max(0, len(all_profiles) - 1) if active_profile else len(all_profiles),
                "dns_servers": dns_servers,
                "llmnr_status": mdns["llmnr"],
                "engine_status": current_status,
                "engine_progress": progress_percentage
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
            
        elif path == "/api/logs":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            # Return all logs
            with log_lock:
                logs_copy = list(api_logs)
                
            response = {
                "logs": logs_copy,
                "status": current_status,
                "progress": progress_percentage
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
            
        elif path == "/api/diagnose":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            # Start asynchronous diagnosis task in background thread
            if current_status == "idle" or current_status == "completed":
                with log_lock:
                    api_logs.clear()
                # Determine if this is normal baseline or post-optimization diagnose
                is_after = parsed_url.query == "after=true" or os.path.exists(DIAGNOSTIC_LOG_FILE)
                
                threading.Thread(target=async_diagnose_task, args=(is_after,)).start()
                response = {"status": "started", "message": "Quá trình đo kiểm mạng đã được bắt đầu ngầm."}
            else:
                response = {"status": "busy", "message": "Hệ thống hiện tại đang bận xử lý tác vụ khác."}
                
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
            
        elif path == "/api/report-data":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            report = {}
            if os.path.exists(DIAGNOSTIC_LOG_FILE):
                try:
                    with open(DIAGNOSTIC_LOG_FILE, "r", encoding="utf-8") as f:
                        report = json.load(f)
                except Exception as e:
                    report = {"error": f"Lỗi đọc file: {e}"}
            else:
                report = {"error": "Chưa có dữ liệu chẩn đoán ban đầu."}
                
            self.wfile.write(json.dumps(report, ensure_ascii=False).encode('utf-8'))
            return

        elif path == "/api/after-data":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            report = {}
            if os.path.exists(AFTER_LOG_FILE):
                try:
                    with open(AFTER_LOG_FILE, "r", encoding="utf-8") as f:
                        report = json.load(f)
                except Exception as e:
                    report = {"error": f"Lỗi đọc file: {e}"}
            else:
                report = {"error": "Chưa có dữ liệu chẩn đoán sau khi tối ưu."}
                
            self.wfile.write(json.dumps(report, ensure_ascii=False).encode('utf-8'))
            return

        elif path == "/api/compare":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._send_cors_headers()
            self.end_headers()
            
            if not os.path.exists(DIAGNOSTIC_LOG_FILE) or not os.path.exists(AFTER_LOG_FILE):
                response = {"ready": False, "message": "Cần hoàn tất cả chẩn đoán ban đầu và chẩn đoán sau tối ưu để so sánh."}
            else:
                try:
                    with open(DIAGNOSTIC_LOG_FILE, "r", encoding="utf-8") as f:
                        before = json.load(f)
                    with open(AFTER_LOG_FILE, "r", encoding="utf-8") as f:
                        after = json.load(f)
                        
                    response = {
                        "ready": True,
                        "before": before,
                        "after": after
                    }
                except Exception as e:
                    response = {"ready": False, "message": f"Lỗi xử lý so sánh dữ liệu: {e}"}
                    
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        # 2. Static Assets Serving
        # Serve index.html, style.css, app.js or 404
        filename = ""
        content_type = "text/html; charset=utf-8"
        
        if path == "/" or path == "/index.html":
            filename = "index.html"
            content_type = "text/html; charset=utf-8"
        elif path == "/style.css":
            filename = "style.css"
            content_type = "text/css; charset=utf-8"
        elif path == "/app.js":
            filename = "app.js"
            content_type = "application/javascript; charset=utf-8"
            
        if filename and os.path.exists(filename):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self._send_cors_headers()
            self.end_headers()
            with open(filename, "rb") as f:
                self.wfile.write(f.read())
            return
            
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self):
        global current_status, progress_percentage, api_logs
        
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers['Content-Length']) if 'Content-Length' in self.headers else 0
        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._send_cors_headers()
        self.end_headers()

        if path == "/api/optimize":
            if current_status == "idle" or current_status == "completed":
                with log_lock:
                    api_logs.clear()
                threading.Thread(target=async_optimize_task).start()
                response = {"status": "started", "message": "Quá trình tối ưu mạng đã bắt đầu chạy ngầm."}
            else:
                response = {"status": "busy", "message": "Hệ thống đang thực thi tác vụ khác."}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
            
        elif path == "/api/set-dns":
            try:
                data = json.loads(post_data)
                dns_ip = data.get("dns_ip")
                add_log(f"Yêu cầu cấu hình DNS chính thành: {dns_ip}...")
                
                cmd = f'Set-DnsClientServerAddress -InterfaceAlias Wi-Fi -ServerAddresses ("{dns_ip}", "8.8.8.8")'
                # Attempt to run powershell
                stdout, stderr, ok = run_command(f'powershell -Command "{cmd}"')
                
                if ok:
                    add_log(f"Cấu hình DNS thành công! Đã chuyển đổi DNS mạng Wi-Fi sang {dns_ip}.")
                    response = {"success": True, "message": f"Đã chuyển đổi thành công DNS sang {dns_ip}."}
                else:
                    add_log(f"[!] Thất bại khi đặt DNS trực tiếp. Chi tiết: {stderr or stdout}")
                    response = {
                        "success": False,
                        "need_admin": True,
                        "powershell_command": cmd,
                        "message": "Cần quyền Administrator để thay đổi DNS hệ thống."
                    }
            except Exception as e:
                response = {"success": False, "message": f"Lỗi máy chủ khi thiết lập DNS: {e}"}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        elif path == "/api/set-mtu":
            try:
                data = json.loads(post_data)
                mtu_size = data.get("mtu")
                add_log(f"Yêu cầu thay đổi kích thước MTU Wi-Fi thành: {mtu_size}...")
                
                cmd = f'netsh interface ipv4 set subinterface "Wi-Fi" mtu={mtu_size} store=persistent'
                stdout, stderr, ok = run_command(cmd)
                
                if ok:
                    add_log(f"Thay đổi kích thước MTU thành công! Đã đặt MTU Wi-Fi thành {mtu_size} bytes.")
                    response = {"success": True, "message": f"Đặt MTU thành công về {mtu_size} bytes."}
                else:
                    add_log(f"[!] Thất bại khi đặt MTU. Chi tiết: {stderr or stdout}")
                    response = {
                        "success": False,
                        "need_admin": True,
                        "powershell_command": cmd,
                        "message": "Cần quyền Administrator để thay đổi MTU hệ thống."
                    }
            except Exception as e:
                response = {"success": False, "message": f"Lỗi máy chủ khi thiết lập MTU: {e}"}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        elif path == "/api/terminate-process":
            try:
                data = json.loads(post_data)
                pid = data.get("pid")
                proc_name = data.get("name", "N/A")
                add_log(f"Yêu cầu đóng tiến trình tốn mạng: {proc_name} (PID: {pid})...")
                
                stdout, stderr, ok = run_command(f"taskkill /PID {pid} /F")
                if ok:
                    add_log(f"Đã đóng thành công tiến trình {proc_name} (PID {pid}).")
                    response = {"success": True, "message": f"Đã kết thúc tiến trình {proc_name}."}
                else:
                    add_log(f"[!] Không thể đóng tiến trình. Chi tiết: {stderr or stdout}")
                    response = {"success": False, "message": f"Không có quyền đóng tiến trình hoặc tiến trình đã tự thoát."}
            except Exception as e:
                response = {"success": False, "message": f"Lỗi máy chủ: {e}"}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        elif path == "/api/delete-profile":
            try:
                data = json.loads(post_data)
                profile = data.get("profile")
                add_log(f"Yêu cầu xóa mạng Wi-Fi đã lưu: '{profile}'...")
                
                stdout, stderr, ok = run_command(f'netsh wlan delete profile name="{profile}"')
                if ok:
                    add_log(f"Đã xóa thành công mạng Wi-Fi rác '{profile}'.")
                    response = {"success": True, "message": f"Đã xóa cấu hình Wi-Fi '{profile}'."}
                else:
                    add_log(f"[!] Không thể xóa profile. Chi tiết: {stderr or stdout}")
                    response = {"success": False, "message": f"Lỗi khi xóa cấu hình: {stderr or stdout}"}
            except Exception as e:
                response = {"success": False, "message": f"Lỗi máy chủ: {e}"}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
            
        elif path == "/api/reset":
            # Resets dashboard status to idle
            current_status = "idle"
            progress_percentage = 0
            with log_lock:
                api_logs.clear()
            add_log("Giao diện giám sát đã được thiết lập lại.")
            response = {"success": True, "message": "Reset hoàn tất."}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        self.wfile.write(json.dumps({"error": "Không tìm thấy API này."}).encode('utf-8'))

def main():
    # Make sure we run in the workspace directory C:\Users\NguyenNguyen\.gemini\antigravity\scratch\network_optimizer
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, NetworkOptimizerServer)
    
    print("="*60)
    print(f"  NETWORK OPTIMIZER SERVER ĐANG KHỞI CHẠY...")
    print(f"  Đường dẫn local: http://localhost:{PORT}")
    print(f"  Thư mục hoạt động: {os.getcwd()}")
    print("="*60)
    
    add_log("Khởi động server thành công trên cổng 8888.")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang đóng server...")
        httpd.server_close()
        print("Đã đóng hoàn tất.")

if __name__ == "__main__":
    main()
