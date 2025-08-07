#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi二次认证代理服务器
实现流量拦截、认证检查和页面跳转功能
"""

import http.server
import socketserver
import urllib.parse
import urllib.request
import select
import json
import sqlite3
import logging
import argparse
import sys
import os
import socket
from datetime import datetime, timedelta
from pathlib import Path

# 设置日志
def setup_logging():
    """配置日志记录"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'wifi_proxy.log')
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 如果没有处理器，则添加
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

setup_logging()
logger = logging.getLogger(__name__)

import queue
import threading

# 全局数据库连接池
class DatabaseConnectionPool:
    def __init__(self, db_path, max_connections=10):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool = queue.Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        
        # 初始化连接池
        for _ in range(max_connections):
            try:
                conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                conn.execute('PRAGMA journal_mode=WAL;')
                self._pool.put(conn)
            except Exception as e:
                logger.error(f"创建数据库连接失败: {e}")

    def get_conn(self):
        """从池中获取一个连接"""
        return self._pool.get()

    def return_conn(self, conn):
        """将连接返回到池中"""
        self._pool.put(conn)

# 创建全局连接池实例
db_pool = DatabaseConnectionPool(str(Path(__file__).parent.parent.parent / "wifi_auth.db"))

class WiFiAuthProxy(http.server.BaseHTTPRequestHandler):
    """WiFi认证代理处理器"""
    
    # 数据库路径 (现在由连接池管理)
    # db_path = 'wifi_auth.db'
    
    # IP-MAC映射缓存 (保留)
    _ip_mac_cache = {}
    
    # 白名单域名 - 只放行本地服务
    WHITELIST_DOMAINS = {
        'localhost', '127.0.0.1', '::1',
    }
    
    # 白名单端口 - 这些端口直接放行
    WHITELIST_PORTS = {5173, 8080}  # 前端端口和API端口
    
    # 认证相关的路径
    AUTH_PATHS = {'/api/auth', '/api/health', '/api/admin'}
    
    def __init__(self, *args, **kwargs):
        # self.db_path = Path(__file__).parent.parent.parent / "wifi_auth.db"
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """自定义日志格式 - 只记录重要信息"""
        # 减少日志输出，只记录错误和重要事件
        pass
    
    def do_GET(self):
        """处理GET请求"""
        self._handle_http_request()

    def do_POST(self):
        """处理POST请求"""
        self._handle_http_request()
        
    def do_OPTIONS(self):
        """处理OPTIONS请求 (CORS预检)"""
        self._handle_http_request()

    def _handle_http_request(self):
        """
        统一处理所有HTTP请求 (GET, POST, OPTIONS)。
        这是强制门户的核心：所有未认证的HTTP请求都将被重定向到认证页面。
        """
        client_ip = self.client_address[0]
        host = self.headers.get('Host', '')
        
        # 优先处理对认证系统自身（前端/API）的请求
        if self._is_whitelisted(host):
            self._proxy_request()
            return

        # 检查认证状态
        if self._is_authenticated(client_ip):
            self._proxy_request()
        else:
            # 对于未认证的OPTIONS请求（CORS预检），总是允许通过，否则登录请求会被浏览器阻止
            if self.command == 'OPTIONS':
                self._proxy_request()
                return

            # 其他所有未认证GET请求，一律重定向
            if self.command == 'GET':
                logger.info(f"[{client_ip}] 未认证的 {self.command} 请求: {host}{self.path}，强制重定向")
                self._redirect_to_auth()
            else:
                # 对于未认证的POST等其他请求，直接拒绝
                logger.warning(f"[{client_ip}] 拦截到未认证的 {self.command} 请求: {host}{self.path}")
                self.send_error(403, "Forbidden")
            
    def do_CONNECT(self):
        """
        处理HTTPS连接请求。
        对于未认证用户，直接拒绝连接，依赖HTTP的重定向来触发认证。
        """
        client_ip = self.client_address[0]
        host, port_str = self.path.split(':', 1)

        # 优先处理对认证系统自身（前端/API）的请求
        if self._is_whitelisted(host):
            self._tunnel_https()
            return
            
        if self._is_authenticated(client_ip):
            logger.info(f"[{client_ip}] 已认证的HTTPS请求，建立隧道: {host}:{port_str}")
            self._tunnel_https()
        else:
            logger.info(f"[{client_ip}] 未认证的HTTPS请求，拒绝连接: {host}:{port_str}")
            self.send_error(503, "Service Unavailable") # 返回一个明确的错误
            
    def _is_whitelisted(self, host):
        """检查是否是白名单域名或认证服务器IP"""
        if not host:
            return False
        
        # 分离主机名和端口
        hostname = host.split(':')[0].lower()
        
        # 检查是否是认证服务器的IP或localhost
        auth_server_ip = get_local_ip()
        if hostname in ('localhost', '127.0.0.1', '::1', auth_server_ip):
            return True
            
        # 检查是否是白名单中的其他域名
        if hostname in self.WHITELIST_DOMAINS:
            return True
            
        return False
    
    def _is_auth_request(self, path):
        """检查是否是认证相关请求"""
        # 使用更精确的匹配来避免误判
        return path.startswith(('/api/auth', '/api/health', '/api/admin'))
    
    def _is_authenticated(self, client_ip: str) -> bool:
        """
        检查设备是否已认证。
        """
        conn = None
        try:
            conn = db_pool.get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT expires_at
                FROM device_sessions 
                WHERE ip_address = ? AND is_active = 1
            """, (client_ip,))
            result = cursor.fetchone()

            if not result:
                return False

            expires_at_str = result[0]
            expires_time = datetime.fromisoformat(expires_at_str)

            if datetime.now() > expires_time:
                self._deactivate_session(client_ip, conn)
                return False
            
            self._update_activity(client_ip, conn)
            return True

        except Exception as e:
            logger.error(f"检查认证状态失败: {e}")
            return False
        finally:
            if conn:
                db_pool.return_conn(conn)

    def _update_activity(self, client_ip: str, conn):
        """更新设备的最后活动时间"""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE device_sessions 
                SET last_activity = ? 
                WHERE ip_address = ? AND is_active = 1
            """, (datetime.now().isoformat(), client_ip))
            conn.commit()
        except Exception as e:
            logger.error(f"更新活动时间失败: {e}")

    def _deactivate_session(self, client_ip: str, conn):
        """使用传入的数据库连接停用会话"""
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE device_sessions SET is_active = 0 WHERE ip_address = ?", (client_ip,))
            cursor.execute("UPDATE devices SET is_authenticated = 0 WHERE ip_address = ?", (client_ip,))
            conn.commit()
            logger.info(f"[{client_ip}] 会话已停用")
        except Exception as e:
            logger.error(f"停用会话失败: {e}")
    

    
    def _redirect_to_auth(self):
        """重定向到认证页面"""
        # 使用统一的IP检测逻辑
        local_ip = get_local_ip()
        
        # 直接重定向到React认证页面
        auth_url = f"http://{local_ip}:5173?client_ip={self.client_address[0]}"
        
        self.send_response(302)
        self.send_header('Location', auth_url)
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
    
    def _proxy_request(self):
        """
        使用底层Socket转发HTTP请求，确保请求的原始性。
        """
        try:
            # 解析目标主机和端口
            host = self.headers.get('Host', '')
            if not host:
                self.send_error(400, "Bad Request: Missing Host header")
                return

            port = 80 # 默认为80端口
            if ':' in host:
                host, port_str = host.split(':', 1)
                port = int(port_str)

            # 建立到目标服务器的连接
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10)
            target_socket.connect((host, port))

            # 构造并发送原始请求
            request_line = f"{self.command} {self.path} {self.protocol_version}\r\n"
            headers_str = "".join([f"{key}: {value}\r\n" for key, value in self.headers.items()])
            raw_request = request_line.encode('utf-8') + headers_str.encode('utf-8') + b"\r\n"
            
            target_socket.sendall(raw_request)

            # 转发请求体 (适用于POST等)
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                target_socket.sendall(body)

            # 直接转发来自目标服务器的响应
            self.connection.settimeout(10)
            self._forward_socket_data(target_socket, self.connection)

        except Exception as e:
            logger.error(f"HTTP代理请求失败: {e}")
            try:
                self.send_error(502, "Proxy Error")
            except:
                pass
        finally:
            if 'target_socket' in locals():
                target_socket.close()

    def _tunnel_https(self):
        """
        使用底层Socket和select模型建立高效的HTTPS隧道。
        """
        try:
            host, port_str = self.path.split(':', 1)
            port = int(port_str)
            
            # 建立到目标服务器的连接
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10)
            target_socket.connect((host, port))

            # 向客户端发送连接成功响应
            self.send_response(200, 'Connection Established')
            self.end_headers()

            # 开始双向转发数据
            self.connection.settimeout(10)
            target_socket.settimeout(10)
            self._forward_socket_data(self.connection, target_socket)

        except Exception as e:
            if "timed out" not in str(e).lower(): # 忽略超时日志
                logger.error(f"HTTPS隧道错误: {e}")
            try:
                self.send_error(502, "Tunnel Error")
            except:
                pass
        finally:
            if 'target_socket' in locals():
                target_socket.close()
                
    def _forward_socket_data(self, src, dst):
        """
        使用select模型在两个socket之间高效、双向地转发数据。
        """
        sockets = [src, dst]
        while True:
            readable, _, exceptional = select.select(sockets, [], sockets, 5)
            
            if exceptional:
                break # 出现异常，中断连接
            
            if not readable:
                continue # 没有可读数据，继续等待
            
            for sock in readable:
                try:
                    data = sock.recv(8192)
                    if not data: # 对端关闭连接
                        return
                    
                    if sock is src:
                        dst.sendall(data)
                    else:
                        src.sendall(data)
                except Exception:
                    return # 发生错误，中断转发

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """多线程HTTP服务器"""
    daemon_threads = True
    allow_reuse_address = True

