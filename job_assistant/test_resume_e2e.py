"""端到端测试:简历上传 → AI 解析 → 用户编辑 → AI 补充 → 确认 → 匹配。

对服务器 localhost:5000 发起真实 API 调用,验证完整用户流程。
"""
import json
import sys
import time

import requests

BASE = "http://localhost:5000"
ORDER_ID = "test_e2e_001"

# 一份示例简历(计算机硕士,目标 AI/后端)
RESUME_TEXT = """
张三
清华大学 计算机科学与技术 硕士 2026届
电话:138****1234  邮箱:zhangsan@example.com

教育背景
2023.09 - 2026.06  清华大学  计算机科学与技术  硕士  GPA:3.8/4.0
2019.09 - 2023.06  北京大学  软件工程  本科  GPA:3.7/4.0

实习经历
2025.06 - 2025.09  字节跳动  AI 算法实习生
- 参与推荐系统召回模型优化,使用 Python、PyTorch 实现双塔模型
- 线上 AUC 提升 2.3%,召回率提升 5%
- 熟悉机器学习、深度学习、推荐系统、NLP

2024.07 - 2024.09  腾讯  后端开发实习生
- 参与微服务架构下的订单系统开发,使用 Go、MySQL、Redis
- 设计并实现分布式锁,解决并发扣减库存问题
- QPS 从 5000 提升到 12000

项目经历
2025.03 - 2025.05  基于大语言模型的智能问答系统
- 使用 LangChain + FastAPI 搭建 RAG 系统
- 集成向量数据库 Milvus,支持百万级文档检索

技能
- 编程语言:Python、Go、Java、C++
- 框架:PyTorch、TensorFlow、FastAPI、Spring Boot
- 数据库:MySQL、Redis、MongoDB、Milvus
- 其他:机器学习、深度学习、NLP、推荐系统、分布式系统

证书:CET-6、计算机二级
"""


