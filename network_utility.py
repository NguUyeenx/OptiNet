import os
import sys
import subprocess
import socket
import time
import json
import re
import winreg

# Configuration
TEST_DOMAINS = ["google.com", "wikipedia.org", "cloudflare.com", "github.com"]
DNS_SERVERS = {
    "1.1.1.1": "Cloudflare DNS",
    "8.8.8.8": "Google DNS",
    "9.9.9.9": "Quad9 DNS",
    "208.67.222.222": "OpenDNS"
}
DIAGNOSTIC_LOG_FILE = "diagnostics_report.json"

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
        sock.settimeout(1.5)
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
    print("[*] Benchmarking DNS response times...")
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
    except Exception:
        pass

    for ip, name in DNS_SERVERS.items():
        times = []
        for domain in TEST_DOMAINS:
            t = dns_query_time(ip, domain)
            if t is not None:
                times.append(t)
        if times:
            avg_time = sum(times) / len(times)
            results[ip] = {"name": name, "avg_ms": round(avg_time, 2), "status": "Online"}
        else:
            results[ip] = {"name": name, "avg_ms": 9999, "status": "Failed/Offline"}
            
    # Sort by speed
    sorted_dns = sorted(results.items(), key=lambda x: x[1]["avg_ms"])
    print("    DNS Server Benchmark Results:")
    for ip, info in sorted_dns:
        ms_str = f"{info['avg_ms']} ms" if info['avg_ms'] != 9999 else "Timed Out"
        print(f"    - {info['name']} ({ip}): {ms_str}")
        
    return results

def get_active_profile():
    """Gets the active Wi-Fi profile name (SSID) using Get-NetConnectionProfile."""
    cmd = 'powershell -Command "(Get-NetConnectionProfile -InterfaceAlias Wi-Fi -ErrorAction SilentlyContinue).Name"'
    stdout, _, success = run_command(cmd)
    if success and stdout.strip():
        # Handle multiple connected networks if any
        profiles = [p.strip() for p in stdout.strip().split('\n') if p.strip()]
        return profiles[0] if profiles else None
    return None

def list_wifi_profiles():
    """Lists all configured Wi-Fi profiles."""
    stdout, _, success = run_command("netsh wlan show profiles")
    profiles = []
    if success:
        for line in stdout.split('\n'):
            if "All User Profile" in line or "Hồ sơ người dùng" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    profiles.append(parts[1].strip())
    return profiles

def get_latency_stats(target="1.1.1.1", count=15):
    """Pings target to calculate packet loss, latency, and jitter."""
    print(f"[*] Measuring latency and packet loss to {target} ({count} pings)...")
    stdout, _, success = run_command(f"ping -n {count} {target}")
    
    loss_match = re.search(r"Lost = (\d+) \((\d+)% loss\)", stdout) or re.search(r"Bị mất = (\d+) \((\d+)% mất\)", stdout)
    min_max_avg = re.search(r"Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms", stdout) or re.search(r"Tối thiểu = (\d+)ms, Tối đa = (\d+)ms, Trung bình = (\d+)ms", stdout)
    
    loss_pct = 0
    stats = {"min": 0, "max": 0, "avg": 0, "loss_pct": 100}
    
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
    else:
        stats["jitter"] = 0
        
    print(f"    Avg Latency: {stats['avg']} ms | Jitter: {stats['jitter']} ms | Packet Loss: {stats['loss_pct']}%")
    return stats

def discover_mtu(target="1.1.1.1"):
    """Finds the maximum packet size that passes without fragmentation."""
    print("[*] Discovering optimal MTU size using DF ping sweep...")
    
    # Standard ethernet MTU is 1500, IP + ICMP headers take 28 bytes. Max payload size is 1472.
    low = 1300
    high = 1472
    optimal_payload = 1472
    
    # Quick sanity check
    _, _, ok = run_command(f"ping -f -l {high} -n 1 {target}")
    if ok:
        print(f"    No fragmentation at max segment payload {high}. Optimal MTU is 1500 (standard Ethernet/Wi-Fi).")
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
    print(f"    Optimal MTU size found: {optimal_mtu} (Payload: {optimal_payload} bytes + 28 bytes headers).")
    return optimal_mtu

def list_bandwidth_hogs():
    """Lists active processes established network connections."""
    print("[*] Scanning for bandwidth-consuming background processes...")
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
        print(f"    [!] Error scanning network processes: {e}")
        
    if success and stdout.strip():
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                proc_name = item.get("ProcessName", "").lower()
                # Ignore core system and browser processes if you want, but display all established ones
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
        if any(x in name for x in ["vantage", "widget", "searchhost", "update", "cortana", "onedrive", "teams"]):
            suspects.append(h)
            
    print(f"    Found {len(hogs)} processes with active connections. {len(suspects)} flagged as potential background noise:")
    for s in suspects:
        print(f"    - [PID {s['pid']}] {s['name']} ({s['path']})")
        
    return {"all": hogs, "noise": suspects}

