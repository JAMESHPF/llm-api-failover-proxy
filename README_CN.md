# Claude Code 故障转移代理

轻量级、零依赖的 LLM API HTTP 代理，支持自动故障转移、并发请求处理和运维监控。

[English Documentation](README.md)

## 功能特性

- **并发请求处理**：ThreadingHTTPServer 并行处理多个流式请求，不再互相阻塞
- **自动故障转移**：当一个 API 端点失败时，无缝切换到其他端点
- **智能错误分类**：5xx/连接错误触发断路器；401/403/429 重试下一个端点；400/404/422 直接转发给客户端
- **健康检查与状态端点**：`/_proxy/health` 和 `/_proxy/status` 用于监控和告警
- **请求追踪**：每条日志带唯一请求 ID，端到端问题追踪
- **热重载**：`SIGHUP` 重载配置无需重启；`SIGTERM` 优雅关机
- **流式响应**：SSE 流式传输，chunked 编码实时输出 LLM 响应
- **断路器保护**：连续失败后自动跳过故障端点，支持配置阈值和冷却时间
- **模型名称映射**：透明地为使用不同命名规则的 API 映射模型名称
- **多协议认证**：同时支持 Anthropic（`x-api-key`）和 OpenAI（`Authorization: Bearer`）认证方式
- **端点级超时**：为慢速或快速端点单独设置超时时间
- **配置验证**：`--validate` 模式检查配置是否正确，无需启动服务
- **环境变量覆盖**：`PROXY_*` 环境变量覆盖配置文件中的值
- **零依赖**：仅使用 Python 标准库
- **请求体大小限制**：超大请求返回 HTTP 413（默认 50MB）

## 使用场景

- 使用多个第三方 LLM API 提供商（如 Claude API 中转服务）
- 需要在某个提供商出现故障时自动切换
- 在 VPS 上运行 Claude Code，需要并发处理流式请求
- 不同提供商使用不同的模型命名规则
- 希望通过健康检查和端点统计获得运维可见性

## 系统要求

- Python 3.7+
- Linux/macOS（信号处理需要 Unix；Windows 可用但不支持 SIGHUP）

## 快速开始

1. **克隆仓库**
   ```bash
   git clone https://github.com/JAMESHPF/claude-code-failover-proxy.git
   cd claude-code-failover-proxy
   ```

2. **创建配置文件**
   ```bash
   cp config.example.json ~/.llm-proxy-config.json
   vim ~/.llm-proxy-config.json
   ```

3. **创建环境变量文件**
   ```bash
   cp .env.example ~/.llm-proxy.env
   vim ~/.llm-proxy.env
   chmod 600 ~/.llm-proxy.env
   ```

4. **验证并启动**
   ```bash
   # 先验证配置
   python3 llm-api-proxy.py --validate -c ~/.llm-proxy-config.json

   # 启动代理
   python3 llm-api-proxy.py
   ```

5. **确认运行正常**
   ```bash
   curl http://127.0.0.1:5000/_proxy/health
   # {"status": "ok", "version": "3.0.0", "uptime_seconds": 5}
   ```

6. **安装为 systemd 服务**（可选）
   ```bash
   sudo cp llm-api-proxy.service /etc/systemd/system/
   sudo vim /etc/systemd/system/llm-api-proxy.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now llm-api-proxy
   ```

## 命令行选项

```
用法: llm-api-proxy.py [-h] [-c CONFIG] [-p PORT] [--host HOST] [-e ENV]
                       [--log-level {DEBUG,INFO,WARNING,ERROR}]
                       [--validate] [-v] [--init]

选项:
  -c, --config CONFIG   配置文件路径
  -p, --port PORT       覆盖代理端口
  --host HOST           覆盖代理主机
  -e, --env ENV         .env 文件路径
  --log-level LEVEL     设置日志级别 (DEBUG, INFO, WARNING, ERROR)
  --validate            验证配置后退出（退出码 0 = 有效）
  -v, --version         显示版本
  --init                在当前目录创建默认配置
```

