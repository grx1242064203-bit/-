"""
飞书事件回调服务 — 接收用户安装/打开应用事件,触发 onboarding。

部署:
- 生产:云函数(阿里云/腾讯云)或服务器上的 Flask/FastAPI
- MVP:本地 Flask + ngrok 内网穿透

飞书事件订阅配置:
- 请求地址: https://your-domain.com/feishu/callback
- 订阅事件: app_open, app_install
"""
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

from onboarding import handle_feishu_callback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/feishu/callback":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))

        try:
            result = handle_feishu_callback(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            logger.exception("回调处理失败")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"code":-1,"msg":"error"}')

    def log_message(self, format, *args):
        logger.info(format % args)


def run(host="0.0.0.0", port=8080):
    server = HTTPServer((host, port), CallbackHandler)
    logger.info(f"回调服务启动: http://{host}:{port}/feishu/callback")
    server.serve_forever()


if __name__ == "__main__":
    run()
