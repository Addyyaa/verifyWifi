#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""WiFi二次认证系统 - 启动脚本（纯Python）"""


def build_tray(exit_event=None):
    # 动态加载可选依赖，避免静态检查的导入错误
    import importlib

    try:
        pystray = importlib.import_module("pystray")
    except ImportError:
        pystray = None
    try:
        pil_image_mod = importlib.import_module("PIL.Image")
    except ImportError:
        pil_image_mod = None

    icon_path = Path(__file__).parent / "src" / "assets" / "wifiVerify.ico"

    # 简化：仅提供打开主页面/日志与退出
    def on_open_logs(_icon, _item):
        try:
            os.startfile(str(Path(__file__).parent / "logs"))
        except OSError:
            pass

    def on_open_main(_icon=None, _item=None):
        try:
            import webbrowser
        except ImportError:
            webbrowser = None
        try:
            # 动态获取当前可用IP
            url = f"http://{get_local_ip()}:8080/api/auth/fallback"
            if webbrowser is not None:
                webbrowser.open(url)
            else:
                os.startfile(url)
        except Exception:
            pass

    def on_exit(icon, _item):
        icon.visible = False
        icon.stop()
        try:
            # 通知主线程退出
            if exit_event is not None:
                exit_event.set()
        except Exception:
            pass

    if pystray is not None and pil_image_mod is not None:
        # 构造图像（Pillow）
        image = None
        try:
            if icon_path.exists():
                image = pil_image_mod.open(str(icon_path))
        except OSError:
            image = None
        if image is None:
            try:
                image = pil_image_mod.new("RGBA", (16, 16), (0, 122, 255, 255))
            except Exception:
                image = None
        if image is None:
            # 若仍失败，回退到原生托盘
            pass
        else:
            try:
                menu = pystray.Menu(
                    pystray.MenuItem("打开认证页面", on_open_main),
                    pystray.MenuItem("打开日志目录", on_open_logs),
                    pystray.MenuItem("退出", on_exit),
                )
                tray = pystray.Icon("WiFiVerifyTray", image, "WiFi认证系统", menu)
                return tray
            except Exception:
                pass

    # 若 pystray 不可用或 Pillow 不可用，回退 Win32 原生托盘
    # ---- Fallback: 使用 Win32 原生托盘（pywin32）----
    try:
        import win32api
        import win32con
        import win32gui
        import win32gui_struct

        class _Win32Tray:
            def __init__(self):
                # 延迟到 run() 再创建窗口和图标
                self.hInstance = None
                self.className = "WiFiVerifyTrayWndClass"
                self.hwnd = None
                self.hicon = None
                self.menu = None
                self._visible = False

            def _on_destroy(self, hwnd, msg, wparam, lparam):
                nid = (self.hwnd, 0)
                try:
                    win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
                except win32gui.error:
                    pass
                win32gui.PostQuitMessage(0)
                return True

            def _on_command(self, hwnd, msg, wparam, lparam):
                cmd = win32api.LOWORD(wparam)
                if cmd == 1024:
                    on_open_logs(None, None)
                elif cmd == 1025:
                    try:
                        if exit_event is not None:
                            exit_event.set()
                    except Exception:
                        pass
                    win32gui.DestroyWindow(self.hwnd)
                return True

            def _on_notify(self, hwnd, msg, wparam, lparam):
                if lparam == win32con.WM_RBUTTONUP or lparam == win32con.WM_CONTEXTMENU:
                    pos = win32gui.GetCursorPos()
                    win32gui.SetForegroundWindow(self.hwnd)
                    win32gui.TrackPopupMenu(
                        self.menu,
                        win32con.TPM_LEFTALIGN,
                        pos[0],
                        pos[1],
                        0,
                        self.hwnd,
                        None,
                    )
                    win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
                return True

            # pystray 接口兼容
            def run(self):
                self.hInstance = win32api.GetModuleHandle(None)
                message_map = {
                    win32con.WM_COMMAND: self._on_command,
                    win32con.WM_DESTROY: self._on_destroy,
                    win32con.WM_USER + 20: self._on_notify,
                }
                wndclass = win32gui.WNDCLASS()
                wndclass.hInstance = self.hInstance
                wndclass.lpszClassName = self.className
                wndclass.lpfnWndProc = message_map
                try:
                    win32gui.RegisterClass(wndclass)
                except win32gui.error:
                    pass
                self.hwnd = win32gui.CreateWindow(
                    self.className,
                    "WiFiVerify",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    self.hInstance,
                    None,
                )
                if icon_path.exists():
                    self.hicon = win32gui.LoadImage(
                        0,
                        str(icon_path),
                        win32con.IMAGE_ICON,
                        16,
                        16,
                        win32con.LR_LOADFROMFILE,
                    )
                else:
                    self.hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
                nid = (
                    self.hwnd,
                    0,
                    win32gui.NIF_MESSAGE | win32gui.NIF_ICON | win32gui.NIF_TIP,
                    win32con.WM_USER + 20,
                    self.hicon,
                    "WiFi认证系统",
                )
                win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
                self.menu = win32gui.CreatePopupMenu()
                win32gui.AppendMenu(self.menu, win32con.MF_STRING, 1023, "打开认证页面")
                win32gui.AppendMenu(self.menu, win32con.MF_STRING, 1024, "打开日志目录")
                win32gui.AppendMenu(self.menu, win32con.MF_STRING, 1025, "退出")
                self._visible = True
                win32gui.PumpMessages()

            def stop(self):
                try:
                    win32gui.DestroyWindow(self.hwnd)
                except win32gui.error:
                    pass

            def notify(self, text):
                try:
                    nid = (
                        self.hwnd,
                        0,
                        win32gui.NIF_INFO,
                        win32con.WM_USER + 20,
                        self.hicon,
                        "WiFi认证系统",
                        text,
                        200,
                        "提示",
                    )
                    win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
                except win32gui.error:
                    pass

            @property
            def visible(self):
                return self._visible

            @visible.setter
            def visible(self, v):
                self._visible = v

        return _Win32Tray()
    except Exception:
        return None


