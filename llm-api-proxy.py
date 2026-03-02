#!/usr/bin/env python3
"""
LLM API Failover Proxy
轻量级 API 故障转移代理，支持多个端点自动切换
支持配置文件、环境变量和模型名称映射
"""

import json
import logging
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import socket

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_FILE = os.path.expanduser("~/.llm-proxy-config.json")

# 默认配置
DEFAULT_CONFIG = {
    "proxy": {
        "host": "127.0.0.1",
        "port": 5000,
        "timeout": 15
    },
    "endpoints": [
        {
            "name": "Codesome AI",
            "base_url": "https://cc.codesome.ai",
            "api_key_env": "CODESOME_API_KEY"
        },
        {
            "name": "SSS AI Code",
            "base_url": "https://node-hk.sssaicode.com/api",
            "api_key_env": "SSSAI_API_KEY"
        }
    ]
}


def validate_config(config):
    """验证配置文件的完整性和正确性"""
    errors = []
    warnings = []
    
    # 检查必需的顶层字段
    if "proxy" not in config:
        errors.append("缺少 'proxy' 配置节")
    else:
        proxy = config["proxy"]
        # 检查 proxy 配置的字段类型
        if "host" in proxy and not isinstance(proxy["host"], str):
            errors.append("proxy.host 必须是字符串")
        if "port" in proxy and not isinstance(proxy["port"], int):
            errors.append("proxy.port 必须是整数")
        if "timeout" in proxy and not isinstance(proxy["timeout"], (int, float)):
            errors.append("proxy.timeout 必须是数字")
    
    if "endpoints" not in config:
        errors.append("缺少 'endpoints' 配置节")
    elif not isinstance(config["endpoints"], list):
        errors.append("'endpoints' 必须是数组")
    elif len(config["endpoints"]) == 0:
        warnings.append("'endpoints' 数组为空，代理将无法工作")
    else:
        # 检查每个端点的必需字段
        for i, endpoint in enumerate(config["endpoints"]):
            endpoint_id = f"端点 #{i+1}"
            
            # 检查必需字段
            if "name" not in endpoint:
                errors.append(f"{endpoint_id}: 缺少 'name' 字段")
            elif not isinstance(endpoint["name"], str):
                errors.append(f"{endpoint_id}: 'name' 必须是字符串")
            else:
                endpoint_id = f"端点 '{endpoint['name']}'"
            
            if "base_url" not in endpoint:
                errors.append(f"{endpoint_id}: 缺少 'base_url' 字段")
            elif not isinstance(endpoint["base_url"], str):
                errors.append(f"{endpoint_id}: 'base_url' 必须是字符串")
            else:
                # 验证 URL 格式
                url = endpoint["base_url"]
                if not url.startswith("http://") and not url.startswith("https://"):
                    errors.append(f"{endpoint_id}: 'base_url' 必须以 http:// 或 https:// 开头")
                if url.endswith("/"):
                    warnings.append(f"{endpoint_id}: 'base_url' 不应以 / 结尾（将自动处理）")
            
            # 检查 API Key 配置
            if "api_key" not in endpoint and "api_key_env" not in endpoint:
                errors.append(f"{endpoint_id}: 必须配置 'api_key' 或 'api_key_env' 之一")
            
            if "api_key" in endpoint and not isinstance(endpoint["api_key"], str):
                errors.append(f"{endpoint_id}: 'api_key' 必须是字符串")
            
            if "api_key_env" in endpoint and not isinstance(endpoint["api_key_env"], str):
                errors.append(f"{endpoint_id}: 'api_key_env' 必须是字符串")
            
            # 检查 model_mapping（可选）
            if "model_mapping" in endpoint:
                if not isinstance(endpoint["model_mapping"], dict):
                    errors.append(f"{endpoint_id}: 'model_mapping' 必须是对象")
                else:
                    for key, value in endpoint["model_mapping"].items():
                        if not isinstance(key, str) or not isinstance(value, str):
                            errors.append(f"{endpoint_id}: 'model_mapping' 的键和值必须都是字符串")
                            break
    
    # 输出验证结果
    if errors:
        logger.error("❌ 配置验证失败:")
        for error in errors:
            logger.error(f"  - {error}")
        if warnings:
            logger.warning("⚠️  配置警告:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        logger.error("\n请修复配置文件后重试")
        sys.exit(1)
    
    if warnings:
        logger.warning("⚠️  配置警告:")
        for warning in warnings:
            logger.warning(f"  - {warning}")
    
    logger.info("✓ 配置验证通过")
    return True


def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"配置文件不存在: {CONFIG_FILE}")
        logger.info("使用默认配置")
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"✓ 配置文件加载成功: {CONFIG_FILE}")
        return config
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件 JSON 格式错误: {str(e)}")
        logger.error(f"   位置: 第 {e.lineno} 行, 第 {e.colno} 列")
        logger.error("\n提示: 可以使用以下命令验证 JSON 格式:")
        logger.error(f"   python3 -m json.tool {CONFIG_FILE}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"配置文件加载失败: {str(e)}")
        logger.info("使用默认配置")
        return DEFAULT_CONFIG


def resolve_api_key(endpoint):
    """解析 API Key（支持环境变量和直接配置）"""
    # 优先使用环境变量
    if "api_key_env" in endpoint:
        env_var = endpoint["api_key_env"]
        api_key = os.environ.get(env_var)
        if api_key:
            return api_key
        logger.warning(f"环境变量 {env_var} 未设置")

    # 回退到直接配置的 api_key
    if "api_key" in endpoint:
        return endpoint["api_key"]

    logger.error(f"端点 {endpoint.get('name', 'unknown')} 没有配置 API Key")
    return None


def apply_model_mapping(endpoint, body_data):
    """应用模型名称映射"""
    if "model_mapping" not in endpoint:
        return body_data
    
    model_mapping = endpoint["model_mapping"]
    if "model" in body_data and body_data["model"] in model_mapping:
        original_model = body_data["model"]
        mapped_model = model_mapping[original_model]
        body_data["model"] = mapped_model
        logger.info(f"  模型映射: {original_model} → {mapped_model}")
    
    return body_data


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP 代理请求处理器"""

    def log_message(self, format, *args):
        """重写日志方法，使用标准 logger"""
        logger.info(f"{self.address_string()} - {format % args}")

    def do_POST(self):
        """处理 POST 请求"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            # 获取配置
            config = load_config()
            endpoints = config.get("endpoints", [])
            timeout = config.get("proxy", {}).get("timeout", 15)

            # 尝试每个 API 端点
            for endpoint in endpoints:
                api_key = resolve_api_key(endpoint)
                if not api_key:
                    continue

                try:
                    response_data, status_code, headers = self._forward_request(
                        endpoint, api_key, body, timeout
                    )

                    # 成功，返回响应
                    self._send_response(response_data, status_code, headers)
                    logger.info(f"✓ 请求成功: {endpoint['name']}")
                    return

                except Exception as e:
                    logger.warning(f"✗ {endpoint['name']} 失败: {str(e)}")
                    continue

            # 所有端点都失败
            error_msg = json.dumps({
                "error": {
                    "message": "所有 API 端点均不可用",
                    "type": "service_unavailable"
                }
            }).encode('utf-8')

            self._send_response(error_msg, 503, {'Content-Type': 'application/json'})
            logger.error("所有 API 端点均不可用")

        except Exception as e:
            logger.error(f"请求处理失败: {str(e)}")
            self.send_error(500, f"Internal Server Error: {str(e)}")

    def _forward_request(self, endpoint, api_key, body, timeout):
        """转发请求到指定端点"""
        # 解析请求体并应用模型映射
        try:
            body_data = json.loads(body)
            body_data = apply_model_mapping(endpoint, body_data)
            body = json.dumps(body_data).encode('utf-8')
        except json.JSONDecodeError:
            # 如果不是 JSON，保持原样
            pass

        # 构造目标 URL
        target_url = f"{endpoint['base_url']}{self.path}"

        # 构造请求头
        headers = {
            'Content-Type': self.headers.get('Content-Type', 'application/json'),
            'x-api-key': api_key,
            'anthropic-version': self.headers.get('anthropic-version', '2023-06-01'),
            'User-Agent': 'LLM-API-Failover-Proxy/2.1'
        }

        # 创建请求
        req = Request(target_url, data=body, headers=headers, method='POST')

        # 发送请求
        with urlopen(req, timeout=timeout) as response:
            response_data = response.read()
            status_code = response.status
            response_headers = dict(response.headers)

            return response_data, status_code, response_headers

    def _send_response(self, data, status_code, headers):
        """发送响应"""
        self.send_response(status_code)

        # 设置响应头
        for key, value in headers.items():
            if key.lower() not in ['connection', 'transfer-encoding']:
                self.send_header(key, value)

        self.end_headers()
        self.wfile.write(data)


def create_default_config():
    """创建默认配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ 默认配置文件已创建: {CONFIG_FILE}")
        logger.info("请编辑配置文件并设置环境变量")
    except Exception as e:
        logger.error(f"创建配置文件失败: {str(e)}")


def main():
    """启动代理服务器"""
    # 如果配置文件不存在，创建默认配置
    if not os.path.exists(CONFIG_FILE):
        create_default_config()

    # 加载配置
    config = load_config()
    
    # 验证配置
    validate_config(config)
    
    proxy_config = config.get("proxy", {})
    host = proxy_config.get("host", "127.0.0.1")
    port = proxy_config.get("port", 5000)

    server_address = (host, port)

    try:
        httpd = HTTPServer(server_address, ProxyHandler)
        logger.info(f"🚀 代理服务器启动: http://{host}:{port}")
        logger.info(f"📋 配置了 {len(config.get('endpoints', []))} 个 API 端点")

        for i, endpoint in enumerate(config.get('endpoints', []), 1):
            api_key = resolve_api_key(endpoint)
            status = "✓" if api_key else "✗"
            model_mapping_info = ""
            if "model_mapping" in endpoint:
                mappings = endpoint["model_mapping"]
                model_mapping_info = f" (模型映射: {len(mappings)} 个)"
            logger.info(f"  {i}. {status} {endpoint['name']} - {endpoint['base_url']}{model_mapping_info}")

        httpd.serve_forever()

    except KeyboardInterrupt:
        logger.info("\n⏹️  收到停止信号，关闭服务器...")
        httpd.shutdown()
        sys.exit(0)

    except socket.error as e:
        if e.errno == 48:  # Address already in use
            logger.error(f"❌ 端口 {port} 已被占用")
        else:
            logger.error(f"❌ Socket 错误: {str(e)}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"❌ 启动失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
