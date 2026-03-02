# Claude Code Failover Proxy

A lightweight, zero-dependency HTTP proxy for LLM API services with automatic failover, concurrent request handling, and operational monitoring.

[中文文档](README_CN.md)

## Features

- **Concurrent Request Handling**: ThreadingHTTPServer processes multiple streaming requests in parallel
- **Automatic Failover**: Seamlessly switches between multiple API endpoints when one fails
- **Smart Error Classification**: 5xx/connection errors trip circuit breaker; 401/403/429 retry next; 400/404/422 forward directly
- **Health & Status Endpoints**: `/_proxy/health` and `/_proxy/status` for monitoring and alerting
- **Request Tracing**: Unique request ID in every log line for end-to-end debugging
- **Hot Reload**: `SIGHUP` to reload config without restarting; `SIGTERM` for graceful shutdown
- **Streaming Support**: SSE streaming with chunked transfer encoding for real-time LLM output
- **Circuit Breaker**: Skips failing endpoints after consecutive failures, with configurable threshold and cooldown
- **Model Name Mapping**: Transparently maps model names for APIs with different naming conventions
- **Multi-Protocol Auth**: Supports both Anthropic (`x-api-key`) and OpenAI (`Authorization: Bearer`) styles
- **Per-Endpoint Timeout**: Override global timeout for slow or fast endpoints
- **Config Validation**: `--validate` mode to check config without starting the server
- **Environment Overrides**: `PROXY_*` env vars override config file values
- **Zero Dependencies**: Uses only Python standard library
- **Request Size Limit**: Rejects oversized requests with HTTP 413 (default 50MB)

## Use Cases

- Using multiple third-party LLM API providers (e.g., Claude API resellers)
- Need automatic failover when one provider experiences outages
- Running Claude Code on a VPS with concurrent streaming requests
- Different providers use different model naming conventions
- Want operational visibility with health checks and per-endpoint stats

## Requirements

- Python 3.7+
- Linux/macOS (signal handling requires Unix; Windows supported without SIGHUP)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/JAMESHPF/claude-code-failover-proxy.git
   cd claude-code-failover-proxy
   ```

2. **Create configuration file**
   ```bash
   cp config.example.json ~/.llm-proxy-config.json
   vim ~/.llm-proxy-config.json
   ```

3. **Create environment file**
   ```bash
   cp .env.example ~/.llm-proxy.env
   vim ~/.llm-proxy.env
   chmod 600 ~/.llm-proxy.env
   ```

4. **Validate and start**
   ```bash
   # Validate config first
   python3 llm-api-proxy.py --validate -c ~/.llm-proxy-config.json

   # Start the proxy
   python3 llm-api-proxy.py
   ```

5. **Verify it's running**
   ```bash
   curl http://127.0.0.1:5000/_proxy/health
   # {"status": "ok", "version": "3.0.0", "uptime_seconds": 5}
   ```

6. **Install as systemd service** (optional)
   ```bash
   sudo cp llm-api-proxy.service /etc/systemd/system/
   sudo vim /etc/systemd/system/llm-api-proxy.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now llm-api-proxy
   ```

## CLI Options

```
usage: llm-api-proxy.py [-h] [-c CONFIG] [-p PORT] [--host HOST] [-e ENV]
                        [--log-level {DEBUG,INFO,WARNING,ERROR}]
                        [--validate] [-v] [--init]

options:
  -c, --config CONFIG   Path to configuration file
  -p, --port PORT       Override proxy port
  --host HOST           Override proxy host
  -e, --env ENV         Path to .env file
  --log-level LEVEL     Set log level (DEBUG, INFO, WARNING, ERROR)
  --validate            Validate config and exit (exit 0 = valid)
  -v, --version         Show version
  --init                Create default config in current directory
```

## Configuration

### Config File (`~/.llm-proxy-config.json`)

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
      "name": "Primary API",
      "base_url": "https://api.example.com",
      "api_key_env": "PRIMARY_API_KEY",
      "timeout": 10
    },
    {
      "name": "Backup API (slower)",
      "base_url": "https://backup-api.example.com",
      "api_key_env": "BACKUP_API_KEY",
      "timeout": 30,
      "model_mapping": {
        "claude-opus-4-6": "claude-opus-4-6-thinking"
      }
    },
    {
      "name": "OpenAI Compatible",
      "base_url": "https://api.openai.com",
      "api_key_env": "OPENAI_API_KEY",
      "auth_type": "openai"
    }
  ]
}
```

### Proxy Settings

| Field | Default | Description |
|-------|---------|-------------|
| `host` | `127.0.0.1` | Bind address |
| `port` | `5000` | Bind port |
| `timeout` | `15` | Global request timeout (seconds) |
| `circuit_breaker_threshold` | `3` | Failures before skipping endpoint |
| `circuit_breaker_cooldown` | `60` | Seconds before retrying skipped endpoint |
| `max_body_size` | `52428800` | Max request body size in bytes (50MB) |

### Endpoint Settings

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name for logs |
| `base_url` | Yes | Upstream API base URL |
| `api_key_env` | No* | Environment variable name containing API key |
| `api_key` | No* | Inline API key (not recommended) |
| `auth_type` | No | `"anthropic"` (default) or `"openai"` |
| `model_mapping` | No | Model name translation map |
| `timeout` | No | Per-endpoint timeout (overrides global) |

