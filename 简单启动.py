#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi二次认证系统 - 最简启动脚本
一键启动，自动配置防火墙，并提供生产模式前端服务
"""

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

def is_admin():
    """检查当前脚本是否以管理员权限运行 (仅限Windows)"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def setup_firewall_rules():
    """自动配置Windows防火墙规则"""
    if platform.system() != "Windows":
        print("ℹ️  非Windows系统，跳过防火墙配置。")
        return True

    print("⚙️  正在配置Windows防火墙规则...")
    rules = {
        "8888": "WiFi Auth Proxy (8888)",
        "5173": "WiFi Auth Frontend (5173)",
        "8080": "WiFi Auth API (8080)",
        "80": "WiFi Captive HTTP (80)"
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

def get_local_ip():
    """获取本机在局域网中的IP地址"""
    try:
        import psutil
        for interface, addrs in psutil.net_if_addrs().items():
            if 'wlan' in interface.lower() or 'wi-fi' in interface.lower() or 'ethernet' in interface.lower():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31):
                            return ip
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1); s.connect(('8.8.8.8', 80)); return s.getsockname()[0]
    except Exception: return "192.168.1.101"

def check_port(host, port, timeout=5):
    """检查端口是否开放"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except: return False

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
    except Exception:
        pass # 进程终止时可能出现管道关闭错误，可以忽略

def ensure_node_dependencies(project_root: Path, log_dir: Path):
    """确保 node 依赖已安装（存在 vite 可执行文件）。若缺失则自动执行 npm ci。"""
    vite_script = "vite.cmd" if platform.system() == "Windows" else "vite"
    vite_bin = project_root / "node_modules/.bin" / vite_script
    if vite_bin.exists():
        return True
    print("📦 正在安装前端依赖 (npm ci)...")
    install_cmd = "npm ci"
    try:
        proc = subprocess.Popen(
            install_cmd,
            shell=True,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        npm_log_path = log_dir / "npm_install.log"
        with open(npm_log_path, 'w', encoding='utf-8') as f:
            for line in iter(proc.stdout.readline, ''):
                print(line, end='')
                f.write(line)
        code = proc.wait()
        if code != 0:
            print("❌ 前端依赖安装失败，请手动运行 npm ci 后重试。")
            return False
        print("✅ 前端依赖安装完成。")
        return True
    except Exception as e:
        print(f"❌ 无法自动安装前端依赖: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="WiFi二次认证系统一键启动")
    parser.add_argument("--skip-build", action="store_true", help="跳过前端打包步骤")
    parser.add_argument("--force-build", action="store_true", help="无论是否已有 dist 均强制打包")
    parser.add_argument("--python-serve", action="store_true", help="用Python内置HTTP服务静态dist而不是Node serve")
    parser.add_argument("--no-frontend", action="store_true", help="不启动前端服务并跳过前端构建/依赖")
    args = parser.parse_args()
    if platform.system() == "Windows" and not is_admin():
        print("ℹ️  需要管理员权限来配置防火墙，正在尝试提权...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
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
    
    processes = []
    threads = []
    local_ip = get_local_ip()
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "UTF-8"
    
    try:
        # --- 0. 无前端模式跳过依赖安装 ---
        if not args.no_frontend:
            if not ensure_node_dependencies(project_root, log_dir):
                raise Exception("自动安装前端依赖失败或未安装 Node/npm。请安装 Node.js 并执行 npm ci 后重试。")

        # --- 1. 打包前端应用（可跳过/强制） ---
        dist_dir = project_root / "dist"
        need_build = not args.no_frontend
        if need_build:
            if args.skip_build and dist_dir.exists():
                need_build = False
            elif dist_dir.exists() and not args.force_build:
                need_build = False

        if need_build:
            print("🚀 正在打包前端应用 (npm run build)...")
            build_process = subprocess.Popen(
                ["npm", "run", "build"], cwd=project_root, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding='utf-8', errors='replace'
            )
            build_log_path = log_dir / "build.log"
            with open(build_log_path, 'w', encoding='utf-8') as f:
                for line in iter(build_process.stdout.readline, ''):
                    print(line, end='')
                    f.write(line)
            return_code = build_process.wait()
            if return_code != 0:
                raise Exception(f"前端打包失败 (npm run build)，请查看上面👆的错误日志以及 logs/build.log 文件。")
            print("✅ 前端应用打包完成！")
        else:
            print("⚡ 跳过打包：使用现有 dist 目录。")

        # --- 2. 启动所有后台服务 ---
        if not args.no_frontend:
            # 使用 Vite Preview 提供生产静态资源服务，优先使用本地 vite 可执行文件
            vite_script = "vite.cmd" if platform.system() == "Windows" else "vite"
            vite_bin = project_root / "node_modules/.bin" / vite_script
            if vite_bin.exists():
                serve_command = [
                    str(vite_bin), "preview",
                    "--host", "0.0.0.0",
                    "--port", "5173",
                    "--strictPort"
                ]
                serve_shell = False
            else:
                # 回退到 npm 脚本（需要 npm 在 PATH 中）
                serve_command = "npm run preview -- --host 0.0.0.0 --port 5173 --strictPort"
                serve_shell = True
        
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

        # 无前端模式：不追加前端服务

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
                cwd=str(project_root)
            )
            processes.append((name, process))

            stdout_thread = threading.Thread(target=stream_output, args=(process.stdout, config["log_file"]))
            stderr_thread = threading.Thread(target=stream_output, args=(process.stderr, config["log_file"]))
            stdout_thread.daemon = True; stderr_thread.daemon = True
            threads.extend([stdout_thread, stderr_thread])
            stdout_thread.start(); stderr_thread.start()
            
            if not wait_for_service(name, config["check"], max_wait=60):
                raise Exception(f"{name}启动失败")

        print("\n" + "=" * 60)
        print("🎯 系统启动完成！")
        print("=" * 60)
        print("📋 访问地址：")
        if not args.no_frontend:
            print(f"  • 认证页面: http://{local_ip}:5173")
        else:
            print(f"  • 认证页面(后端HTML): http://{local_ip}:8080/api/auth/fallback")
        print(f"  • API健康检查: http://{local_ip}:8080/api/health")
        print("\n📱 手机代理设置：")
        print(f"  • 代理服务器: {local_ip}")
        print("  • 端口: 8888")
        print("\n按 Ctrl+C 停止所有服务...")
        print("=" * 60)
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n用户中断，开始关闭服务...")
    except Exception as e:
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
                except Exception as ex:
                    print(f"   ⚠️  强制停止 {name} 时出错: {ex}")
                    process.kill()
            print("✅ 所有服务已停止")
        
        # --- 关键改动：在脚本退出前暂停 ---
        print("\n" + "="*60)
        input("脚本执行结束。按任意键退出...")

if __name__ == "__main__":
    main()