import os
import subprocess
import sys
import time
import socket
from pathlib import Path
import ctypes
import msvcrt
from tempfile import gettempdir
import platform
import threading
import argparse
from typing import List, Tuple

# Windows: creation flag to hide child process consoles
CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
ERROR_ALREADY_EXISTS = 183
CONTROL_UDP_PORT = 49621  # 本地UDP端口用于激活已运行实例


class _InstanceState:
    handle = None
    lock_file_handle = None
    lock_file_path = None
    control_sock = None


def ensure_single_instance(name: str = "VerifyWifiSingleInstance") -> bool:
    """Windows下使用本地会话互斥 + 文件锁双保险，确保单实例运行。"""
    # 1) Windows命名互斥（会话内），避免管理员/普通用户跨会话不可见问题
    if platform.system() == "Windows":
        try:
            mutex_name = f"Local\\{name}"
            handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
            last_error = ctypes.windll.kernel32.GetLastError()
            _InstanceState.handle = handle
            if last_error == ERROR_ALREADY_EXISTS:
                return False
        except OSError:
            # 互斥创建异常不阻塞，继续进行文件锁
            pass

    # 2) 文件锁（跨平台可用），作为双保险
    try:
        base_dir = os.getenv("LOCALAPPDATA") or gettempdir()
        app_dir = Path(base_dir) / "VerifyWifi"
        app_dir.mkdir(parents=True, exist_ok=True)
        lock_path = app_dir / "app.lock"
        f = open(lock_path, "a+")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            try:
                f.close()
            except OSError:
                pass
            return False
        _InstanceState.lock_file_handle = f
        _InstanceState.lock_file_path = str(lock_path)
    except OSError:
        # 文件锁失败不影响，但可能导致双开；尽量通过互斥已拦截
        pass
    return True


