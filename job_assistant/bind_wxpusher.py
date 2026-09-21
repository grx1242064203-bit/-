"""
用户绑定 WxPusher — 生成二维码让用户扫码关注,获取 uid 后绑定到用户配置。

使用方式:
    python bind_wxpusher.py <user_id>

会打印一个二维码 URL,用户微信扫码关注后,
从 WxPusher 后台查到该用户的 uid,填入并保存。

(MVP 阶段手动查 uid;生产阶段可通过 WxPusher 回调自动获取)
"""
import sys
from models import UserStore
from wxpusher_client import WxPusherClient


def bind(user_id: str):
    store = UserStore()
    user = store.get(user_id)
    if not user:
        print(f"用户不存在: {user_id}")
        return

    client = WxPusherClient()
    qr_url = client.get_qrcode()
    if not qr_url:
        print("WxPusher 未配置,请设置 WXPUSHER_APP_TOKEN 环境变量")
        return

    print(f"\n请让用户微信扫码关注: {qr_url}\n")
    print("用户关注后,在 WxPusher 后台 → 我的应用 → 用户管理 中找到该用户的 UID")
    uid = input("请输入用户的 WxPusher UID: ").strip()
    if uid:
        user.wxpusher_uid = uid
        store.upsert(user)
        print(f"绑定成功!用户 {user_id} → {uid}")
    else:
        print("未输入 UID,取消绑定")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python bind_wxpusher.py <user_id>")
        sys.exit(1)
    bind(sys.argv[1])
