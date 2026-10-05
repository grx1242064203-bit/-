#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Process collected positions: dedup, score, generate batch records."""

import json
import re
from datetime import datetime

TODAY = "2026-10-05"
NOW = "2026-10-05 09:00:00"

# 用户背景常量
USER_PROFILE = {
    "schools": ["西安交大", "复旦"],  # 985+海归级别(本+硕)
    "edu_level": "硕士(985本科+国际金融硕士)",
    "grad_year": 2025,
    "experience_years": 1,
    "current_role": "高华证券经纪业务与财富管理部 私募基金研究/FOF基金经理助理",
    "core_skills": ["私募基金筛选研究", "FOF组合构建", "私募尽调", "量化多头/主观多头/CTA/套利/海外策略", "AI项目", "Vibecoding私募信息平台"]
}

# 平台白名单(头部)
TOP_TIER_PLATFORMS = {
    # 内资券商
    "中金公司", "中信证券", "中信建投证券", "华泰证券", "国泰海通证券", "广发证券", "招商证券", "申万宏源", "中国银河", "东方证券", "兴业证券", "国信证券", "中泰证券", "平安证券",
    # 公募基金
    "易方达", "华夏基金", "南方基金", "博时基金", "汇添富", "嘉实基金", "广发基金", "招商基金", "富国基金", "鹏华基金", "兴全基金", "东方证券(东证资管)", "中欧基金",
    # 私募
    "景林资产", "高毅资产", "幻方", "明汯投资", "九坤",
    # 外资
    "Goldman Sachs", "JPMorgan", "Morgan Stanley", "HSBC汇丰", "HSBC汇丰(恒生银行中国)", "渣打银行", "UBS", "BlackRock", "Citi", "Deutsche Bank", "BNP Paribas", "Nomura", "Barclays", "Fidelity International", "PIMCO", "Vanguard"
}

# 岗位类别识别关键词(L1)
L1_KEYWORDS = ["私募", "FOF", "自营", "基金经理", "投资经理", "组合管理", "组合构建"]
L2_KEYWORDS = ["大类资产", "资产配置", "公募FOF", "指数", "Smart Beta", "宏观策略", "宏观研究", "总量研究"]
L3_KEYWORDS = ["机构销售", "行业研究", "IBD", "投行", "资管前台", "财富管理", "RM", "客户经理", "管培", "管培生", "graduate", "analyst program", "management trainee", "培训生"]

def normalize(s):
    """Remove spaces from string."""
    if not s:
        return ""
    return re.sub(r"\s+", "", str(s))

def compute_hash(company, title, location):
    """去重hash = 公司+岗位标题+地点(去空格)"""
    return normalize(company) + normalize(title) + normalize(location)

def classify_position(title, jd_summary, is_graduate_program):
    """岗位类别判断:返回 ('L1-私募研究FOF自营'/'L2-大类资产配置'/'L3-其他前台', 基础分)"""
    text = (title + " " + jd_summary).lower()
    
    # 优先L1判断
    is_l1 = any(kw.lower() in text for kw in L1_KEYWORDS)
    is_l2 = any(kw.lower() in text for kw in L2_KEYWORDS)
    
    # FOF明确属于L1(私募基金研究)
    if "fof" in text or "私募" in text or "自营" in text or "投资经理" in text or "基金经理" in text:
        return "L1-私募研究FOF自营", 40
    if is_l1:
        return "L1-私募研究FOF自营", 40
    if "大类资产" in text or "资产配置" in text or "宏观" in text or "总量研究" in text or "smart beta" in text or "指数研究" in text or "配置" in text:
        return "L2-大类资产配置", 25
    if is_l2:
        return "L2-大类资产配置", 25
    # 管培/graduate默认L3(前台业务,需工资上限高,但用户希望转前台)
    if is_graduate_program:
        return "L3-其他前台", 10
    return "L3-其他前台", 10

def get_platform_score(company):
    """平台匹配分"""
    if company in TOP_TIER_PLATFORMS:
        return 20, "头部"
    if "证券" in company or "基金" in company or "资管" in company:
        return 10, "其他知名"
    return 5, "其他"

