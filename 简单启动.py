#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""WiFi二次认证系统 - 启动脚本（纯Python）"""

def build_tray():
    # 动态加载可选依赖，避免静态检查的导入错误
    try:
        import importlib
        pystray = importlib.import_module('pystray')
        pil_image_mod = importlib.import_module('PIL.Image')
    except ImportError:
        return None

    icon_path = Path(__file__).parent / 'src' / 'assets' / 'wifiVerify.ico'
    image = None
    try:
        if icon_path.exists():
            image = pil_image_mod.open(str(icon_path))
    except OSError:
        image = None

    # 简化：仅提供打开日志与退出
    def on_open_logs(_icon, _item):
        try:
            os.startfile(str(Path(__file__).parent / 'logs'))
        except OSError:
            pass

    def on_exit(icon, _item):
        icon.visible = False
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem('打开日志目录', on_open_logs),
        pystray.MenuItem('退出', on_exit)
    )

    tray = pystray.Icon('VerifyWiFi', image, 'WiFi认证系统', menu)
    return tray
 

import os
import subprocess
import sys
import time
import socket
from pathlib import Path
import ctypes
import platform
import threading
import argparse
from typing import List, Tuple

# Windows: creation flag to hide child process consoles
CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
ERROR_ALREADY_EXISTS = 183
class _InstanceState:
    handle = None

def ensure_single_instance(name: str = "Global\\VerifyWifiSingleInstance") -> bool:
    """Ensure only one instance runs on Windows using a named mutex.
    Returns True if this is the first instance; False if another is running.
    """
    if platform.system() != "Windows":
        return True
    try:
        # Create or open a named mutex
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        last_error = ctypes.windll.kernel32.GetLastError()
        _InstanceState.handle = handle  # keep reference without使用global
        if last_error == ERROR_ALREADY_EXISTS:
            return False
        return True
    except OSError:
        # On error, do not block startup
        return True

def is_admin():
    """检查当前脚本是否以管理员权限运行 (仅限Windows)"""
    if platform.system() != "Windows":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except OSError:
        return False

def setup_firewall_rules():
    """自动配置Windows防火墙规则"""
    if platform.system() != "Windows":
        print("ℹ️  非Windows系统，跳过防火墙配置。")
        return True

    print("⚙️  正在配置Windows防火墙规则...")
    rules = {
        "8888": "WiFi Auth Proxy (8888)",
        "8080": "WiFi Auth API (8080)"
    }
    success = True
    for port, name in rules.items():
        # 删除可能存在的旧规则以避免冲突
        subprocess.run(
            f'netsh advfirewall firewall delete rule name="{name}"',
            shell=True,
            capture_output=True,
            check=False
        )
        # 为Python.exe创建特定的规则，更安全
        command = (
            f'netsh advfirewall firewall add rule name="{name}" '
            f'dir=in action=allow protocol=TCP localport={port}'
        )
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='cp936',
            errors='ignore',
            check=False
        )
        if result.returncode == 0:
            print(f"   ✅ 已为端口 {port} 添加入站规则。")
        else:
            print(f"   ⚠️  为端口 {port} 添加防火墙规则失败: {result.stderr or result.stdout}")
            success = False
    return success

def _is_private_ipv4(ip: str) -> bool:
    # RFC1918 + 常见 CGNAT 网段
    try:
        parts = [int(p) for p in ip.split('.')]
        if len(parts) != 4:
            return False
        a, b = parts[0], parts[1]
        if a == 10:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        # CGNAT 100.64.0.0/10
        if a == 100 and 64 <= b <= 127:
            return True
        return False
    except ValueError:
        return False


def _looks_like_vpn_or_virtual(name: str) -> bool:
    lower = name.lower()
    keywords = [
        'vpn', 'anyconnect', 'ppp', 'pptp', 'l2tp', 'ikev2', 'wireguard', 'wg',
        'zerotier', 'tailscale', 'tun', 'tap', 'vmware', 'virtual', 'hyper-v'
    ]
    return any(k in lower for k in keywords)