*One of `api_key_env` or `api_key` should be provided.

### Environment Variable Overrides

Environment variables override config file values (priority: CLI > env var > config):

| Env Var | Overrides |
|---------|-----------|
| `PROXY_TIMEOUT` | `proxy.timeout` |
| `PROXY_CB_THRESHOLD` | `proxy.circuit_breaker_threshold` |
| `PROXY_CB_COOLDOWN` | `proxy.circuit_breaker_cooldown` |
| `PROXY_MAX_BODY_SIZE` | `proxy.max_body_size` |
| `PROXY_LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) |

### Environment File (`~/.llm-proxy.env`)

```bash
PRIMARY_API_KEY=sk-your-primary-key
BACKUP_API_KEY=sk-your-backup-key
OPENAI_API_KEY=sk-your-openai-key
```

Quoted values are supported: `KEY="value"` and `KEY='value'` are automatically unquoted.

## Management Endpoints

### `GET /_proxy/health`

Returns proxy health status. Use for uptime monitoring and load balancer health checks.

```bash
curl http://127.0.0.1:5000/_proxy/health
```
```json
{"status": "ok", "version": "3.0.0", "uptime_seconds": 12345}
```

### `GET /_proxy/status`

Returns detailed operational statistics per endpoint.

```bash
curl -s http://127.0.0.1:5000/_proxy/status | python3 -m json.tool
```
```json
{
  "uptime_seconds": 12345,
  "total_requests": 567,
  "endpoints": [
    {
      "name": "Primary API",
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

## Error Classification

The proxy classifies upstream HTTP errors and handles them differently:

| Status Code | Action | Trips Circuit Breaker |
|-------------|--------|-----------------------|
| 5xx | Retry next endpoint | Yes |
| Connection error / timeout | Retry next endpoint | Yes |
| 401, 403, 429 | Retry next endpoint | No (client/auth issue) |
| 400, 404, 422 | Forward to client immediately | No |

## Signal Handling

| Signal | Action |
|--------|--------|
| `SIGHUP` | Reload config from disk (validates before applying) |
| `SIGTERM` | Graceful shutdown (waits for in-flight requests) |
| `SIGINT` / `Ctrl-C` | Immediate shutdown |

```bash
# Reload config after editing
kill -HUP $(pgrep -f llm-api-proxy)

# Graceful shutdown
kill $(pgrep -f llm-api-proxy)
```

For systemd services:
```bash
sudo systemctl reload llm-api-proxy   # SIGHUP
sudo systemctl stop llm-api-proxy     # SIGTERM
```

## Model Name Mapping

Some API providers use different model naming conventions. The proxy can automatically map model names:

```json
{
  "name": "Custom API",
  "base_url": "https://custom-api.com",
  "api_key_env": "CUSTOM_API_KEY",
  "model_mapping": {
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-sonnet-4-6": "claude-sonnet-4-6-thinking"
  }
}
```

When your client requests `claude-opus-4-6`, the proxy automatically sends `claude-opus-4-6-thinking` to this endpoint.

### Authentication Types

| `auth_type` | Header Sent | Default |
|-------------|-------------|---------|
| `"anthropic"` | `x-api-key` + `anthropic-version` | Yes |
| `"openai"` | `Authorization: Bearer <key>` | No |

## Using with Claude Code

Configure Claude Code to use the proxy:

```json
// ~/.claude/settings.json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:5000",
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED"
  }
}
```

## Verification

```bash
# Health check
curl http://127.0.0.1:5000/_proxy/health

# Operational status
curl http://127.0.0.1:5000/_proxy/status

# Test POST request
curl -X POST http://127.0.0.1:5000/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"claude-opus-4-6","max_tokens":20,"messages":[{"role":"user","content":"test"}]}'

# Test GET request
curl http://127.0.0.1:5000/v1/models
```

## Log Format

Each request gets a unique 8-character ID for tracing:

```
[a1b2c3d4] POST /v1/messages → Primary API | 200 | 3.21s | streaming | attempts=1
```

When all endpoints fail, a detailed summary is logged:

```
[a1b2c3d4] All endpoints exhausted (3 attempted):
  1. Primary API: connection timeout
  2. Backup API: circuit breaker open
  3. OpenAI: HTTP 429
```

Set log level via CLI (`--log-level DEBUG`) or env var (`PROXY_LOG_LEVEL=DEBUG`).

## Troubleshooting

**Port already in use**
- Change the `port` in config or use `-p` flag

**All endpoints fail**
- Check `/_proxy/status` for per-endpoint error counts
- Check API keys in `.env` file
- Verify endpoint URLs are correct

**Service won't start**
- Validate config: `python3 llm-api-proxy.py --validate -c config.json`
- Check logs: `journalctl -u llm-api-proxy -n 50`

**Config changes not taking effect**
- Send SIGHUP: `sudo systemctl reload llm-api-proxy`
- Check logs for "Config reloaded via SIGHUP" or reload errors

## Security Notes

- API keys are stored in environment file with 600 permissions
- Config file is separate from code (easier to version control without secrets)
- Proxy binds to 127.0.0.1 only (not accessible from network)
- Request body size limited to prevent memory exhaustion (default 50MB)
- Never commit `.llm-proxy.env` or `.llm-proxy-config.json` to version control

## License

MIT License - see [LICENSE](LICENSE) file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