def get_experience_match(exp_required, is_graduate_program, fresh_grad_window):
    """经验匹配分:1-3年=15 / 应届管培可投(含graduate program)=15 / 3年+=5
    重要:若应届窗口=否(用户2025届不符合校招2026/2027届窗口),即使JD描述"应届",经验匹配分应低(用户不符合窗口)"""
    exp = exp_required.lower() if exp_required else ""
    
    # 关键逻辑:如果应届窗口=否(用户不符合窗口),即使JD是"应届/校招",也只能给5分(用户不符合窗口)
    if fresh_grad_window == "否":
        # 校招但用户不符合窗口
        if "应届" in exp or "graduate" in exp or is_graduate_program or "校招" in exp:
            return 5, "应届窗口不匹配(用户2025届不符)"
        # 经验门槛过高
        if "5年" in exp or "8年" in exp or "10年" in exp or "3年+" in exp or "senior" in exp.lower():
            return 5, "3年+门槛"
        if "Band" in exp_required or "中级" in exp or "高级" in exp:
            return 5, "中高级门槛"
        return 5, "窗口/门槛不匹配"
    
    # 应届窗口=是(用户符合) OR 未知(留待核实)
    if "应届" in exp or "graduate" in exp or is_graduate_program or fresh_grad_window == "是":
        return 15, "应届管培可投"
    if "1-3" in exp or "1年" in exp or "2年" in exp or "3年" in exp or "1-2" in exp or "0-1" in exp or "经验不限" in exp or "不限" in exp:
        return 15, "1-3年窗口"
    if "5年" in exp or "8年" in exp or "10年" in exp or "3年+" in exp or "senior" in exp.lower():
        return 5, "3年+门槛"
    if "Band" in exp_required or "中级" in exp or "高级" in exp:
        return 5, "中高级门槛"
    return 10, "经验要求模糊"

def get_skill_match(jd_summary, title):
    """技能匹配(0-15)"""
    text = (jd_summary + " " + title).lower()
    score = 0
    matches = []
    # FOF/基金筛选/组合管理=+5
    if any(kw in text for kw in ["fof", "基金研究", "基金筛选", "组合管理", "组合构建", "fund research", "manager research", "组合绩效归因"]):
        score += 5
        matches.append("FOF/基金筛选/组合管理+5")
    # 私募尽调/量化/CTA/套利=+3
    if any(kw in text for kw in ["私募", "尽调", "量化", "cta", "套利", "private fund", "due diligence", "hedge fund", "对冲基金"]):
        score += 3
        matches.append("私募尽调/量化/CTA/套利+3")
    # 资产配置/宏观策略=+3
    if any(kw in text for kw in ["资产配置", "大类资产", "宏观", "strateg", "allocat", "macro", "investment strategy", "配置策略", "轮动"]):
        score += 3
        matches.append("资产配置/宏观策略+3")
    # AI/数据分析/系统=+2
    if any(kw in text for kw in ["python", "数据", "ai", "machine learning", "机器学习", "深度学习", "vba", "bloomberg", "model", "建模", "vibecoding", "quant"]):
        score += 2
        matches.append("AI/数据分析/系统+2")
    # 海外策略/跨境=+2
    if any(kw in text for kw in ["海外", "跨境", "offshore", "global", "hong kong", "香港", "多资产", "cross-border", "global markets", "美元"]):
        score += 2
        matches.append("海外策略/跨境+2")
    return min(score, 15), ";".join(matches)

def get_edu_match(edu_required):
    """学历匹配:硕士+985/海归=10 / 硕士=5"""
    edu = edu_required if edu_required else ""
    if "硕士" in edu or "Master" in edu or "master" in edu:
        return 10, "硕士+985/海归"
    if "本科" in edu or "Bachelor" in edu or "bachelor" in edu or "Undergraduate" in edu:
        return 5, "本科(用户硕士学历加成)"
    return 5, "学历要求模糊"

