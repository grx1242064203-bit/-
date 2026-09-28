"""
数据模型 + 用户存储(MVP 用 JSON 文件,生产可替换为 DB)。

第一原则:用户数据与岗位数据分离存储。
- 用户配置:data/users.json (少量,全量加载)
- 岗位去重哈希:data/hashes/{user_id}.json (避免重复写入已关闭岗位)

并发安全:
- 写操作通过 fcntl.flock 获取排他锁,防止文件损坏
- upsert/delete 前从磁盘重新加载,合并后写回,防止 lost-update
"""
import json
import os
import time
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

from config import settings


@dataclass
class UserProfile:
    """用户画像 — 用于评分匹配(通用化,支持任意专业/职业阶段)"""
    # === 角色分化 ===
    role: str = ""             # 求职角色: internship(实习)/campus(校招)/social(社招)
    mt_program_preference: str = "all"  # 管培项目偏好: all/finance/internet/consulting_fmcg/soe(仅校招用户)
    # === 基本信息 ===
    school: str = ""           # 学校
    degree: str = ""           # 学历:本科/硕士/博士
    major: str = ""            # 专业
    graduation_year: str = ""  # 毕业年份(如 2026)
    graduation_date: str = ""  # 毕业年月(如 2026-06,校招用户必填,用于严格匹配JD届数要求)
    experience_years: float = 0  # 工作年限(0=应届,校招用户忽略此字段)
    current_role: str = ""     # 当前岗位/身份(学生/在职)
    core_skills: List[str] = field(default_factory=list)  # 核心技能/标签
    # 目标方向 + 关键词(用户自定义,通用化)
    direction_keywords: Dict[str, List[str]] = field(default_factory=dict)
    target_companies: List[str] = field(default_factory=list)   # 目标公司(可空=全部)
    target_industries: List[str] = field(default_factory=list)  # 目标行业(可空=全部)
    target_cities: List[str] = field(default_factory=list)      # 目标城市(可空=不限)
    target_certificates: List[str] = field(default_factory=list)  # 已持证书(CFA/CPA/法考等)
    # === 校招用户专属:企业匹配维度(可多选) ===
    preferred_company_types: List[str] = field(default_factory=list)  # 偏好公司类型:国央企/民企/外企
    preferred_difficulties: List[str] = field(default_factory=list)   # 偏好难度:最激烈/较为激烈/中等难度/较低难度
    preferred_locations: List[str] = field(default_factory=list)      # 偏好城市
    # === LLM 简历解析留档 ===
    resume_text: str = ""      # 原始简历文本(留档,便于重新解析)
    summary: str = ""          # LLM 生成的候选人一句话画像
    highlights: List[str] = field(default_factory=list)  # 简历亮点(丰富画像展示)


@dataclass
class User:
    id: str
    # 订单身份(XHS 店铺订单号,新身份体系的核心标识)
    order_id: str = ""
    # 飞书 — 用户专属多维表格(互联网分享,无需用户飞书账号)
    feishu_tenant_key: str = ""      # 可选:旧版飞书应用安装用户保留
    feishu_open_id: str = ""         # 可选:旧版飞书应用安装用户保留
    feishu_base_token: str = ""      # 用户专属多维表格 app_token
    feishu_table_id: str = ""        # 岗位表ID
    feishu_closed_table_id: str = "" # 已关闭岗位表ID
    feishu_mt_table_id: str = ""     # 管培生项目表ID(校招用户专项)
    # 微信推送(可选,辅助提醒)
    wxpusher_uid: str = ""
    # 邮箱(可选,用于岗位更新提醒)
    email: str = ""
    # 画像
    profile: UserProfile = field(default_factory=UserProfile)
    # 套餐
    plan: str = "autumn"             # trial / autumn / spring / yearly / monthly
    expire_date: str = ""            # YYYY-MM-DD
    created_at: float = field(default_factory=time.time)
    last_run_at: float = 0.0


class UserStore:
    """用户存储 — JSON 文件,加文件锁防并发"""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(settings.DATA_DIR, "users.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock_path = self.path + ".lock"
        self._users: Dict[str, User] = {}
        self._load()

    @contextmanager
    def _file_lock(self):
        """获取排他文件锁,防止并发写导致数据损坏"""
        lock_fd = open(self._lock_path, "w")
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for uid, data in raw.items():
                data.pop("id", None)  # 避免与 id=uid 冲突
                prof_data = data.pop("profile", {})
                data["profile"] = UserProfile(**prof_data)
                self._users[uid] = User(id=uid, **data)

    def _save(self):
        """写回磁盘(调用方需持有文件锁)"""
        raw = {}
        for uid, u in self._users.items():
            d = asdict(u)
            raw[uid] = d
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # 原子写入

    def _reload_from_disk(self):
        """持锁后从磁盘全量重新加载,确保拿到最新状态。
        会清空内存再加载,调用方必须已经持有文件锁。
        修复多进程 lost-update: 若只加载内存中不存在的用户,
        两个进程修改不同用户时,后保存的进程会覆盖先保存进程的修改。"""
        self._users = {}
        self._load()

    def get(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def get_by_order_id(self, order_id: str) -> Optional[User]:
        """按 XHS 订单号查找用户(新身份体系)。"""
        if not order_id:
            return None
        for u in self._users.values():
            if u.order_id == order_id:
                return u
        return None

    def list_active(self) -> List[User]:
        """返回未过期的用户"""
        now = time.strftime("%Y-%m-%d")
        return [u for u in self._users.values()
                if not u.expire_date or u.expire_date >= now]

    def upsert(self, user: User):
        """插入或更新用户。
        持锁 → 全量重载磁盘(拿到最新状态) → 应用修改 → 写回。
        全量重载确保不会丢失其他进程对其他用户的修改。"""
        with self._file_lock():
            self._reload_from_disk()
            self._users[user.id] = user
            self._save()

    def delete(self, user_id: str):
        """删除用户。持锁 → 全量重载磁盘 → 删除 → 写回。"""
        with self._file_lock():
            self._reload_from_disk()
            self._users.pop(user_id, None)
            self._save()


class HashStore:
    """去重哈希存储 — 每个用户一个文件,记录已见过的岗位hash。

    并发安全: 写操作(add)通过 fcntl.flock 获取排他锁,防止并发写损坏文件。
    """

    def __init__(self, user_id: str):
        self.path = os.path.join(settings.DATA_DIR, "hashes", f"{user_id}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock_path = self.path + ".lock"
        self._hashes: Dict[str, Any] = {}
        self._load()

    @contextmanager
    def _file_lock(self):
        """获取排他文件锁,防止并发写导致 hash 文件损坏"""
        lock_fd = open(self._lock_path, "w")
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._hashes = json.load(f)

    def exists(self, h: str) -> bool:
        return h in self._hashes

    def add(self, h: str, meta: dict = None):
        """添加 hash 并持久化。持文件锁 + 原子写入,防止并发损坏。"""
        with self._file_lock():
            # 持锁后从磁盘重新加载,避免覆盖其他进程写入的 hash
            self._hashes = {}
            self._load()
            self._hashes[h] = meta or {"ts": time.time()}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._hashes, f, ensure_ascii=False)
            os.replace(tmp, self.path)  # 原子写入