def step(name, fn):
    print(f"\n{'='*60}")
    print(f"▶ {name}")
    print(f"{'='*60}")
    try:
        result = fn()
        print(f"✅ {name} 成功")
        return result
    except Exception as e:
        print(f"❌ {name} 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_health():
    r = requests.get(f"{BASE}/health", timeout=10)
    r.raise_for_status()
    print(f"  状态: {r.json()}")
    return r.json()


def test_parse_resume():
    """步骤1:简历解析"""
    files = {}
    data = {"resume_text": RESUME_TEXT}
    r = requests.post(f"{BASE}/api/parse-resume", data=data, files=files, timeout=120)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  错误: {r.text[:300]}")
        r.raise_for_status()
    result = r.json()
    profile = result.get("profile", {})
    print(f"  姓名: {profile.get('name')}")
    print(f"  学校: {profile.get('school')}")
    print(f"  学历: {profile.get('degree')}")
    print(f"  专业: {profile.get('major')}")
    print(f"  核心技能: {profile.get('core_skills')}")
    print(f"  目标公司: {profile.get('target_companies')}")
    print(f"  目标城市: {profile.get('target_cities')}")
    summary = profile.get("summary", "")
    print(f"  摘要({len(summary)}字): {summary[:150]}...")
    highlights = profile.get("highlights", [])
    print(f"  亮点({len(highlights)}条): {highlights[:3]}")
    fit_dirs = profile.get("fit_directions", [])
    print(f"  适配方向({len(fit_dirs)}个):")
    for d in fit_dirs[:5]:
        print(f"    - {d.get('direction')} (权重{d.get('weight')}) cat={d.get('category_name')}/{d.get('sub_key')}")
        if d.get("evidence"):
            print(f"      证据: {d['evidence'][:80]}")
    keywords = profile.get("structured_keywords", [])
    print(f"  结构化关键词({len(keywords)}个):")
    for k in keywords[:8]:
        if isinstance(k, dict):
            print(f"    - {k.get('kw')} [{k.get('category')}] w={k.get('weight')}")
        else:
            print(f"    - {k}")
    return profile


def test_supplement_profile(profile):
    """步骤2:用户编辑后 AI 补充"""
    # 模拟用户编辑:新增方向、技能、目标公司
    edited = dict(profile)
    edited["directions"] = ["AI算法", "后端开发"]
    edited["skills"] = ["Python", "PyTorch", "Go", "MySQL", "Redis", "机器学习"]
    edited["companies"] = ["字节跳动", "腾讯", "阿里巴巴"]
    edited["cities"] = ["北京", "上海", "杭州"]
    edited["summary"] = profile.get("summary", "") + " 热爱技术,追求极致。"

    payload = {"profile": edited, "resume_text": RESUME_TEXT}
    r = requests.post(f"{BASE}/api/supplement-profile", json=payload, timeout=120)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  错误: {r.text[:300]}")
        r.raise_for_status()
    result = r.json()
    new_dirs = result.get("new_directions", [])
    new_skills = result.get("new_skills", [])
    all_dirs = result.get("fit_directions", [])
    all_kw = result.get("structured_keywords", [])
    print(f"  新增方向({len(new_dirs)}个):")
    for d in new_dirs:
        print(f"    - {d.get('direction')}")
    print(f"  新增技能({len(new_skills)}个):")
    for s in new_skills:
        if isinstance(s, dict):
            print(f"    - {s.get('kw')}")
        else:
            print(f"    - {s}")
    print(f"  总方向数: {len(all_dirs)}, 总关键词数: {len(all_kw)}")
    return result


def test_confirm_setup(profile, supplement_result):
    """步骤3:确认配置 → 创建用户 + 飞书表 + 匹配"""
    # 合并解析 + 补充结果
    final = dict(profile)
    final["directions"] = ["AI算法", "后端开发"]
    final["skills"] = ["Python", "PyTorch", "Go", "MySQL", "Redis", "机器学习"]
    final["companies"] = ["字节跳动", "腾讯", "阿里巴巴"]
    final["cities"] = ["北京", "上海", "杭州"]
    final["fit_directions"] = supplement_result.get("fit_directions", [])
    final["structured_keywords"] = supplement_result.get("structured_keywords", [])

    payload = {"order_id": ORDER_ID, "profile": final}
    print(f"  提交确认... (可能需要 30-90 秒,含飞书建表+匹配)")
    r = requests.post(f"{BASE}/api/confirm-setup", json=payload, timeout=300)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  错误: {r.text[:500]}")
        r.raise_for_status()
    result = r.json()
    print(f"  用户ID: {result.get('user_id')}")
    print(f"  飞书链接: {result.get('share_url', 'N/A')}")
    matches = result.get("matches") or result.get("top_matches") or []
    print(f"  匹配岗位数: {len(matches)}")
    for m in matches[:5]:
        if isinstance(m, dict):
            print(f"    - {m.get('position_title') or m.get('position_name')} @ {m.get('company_name')}  评分={m.get('相关性评分') or m.get('score')}")
    return result


def main():
    print("🎯 简历解析端到端测试")
    print(f"   目标: {BASE}")
    print(f"   订单号: {ORDER_ID}")

    step("0. 健康检查", test_health)
    profile = step("1. 简历解析(parse-resume)", test_parse_resume)
    if not profile:
        print("\n❌ 简历解析失败,终止测试")
        sys.exit(1)

    supplement = step("2. AI 补充(supplement-profile)", lambda: test_supplement_profile(profile))
    if not supplement:
        print("\n⚠️ AI 补充失败,用原始 profile 继续确认")
        supplement = {"fit_directions": profile.get("fit_directions", []),
                      "structured_keywords": profile.get("structured_keywords", [])}

    step("3. 确认配置(confirm-setup)", lambda: test_confirm_setup(profile, supplement))

    print("\n" + "="*60)
    print("🎉 端到端测试流程完成")
    print("="*60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE = sys.argv[1]
    main()
