#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi认证API服务器 - 提供RESTful API接口
支持认证验证、设备管理、会话控制等功能
"""

import json
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from typing import Dict, Optional, Tuple
import os
import sys

# 添加父目录到路径，以便导入DeviceManager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def setup_logging():
    """配置日志记录"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'auth_api.log')
    
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

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置
AUTH_CONFIG = {
    'valid_credentials': {
        'addyya': 'sf123123'
    },
    'session_duration': 3600,  # 会话持续时间（秒）
    'max_login_attempts': 5,   # 最大登录尝试次数
    'lockout_duration': 300    # 锁定时间（秒）
}

class AuthManager:
    """认证管理器"""
    
    def __init__(self, db_path: str = "wifi_auth.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        try:
            # 连接数据库并立即启用WAL模式
            conn = sqlite3.connect(self.db_path, timeout=10) # 增加超时时间
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            
            # 创建认证尝试表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    username TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT
                )
            ''')
            
            # 创建IP锁定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ip_lockouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    locked_until TIMESTAMP NOT NULL,
                    attempts_count INTEGER DEFAULT 0
                )
            ''')
            
            # 创建设备表 - 基于IP地址
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    user_agent TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_authenticated BOOLEAN DEFAULT 0,
                    auth_expires TIMESTAMP
                )
            ''')
            
            # 创建设备会话表 - 基于IP地址
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    last_activity TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("认证数据库初始化完成，已启用WAL模式")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            sys.exit(1)
    

    
    def is_ip_locked(self, ip_address: str) -> Tuple[bool, Optional[datetime]]:
        """检查IP是否被锁定"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT locked_until FROM ip_lockouts 
            WHERE ip_address = ? AND locked_until > CURRENT_TIMESTAMP
        ''', (ip_address,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            locked_until = datetime.fromisoformat(result[0])
            return True, locked_until
        
        return False, None
    
    def record_login_attempt(self, ip_address: str, username: str, 
                           success: bool, user_agent: str = None):
        """记录登录尝试"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 记录登录尝试
            cursor.execute('''
                INSERT INTO login_attempts 
                (ip_address, username, success, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (ip_address, username, success, user_agent))
            
            # 如果登录失败，检查是否需要锁定IP
            if not success:
                # 获取最近的失败尝试次数
                cursor.execute('''
                    SELECT COUNT(*) FROM login_attempts 
                    WHERE ip_address = ? AND success = FALSE 
                    AND timestamp > datetime('now', '-1 hour')
                ''', (ip_address,))
                
                fail_count = cursor.fetchone()[0]
                
                if fail_count >= AUTH_CONFIG['max_login_attempts']:
                    # 锁定IP
                    locked_until = datetime.now() + timedelta(
                        seconds=AUTH_CONFIG['lockout_duration']
                    )
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO ip_lockouts 
                        (ip_address, locked_until, attempts_count)
                        VALUES (?, ?, ?)
                    ''', (ip_address, locked_until, fail_count))
                    
                    logger.warning(f"IP地址被锁定: {ip_address}, 失败次数: {fail_count}")
            
            conn.commit()
            
        except sqlite3.Error as e:
            logger.error(f"记录登录尝试失败: {e}")
        finally:
            conn.close()
    
    def validate_credentials(self, username: str, password: str) -> bool:
        """验证用户凭据"""
        valid_creds = AUTH_CONFIG['valid_credentials']
        return username in valid_creds and valid_creds[username] == password
    
    def create_device_session(self, ip_address: str, session_token: str, user_agent: str = None):
        """创建设备会话"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 计算过期时间
            expires_at = datetime.now() + timedelta(seconds=AUTH_CONFIG['session_duration'])
            
            # 更新或插入设备信息
            cursor.execute("""
                INSERT OR REPLACE INTO devices 
                (ip_address, user_agent, first_seen, last_seen, is_authenticated, auth_expires)
                VALUES (?, ?, 
                    COALESCE((SELECT first_seen FROM devices WHERE ip_address = ?), ?),
                    ?, 1, ?)
            """, (ip_address, user_agent, ip_address, 
                  datetime.now().isoformat(), datetime.now().isoformat(), expires_at.isoformat()))
            
            # 停用该IP的旧会话
            cursor.execute("""
                UPDATE device_sessions 
                SET is_active = 0 
                WHERE ip_address = ?
            """, (ip_address,))
            
            # 创建新会话
            cursor.execute("""
                INSERT INTO device_sessions 
                (ip_address, session_token, expires_at, last_activity)
                VALUES (?, ?, ?, ?)
            """, (ip_address, session_token, expires_at.isoformat(), datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"设备会话已创建: IP={ip_address}, 过期时间={expires_at}")
            
        except Exception as e:
            logger.error(f"创建设备会话失败: {e}")
    
    def deactivate_device_session(self, ip_address: str):
        """停用设备会话"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 将对应IP的会话设置为不活跃
            cursor.execute("""
                UPDATE device_sessions 
                SET is_active = 0 
                WHERE ip_address = ?
            """, (ip_address,))
            
            # 同时更新devices表的状态
            cursor.execute("""
                UPDATE devices 
                SET is_authenticated = 0, auth_expires = NULL 
                WHERE ip_address = ?
            """, (ip_address,))
            
            conn.commit()
            conn.close()
            logger.info(f"设备会话已停用: IP={ip_address}")
            
        except Exception as e:
            logger.error(f"停用设备会话失败: {e}")

    def verify_device_session(self, session_token: str, ip_address: str) -> bool:
        """验证设备会话"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT expires_at FROM device_sessions
                WHERE session_token = ?
                  AND ip_address = ?
                  AND is_active = 1
                  AND expires_at > ?
            """, (session_token, ip_address, datetime.now().isoformat()))

            result = cursor.fetchone()

            if result:
                # 更新最后活动时间
                cursor.execute("""
                    UPDATE device_sessions
                    SET last_activity = ?
                    WHERE session_token = ?
                """, (datetime.now().isoformat(), session_token))
                conn.commit()
                conn.close()
                logger.info(f"会话验证成功: IP={ip_address}")
                return True

            conn.close()
            logger.warning(f"会话验证失败: IP={ip_address}, Token={session_token}")
            return False

        except Exception as e:
            logger.error(f"验证设备会话异常: {e}")
            return False
            
    def get_client_ip(self, request_obj) -> str:
        """获取客户端真实IP地址"""
        # 检查代理头
        if request_obj.headers.get('X-Forwarded-For'):
            return request_obj.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request_obj.headers.get('X-Real-IP'):
            return request_obj.headers.get('X-Real-IP')
        else:
            return request_obj.remote_addr

# 创建认证管理器实例
auth_manager = AuthManager()

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'WiFi认证API服务'
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录接口"""
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求数据格式错误'
            }), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        client_ip = auth_manager.get_client_ip(request)
        user_agent = request.headers.get('User-Agent', '')
        
        # 验证必填字段
        if not username or not password:
            return jsonify({
                'success': False,
                'error': '用户名和密码不能为空'
            }), 400
        
        # 检查IP是否被锁定
        is_locked, locked_until = auth_manager.is_ip_locked(client_ip)
        if is_locked:
            remaining_time = int((locked_until - datetime.now()).total_seconds())
            return jsonify({
                'success': False,
                'error': f'IP地址已被锁定，请在 {remaining_time} 秒后重试',
                'locked_until': locked_until.isoformat(),
                'remaining_seconds': remaining_time
            }), 429
        
        # 验证凭据
        is_valid = auth_manager.validate_credentials(username, password)
        
        # 记录登录尝试
        auth_manager.record_login_attempt(client_ip, username, is_valid, user_agent)
        
        if is_valid:
            # 生成会话令牌
            session_data = f"{client_ip}:{username}:{datetime.now().timestamp()}"
            session_token = hashlib.sha256(session_data.encode()).hexdigest()
            
            # 创建设备会话
            auth_manager.create_device_session(client_ip, session_token, user_agent)
            
            logger.info(f"用户登录成功: IP={client_ip}, 用户={username}")
            
            return jsonify({
                'success': True,
                'message': '认证成功',
                'data': {
                    'session_token': session_token,
                    'expires_in': AUTH_CONFIG['session_duration'],
                    'username': username,
                    'client_ip': client_ip
                }
            })
        else:
            logger.warning(f"用户登录失败: IP={client_ip}, 用户={username}")
            
            return jsonify({
                'success': False,
                'error': '用户名或密码错误'
            }), 401
    
    except Exception as e:
        logger.error(f"登录接口异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/auth/verify', methods=['POST'])
def verify_session():
    """验证会话接口"""
    try:
        data = request.get_json()
        session_token = data.get('session_token') if data else None
        client_ip = auth_manager.get_client_ip(request)
        
        if not session_token:
            return jsonify({
                'success': False,
                'error': '会话令牌不能为空'
            }), 400
        
        # 调用新的验证方法
        is_valid_session = auth_manager.verify_device_session(session_token, client_ip)
        
        if is_valid_session:
            return jsonify({
                'success': True,
                'message': '会话有效',
                'data': {
                    'client_ip': client_ip,
                    'session_valid': True
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': '会话无效或已过期'
            }), 401
    
    except Exception as e:
        logger.error(f"会话验证异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出接口"""
    try:
        data = request.get_json()
        client_ip = data.get('client_ip') if data else auth_manager.get_client_ip(request)
        
        if not client_ip:
            return jsonify({'success': False, 'error': '无法确定客户端IP'}), 400
        
        logger.info(f"[{client_ip}] 收到登出请求")
        
        # 停用设备会话
        auth_manager.deactivate_device_session(client_ip)
        

            
        return jsonify({
            'success': True,
            'message': '登出成功'
        })
    
    except Exception as e:
        logger.error(f"登出接口异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/admin/devices', methods=['GET'])
def get_devices():
    """获取设备列表（管理接口）"""
    try:
        conn = sqlite3.connect(auth_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ip_address, user_agent, first_seen, last_seen, 
                   is_authenticated, auth_expires
            FROM devices 
            ORDER BY last_seen DESC
            LIMIT 100
        ''')
        
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'devices': devices,
                'total': len(devices)
            }
        })
    
    except Exception as e:
        logger.error(f"获取设备列表异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/admin/logs', methods=['GET'])
def get_auth_logs():
    """获取认证日志（管理接口）"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        conn = sqlite3.connect(auth_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ip_address, username, success, timestamp, user_agent
            FROM login_attempts 
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'limit': limit,
                'offset': offset
            }
        })
    
    except Exception as e:
        logger.error(f"获取认证日志异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({
        'success': False,
        'error': '接口不存在'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500

if __name__ == '__main__':
    # 启动API服务器
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"WiFi认证API服务启动: 端口={port}, 调试模式={debug}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )