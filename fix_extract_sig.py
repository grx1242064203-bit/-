#!/usr/bin/env python3
"""修改 extract_positions 签名和调用，注入源表元数据"""

with open("llm_enricher.py") as f:
    src = f.read()

# 1. 修改 extract_positions 签名，添加源表元数据参数
old_sig = '    def extract_positions(self, content: str, company: str = "",\n                          title: str = "") -> List[Dict]:'
new_sig = '    def extract_positions(self, content: str, company: str = "",\n                          title: str = "", industry: str = "",\n                          company_type: str = "", location: str = "",\n                          education: str = "") -> List[Dict]:'
assert old_sig in src, "signature not found"
src = src.replace(old_sig, new_sig)

# 2. 修改 prompt.format 调用，添加新参数
old_fmt = """        prompt = POSITION_EXTRACT_PROMPT.format(
            company=company or "未知",
            title=title or "",
            content=content[:8000],  # 截断控制成本(校招公告通常 2000-6000 字)
            job_tree_block=job_tree.prompt_block(),
        )"""
new_fmt = """        prompt = POSITION_EXTRACT_PROMPT.format(
            company=company or "未知",
            industry=industry or "未知",
            company_type=company_type or "未知",
            location=location or "未知",
            education=education or "不限",
            title=title or "",
            content=content[:8000],  # 截断控制成本(校招公告通常 2000-6000 字)
            job_tree_block=job_tree.prompt_block(),
        )"""
assert old_fmt in src, "prompt.format not found"
src = src.replace(old_fmt, new_fmt)

# 3. 修改 enrich_announcement 中的调用，传入源表元数据
old_call = '        positions = self.extract_positions(content, company=company_name, title=ann_title)'
new_call = """        positions = self.extract_positions(
            content, company=company_name, title=ann_title,
            industry=announcement.get("industry_raw", ""),
            company_type=announcement.get("company_type_raw", ""),
            location=announcement.get("location", ""),
            education=announcement.get("education_req", ""),
        )"""
assert old_call in src, "call site not found"
src = src.replace(old_call, new_call)

with open("llm_enricher.py", "w") as f:
    f.write(src)
print("OK: extract_positions 签名和调用已修改")