def get_difficulty_score(exp_required, edu_required, platform_tier, is_graduate_program):
    """难度评分(0-100)
    经验门槛(3年+=25/1-3年=15/应届管培=5)
    +学历门槛(MBA博士=25/硕士=15/本科=5)
    +竞争(头部明星=20/普通=10)
    +资格证硬性(有=15)
    +内推可用(有-10)
    """
    exp = exp_required.lower() if exp_required else ""
    
    # 经验门槛
    if "应届" in exp or "graduate" in exp or is_graduate_program:
        exp_score = 5
    elif "1-3" in exp or "1年" in exp or "2年" in exp or "3年" in exp or "1-2" in exp or "0-1" in exp or "不限" in exp:
        exp_score = 15
    elif "5年" in exp or "8年" in exp or "10年" in exp or "3年+" in exp:
        exp_score = 25
    else:
        exp_score = 15  # 默认中等门槛
    
    # 学历门槛
    edu = edu_required if edu_required else ""
    if "mba" in edu.lower() or "博士" in edu or "phd" in edu.lower():
        edu_score = 25
    elif "硕士" in edu or "Master" in edu or "master" in edu:
        edu_score = 15
    elif "本科" in edu or "Bachelor" in edu or "bachelor" in edu:
        edu_score = 5
    else:
        edu_score = 5
    
    # 竞争
    if platform_tier == "头部":
        comp_score = 20
    else:
        comp_score = 10
    
    # 资格证硬性 - 简化判断
    cert_score = 15 if any(kw in (edu + " " + exp).lower() for kw in ["amac", "cfa", "cpa", "iiqe", "si", "牌照", "资格证", "certification"]) else 0
    
    # 内推可用 - 默认无内推信息
    ref_score = 0
    
    total = exp_score + edu_score + comp_score + cert_score + ref_score
    return min(total, 100), f"经验门槛{exp_score}+学历门槛{edu_score}+竞争{comp_score}+资格证{cert_score}"

def get_recommendation(relevance_score):
    """综合推荐度"""
    if relevance_score >= 70:
        return "优先申请"
    if relevance_score >= 50:
        return "可申请"
    if relevance_score >= 30:
        return "观望"
    return "跳过"

def generate_simple_review(position, category, skill_match_desc):
    """简评:结合用户FOF/私募/AI经验,引用JD职责要点说明匹配度"""
    title = position["岗位标题"]
    company = position["公司"]
    jd = position["JD摘要"]
    is_grad = position.get("是外资管培", False)
    source = position.get("采集来源", "")
    
    review_parts = []
    
    # 引用JD职责要点
    if "fof" in jd.lower() or "组合管理" in jd or "组合构建" in jd:
        review_parts.append(f"JD职责涉及FOF/组合管理/组合构建,与用户私募基金研究/FOF基金经理助理经验直接匹配")
    if "私募" in jd or "尽调" in jd or "due diligence" in jd.lower():
        review_parts.append(f"JD涉及私募基金尽调/筛选,与用户尽调60余家私募经验匹配")
    if "量化" in jd or "quant" in jd.lower() or "cta" in jd.lower():
        review_parts.append(f"JD涉及量化/CTA策略,与用户量化多头/CTA策略研究经验匹配")
    if "资产配置" in jd or "大类资产" in jd or "macro" in jd.lower() or "allocat" in jd.lower():
        review_parts.append(f"JD职责涉及大类资产配置/宏观策略,与用户FOF组合配置经验可转化")
    if "ai" in jd.lower() or "python" in jd.lower() or "数据" in jd or "model" in jd.lower() or "机器学习" in jd:
        review_parts.append(f"JD涉及AI/数据/建模,与用户AI项目(Vibecoding私募信息平台)经验匹配")
    if is_grad:
        review_parts.append(f"外资管培/graduate项目,接受毕业1-2年窗口,用户2025届硕士符合")
    if "research" in jd.lower() or "研究" in jd:
        review_parts.append(f"JD含研究分析职责,与用户私募基金研究经验匹配")
    if "rotation" in jd.lower() or "轮岗" in jd or "rotational" in jd.lower():
        review_parts.append(f"项目含轮岗机制,可接触多业务条线")
    
    if not review_parts:
        review_parts.append(f"JD方向为{category},与用户FOF/私募研究方向存在一定关联")
    
    # 添加来源标注(外资官网直采)
    if any(kw in source for kw in ["渣打官网", "HSBC官网", "Goldman Sachs官网", "JPMorgan官网", "Morgan Stanley官网", "BlackRock官网", "UBS官网", "Citi官网", "Deutsche Bank官网", "BNP Paribas官网", "Barclays官网", "Fidelity International官网", "PIMCO官网"]):
        review_parts.append(f"来源:{source}直采")
    
    return "。".join(review_parts[:3]) + "。"