def get_local_ip():
    """优先选择物理网卡的私网IPv4，避开VPN/虚拟网卡；否则回退socket路由；再回退127.0.0.1。"""
    # 1) 使用 psutil 精选网卡
    try:
        import importlib
        psutil = importlib.import_module('psutil')
        preferred_keywords = ['wlan', 'wi-fi', 'ethernet', '以太网', '无线']
        candidates = []
        for if_name, addrs in psutil.net_if_addrs().items():
            if _looks_like_vpn_or_virtual(if_name):
                continue
            score = 0
            lname = if_name.lower()
            if any(k in lname for k in preferred_keywords):
                score += 10
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip.startswith('127.') or ip.startswith('169.254.'):
                        continue
                    if _is_private_ipv4(ip):
                        candidates.append((score, ip))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except (ModuleNotFoundError, ImportError):
        pass

    # 2) 路由法（可能返回VPN出口）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            # 若为公网/非私网，尽量不要用
            if _is_private_ipv4(ip):
                return ip
    except OSError:
        pass

    # 3) 兜底
    return "127.0.0.1"

def check_port(host, port, timeout=5):
    """检查端口是否开放"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False

def wait_for_service(name, check_func, max_wait=30):
    """等待服务启动"""
    print(f"⏳ 等待 {name} 启动...")
    for i in range(max_wait):
        if check_func(): print(f"✅ {name} 启动成功"); return True
        time.sleep(1)
        if i % 5 == 4: print(f"   仍在等待 {name}... ({i+1}/{max_wait}s)")
    print(f"❌ {name} 启动超时"); return False

def stream_output(pipe, log_file_path):
    """将子进程的输出流式传输到日志文件"""
    try:
        with open(log_file_path, 'w', encoding='utf-8') as f:
            for line in iter(pipe.readline, ''):
                f.write(line)
                f.flush()
    except OSError:
        pass # 进程终止时可能出现管道关闭错误，可以忽略

# 纯Python模式：移除所有 npm/Vite 相关逻辑

def main():
    # 当前无命令行参数
    argparse.ArgumentParser(description="WiFi二次认证系统一键启动（纯Python）").parse_args()
    if platform.system() == "Windows" and not is_admin():
        print("ℹ️  需要管理员权限来配置防火墙，正在尝试提权...")
        # 区分两种运行形态：
        # - 非打包(.py)：以 python.exe + 脚本路径 + 参数 启动
        # - 打包(.exe / PyInstaller frozen)：直接以当前 exe + 参数 启动（不可附加脚本路径，否则 argparse 报 unrecognized arguments）
        is_frozen = bool(getattr(sys, "frozen", False))
        if is_frozen:
            exe_path = sys.executable
            params = subprocess.list2cmdline(sys.argv[1:])
            workdir = str(Path(exe_path).parent.resolve())
            rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, params, workdir, 1)
        else:
            try:
                script_path = os.path.abspath(__file__)
            except NameError:
                script_path = sys.argv[0]
            params = subprocess.list2cmdline([script_path] + sys.argv[1:])
            workdir = str(Path(script_path).parent.resolve())
            rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, workdir, 1)
        # ShellExecuteW 返回值 <= 32 表示失败
        if rc <= 32:
            try:
                ctypes.windll.user32.MessageBoxW(0, "提权启动失败，请以管理员身份重新运行此程序。", "WiFi认证系统", 0x00000010)
            except OSError:
                pass
        return

    # Single-instance guard (after elevation)
    if not ensure_single_instance():
        try:
            ctypes.windll.user32.MessageBoxW(0, "程序已在运行中。", "WiFi认证系统", 0x00000040)
        except OSError:
            print("程序已在运行中。")
        return

    print("=" * 60)
    print("🎉 WiFi二次认证系统 - 启动程序 (管理员模式)")
    print("=" * 60)
    if not setup_firewall_rules():
        print("❌ 防火墙配置失败，请检查权限或手动配置。")
        return # 直接退出
    
    project_root = Path(__file__).parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    processes: List[Tuple[str, subprocess.Popen]] = []
    threads = []
    local_ip = get_local_ip()
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "UTF-8"
    
    try:
        # 纯Python：仅启动 API 与 代理
        services = {
            "API服务器": {
                "command": [sys.executable, str(project_root / "src/pyserver/auth_api.py")],
                "check": lambda: check_port("localhost", 8080),
                "log_file": log_dir / "auth_api.log"
            },
            # 关键：明确绑定代理到本机局域网IP，避免某些环境下 0.0.0.0 触发 10013 权限错误
            "代理服务器": {
                "command": [
                    sys.executable,
                    str(project_root / "src/pyserver/wifi_proxy.py"),
                    "--host", "0.0.0.0",
                    "--port", "8888"
                ],
                # 代理应对本机IP开放
                "check": lambda: (check_port("127.0.0.1", 8888) or check_port(local_ip, 8888)),
                "log_file": log_dir / "wifi_proxy.log"
            }
        }

        for name, config in services.items():
            print(f"🚀 启动 {name}...")
            process = subprocess.Popen(
                config["command"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                shell=config.get("shell", False),
                cwd=str(project_root),
                creationflags=CREATE_NO_WINDOW
            )
            processes.append((name, process))

            stdout_thread = threading.Thread(target=stream_output, args=(process.stdout, config["log_file"]))
            stderr_thread = threading.Thread(target=stream_output, args=(process.stderr, config["log_file"]))
            stdout_thread.daemon = True; stderr_thread.daemon = True
            threads.extend([stdout_thread, stderr_thread])
            stdout_thread.start(); stderr_thread.start()
            
            if not wait_for_service(name, config["check"], max_wait=60):
                raise RuntimeError(f"{name}启动失败")

        print("\n" + "=" * 60)
        print("🎯 系统启动完成！")
        print("=" * 60)
        print("📋 访问地址：")
        print(f"  • 认证页面(后端HTML): http://{local_ip}:8080/api/auth/fallback")
        print(f"  • API健康检查: http://{local_ip}:8080/api/health")
        # 输出候选IP，帮助在VPN/虚拟网卡存在时手动选择
        try:
            import importlib
            psutil = importlib.import_module('psutil')
            all_ips = []
            for if_name, addrs in psutil.net_if_addrs().items():
                if _looks_like_vpn_or_virtual(if_name):
                    continue
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith('127.') and not ip.startswith('169.254.'):
                            all_ips.append(ip)
            if all_ips:
                print("\n🔎 检测到以下可能可用的IPv4（已排除VPN/虚拟网卡/回环）：")
                for ip in sorted(set(all_ips)):
                    note = " ← 当前选择" if ip == local_ip else ""
                    print(f"  • {ip}{note}")
        except (ModuleNotFoundError, ImportError):
            pass
        print("\n📱 手机代理设置：")
        print(f"  • 代理服务器: {local_ip}")
        print("  • 端口: 8888")
        print("\n按 Ctrl+C 停止所有服务...")
        print("=" * 60)
        
        tray = build_tray()
        if tray is not None and platform.system() == 'Windows':
            # 进入系统托盘，无控制台环境下也不会退出
            tray.run()
        else:
            while True:
                time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n用户中断，开始关闭服务...")
    except (RuntimeError, OSError) as e:
        print(f"❌ 系统启动失败: {e}")
    finally:
        if processes:
            print("\n🛑 正在停止服务...")
            for name, process in reversed(processes):
                try:
                    if process.poll() is None:
                        print(f"   停止 {name}...")
                        process.terminate()
                        process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError) as ex:
                    print(f"   ⚠️  强制停止 {name} 时出错: {ex}")
                    process.kill()
            print("✅ 所有服务已停止")
        
        # 不再阻塞等待按键，避免“按回车才继续”的卡顿

def _excepthook(exc_type, exc, tb):
    # 控制台打印
    import traceback
    traceback.print_exception(exc_type, exc, tb)
    # Windows下弹窗提示
    if platform.system() == 'Windows':
        try:
            ctypes.windll.user32.MessageBoxW(0, str(exc), "WiFi认证启动失败", 0x00000010)
        except OSError:
            pass


if __name__ == "__main__":
    sys.excepthook = _excepthook
    main()
