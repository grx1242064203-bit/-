"""
飞书事件回调服务 — 接收用户安装/打开应用事件,触发 onboarding。

部署:
- 生产:云函数(阿里云/腾讯云)或服务器上的 Flask/FastAPI
- MVP:本地 Flask + ngrok 内网穿透

飞书事件订阅配置:
- 请求地址: https://your-domain.com/feishu/callback
- 订阅事件: app_open, app_install

安全加固:
- 请求体大小限制 1MB,防止恶意大包耗尽内存
-  malformed JSON 返回 400,不崩溃
- GET /health 健康检查端点,供监控探活
"""
import json
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from onboarding import handle_feishu_callback
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 请求体大小上限:1MB(飞书事件回调体通常 < 10KB)
MAX_BODY_SIZE = 1 * 1024 * 1024

# 服务启动时间,用于健康检查
_SERVICE_START_TIME = time.time()


def _verify_feishu_token(body: dict) -> bool:
    """校验飞书回调的 verification_token。
    若配置了 FEISHU_VERIFICATION_TOKEN,则请求体中的 token 必须匹配。
    兼容 v1(body.token) 和 v2(body.header.token) 结构。
    未配置时跳过校验(MVP 兼容),生产环境强烈建议配置。
    """
    expected = settings.FEISHU_VERIFICATION_TOKEN
    if not expected:
        return True
    token = body.get("token") or body.get("header", {}).get("token", "")
    return token == expected


class CallbackHandler(BaseHTTPRequestHandler):
    # 超时设置,防止慢连接占用资源
    timeout = 10

    def do_GET(self):
        """健康检查端点"""
        if self.path == "/health" or self.path == "/healthz":
            uptime = int(time.time() - _SERVICE_START_TIME)
            body = json.dumps({
                "status": "ok",
                "uptime_seconds": uptime,
                "service": "job-callback",
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/feishu/callback":
            self.send_response(404)
            self.end_headers()
            return

        # 1. 限制请求体大小
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._send_error(400, "invalid Content-Length")
            return

        if length <= 0:
            self._send_error(400, "empty body")
            return
        if length > MAX_BODY_SIZE:
            self._send_error(413, "body too large")
            return

        # 2. 解析 JSON(容错)
        try:
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"回调 JSON 解析失败: {e}")
            self._send_error(400, "invalid JSON")
            return

        # 2.5 校验飞书 verification_token(防伪造回调)
        if not _verify_feishu_token(body):
            logger.warning("回调 verification_token 校验失败,拒绝处理")
            self._send_error(403, "invalid token")
            return

        # 3. 处理回调
        try:
            result = handle_feishu_callback(body)
            resp_body = json.dumps(result, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp_body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(resp_body.encode("utf-8"))
        except Exception:
            logger.exception("回调处理失败")
            self._send_error(500, "internal error")

    def _send_error(self, code: int, msg: str):
        body = json.dumps({"code": -1, "msg": msg})
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        logger.info(format % args)


def run(host="0.0.0.0", port=8080):
    server = HTTPServer((host, port), CallbackHandler)
    logger.info(f"回调服务启动: http://{host}:{port}/feishu/callback")
    logger.info(f"健康检查: http://{host}:{port}/health")
    server.serve_forever()


if __name__ == "__main__":
    run()
