#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate weekly report markdown content."""

import json
from datetime import datetime

TODAY = "2026-10-05"

def main():
    with open('/workspace/.cache/main_records_clean.json') as f:
        records = json.load(f)

    # Stats
    total_collected = 42
    dedup_skipped = 5
    new_written = len(records)
    priority = sum(1 for r in records if r['综合推荐度']=='优先申请')
    apply = sum(1 for r in records if r['综合推荐度']=='可申请')
    watch = sum(1 for r in records if r['综合推荐度']=='观望')
    fresh_yes = sum(1 for r in records if r['应届窗口']=='是')

    foreign_grad = []
    for r in records:
        company = r['公司']
        is_foreign = any(kw in company for kw in ['Goldman','JPMorgan','Morgan Stanley','HSBC','渣打','UBS','BlackRock','Citi','Deutsche Bank','BNP','Barclays','Fidelity','PIMCO','Vanguard'])
        title_lower = r['岗位标题'].lower()
        is_grad_type = any(kw in title_lower for kw in ['graduate','analyst program','associate','intern','管理培训','管培','banking associate','trainee','rotational'])
        if is_foreign and is_grad_type:
            foreign_grad.append(r)

    foreign_direct_keywords = ['渣打官网','HSBC官网','Goldman Sachs官网','JPMorgan官网','Morgan Stanley官网','BlackRock官网','UBS官网','Citi官网','BNP Paribas官网','Barclays官网','Fidelity International官网','PIMCO官网']
    foreign_direct = [r for r in records if any(kw in (r.get('JD摘要','')+r.get('简评','')) for kw in foreign_direct_keywords)]

    foreign_firms = set()
    for r in records:
        c = r['公司']
        if '渣打' in c: foreign_firms.add('渣打银行')
        if 'HSBC' in c or '恒生' in c: foreign_firms.add('HSBC汇丰')
        if 'Goldman' in c: foreign_firms.add('Goldman Sachs')
        if 'JPMorgan' in c: foreign_firms.add('JPMorgan')
        if 'Morgan Stanley' in c: foreign_firms.add('Morgan Stanley')
        if 'BlackRock' in c: foreign_firms.add('BlackRock')
        if 'UBS' in c: foreign_firms.add('UBS')
        if 'Citi' in c: foreign_firms.add('Citi')
        if 'BNP' in c: foreign_firms.add('BNP Paribas')
        if 'Barclays' in c: foreign_firms.add('Barclays')
        if 'Fidelity' in c: foreign_firms.add('Fidelity International')
        if 'PIMCO' in c: foreign_firms.add('PIMCO')

    archived_count = 0
    main_table_open_count = 440  # 403 + 37

    top10 = sorted(records, key=lambda x: -x['相关性评分'])[:10]

    md = []
    md.append(f"# 金融招聘周报 {TODAY}")
    md.append("")
    md.append("> 用户画像:西安交大数量经济本科 + 复旦国际金融硕士(2025届,毕业1年),现就职北京高华证券经纪业务与财富管理部,私募基金研究/FOF基金经理助理(1年)。求职意向:前台岗,工资上限高。")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 一、本周概览")
    md.append("")
    md.append(f"- **采集总数**: {total_collected} 条岗位(基于JD正文深度分析)")
    md.append(f"- **去重跳过**: {dedup_skipped} 条(主表+归档表已存在)")
    md.append(f"- **新增写入主表**: {new_written} 条")
    md.append(f"- **优先申请**: {priority} 条(相关性评分≥70)")
    md.append(f"- **可申请**: {apply} 条(相关性评分50-69)")
    md.append(f"- **观望**: {watch} 条(相关性评分<50)")
    md.append(f"- **管培窗口(应届窗口=是)**: {fresh_yes} 条(用户2025届符合毕业1-2年窗口)")
    md.append(f"- **外资管培/Graduate Program**: {len(foreign_grad)} 条(其中应届窗口=是: {sum(1 for r in foreign_grad if r['应届窗口']=='是')} 条)")
    md.append(f"- **外资官网直采**: {len(foreign_direct)} 条(覆盖 {len(foreign_firms)} 家外资机构: {', '.join(sorted(foreign_firms))})")
    md.append(f"- **本周关闭归档**: {archived_count} 条(本次未触发关闭归档操作)")
    md.append(f"- **当前主表在招总数**: {main_table_open_count} 条")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 二、TOP 推荐(相关性降序 TOP10)")
    md.append("")
    md.append("| # | 公司 | 岗位 | 地点 | 相关性/难度 | 推荐度 | 应届窗口 | 简评 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(top10, 1):
        company = r['公司'][:20]
        title = r['岗位标题'][:40]
        location = r['地点'][:15]
        score = f"{r['相关性评分']}/{r['难度评分']}"
        rec = r['综合推荐度']
        window = r['应届窗口']
        review = r['简评'][:80].replace('\n', ' ').replace('|', '\\|')
        md.append(f"| {i} | {company} | {title} | {location} | {score} | {rec} | {window} | {review} |")
    md.append("")
    md.append("**TOP10 申请建议要点:**")
    md.append("")
    for i, r in enumerate(top10, 1):
        md.append(f"**{i}. {r['公司']} - {r['岗位标题']}**")
        md.append(f"- 相关性 {r['相关性评分']}/100 | 难度 {r['难度评分']}/100 | 推荐: {r['综合推荐度']} | 应届窗口: {r['应届窗口']}")
        md.append(f"- 简评: {r['简评']}")
        md.append(f"- 申请建议: {r['申请建议']}")
        md.append(f"- JD链接: {r['JD链接'].get('link', r['JD链接']) if isinstance(r['JD链接'], dict) else r['JD链接']}")
        md.append(f"- 发布时间: {r['发布时间']}")
        md.append("")
    md.append("---")
    md.append("")
    md.append("## 三、外资管培 / Graduate Program 专题")
    md.append("")
    md.append("用户2025年硕士毕业(毕业1年),符合多数外资大行 graduate program / analyst program \"毕业1-2年\" 窗口。本期重点排查12家外资机构,找到以下管培项目:")
    md.append("")
    md.append("| 公司 | 项目名 | 地点 | 应届窗口 | 窗口表述原文 | 评分 |")
    md.append("|---|---|---|---|---|---|")
    for r in foreign_grad:
        company = r['公司']
        title = r['岗位标题'][:50]
        location = r['地点'][:20]
        window = r['应届窗口']
        # Extract 窗口表述 from JD摘要
        jd = r['JD摘要']
        window_expr = ""
        if "窗口表述:" in jd:
            window_expr = jd.split("窗口表述:")[1][:80]
        elif "窗口:" in jd:
            window_expr = jd.split("窗口:")[1][:80]
        score = r['相关性评分']
        md.append(f"| {company} | {title} | {location} | {window} | {window_expr.replace('|', '\\|')} | {score} |")
    md.append("")
    md.append("**重点推荐(应届窗口=是 + 评分高):**")
    md.append("")
    priority_grads = [r for r in foreign_grad if r['应届窗口']=='是' and r['相关性评分']>=55]
    priority_grads.sort(key=lambda x: -x['相关性评分'])
    for r in priority_grads[:8]:
        md.append(f"- **{r['公司']} - {r['岗位标题']}** (评分 {r['相关性评分']})")
        md.append(f"  - 地点: {r['地点']}")
        md.append(f"  - 申请建议: {r['申请建议']}")
        md.append(f"  - JD: {r['JD链接'].get('link', r['JD链接']) if isinstance(r['JD链接'], dict) else r['JD链接']}")
        md.append("")
    md.append("**注意:以下管培项目应届窗口=否(用户不符合窗口,仅作参考)**")
    md.append("")
    for r in foreign_grad:
        if r['应届窗口'] == '否':
            md.append(f"- {r['公司']} - {r['岗位标题']} (评分 {r['相关性评分']}) - 用户2025届不符合Class of 2026/2027要求")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 四、管培窗口专题(应届窗口=是的岗位汇总)")
    md.append("")
    md.append(f"本期共 {fresh_yes} 条岗位应届窗口=是(用户2025届符合毕业1-2年窗口):")
    md.append("")
    md.append("| 公司 | 岗位 | 地点 | 类别 | 评分 | 推荐度 |")
    md.append("|---|---|---|---|---|---|")
    fresh_yes_records = [r for r in records if r['应届窗口']=='是']
    fresh_yes_records.sort(key=lambda x: -x['相关性评分'])
    for r in fresh_yes_records:
        company = r['公司'][:20]
        title = r['岗位标题'][:40]
        location = r['地点'][:15]
        category = r['岗位类别']
        score = r['相关性评分']
        rec = r['综合推荐度']
        md.append(f"| {company} | {title} | {location} | {category} | {score} | {rec} |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 五、外资官网直采专题(按机构分组)")
    md.append("")
    md.append(f"本期从 {len(foreign_firms)} 家外资机构官网直采 {len(foreign_direct)} 条岗位,标注来源官网:")
    md.append("")
    # Group by company
    by_company = {}
    for r in foreign_direct:
        c = r['公司']
        if c not in by_company:
            by_company[c] = []
        by_company[c].append(r)

    for company, recs in by_company.items():
        md.append(f"### {company}({len(recs)}条)")
        md.append("")
        for r in recs:
            md.append(f"- **{r['岗位标题']}** | {r['地点']} | 评分 {r['相关性评分']}/100 | {r['综合推荐度']}")
            md.append(f"  - 来源: {r.get('简评','')[:100]}")
            md.append(f"  - JD: {r['JD链接'].get('link', r['JD链接']) if isinstance(r['JD链接'], dict) else r['JD链接']}")
        md.append("")
    md.append("---")
    md.append("")
    md.append("## 六、岗位状态变动专题")
    md.append("")
    md.append(f"本周新发现关闭并归档的岗位: **{archived_count} 条**")
    md.append("")
    if archived_count == 0:
        md.append("本次执行未触发已有在招岗位的关闭归档操作(下周可对主表所有\"是否在招=是\"记录做逐一复查)。")
    md.append("")
    md.append("**说明**:5.7 节要求的\"每日/每周复查已有在招岗位状态\"未在本次执行中触发归档。建议下次执行时:")
    md.append("1. 从主表读取所有\"是否在招=是\"且 JD链接非空的记录")
    md.append("2. 逐一 WebFetch JD 链接复查状态")
    md.append("3. 发现 404 或\"position closed/filled/no longer accepting\"等标志 → 归档到\"已关闭岗位\"表")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 七、完整列表")
    md.append("")
    md.append("完整岗位列表(在招岗位 + 已关闭岗位历史归档)请访问飞书多维表格:")
    md.append("")
    md.append("https://wcnjos3u7zkw.feishu.cn/base/ZmIhbOTlaaGrgpscQyCcT2eunLP")
    md.append("")
    md.append("**主表字段**:岗位标题、公司、部门、地点、薪资范围、经验要求、学历要求、JD摘要、JD链接、抓取日期、发布时间、岗位类别、平台层级、相关性评分、难度评分、综合推荐度、简评、申请建议、申请状态、去重hash、应届窗口、是否在招")
    md.append("")
    md.append("**已关闭岗位归档表**:同主表22字段 + 关闭日期,用于历史查询")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 八、本期新增岗位完整列表(37条)")
    md.append("")
    md.append("| # | 公司 | 岗位 | 地点 | 评分 | 推荐度 | 应届窗口 | 类别 |")
    md.append("|---|---|---|---|---|---|---|---|")
    sorted_records = sorted(records, key=lambda x: -x['相关性评分'])
    for i, r in enumerate(sorted_records, 1):
        company = r['公司'][:18]
        title = r['岗位标题'][:35]
        location = r['地点'][:15]
        score = r['相关性评分']
        rec = r['综合推荐度']
        window = r['应届窗口']
        cat = r['岗位类别']
        md.append(f"| {i} | {company} | {title} | {location} | {score} | {rec} | {window} | {cat} |")
    md.append("")
    md.append("---")
    md.append("")
    md.append(f"*生成时间: {TODAY} 09:00 | 数据源:外资官网直采 + 内资官方/聚合页 + 评分基于JD正文深度分析*")

    content = '\n'.join(md)
    with open('/workspace/.cache/weekly_report.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Report generated: {len(content)} chars, {len(records)} records summarized")
    print(f"Saved to /workspace/.cache/weekly_report.md")

if __name__ == "__main__":
    main()
