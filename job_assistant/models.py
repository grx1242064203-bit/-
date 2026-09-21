"""
数据模型 + 用户存储(MVP 用 JSON 文件,生产可替换为 DB)。

第一原则:用户数据与岗位数据分离存储。
- 用户配置:data/users.json (少量,全量加载)
- 岗位去重哈希:data/hashes/{user_id}.json (避免重复写入已关闭岗位)
"""
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

from config import settings


@dataclass
class UserProfile:
    """用户画像 — 用于评分匹配"""
    school: str = ""           # 学校
    degree: str = ""           # 学历:本科/硕士/博士
    major: str = ""            # 专业
    experience_years: float = 0  # 工作年限
    current_role: str = ""     # 当前岗位
    core_skills: List[str] = field(default_factory=list)  # 核心技能
    target_directions: List[str] = field(default_factory=list)  # 目标方向: L1/L2/L3
    target_companies: List[str] = field(default_factory=list)   # 目标机构(可空=全部)
    target_cities: List[str] = field(default_factory=list)      # 目标城市(可空=不限)


@dataclass
class User:
    id: str
    # 飞书
    feishu_tenant_key: str = ""
    feishu_open_id: str = ""
    feishu_base_token: str = ""      # 用户专属多维表格
    feishu_table_id: str = ""        # 岗位表ID
    feishu_closed_table_id: str = "" # 已关闭岗位表ID
    # 微信推送
    wxpusher_uid: str = ""
    # 画像
    profile: UserProfile = field(default_factory=UserProfile)
    # 套餐
    plan: str = "autumn"             # trial / autumn / spring / yearly
    expire_date: str = ""            # YYYY-MM-DD
    created_at: float = field(default_factory=time.time)
    last_run_at: float = 0.0


class UserStore:
    """用户存储 — JSON 文件,加文件锁防并发"""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(settings.DATA_DIR, "users.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._users: Dict[str, User] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for uid, data in raw.items():
                prof_data = data.pop("profile", {})
                data["profile"] = UserProfile(**prof_data)
                self._users[uid] = User(id=uid, **data)

    def _save(self):
        raw = {}
        for uid, u in self._users.items():
            d = asdict(u)
            raw[uid] = d
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # 原子写入

    def get(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def list_active(self) -> List[User]:
        """返回未过期的用户"""
        now = time.strftime("%Y-%m-%d")
        return [u for u in self._users.values()
                if not u.expire_date or u.expire_date >= now]

    def upsert(self, user: User):
        self._users[user.id] = user
        self._save()

    def delete(self, user_id: str):
        self._users.pop(user_id, None)
        self._save()


class HashStore:
    """去重哈希存储 — 每个用户一个文件,记录已见过的岗位hash"""

    def __init__(self, user_id: str):
        self.path = os.path.join(settings.DATA_DIR, "hashes", f"{user_id}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._hashes: Dict[str, Any] = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._hashes = json.load(f)

    def exists(self, h: str) -> bool:
        return h in self._hashes

    def add(self, h: str, meta: dict = None):
        self._hashes[h] = meta or {"ts": time.time()}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._hashes, f, ensure_ascii=False)
        os.replace(tmp, self.path)