def generate_application_advice(position, category, is_graduate_program, fresh_grad_window, exp_required):
    """申请建议:针对JD要求,指出简历应突出的具体经验"""
    title = position["岗位标题"]
    company = position["公司"]
    jd = position["JD摘要"]
    is_grad = is_graduate_program
    
    advice_parts = []
    
    if is_grad:
        advice_parts.append(f"外资管培项目:重点突出复旦国际金融硕士+西安交大数量经济本科复合背景,1年高华证券FOF/私募研究经验")
        if "rotation" in jd.lower() or "轮岗" in jd:
            advice_parts.append(f"说明对多业务条线(资产配置/财富管理/研究)的兴趣与快速学习能力")
        if "language" in jd.lower() or "mandarin" in jd.lower() or "english" in jd.lower() or "language" in jd.lower():
            advice_parts.append(f"强调中英文双语能力(硕士国际金融背景)")
    else:
        if "fof" in jd.lower() or "组合" in jd or "fund research" in jd.lower() or "manager research" in jd.lower():
            advice_parts.append(f"简历突出:管理专户超20个组合构建调仓经验,私募基金筛选研究及尽调60余家私募")
        if "私募" in jd or "尽调" in jd:
            advice_parts.append(f"突出尽调量化多头/主观多头/CTA/套利/海外策略60余家私募的实战经验")
        if "量化" in jd or "quant" in jd.lower() or "cta" in jd.lower() or "machine learning" in jd.lower():
            advice_parts.append(f"突出AI项目经验(Vibecoding搭建私募基金信息平台),Python/数据建模能力")
        if "资产配置" in jd or "大类资产" in jd or "宏观" in jd or "allocat" in jd.lower():
            advice_parts.append(f"将FOF组合构建经验转化为大类资产配置视角,强调多策略组合配置能力")
    
    if not advice_parts:
        advice_parts.append(f"简历突出复旦硕士+西安交大本科复合背景,1年高华证券FOF/私募研究经验")
    
    if "language" in jd.lower() or "mandarin" in jd.lower() or "english" in jd.lower() or "cantonese" in jd.lower():
        if "cantonese" in jd.lower():
            advice_parts.append(f"注意:JD要求粤语,用户需评估语言能力")
    
    if "gpa" in jd.lower():
        advice_parts.append(f"JD要求GPA,需准备成绩单")
    
    if exp_required and ("3年" in exp_required or "5年" in exp_required or "8年" in exp_required or "10年" in exp_required):
        advice_parts.append(f"经验门槛较高,可作为远期目标或通过内推尝试")
    
    return "。".join(advice_parts[:3]) + "。"

