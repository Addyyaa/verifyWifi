# WiFi 二次认证系统（后端纯 HTML 认证页）

一个轻量的 WiFi 二次认证系统：显式 HTTP 代理 + Python 后端。未认证时拦截 HTTP 流量并引导至后端输出的纯 HTML 认证/成功页面（兼容 iOS/Android 迷你浏览器）。

## ✨ 功能
- 未认证 HTTP：返回 302 或 511，跳转/提示认证
- 未认证 HTTPS：拒绝 CONNECT 隧道（技术限制，无法 302）
- 认证页/成功页：后端直接返回纯 HTML（响应式、无 JS 依赖）
- 认证管理：基于设备 IP 的会话（SQLite + WAL）
- 日志：写入 `logs/` 目录
## 🚀 快速开始

### 系统要求

- Python 3.8+

### 一键启动（推荐）

```bash
# 安装Python依赖
python -m pip install -r requirements.txt

# 启动（无前端模式）
python 简单启动.py --no-frontend
```

系统启动后：
- 🔌 API: http://<你的局域网IP>:8080
- 📡 代理: <你的局域网IP>:8888
- 📝 认证页（后端 HTML）：http://<你的局域网IP>:8080/api/auth/fallback

### 手动启动（开发模式）

#### 1. 安装依赖


### 客户端配置

将需要认证的设备的网络代理设置为：
- **代理服务器**: 你的局域网IP
- **端口**: 8888
- **协议**: HTTP（系统代理应同时作用于 HTTPS；建议关闭浏览器 QUIC/HTTP3）

## 🔐 默认凭据

默认的认证凭据：
- **用户名**: `addyya`
- **密码**: `sf123123`

## 🔄 工作流程

1. **设备连接**: 用户设备连接到WiFi网络
2. **代理拦截**: 设备访问网络时被代理服务器拦截
3. **认证检查**: 系统检查设备是否已通过认证
4. **跳转认证**: 未认证设备被重定向到认证页面（HTTP）；HTTPS 未认证时连接将被拒绝
5. **用户认证**: 用户输入凭据进行身份验证
6. **会话创建**: 认证成功后创建会话令牌
7. **网络访问**: 已认证设备可正常访问网络
8. **会话管理**: 系统管理会话有效期和设备状态

## 📁 项目结构（精简后）

```
├── src/
│   └── pyserver/
│       ├── wifi_proxy.py      # 显式 HTTP 代理
│       └── auth_api.py        # 认证 API（纯 HTML 认证/成功页）
├── 简单启动.py                 # 一键启动
├── wifi_auth.db               # SQLite（首次运行自动初始化）
├── requirements.txt           # Python 依赖
└── README.md
```

## 🎯 重要说明
- 显式代理无法对“未经过代理的直连 HTTPS”做重定向，只能拒绝连接。若需强制，需在网关/防火墙层阻断直连 443，或使用 PAC/WPAD/透明网关。

## 🎯 核心功能

### 用户界面
- 现代化的认证表单设计
- 实时表单验证和错误提示
- 密码显示/隐藏切换功能
- 加载状态和成功状态反馈

### 交互体验
- 支持键盘导航（Tab键切换，ESC键重置）
- 响应式设计，适配移动端
- 平滑的动画过渡效果
- 无障碍性标签和提示

### 技术特性
- TypeScript类型安全
- 函数式组件和Hooks
- CSS变量支持主题切换
- 遵循现代前端开发规范

## 🛠 技术栈

- **前端框架**: React 19 + TypeScript
- **构建工具**: Vite 7
- **样式方案**: CSS3 + CSS变量
- **代码规范**: ESLint + TypeScript ESLint
- **字体**: Inter (Google Fonts)
- **后端**: Python + mitmproxy

## 🔧 配置说明

### 修改认证凭据

在 `src/pages/VerifyWifiPage.tsx` 文件中找到以下代码：

```typescript
const VALID_CREDENTIALS = {
  username: 'addyya',
  password: 'sf123123'
};
```

修改为您需要的用户名和密码。

### 自定义样式主题

在 `src/pages/VerifyWifiPage.css` 文件中的 `:root` 选择器内修改CSS变量：

```css
:root {
  --primary-color: #007bff;    /* 主色调 */
  --success-color: #28a745;    /* 成功色 */
  --error-color: #dc3545;      /* 错误色 */
  /* ... 更多变量 */
}
```

## 📱 响应式断点

- **桌面端**: > 480px
- **平板端**: 360px - 480px  
- **手机端**: < 360px

## ♿ 无障碍性

本项目遵循WCAG 2.1 AA无障碍性标准：

- 支持屏幕阅读器
- 键盘导航友好
- 色彩对比度符合标准
- 提供替代文本和标签
- 支持高对比度模式
- 支持减少动画模式

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情