## 配置说明

### 配置文件 (`~/.llm-proxy-config.json`)

```json
{
  "proxy": {
    "host": "127.0.0.1",
    "port": 5000,
    "timeout": 15,
    "circuit_breaker_threshold": 3,
    "circuit_breaker_cooldown": 60,
    "max_body_size": 52428800
  },
  "endpoints": [
    {
      "name": "主要 API",
      "base_url": "https://api.example.com",
      "api_key_env": "PRIMARY_API_KEY",
      "timeout": 10
    },
    {
      "name": "备用 API（较慢）",
      "base_url": "https://backup-api.example.com",
      "api_key_env": "BACKUP_API_KEY",
      "timeout": 30,
      "model_mapping": {
        "claude-opus-4-6": "claude-opus-4-6-thinking"
      }
    },
    {
      "name": "OpenAI 兼容 API",
      "base_url": "https://api.openai.com",
      "api_key_env": "OPENAI_API_KEY",
      "auth_type": "openai"
    }
  ]
}
```

### 代理设置

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `host` | `127.0.0.1` | 绑定地址 |
| `port` | `5000` | 绑定端口 |
| `timeout` | `15` | 全局请求超时（秒） |
| `circuit_breaker_threshold` | `3` | 跳过端点前的失败次数 |
| `circuit_breaker_cooldown` | `60` | 重试被跳过端点前的等待秒数 |
| `max_body_size` | `52428800` | 请求体最大字节数（50MB） |

### 端点设置

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 日志中显示的名称 |
| `base_url` | 是 | 上游 API 地址 |
| `api_key_env` | 否* | 包含 API 密钥的环境变量名 |
| `api_key` | 否* | 内联 API 密钥（不推荐） |
| `auth_type` | 否 | `"anthropic"`（默认）或 `"openai"` |
| `model_mapping` | 否 | 模型名称转换映射 |
| `timeout` | 否 | 端点级超时（覆盖全局超时） |

*`api_key_env` 和 `api_key` 至少提供一个。

### 环境变量覆盖

环境变量覆盖配置文件的值（优先级：CLI > 环境变量 > 配置文件）：

| 环境变量 | 覆盖配置 |
|----------|----------|
| `PROXY_TIMEOUT` | `proxy.timeout` |
| `PROXY_CB_THRESHOLD` | `proxy.circuit_breaker_threshold` |
| `PROXY_CB_COOLDOWN` | `proxy.circuit_breaker_cooldown` |
| `PROXY_MAX_BODY_SIZE` | `proxy.max_body_size` |
| `PROXY_LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |

### 环境变量文件 (`~/.llm-proxy.env`)

```bash
PRIMARY_API_KEY=sk-your-primary-key
BACKUP_API_KEY=sk-your-backup-key
OPENAI_API_KEY=sk-your-openai-key
```

支持带引号的值：`KEY="value"` 和 `KEY='value'` 会自动去除引号。

## 管理端点

### `GET /_proxy/health`

返回代理健康状态。用于运行监控和负载均衡器健康检查。

```bash
curl http://127.0.0.1:5000/_proxy/health
```
```json
{"status": "ok", "version": "3.0.0", "uptime_seconds": 12345}
```

### `GET /_proxy/status`

返回每个端点的详细运行统计。

```bash
curl -s http://127.0.0.1:5000/_proxy/status | python3 -m json.tool
```
```json
{
  "uptime_seconds": 12345,
  "total_requests": 567,
  "endpoints": [
    {
      "name": "主要 API",
      "circuit_state": "closed",
      "failures": 0,
      "stats": {
        "success": 500,
        "fail_5xx": 2,
        "fail_4xx": 0,
        "fail_conn": 5
      },
      "last_success": "2026-03-03T10:00:00",
      "last_failure": "2026-03-03T09:55:00"
    }
  ]
}
```

## 错误分类

代理对上游 HTTP 错误进行分类，采取不同处理策略：

| 状态码 | 处理方式 | 触发断路器 |
|--------|----------|------------|
| 5xx | 重试下一个端点 | 是 |
| 连接错误 / 超时 | 重试下一个端点 | 是 |
| 401, 403, 429 | 重试下一个端点 | 否（客户端/认证问题） |
| 400, 404, 422 | 直接转发给客户端 | 否 |

## 信号处理

| 信号 | 动作 |
|------|------|
| `SIGHUP` | 重载配置（验证通过后才应用） |
| `SIGTERM` | 优雅关机（等待进行中的请求完成） |
| `SIGINT` / `Ctrl-C` | 立即退出 |

```bash
# 编辑配置后重载
kill -HUP $(pgrep -f llm-api-proxy)

