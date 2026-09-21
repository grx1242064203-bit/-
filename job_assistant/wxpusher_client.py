"""
WxPusher 微信推送客户端。

为什么选 WxPusher(对抗性审查后):
- 零资质、零审核,10 分钟接入
- 无推送频率限制(对比微信服务号每月 4 条模板消息)
- 用户扫码关注即可,无需关注公众号
- 支持 Markdown,可发摘要
- 风险:第三方服务,需做降级 — 推送失败不影响飞书数据写入
"""
import logging
from typing import List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

WXPUSHER_API = "https://wxpusher.zjiecode.com/api"


class WxPusherClient:
    """WxPusher 推送 — 用户扫码关注后获得 uid"""

    def __init__(self, app_token: str = None):
        self.app_token = app_token or settings.WXPUSHER_APP_TOKEN

    def get_qrcode(self) -> Optional[str]:
        """获取关注二维码 URL,用于引导用户扫码绑定"""
        if not self.app_token:
            return None
        try:
            resp = requests.post(
                f"{WXPUSHER_API}/fun/create/qrcode",
                json={"appToken": self.app_token, "extra": "bind"},
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                return data["data"]["url"]
            logger.warning(f"获取 WxPusher 二维码失败: {data}")
        except Exception as e:
            logger.error(f"WxPusher 二维码请求异常: {e}")
        return None

    def send(self, uid: str, content: str, content_type: int = 3,
             url: str = None) -> bool:
        """
        推送消息到用户微信。
        content_type: 1=文本 2=HTML 3=Markdown
        """
        if not self.app_token or not uid:
            logger.warning("WxPusher 未配置或 uid 为空,跳过推送")
            return False
        body = {
            "appToken": self.app_token,
            "content": content,
            "contentType": content_type,
            "uids": [uid],
        }
        if url:
            body["url"] = url
        try:
            resp = requests.post(f"{WXPUSHER_API}/send/message",
                                 json=body, timeout=15)
            data = resp.json()
            if data.get("success"):
                return True
            logger.warning(f"WxPusher 推送失败: {data}")
        except Exception as e:
            logger.error(f"WxPusher 推送异常: {e}")
        return False

    def send_daily_summary(self, uid: str, date_str: str, jobs: List[dict],
                           doc_url: str, closed_count: int = 0) -> bool:
        """推送每日摘要 — Markdown 格式"""
        if not jobs:
            content = f"## 金融招聘日报 {date_str}\n\n今日暂无新增岗位。\n\n[查看完整岗位库]({doc_url})"
            return self.send(uid, content, url=doc_url)

        priority = [j for j in jobs if j.get("综合推荐度") == "优先申请"]
        top3 = sorted(jobs, key=lambda x: x.get("相关性评分", 0), reverse=True)[:3]

        lines = [f"## 金融招聘日报 {date_str}\n"]
        lines.append(f"**今日新增 {len(jobs)} 条** | 优先申请 {len(priority)} 条"
                     + (f" | 已归档关闭 {closed_count} 条" if closed_count else ""))
        lines.append("")
        lines.append("### TOP 推荐")
        for i, j in enumerate(top3, 1):
            lines.append(
                f"{i}. **{j.get('公司','')} · {j.get('岗位标题','')}**\n"
                f"   - 地点: {j.get('地点','')} | 相关性: {j.get('相关性评分','?')} | 难度: {j.get('难度评分','?')}\n"
                f"   - {j.get('简评','')[:80]}"
            )
        lines.append("")
        lines.append(f"[点击查看完整日报]({doc_url})")
        content = "\n".join(lines)
        return self.send(uid, content, url=doc_url)
