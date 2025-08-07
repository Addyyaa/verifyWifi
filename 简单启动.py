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
import webbrowser
import socket
import requests
from pathlib import Path
import ctypes
import platform
import threading

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
        "5173": "WiFi Auth Frontend (5173)"
    }
    success = True
    for port, name in rules.items():
        # 删除可能存在的旧规则以避免冲突
        subprocess.run(f'netsh advfirewall firewall delete rule name="{name}"', shell=True, capture_output=True)
        # 为Python.exe创建特定的规则，更安全
        command = (
            f'netsh advfirewall firewall add rule name="{name}" '
            f'dir=in action=allow protocol=TCP localport={port}'
        )
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, encoding='cp936', errors='ignore'
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

def main():
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
        # --- 1. 打包前端应用 ---
        print("🚀 正在打包前端应用 (npm run build)...")
        # 使用 shell=True 兼容Windows环境，并直接在控制台显示输出
        build_process = subprocess.Popen(
            ["npm", "run", "build"], cwd=project_root, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
            text=True, encoding='utf-8', errors='replace'
        )
        build_log_path = log_dir / "build.log"
        with open(build_log_path, 'w', encoding='utf-8') as f:
            for line in iter(build_process.stdout.readline, ''):
                print(line, end='') # 实时打印到控制台
                f.write(line) # 同时写入日志
        
        return_code = build_process.wait()
        if return_code != 0:
            raise Exception(f"前端打包失败 (npm run build)，请查看上面👆的错误日志以及 logs/build.log 文件。")
        print("✅ 前端应用打包完成！")

        # --- 2. 启动所有后台服务 ---
        serve_script = "serve.cmd" if platform.system() == "Windows" else "serve"
        serve_command = [str(project_root / "node_modules/.bin" / serve_script), "-s", "dist", "-l", "5173"]
        
        services = {
            "API服务器": {"command": [sys.executable, str(project_root / "src/pyserver/auth_api.py")], "check": lambda: check_port("localhost", 8080), "log_file": log_dir / "auth_api.log"},
            "代理服务器": {"command": [sys.executable, str(project_root / "src/pyserver/wifi_proxy.py"), "--port", "8888"], "check": lambda: check_port("localhost", 8888), "log_file": log_dir / "wifi_proxy.log"},
            "前端SPA服务器": {"command": serve_command, "check": lambda: check_port(local_ip, 5173), "log_file": log_dir / "frontend.log"}
        }

        for name, config in services.items():
            print(f"🚀 启动 {name}...")
            process = subprocess.Popen(config["command"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', env=env)
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
        print(f"  • 认证页面: http://{local_ip}:5173")
        print(f"  • API健康检查: http://{local_ip}:8080/api/health")
        print("\n📱 手机代理设置：")
        print(f"  • 代理服务器: {local_ip}")
        print("  • 端口: 8888")
        print("\n按 Ctrl+C 停止所有服务...")
        print("=" * 60)
        
        while True: time.sleep(1)
            
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
