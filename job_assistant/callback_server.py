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
import os
import time

# 加载 .env 文件(与 main.py 保持一致,不依赖 python-dotenv)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from onboarding import handle_feishu_callback
from models import UserStore, UserProfile
from wxpusher_client import WxPusherClient
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 请求体大小上限:1MB(飞书事件回调体通常 < 10KB)
MAX_BODY_SIZE = 1 * 1024 * 1024

# 服务启动时间,用于健康检查
_SERVICE_START_TIME = time.time()

# 自助配置页面 HTML
_ONBOARDING_HTML_PATH = os.path.join(os.path.dirname(__file__), "onboarding_page.html")


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
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # 健康检查
        if path == "/health" or path == "/healthz":
            uptime = int(time.time() - _SERVICE_START_TIME)
            body = json.dumps({
                "status": "ok",
                "uptime_seconds": uptime,
                "service": "job-callback",
            })
            self._send_json(200, body)
            return

        # 客户自助配置页面
        if path == "/onboarding":
            try:
                with open(_ONBOARDING_HTML_PATH, "r", encoding="utf-8") as f:
                    html = f.read()
                self._send_html(200, html)
            except FileNotFoundError:
                self._send_error(404, "onboarding page not found")
            return

        # 获取用户已有画像（回显到表单）
        if path == "/api/profile":
            user_id = (params.get("user_id") or [""])[0]
            if not user_id:
                self._send_error(400, "missing user_id")
                return
            store = UserStore()
            user = store.get(user_id)
            if not user:
                self._send_error(404, "user not found")
                return
            from dataclasses import asdict
            resp = {
                "code": 0,
                "profile": asdict(user.profile),
                "wxpusher_bound": bool(user.wxpusher_uid),
            }
            self._send_json(200, json.dumps(resp, ensure_ascii=False))
            return

        # 获取 WxPusher 关注二维码
        if path == "/api/wxpusher-qrcode":
            client = WxPusherClient()
            url = client.get_qrcode()
            self._send_json(200, json.dumps({"url": url}))
            return

        self._send_error(404, "not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 飞书事件回调
        if path == "/feishu/callback":
            self._handle_feishu_callback()
            return

        # 保存用户画像
        if path == "/api/profile":
            self._handle_save_profile()
            return

        # 绑定 WxPusher
        if path == "/api/bind-wxpusher":
            self._handle_bind_wxpusher()
            return

        self._send_error(404, "not found")

    def _handle_feishu_callback(self):
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
            self._send_json(200, resp_body)
        except Exception:
            logger.exception("回调处理失败")
            self._send_error(500, "internal error")

    def _handle_save_profile(self):
        """保存用户画像（客户自助配置）"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_error(400, "invalid JSON")
            return

        user_id = data.get("user_id", "")
        profile_data = data.get("profile", {})
        if not user_id:
            self._send_error(400, "missing user_id")
            return

        store = UserStore()
        user = store.get(user_id)
        if not user:
            self._send_error(404, "user not found")
            return

        # 更新画像字段（只更新传入的字段）
        allowed_fields = {"major", "degree", "experience_years", "core_skills",
                          "direction_keywords", "target_companies", "target_industries",
                          "target_cities", "target_certificates", "school", "current_role"}
        for key in allowed_fields:
            if key in profile_data:
                setattr(user.profile, key, profile_data[key])

        store.upsert(user)
        logger.info(f"用户 {user_id} 画像已更新")
        self._send_json(200, json.dumps({"code": 0, "msg": "ok"}, ensure_ascii=False))

    def _handle_bind_wxpusher(self):
        """绑定 WxPusher UID，并发送测试消息"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_error(400, "invalid JSON")
            return

        user_id = data.get("user_id", "")
        uid = data.get("wxpusher_uid", "")
        if not user_id or not uid:
            self._send_error(400, "missing user_id or wxpusher_uid")
            return

        store = UserStore()
        user = store.get(user_id)
        if not user:
            self._send_error(404, "user not found")
            return

        user.wxpusher_uid = uid
        store.upsert(user)

        # 发送测试消息
        client = WxPusherClient()
        sent = client.send(
            uid,
            "## 招聘情报助手\n\n✅ 微信推送绑定成功！\n\n明天早上 9:00 起，您将收到每日岗位日报推送。",
            content_type=3,
        )
        logger.info(f"用户 {user_id} WxPusher 绑定完成, 测试消息发送={'成功' if sent else '失败'}")

        self._send_json(200, json.dumps({
            "code": 0,
            "msg": "ok",
            "test_sent": sent,
        }, ensure_ascii=False))

    def _send_json(self, code: int, body: str):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, code: int, html: str):
        data = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
    logger.info(f"客户配置页: http://{host}:{port}/onboarding")
    server.serve_forever()


if __name__ == "__main__":
    run()
