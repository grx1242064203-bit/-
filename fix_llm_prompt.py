#!/usr/bin/env python3
"""修改 llm_enricher.py: 移除 department/recruitment_process, 注入源表元数据"""

with open("llm_enricher.py") as f:
    src = f.read()

# 1. Prompt header: 添加源表元数据上下文
old_header = 'POSITION_EXTRACT_PROMPT = """你是校招信息解析专家。请从以下招聘公告中提取所有可独立投递的具体岗位,并填入结构化字段。\n\n公司: {company}\n公告标题: {title}\n\n公告内容:\n\\"\\"\\"{content}\\"\\"\\"'
new_header = 'POSITION_EXTRACT_PROMPT = """你是校招信息解析专家。请从以下招聘公告中提取所有可独立投递的具体岗位,并填入结构化字段。\n\n公司: {company}\n公司行业: {industry}\n公司类型: {company_type}\n工作地点: {location}\n学历要求: {education}\n公告标题: {title}\n\n公告内容:\n\\"\\"\\"{content}\\"\\"\\"'
assert old_header in src, "header not found"
src = src.replace(old_header, new_header)

# 2. 移除 department 字段
old_dept = '    "department": "部门或条线(如:技术中台/零售金融,无法确定填空字符串)",\n'
assert old_dept in src, "department field not found"
src = src.replace(old_dept, "")

# 3. 移除 recruitment_process 字段
old_rp = '    "recruitment_process": "招聘流程简述(如:网申→笔试→面试→offer,无则空字符串)",\n'
assert old_rp in src, "recruitment_process field not found"
src = src.replace(old_rp, "")

# 4. 添加 requirements 默认值规则 + bonus_points 规则
old_tail = '10. hard_skills: 从职责/要求中提取技能关键词;无明确技能但可从岗位推断的(如Java岗→["Java"]);完全无法推断才空数组。\n"""'
new_tail = '10. hard_skills: 从职责/要求中提取技能关键词;无明确技能但可从岗位推断的(如Java岗→["Java"]);完全无法推断才空数组。\n11. requirements: 有明确要求就摘录;无明确要求时填"详见招聘公告"(不要留空字符串)。\n12. bonus_points: 无加分项时填空字符串。\n"""'
assert old_tail in src, "tail rules not found"
src = src.replace(old_tail, new_tail)

with open("llm_enricher.py", "w") as f:
    f.write(src)
print("OK: prompt 修改完成")