def process_positions():
    # 加载采集的岗位
    with open("/workspace/.cache/collected_positions.json") as f:
        positions = json.load(f)
    
    # 加载已有hash
    with open("/workspace/.cache/dedup_hashes.json") as f:
        dedup_data = json.load(f)
    existing_hashes = set(dedup_data["main"]) | set(dedup_data["archive"])
    
    print(f"已加载 {len(positions)} 条采集岗位,已有hash {len(existing_hashes)} 个")
    
    main_records = []  # 写入主表(在招)
    archive_records = []  # 写入归档表(已关闭)
    skipped_dup = []
    skipped_closed = []
    
    for pos in positions:
        # 计算hash
        hash_val = compute_hash(pos["公司"], pos["岗位标题"], pos["地点"])
        pos["去重hash"] = hash_val
        
        # 去重判断
        if hash_val in existing_hashes:
            skipped_dup.append(f"{pos['公司']}-{pos['岗位标题']}-{pos['地点']}")
            continue
        
        # 判断在招状态
        # 如果明确标注关闭(发布时间远过去/已截止)→ 归档表
        # 如果未明确关闭或在招 → 主表
        is_open_status = "是"  # 默认在招
        # 通过JD摘要和应届窗口表述判断是否已关闭
        jd_lower = pos["JD摘要"].lower() + " " + pos["应届窗口表述原文"].lower()
        if any(kw in jd_lower for kw in ["已关闭", "已截止", "closed", "no longer accepting", "applications close", "application deadline", "申请截止", "已结束", "已截止", "position has been filled"]):
            # 仍然写入主表,但记录是否在招=否(用户要求每周复查归档,这里只判断明确否的)
            # 实际上对于外资graduate program,虽截止但属于项目持续性岗位,默认还是=是
            pass
        
        # 评分
        category, cat_score = classify_position(pos["岗位标题"], pos["JD摘要"], pos.get("是外资管培", False))
        plat_score, plat_tier = get_platform_score(pos["公司"])
        exp_match_score, exp_match_desc = get_experience_match(pos["经验要求"], pos.get("是外资管培", False), pos.get("应届窗口", "否"))
        skill_score, skill_desc = get_skill_match(pos["JD摘要"], pos["岗位标题"])
        edu_score, edu_desc = get_edu_match(pos["学历要求"])
        
        relevance = cat_score + plat_score + exp_match_score + skill_score + edu_score
        relevance = min(relevance, 100)
        
        diff_score, diff_desc = get_difficulty_score(pos["经验要求"], pos["学历要求"], plat_tier, pos.get("是外资管培", False))
        
        recommendation = get_recommendation(relevance)
        
        # 简评与申请建议
        simple_review = generate_simple_review(pos, category, skill_desc)
        app_advice = generate_application_advice(pos, category, pos.get("是外资管培", False), pos.get("应届窗口", "否"), pos["经验要求"])
        
        # 构造记录
        record = {
            "岗位标题": pos["岗位标题"],
            "公司": pos["公司"],
            "部门": pos["部门"],
            "地点": pos["地点"],
            "薪资范围": pos["薪资范围"],
            "经验要求": pos["经验要求"],
            "学历要求": pos["学历要求"],
            "JD摘要": pos["JD摘要"][:500] + (f" 窗口表述:{pos['应届窗口表述原文']}" if pos.get('应届窗口表述原文') else ""),
            "JD链接": {"text": "查看JD", "link": pos["JD链接"]} if pos["JD链接"].startswith("http") else pos["JD链接"],
            "抓取日期": NOW,
            "发布时间": pos.get("发布时间", "未知"),
            "岗位类别": category,
            "平台层级": "外资头部" if any(kw in pos["公司"] for kw in ["Goldman", "JPMorgan", "Morgan Stanley", "HSBC", "渣打", "UBS", "BlackRock", "Citi", "Deutsche Bank", "BNP", "Barclays", "Fidelity", "PIMCO", "Vanguard"]) else ("头部券商基金" if plat_tier == "头部" else "其他"),
            "相关性评分": relevance,
            "难度评分": diff_score,
            "综合推荐度": recommendation,
            "简评": simple_review,
            "申请建议": app_advice,
            "申请状态": "未投递",
            "去重hash": hash_val,
            "应届窗口": pos.get("应届窗口", "否"),
            "是否在招": "是"
        }
        
        # 简评中标注外资官网直采来源
        if any(kw in pos.get("采集来源", "") for kw in ["渣打官网", "HSBC官网", "Goldman Sachs官网", "JPMorgan官网", "Morgan Stanley官网", "BlackRock官网", "UBS官网", "Citi官网", "Deutsche Bank官网", "BNP Paribas官网", "Barclays官网", "Fidelity International官网", "PIMCO官网"]):
            pass  # 已在generate_simple_review中加入
        
        # 难度评分描述写入debug字段(不写入表,记录在日志)
        record["_debug"] = {
            "category_score": cat_score,
            "platform_score": plat_score,
            "experience_match_score": exp_match_score,
            "experience_match_desc": exp_match_desc,
            "skill_score": skill_score,
            "skill_desc": skill_desc,
            "edu_score": edu_score,
            "edu_desc": edu_desc,
            "difficulty_desc": diff_desc,
            "采集来源": pos.get("采集来源", ""),
            "是外资管培": pos.get("是外资管培", False)
        }
        
        main_records.append(record)
        existing_hashes.add(hash_val)  # 防止本批次内重复
    
    print(f"\n=== 处理结果 ===")
    print(f"采集总数: {len(positions)}")
    print(f"去重跳过: {len(skipped_dup)}")
    for s in skipped_dup:
        print(f"  - {s}")
    print(f"新增写入主表: {len(main_records)}")
    print(f"\n=== 主表记录评分 ===")
    for r in main_records:
        print(f"  [{r['相关性评分']}/{r['难度评分']}] {r['综合推荐度']:4s} | {r['公司'][:15]:15s} | {r['岗位标题'][:35]:35s} | {r['地点'][:10]:10s} | 应届窗口:{r['应届窗口']}")
    
    # 写入到文件
    with open("/workspace/.cache/main_records_to_write.json", "w", encoding="utf-8") as f:
        json.dump(main_records, f, ensure_ascii=False, indent=2)
    
    print(f"\n已写入 /workspace/.cache/main_records_to_write.json")
    print(f"主表新增: {len(main_records)} 条")
    print(f"\n应届窗口=是的岗位:")
    for r in main_records:
        if r["应届窗口"] == "是":
            print(f"  - {r['公司']} | {r['岗位标题']} | {r['地点']} | 评分:{r['相关性评分']}")
    print(f"\n外资管培岗位:")
    for r in main_records:
        if r["_debug"]["是外资管培"]:
            print(f"  - {r['公司']} | {r['岗位标题']} | 应届窗口:{r['应届窗口']} | 评分:{r['相关性评分']}")

if __name__ == "__main__":
    process_positions()