# 优雅关机
kill $(pgrep -f llm-api-proxy)
```

systemd 服务：
```bash
sudo systemctl reload llm-api-proxy   # SIGHUP
sudo systemctl stop llm-api-proxy     # SIGTERM
```

## 模型名称映射

某些 API 提供商使用不同的模型命名规则。代理可以自动映射模型名称：

```json
{
  "name": "自定义 API",
  "base_url": "https://custom-api.com",
  "api_key_env": "CUSTOM_API_KEY",
  "model_mapping": {
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-sonnet-4-6": "claude-sonnet-4-6-thinking"
  }
}
```

当客户端请求 `claude-opus-4-6` 时，代理会自动向该端点发送 `claude-opus-4-6-thinking`。

### 认证方式

| `auth_type` | 发送的请求头 | 默认 |
|-------------|-------------|------|
| `"anthropic"` | `x-api-key` + `anthropic-version` | 是 |
| `"openai"` | `Authorization: Bearer <key>` | 否 |

## 与 Claude Code 配合使用

配置 Claude Code 使用代理：

```json
// ~/.claude/settings.json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:5000",
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED"
  }
}
```

## 验证

```bash
# 健康检查
curl http://127.0.0.1:5000/_proxy/health

# 运行状态
curl http://127.0.0.1:5000/_proxy/status

# 测试 POST 请求
curl -X POST http://127.0.0.1:5000/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"claude-opus-4-6","max_tokens":20,"messages":[{"role":"user","content":"test"}]}'

# 测试 GET 请求
curl http://127.0.0.1:5000/v1/models
```

## 日志格式

每个请求分配唯一的 8 位 ID，方便追踪：

```
[a1b2c3d4] POST /v1/messages → Primary API | 200 | 3.21s | streaming | attempts=1
```

所有端点失败时，输出详细摘要：

```
[a1b2c3d4] All endpoints exhausted (3 attempted):
  1. Primary API: connection timeout
  2. Backup API: circuit breaker open
  3. OpenAI: HTTP 429
```

通过 CLI（`--log-level DEBUG`）或环境变量（`PROXY_LOG_LEVEL=DEBUG`）设置日志级别。

## 故障排查

**端口已被占用**
- 修改配置中的 `port` 或使用 `-p` 参数

**所有端点都失败**
- 查看 `/_proxy/status` 了解各端点错误计数
- 检查 `.env` 文件中的 API 密钥
- 验证端点 URL 是否正确

**服务无法启动**
- 验证配置：`python3 llm-api-proxy.py --validate -c config.json`
- 查看日志：`journalctl -u llm-api-proxy -n 50`

**配置更改未生效**
- 发送 SIGHUP：`sudo systemctl reload llm-api-proxy`
- 检查日志中是否有 "Config reloaded via SIGHUP" 或重载错误

## 安全说明

- API 密钥存储在权限为 600 的环境变量文件中
- 配置文件与代码分离（便于版本控制而不包含密钥）
- 代理仅绑定到 127.0.0.1（不可从网络访问）
- 请求体大小限制防止内存耗尽（默认 50MB）
- 永远不要将 `.llm-proxy.env` 或 `.llm-proxy-config.json` 提交到版本控制

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎贡献！请随时提交 Pull Request。
