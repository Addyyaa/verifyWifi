import React from 'react';
import SimpleNotification from '../components/SimpleNotification';
import './VerifyWifiPage.css';

// 定义认证状态常量和类型
const AuthStatus = {
  IDLE: 'idle',
  LOADING: 'loading',
  SUCCESS: 'success',
  ERROR: 'error'
} as const;
type AuthStatus = typeof AuthStatus[keyof typeof AuthStatus];

// 定义表单数据接口
interface FormData {
  username: string;
  password: string;
}

// 定义错误信息接口
interface ErrorMessages {
  username?: string;
  password?: string;
  general?: string;
}

// 定义通知状态接口
interface NotificationState {
  message: string;
  type: 'success' | 'error' | 'info';
  key: number; // 使用key来触发重新渲染
}

const VerifyWifiPage: React.FC = () => {
  // 状态管理
  const [formData, setFormData] = React.useState<FormData>({
    username: '',
    password: ''
  });
  
  const [authStatus, setAuthStatus] = React.useState<AuthStatus>(AuthStatus.IDLE);
  const [errors, setErrors] = React.useState<ErrorMessages>({});
  const [showPassword, setShowPassword] = React.useState<boolean>(false);
  const [clientIP, setClientIP] = React.useState<string>('');
  const [notification, setNotification] = React.useState<NotificationState | null>(null);

  // 显示通知的函数
  const notify = (message: string, type: 'success' | 'error' | 'info') => {
    setNotification({ message, type, key: Date.now() });
  };

  // 获取URL参数中的客户端IP
  React.useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const ip = urlParams.get('client_ip');
    if (ip) {
      setClientIP(ip);
    }
  }, []);

  // 清除错误信息
  const clearErrors = React.useCallback(() => {
    setErrors({});
  }, []);

  // 表单验证
  const validateForm = React.useCallback((): boolean => {
    const newErrors: ErrorMessages = {};

    if (!formData.username.trim()) {
      newErrors.username = '请输入用户名';
    }

    if (!formData.password) {
      newErrors.password = '请输入密码';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData]);

  // 处理输入变化
  const handleInputChange = React.useCallback((field: keyof FormData) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = event.target.value;
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
    
    if (errors[field]) {
      setErrors(prev => ({
        ...prev,
        [field]: undefined
      }));
    }
  }, [errors]);

  // 切换密码显示状态
  const togglePasswordVisibility = React.useCallback(() => {
    setShowPassword(prev => !prev);
  }, []);

  // 处理表单提交
  const handleSubmit = React.useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (!validateForm()) {
      return;
    }

    setAuthStatus(AuthStatus.LOADING);
    clearErrors();

    try {
      const currentHost = window.location.hostname;
      const apiUrl = `http://${currentHost}:8080/api/auth/login`;
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: formData.username,
          password: formData.password
        })
      });

      const result = await response.json();

      if (result.success) {
        setAuthStatus(AuthStatus.SUCCESS);
        notify('认证成功！现在可以自由上网了。', 'success');
        
        if (result.data?.session_token) {
          localStorage.setItem('auth_token', result.data.session_token);
        }
        
        setTimeout(() => {
          if (clientIP) {
            window.close();
          } else {
            window.location.href = '/';
          }
        }, 3000);
      } else {
        setAuthStatus(AuthStatus.ERROR);
        const errorMessage = result.error || '认证失败，请重试';
        notify(errorMessage, 'error');
        setErrors({ general: errorMessage });
      }
    } catch (error) {
      setAuthStatus(AuthStatus.ERROR);
      console.error('认证请求失败:', error);
      
      let errorMessage = '网络连接失败，请检查网络设置后重试';
      if (error instanceof TypeError && error.message.includes('fetch')) {
        errorMessage = '无法连接到认证服务器，请检查网络连接';
      }
      notify(errorMessage, 'error');
      setErrors({ general: errorMessage });
    }
  }, [formData, validateForm, clearErrors, clientIP]);

  // 重置表单
  const handleReset = React.useCallback(() => {
    setFormData({ username: '', password: '' });
    setAuthStatus(AuthStatus.IDLE);
    setErrors({});
    setShowPassword(false);
  }, []);

  // 处理登出
  const handleLogout = React.useCallback(async () => {
    try {
      const currentHost = window.location.hostname;
      const apiUrl = `http://${currentHost}:8080/api/auth/logout`;
      await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_ip: clientIP })
      });
      
      notify('您已成功注销', 'info');
      handleReset();
      setTimeout(() => window.location.reload(), 1500);
      
    } catch (error) {
      console.error('登出失败:', error);
      notify('登出时发生错误，请刷新页面重试', 'error');
    }
  }, [clientIP, handleReset]);
  
  // 键盘快捷键支持
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleReset();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleReset]);

  return (
    <div className="verify-wifi-container">
      {notification && (
        <SimpleNotification
          key={notification.key}
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
        />
      )}
      <div className="verify-wifi-card">
        {/* 页面标题 */}
        <div className="header-section">
          <div className="wifi-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="48" height="48">
              <path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.07 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/>
            </svg>
          </div>
          <h1 className="page-title">WiFi 网络认证</h1>
          <p className="page-description">
            请输入您的认证凭据以连接到网络
          </p>
          {clientIP && (
            <p className="client-info">
              客户端IP: <code>{clientIP}</code>
            </p>
          )}
        </div>
        {/* 认证表单 */}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {/* 用户名输入框 */}
          <div className="input-group">
            <label htmlFor="username" className="input-label">
              用户名
            </label>
            <div className="input-wrapper">
              <input
                id="username"
                type="text"
                className={`form-input ${errors.username ? 'error' : ''}`}
                value={formData.username}
                onChange={handleInputChange('username')}
                placeholder="请输入用户名"
                disabled={authStatus === AuthStatus.LOADING}
                autoComplete="username"
                aria-describedby={errors.username ? "username-error" : undefined}
                aria-invalid={!!errors.username}
              />
              <div className="input-icon user-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </svg>
              </div>
            </div>
            {errors.username && (
              <p id="username-error" className="error-message" role="alert">
                {errors.username}
              </p>
            )}
          </div>

          {/* 密码输入框 */}
          <div className="input-group">
            <label htmlFor="password" className="input-label">
              密码
            </label>
            <div className="input-wrapper">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                className={`form-input ${errors.password ? 'error' : ''}`}
                value={formData.password}
                onChange={handleInputChange('password')}
                placeholder="请输入密码"
                disabled={authStatus === AuthStatus.LOADING}
                autoComplete="current-password"
                aria-describedby={errors.password ? "password-error" : undefined}
                aria-invalid={!!errors.password}
              />
              <div className="input-icon lock-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                </svg>
              </div>
              <button
                type="button"
                className="toggle-password-btn"
                onClick={togglePasswordVisibility}
                aria-label={showPassword ? "隐藏密码" : "显示密码"}
                disabled={authStatus === AuthStatus.LOADING}
              >
                <svg viewBox="0 0 24 24" width="20" height="20">
                  {showPassword ? (
                    <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  ) : (
                    <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                  )}
                </svg>
              </button>
            </div>
            {errors.password && (
              <p id="password-error" className="error-message" role="alert">
                {errors.password}
              </p>
            )}
          </div>

          {/* 通用错误信息 */}
          {errors.general && (
            <div className="general-error" role="alert">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
              </svg>
              <span>{errors.general}</span>
            </div>
          )}

          {/* 提交按钮 */}
          <div className="button-group">
            <button
              type="submit"
              className={`submit-btn ${authStatus}`}
              disabled={authStatus === AuthStatus.LOADING}
              aria-describedby="submit-status"
            >
              <span className="btn-content">
                {authStatus === AuthStatus.LOADING && (
                  <div className="loading-spinner" aria-hidden="true"></div>
                )}
                <span className="btn-text">
                  {authStatus === AuthStatus.LOADING ? '认证中...' : 
                   authStatus === AuthStatus.SUCCESS ? '认证成功' : '连接网络'}
                </span>
              </span>
            </button>
            
            {authStatus !== AuthStatus.LOADING && (
              <button
                type="button"
                className="reset-btn"
                onClick={handleReset}
                aria-label="重置表单"
              >
                重置
              </button>
            )}
          </div>
        </form>

        {/* 状态信息 */}
        {authStatus === AuthStatus.SUCCESS ? (
          <div className="success-message" role="status" aria-live="polite">
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
            </svg>
            <span>认证成功！您现在可以正常上网了。</span>
            <button onClick={handleLogout} className="logout-btn">
              注销并重新认证
            </button>
          </div>
        ) : null}

        {/* 帮助信息 */}
        <div className="help-section">
          <p className="help-text">
            遇到问题？请联系网络管理员获取帮助
          </p>
          <p className="keyboard-hint">
            提示：按 ESC 键可重置表单
          </p>
        </div>
      </div>
    </div>
  );
};

export default VerifyWifiPage;