def _acquire_udp_lock() -> bool:
    """尝试绑定本地 UDP 端口作为系统级单实例锁。绑定成功即为首个实例。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", CONTROL_UDP_PORT))
        _InstanceState.control_sock = s
        return True
    except OSError:
        return False


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
    rules = {"8888": "WiFi Auth Proxy (8888)", "8080": "WiFi Auth API (8080)"}
    success = True
    for port, name in rules.items():
        # 删除可能存在的旧规则以避免冲突
        subprocess.run(
            f'netsh advfirewall firewall delete rule name="{name}"',
            shell=True,
            capture_output=True,
            check=False,
        )
        # 为Python.exe创建特定的规则，更安全
        command = (
            f'netsh advfirewall firewall add rule name="{name}" '
            f"dir=in action=allow protocol=TCP localport={port}"
        )
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="cp936",
            errors="ignore",
            check=False,
        )
        if result.returncode == 0:
            print(f"   ✅ 已为端口 {port} 添加入站规则。")
        else:
            print(
                f"   ⚠️  为端口 {port} 添加防火墙规则失败: {result.stderr or result.stdout}"
            )
            success = False
    return success


def _is_private_ipv4(ip: str) -> bool:
    # RFC1918 + 常见 CGNAT 网段
    try:
        parts = [int(p) for p in ip.split(".")]
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
        "vpn",
        "anyconnect",
        "ppp",
        "pptp",
        "l2tp",
        "ikev2",
        "wireguard",
        "wg",
        "zerotier",
        "tailscale",
        "tun",
        "tap",
        "vmware",
        "virtual",
        "hyper-v",
    ]
    return any(k in lower for k in keywords)


def get_local_ip():
    """优先选择物理网卡的私网IPv4，避开VPN/虚拟网卡；否则回退socket路由；再回退127.0.0.1。"""
    # 1) 使用 psutil 精选网卡
    try:
        import importlib

        psutil = importlib.import_module("psutil")
        preferred_keywords = ["wlan", "wi-fi", "ethernet", "以太网", "无线"]
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
                    if ip.startswith("127.") or ip.startswith("169.254."):
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
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            # 若为公网/非私网，尽量不要用
            if _is_private_ipv4(ip):
                return ip
    except OSError:
        pass

    # 3) 兜底
    return "127.0.0.1"


def check_port(host, port, timeout=15):
    """检查端口是否开放"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            print(f"检查端口 {host}:{port} 结果: {result}")
            return result == 0
    except OSError:
        return False


def wait_for_service(name, check_func, max_wait=30):
    """等待服务启动"""
    print(f"⏳ 等待 {name} 启动...")
    for i in range(max_wait):
        if check_func():
            print(f"✅ {name} 启动成功")
            return True
        time.sleep(1)
        if i % 5 == 4:
            print(f"   仍在等待 {name}... ({i+1}/{max_wait}s)")
    print(f"❌ {name} 启动超时")
    return False


def stream_output(pipe, log_file_path):
    """将子进程的输出流式传输到日志文件"""
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            for line in iter(pipe.readline, ""):
                f.write(line)
                f.flush()
    except OSError:
        pass  # 进程终止时可能出现管道关闭错误，可以忽略