def check_mdns_llmnr():
    """Checks if LLMNR is enabled in registry."""
    print("[*] Inspecting mDNS/LLMNR settings...")
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
        llmnr_status = f"Unknown (Error reading Registry: {e})"
        
    print(f"    LLMNR (Link-Local Multicast Name Resolution) status: {llmnr_status}")
    return {"llmnr": llmnr_status}

def run_speed_test():
    """Runs speedtest-cli and parses JSON output."""
    print("[*] Running Internet Speed Test (download/upload)... This may take 30-45 seconds.")
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
            print(f"    Speed Results: Download: {res['download_mbps']} Mbps | Upload: {res['upload_mbps']} Mbps | Ping: {res['ping_ms']} ms")
            return res
        except Exception as e:
            print(f"    Error parsing speedtest JSON: {e}")
            
    # Fallback to simple parse or manual download check
    print("    [!] Speedtest CLI JSON failed. Trying simple mode...")
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
        print(f"    Speed Results: Download: {res['download_mbps']} Mbps | Upload: {res['upload_mbps']} Mbps | Ping: {res['ping_ms']} ms")
        return res
        
    print("    [!] Speedtest CLI completely failed.")
    return {"download_mbps": 0.0, "upload_mbps": 0.0, "ping_ms": 0.0, "isp": "N/A", "server": "N/A"}

def run_diagnostics():
    """Runs a full suite of diagnostics and saves the report."""
    print("="*60)
    print("             NETWORK PERFORMANCE DIAGNOSTICS            ")
    print("="*60)
    
    speed = run_speed_test()
    dns = benchmark_dns()
    latency = get_latency_stats()
    mtu = discover_mtu()
    hogs = list_bandwidth_hogs()
    mdns = check_mdns_llmnr()
    
    active_profile = get_active_profile()
    all_profiles = list_wifi_profiles()
    stale_profiles = [p for p in all_profiles if p != active_profile]
    
    print(f"[*] Stale Wi-Fi profiles check: {len(stale_profiles)} stale profiles detected out of {len(all_profiles)} total profiles.")
    
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
    
    return report