def get_local_ip():
    """获取本机在局域网中的IP地址，优先选择私有IP段"""
    try:
        import psutil
        # 遍历所有网络接口
        for interface, addrs in psutil.net_if_addrs().items():
            # 优先处理 'wlan', 'wi-fi', 'ethernet'
            if 'wlan' in interface.lower() or 'wi-fi' in interface.lower() or 'ethernet' in interface.lower():
                for addr in addrs:
                    # 筛选出IPv4地址
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # 检查是否是常见的局域网IP地址
                        if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31):
                            logger.info(f"通过psutil在接口 '{interface}' 找到局域网IP: {ip}")
                            return ip
        
        # 如果以上方法找不到，使用socket连接外部地址的方法作为备用
        logger.warning("未能通过psutil找到合适的局域网IP，尝试使用socket方法")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            logger.info(f"通过socket连接找到IP: {ip}")
            return ip
            
    except Exception as e:
        logger.error(f"获取IP地址时发生错误: {e}. 回退到默认IP。")
        # 最终的备用方案
        return "192.168.1.101" # 最后的备用IP

def main():
    parser = argparse.ArgumentParser(description='WiFi认证代理服务器')
    parser.add_argument('--port', type=int, default=8888, help='代理服务器端口')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    args = parser.parse_args()
    
    # 获取本机IP地址
    local_ip = get_local_ip()
    
    try:
        # 创建服务器
        server = ThreadedHTTPServer((args.host, args.port), WiFiAuthProxy)
        
        print("=" * 60)
        print("WiFi认证代理服务器启动成功")
        print("=" * 60)
        print(f"监听地址: {args.host}:{args.port}")
        print(f"本机IP地址: {local_ip}")
        print("")
        print("手机代理设置指南：")
        print("=" * 60)
        print("1. 打开手机WiFi设置")
        print("2. 找到当前连接的WiFi网络")
        print("3. 点击「配置代理」或「代理设置」")
        print("4. 选择「手动」配置")
        print("5. 填入以下信息：")
        print(f"   - 服务器/主机名: {local_ip}")
        print(f"   - 端口: {args.port}")
        print("   - 协议: HTTP")
        print("6. 保存设置")
        print("")
        print("测试方法：")
        print("- 手机浏览器访问任意网站")
        print("- 应该会自动跳转到认证页面")
        print("- 使用 addyya/sf123123 完成认证")
        print("")
        print("请确保以下服务正在运行：")
        print("   - API服务器 (端口8080)")
        print("   - 前端页面 (端口5173)")
        print("")
        print("按 Ctrl+C 停止代理服务")
        print("=" * 60)
        
        # 启动服务器
        server.serve_forever()
        
    except KeyboardInterrupt:
        logger.info("\n代理服务器已停止")
    except Exception as e:
        logger.error(f"代理服务器错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()