def _send_activate_signal():
    """向已运行实例发送激活信号。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.sendto(b"ACTIVATE", ("127.0.0.1", CONTROL_UDP_PORT))
    except OSError:
        pass


# 纯Python模式：移除所有 npm/Vite 相关逻辑


def _run_api_server():
    """在当前进程启动API服务（用于 --role=api）。"""
    # 延迟导入，避免主进程无用依赖
    from src.pyserver import auth_api as _api

    port = int(os.environ.get("PORT", 8080))
    _api.logger.info(f"WiFi认证API服务启动: 端口={port}, 调试模式=False")
    _api.app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


def _run_proxy_server(host: str, port: int):
    """在当前进程启动代理服务（用于 --role=proxy）。"""
    from src.pyserver import wifi_proxy as _proxy

    # 复用其 main()，通过修改 sys.argv 传参，避免大量改动
    argv_backup = sys.argv[:]
    sys.argv = [argv_backup[0], "--host", str(host), "--port", str(port)]
    try:
        _proxy.main()
    finally:
        sys.argv = argv_backup


def main():
    def _can_build_tray() -> bool:
        try:
            import importlib

            importlib.import_module("pystray")
            importlib.import_module("PIL.Image")
            return True
        except ImportError:
            return False

    parser = argparse.ArgumentParser(description="WiFi二次认证系统一键启动（纯Python）")
    parser.add_argument(
        "--role", choices=["api", "proxy"], help="内部工作角色（打包后子进程使用）"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="代理监听地址（仅 --role=proxy 时有效）"
    )
    parser.add_argument(
        "--port", type=int, default=8888, help="代理端口（仅 --role=proxy 时有效）"
    )
    parser.add_argument(
        "--elevate-firewall",
        action="store_true",
        help="以管理员权限仅执行防火墙配置后退出",
    )
    args = parser.parse_args()

    # 子进程模式：不做提权/单实例，直接运行对应服务
    if args.role == "api":
        _run_api_server()
        return
    if args.role == "proxy":
        _run_proxy_server(args.host, args.port)
        return

    # 仅防火墙提权模式：管理员执行后立即退出
    if args.elevate_firewall:
        ok = setup_firewall_rules()
        # 写入标记文件，避免后续重复提权
        try:
            base_dir = os.getenv("LOCALAPPDATA") or gettempdir()
            app_dir = Path(base_dir) / "VerifyWifi"
            app_dir.mkdir(parents=True, exist_ok=True)
            (app_dir / "firewall.ok").write_text("ok", encoding="utf-8")
        except OSError:
            pass
        sys.exit(0 if ok else 1)

    # 常规模式：主进程不提权。仅当未配置过防火墙时，后台发起一次性提权子进程执行 --elevate-firewall
    if platform.system() == "Windows" and not is_admin():
        need_firewall = True
        try:
            base_dir = os.getenv("LOCALAPPDATA") or gettempdir()
            app_dir = Path(base_dir) / "VerifyWifi"
            marker = app_dir / "firewall.ok"
            need_firewall = not marker.exists()
        except OSError:
            pass
        if need_firewall:
            try:
                is_frozen = bool(getattr(sys, "frozen", False))
                if is_frozen:
                    exe_path = sys.executable
                    workdir = str(Path(exe_path).parent.resolve())
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", exe_path, "--elevate-firewall", workdir, 0
                    )
                else:
                    try:
                        script_path = os.path.abspath(__file__)
                    except NameError:
                        script_path = sys.argv[0]
                    workdir = str(Path(script_path).parent.resolve())
                    params = subprocess.list2cmdline(
                        [script_path, "--elevate-firewall"]
                    )
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable, params, workdir, 0
                    )
            except OSError:
                pass

    # 后台模式已取消：关闭控制台仅隐藏，不再派生新进程

    # Single-instance guard (after elevation)
    if not ensure_single_instance() or not _acquire_udp_lock():
        _send_activate_signal()
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "程序已在运行中。", "WiFi认证系统", 0x00000040
            )
        except OSError:
            print("程序已在运行中。")
        return

    print("=" * 60)
    print("🎉 WiFi二次认证系统 - 启动程序")
    print("=" * 60)
    # 防火墙配置已由一次性提权子进程处理；此处不再阻塞

    project_root = Path(__file__).parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    processes: List[Tuple[str, subprocess.Popen]] = []
    threads = []
    local_ip = get_local_ip()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "UTF-8"

    # --- Windows 控制台关闭 -> 隐藏到托盘，仅托盘“退出”才真正退出 ---
    def _hide_console_window():
        if platform.system() == "Windows":
            try:
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
            except OSError:
                pass

    _console_handler_ref = None
    if platform.system() == "Windows":
        try:
            HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def _handler(ctrl_type):
                # CTRL_CLOSE/LOGOFF/SHUTDOWN -> 仅隐藏控制台，托盘与服务保持
                if ctrl_type in (2, 5, 6):
                    _hide_console_window()
                    try:
                        ctypes.windll.kernel32.FreeConsole()
                    except OSError:
                        pass
                    return True
                return False

            _console_handler_ref = HandlerRoutine(_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler_ref, True)
        except OSError:
            _console_handler_ref = None

    # 预先创建托盘并后台运行，确保任何时刻都可见
    exit_event = threading.Event()
    tray = None
    if platform.system() == "Windows":
        tray = build_tray(exit_event=exit_event)
        if tray is not None:
            try:
                # 统一用线程运行，确保与某些桌面环境兼容
                t = threading.Thread(target=tray.run, daemon=True)
                t.start()
                try:
                    tray.visible = True
                    tray.notify("程序已在后台运行，右键此图标可退出。")
                    print("ℹ️ 托盘已创建并后台运行。")
                except Exception:
                    pass
            except Exception:
                tray = None
                print("⚠️ 托盘创建失败，将无托盘运行。")

    # 启动UDP控制监听线程：接受ACTIVATE以显示通知（提示程序已运行）
    def _control_server():
        if _InstanceState.control_sock is None:
            return
        s = _InstanceState.control_sock
        while True:
            try:
                data, _ = s.recvfrom(32)
            except OSError:
                break
            if data == b"ACTIVATE":
                try:
                    if tray is not None:
                        tray.notify("程序已在运行。")
                except Exception:
                    pass

    threading.Thread(target=_control_server, daemon=True).start()

    try:
        # 仅启动 API 与 代理。打包后用自身exe作为子进程入口，通过 --role 分派
        is_frozen = bool(getattr(sys, "frozen", False))
        if is_frozen:
            exe_or_py = [sys.executable]
        else:
            # 开发环境用 python + 脚本路径
            script_path = os.path.abspath(__file__)
            exe_or_py = [sys.executable, script_path]

        services = {
            "API服务器": {
                "command": exe_or_py + ["--role", "api"],
                "check": lambda: check_port("localhost", 8080),
                "log_file": log_dir / "auth_api.log",
            },
            "代理服务器": {
                "command": exe_or_py
                + ["--role", "proxy", "--host", "0.0.0.0", "--port", "8888"],
                "check": lambda: (
                    check_port("127.0.0.1", 8888) or check_port(local_ip, 8888)
                ),
                "log_file": log_dir / "wifi_proxy.log",
            },
        }

        for name, config in services.items():
            print(f"🚀 启动 {name}...")
            process = subprocess.Popen(
                config["command"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                shell=config.get("shell", False),
                cwd=str(project_root),
                creationflags=CREATE_NO_WINDOW,
            )
            processes.append((name, process))

            stdout_thread = threading.Thread(
                target=stream_output, args=(process.stdout, config["log_file"])
            )
            stderr_thread = threading.Thread(
                target=stream_output, args=(process.stderr, config["log_file"])
            )
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            threads.extend([stdout_thread, stderr_thread])
            stdout_thread.start()
            stderr_thread.start()

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

            psutil = importlib.import_module("psutil")
            all_ips = []
            for if_name, addrs in psutil.net_if_addrs().items():
                if _looks_like_vpn_or_virtual(if_name):
                    continue
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith("127.") and not ip.startswith("169.254."):
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

        # 主线程等待托盘退出事件；若托盘不可用，则保持运行
        if tray is not None:
            while not exit_event.is_set():
                time.sleep(0.2)
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
    if platform.system() == "Windows":
        try:
            ctypes.windll.user32.MessageBoxW(
                0, str(exc), "WiFi认证启动失败", 0x00000010
            )
        except OSError:
            pass


if __name__ == "__main__":
    sys.excepthook = _excepthook
    main()