def optimize_network(report):
    """Executes network optimization actions based on report."""
    print("\n" + "="*60)
    print("              EXECUTING NETWORK OPTIMIZATIONS            ")
    print("="*60)
    
    # 1. Clean up Stale Wi-Fi Profiles
    stale = report.get("stale_profiles", [])
    active = report.get("active_profile", "")
    print(f"[*] Connected Wi-Fi network: '{active}' (Keeping)")
    if stale:
        print(f"[*] Cleaning up {len(stale)} stale Wi-Fi profiles...")
        cleaned = 0
        for profile in stale:
            _, _, ok = run_command(f'netsh wlan delete profile name="{profile}"')
            if ok:
                cleaned += 1
        print(f"    Successfully removed {cleaned} stale profiles.")
    else:
        print("    No stale Wi-Fi profiles to remove.")

    # 2. DNS Optimization Command recommendation
    dns_bench = report.get("dns", {})
    sorted_dns = sorted(dns_bench.items(), key=lambda x: x[1]["avg_ms"])
    fastest_dns_ip = sorted_dns[0][0] if sorted_dns else None
    
    if fastest_dns_ip:
        print(f"[*] Fastest DNS server determined: {dns_bench[fastest_dns_ip]['name']} ({fastest_dns_ip})")
        # Generate command to set DNS to the fastest one
        cmd_set_dns = f'Set-DnsClientServerAddress -InterfaceAlias Wi-Fi -ServerAddresses ("{fastest_dns_ip}", "8.8.8.8")'
        print(f"    To apply this permanently, run in elevated PowerShell:")
        print(f"    {cmd_set_dns}")
        
    # 3. MTU Tuning command recommendation
    mtu = report.get("mtu", 1500)
    if mtu != 1500:
        print(f"[*] Optimal MTU is {mtu} (currently 1500). Lower MTU prevents packet fragmentation.")
        cmd_set_mtu = f'netsh interface ipv4 set subinterface "Wi-Fi" mtu={mtu} store=persistent'
        print(f"    To apply this, run in elevated Command Prompt:")
        print(f"    {cmd_set_mtu}")
    else:
        print("[*] MTU is already at optimal size (1500). No fragmentation tuning needed.")
        
    # 4. Disable LLMNR multicast noise
    print("[*] Optimizing LLMNR multicast settings...")
    try:
        # Check if Registry Key exists, otherwise create it
        key_path = r"Software\Policies\Microsoft\Windows NT\DNSClient"
        try:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.SetValueEx(key, "EnableMulticast", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            print("    Successfully disabled LLMNR via local machine Registry policies.")
        except PermissionError:
            print("    [!] Registry write requires elevated admin permissions.")
            print(f"    To manually disable LLMNR, run in Administrator PowerShell:")
            print(f'    New-Item -Path "HKLM:\\Software\\Policies\\Microsoft\\Windows NT\\DNSClient" -Force; Set-ItemProperty -Path "HKLM:\\Software\\Policies\\Microsoft\\Windows NT\\DNSClient" -Name "EnableMulticast" -Value 0 -Type DWord')
    except Exception as e:
        print(f"    Failed to write LLMNR settings: {e}")
        
    # 5. Disable bandwidth hogs
    hogs = report.get("bandwidth_hogs", [])
    if hogs:
        print("[*] Terminating or throttling background noise processes...")
        killed_count = 0
        for h in hogs:
            name = h["name"].lower()
            # Safely terminate known browser components/widgets that waste background net bandwidth
            if any(x in name for x in ["widget", "searchhost", "cortana"]):
                print(f"    Terminating background process: {h['name']} (PID: {h['pid']})")
                _, _, ok = run_command(f"taskkill /PID {h['pid']} /F")
                if ok:
                    killed_count += 1
        print(f"    Stopped {killed_count} non-essential background processes.")
    else:
        print("    No bandwidth hogs to terminate.")

    # 6. Flush DNS Cache
    print("[*] Flushing DNS Resolver Cache...")
    _, _, ok = run_command("ipconfig /flushdns")
    if ok:
        print("    Successfully flushed DNS cache.")
    else:
        print("    [!] Failed to flush DNS cache.")

    # 7. TCP/IP Stack Tweaks
    print("[*] Applying high-end TCP/IP stack tweaks...")
    tcp_tweaks = [
        ("netsh int tcp set global rss=enabled", "Enable Receive-Side Scaling (RSS)"),
        ("netsh int tcp set global rsc=enabled", "Enable Receive Segment Coalescing (RSC)"),
        ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -AutoTuningLevelLocal Normal\"", "Set TCP Auto-Tuning Local Level to Normal"),
        ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -CongestionProvider CUBIC\"", "Set Congestion Provider to CUBIC"),
        ("powershell -Command \"Set-NetTCPSetting -SettingName Internet -EcnCapability Enabled\"", "Enable ECN Capability")
    ]
    for cmd, desc in tcp_tweaks:
        _, _, ok = run_command(cmd)
        if ok:
            print(f"    Successfully applied: {desc}")
        else:
            print(f"    [!] Failed to apply: {desc} (requires elevated Administrator privileges)")

    # 8. Disable Multimedia Throttling & System Responsiveness
    print("[*] Optimizing system responsiveness for networking...")
    try:
        sys_profile_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sys_profile_path, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xffffffff)
        winreg.SetValueEx(key, "SystemResponsiveness", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        print("    Disabled multimedia network throttling and prioritized gaming network packets in Registry.")
    except PermissionError:
        print("    [!] Registry write requires elevated admin permissions to optimize Multimedia SystemProfile.")
    except Exception as e:
        print(f"    Failed to write Multimedia Profile Registry: {e}")

    # 9. Bypass Nagle's Algorithm (TCP No Delay & TCP Ack Frequency)
    print("[*] Tuning Nagle's Algorithm on network adapters for low latency/ping...")
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
            print(f"    Disabled Nagle's Algorithm across {modified_interfaces} active network interfaces (TCPNoDelay = 1, TcpAckFrequency = 1).")
        else:
            print("    [!] No active network interfaces found under standard Tcpip path.")
    except PermissionError:
        print("    [!] Registry write requires elevated admin permissions to tune Nagle's Algorithm.")
    except Exception as e:
        print(f"    Failed to tune Nagle's Algorithm Registry: {e}")

    print("\n[*] Optimizations complete.")

if __name__ == "__main__":
    action = "--diagnose"
    if len(sys.argv) > 1:
        action = sys.argv[1]
        
    if action == "--diagnose":
        report = run_diagnostics()
        with open(DIAGNOSTIC_LOG_FILE, "w") as f:
            json.dump(report, f, indent=4)
        print(f"\n[+] Diagnostics saved to '{DIAGNOSTIC_LOG_FILE}'.")
        
    elif action == "--optimize":
        if os.path.exists(DIAGNOSTIC_LOG_FILE):
            with open(DIAGNOSTIC_LOG_FILE, "r") as f:
                report = json.load(f)
        else:
            print("[!] Baseline diagnostics not found. Running baseline first...")
            report = run_diagnostics()
            with open(DIAGNOSTIC_LOG_FILE, "w") as f:
                json.dump(report, f, indent=4)
        
        optimize_network(report)
        
    elif action == "--report":
        # Run AFTER speedtest and output compare
        if not os.path.exists(DIAGNOSTIC_LOG_FILE):
            print("[!] Baseline 'diagnostics_report.json' not found. Cannot generate comparison report.")
            sys.exit(1)
            
        with open(DIAGNOSTIC_LOG_FILE, "r") as f:
            before = json.load(f)
            
        print("\n" + "="*60)
        print("             RUNNING POST-OPTIMIZATION SCAN             ")
        print("="*60)
        after = run_diagnostics()
        
        # Save after report
        with open("after_report.json", "w") as f:
            json.dump(after, f, indent=4)
            
        print("\n" + "="*60)
        print("            BEFORE VS AFTER COMPARISON REPORT           ")
        print("="*60)
        
        before_s = before["speed"]
        after_s = after["speed"]
        
        before_lat = before["latency"]
        after_lat = after["latency"]
        
        print(f"| Metric                   | Before                  | After                   | Improvement            |")
        print(f"|--------------------------|-------------------------|-------------------------|------------------------|")
        
        # Download Speed
        dl_diff = round(after_s['download_mbps'] - before_s['download_mbps'], 2)
        dl_pct = round((dl_diff / before_s['download_mbps'] * 100), 1) if before_s['download_mbps'] > 0 else 0
        dl_imp = f"+{dl_diff} Mbps ({dl_pct}%)" if dl_diff > 0 else f"{dl_diff} Mbps ({dl_pct}%)"
        print(f"| Download Speed           | {before_s['download_mbps']} Mbps             | {after_s['download_mbps']} Mbps             | {dl_imp} |")
        
        # Upload Speed
        ul_diff = round(after_s['upload_mbps'] - before_s['upload_mbps'], 2)
        ul_pct = round((ul_diff / before_s['upload_mbps'] * 100), 1) if before_s['upload_mbps'] > 0 else 0
        ul_imp = f"+{ul_diff} Mbps ({ul_pct}%)" if ul_diff > 0 else f"{ul_diff} Mbps ({ul_pct}%)"
        print(f"| Upload Speed             | {before_s['upload_mbps']} Mbps             | {after_s['upload_mbps']} Mbps             | {ul_imp} |")
        
        # Ping
        ping_diff = round(before_lat['avg'] - after_lat['avg'], 2)
        ping_imp = f"-{ping_diff} ms" if ping_diff > 0 else f"+{abs(ping_diff)} ms"
        print(f"| Avg Ping / Latency       | {before_lat['avg']} ms                 | {after_lat['avg']} ms                 | {ping_imp} (lower is better) |")
        
        # Jitter
        jit_diff = round(before_lat.get('jitter', 0) - after_lat.get('jitter', 0), 2)
        jit_imp = f"-{jit_diff} ms" if jit_diff > 0 else f"+{abs(jit_diff)} ms"
        print(f"| Latency Jitter           | {before_lat.get('jitter', 0)} ms                 | {after_lat.get('jitter', 0)} ms                 | {jit_imp} (lower is better) |")
        
        # Packet Loss
        loss_diff = before_lat['loss_pct'] - after_lat['loss_pct']
        loss_imp = f"-{loss_diff}%" if loss_diff > 0 else f"+{abs(loss_diff)}%"
        print(f"| Packet Loss              | {before_lat['loss_pct']}%                      | {after_lat['loss_pct']}%                      | {loss_imp} (lower is better) |")
        
        # Wi-Fi Profiles
        prof_diff = before['all_profiles_count'] - after['all_profiles_count']
        print(f"| Active Wi-Fi Profiles    | {before['all_profiles_count']}                      | {after['all_profiles_count']}                      | -{prof_diff} profiles (cleaned) |")
        
        # Background Hogs
        hogs_diff = len(before['bandwidth_hogs']) - len(after['bandwidth_hogs'])
        print(f"| Bandwidth Noise Processes| {len(before['bandwidth_hogs'])}                      | {len(after['bandwidth_hogs'])}                      | -{hogs_diff} processes (throttled) |")
        
        print("="*60)
        print("[+] Optimization report generated successfully!")
