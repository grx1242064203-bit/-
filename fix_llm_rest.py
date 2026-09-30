#!/usr/bin/env python3
"""修改 extract_positions 签名/调用 + _apply_field_fallback"""

with open("llm_enricher.py") as f:
    src = f.read()

# 1. 修改 extract_positions 签名
old_sig = '    def extract_positions(self, content: str, company: str = "",\n                          title: str = "") -> List[Dict]:'
new_sig = '    def extract_positions(self, content: str, company: str = "",\n                          title: str = "", industry: str = "",\n                          company_type: str = "", location: str = "",\n                          education: str = "") -> List[Dict]:'
assert old_sig in src, "sig not found"
src = src.replace(old_sig, new_sig)

# 2. 修改 prompt.format
old_fmt = '            company=company or "未知",\n            title=title or "",\n            content=content[:8000],'
new_fmt = '            company=company or "未知",\n            industry=industry or "未知",\n            company_type=company_type or "未知",\n            location=location or "未知",\n            education=education or "不限",\n            title=title or "",\n            content=content[:8000],'
assert old_fmt in src, "fmt not found"
src = src.replace(old_fmt, new_fmt)

# 3. 修改调用点
old_call = '        positions = self.extract_positions(content, company=company_name, title=ann_title)'
new_call = '        positions = self.extract_positions(\n            content, company=company_name, title=ann_title,\n            industry=announcement.get("industry_raw", ""),\n            company_type=announcement.get("company_type_raw", ""),\n            location=announcement.get("location", ""),\n            education=announcement.get("education_req", ""),\n        )'
assert old_call in src, "call not found"
src = src.replace(old_call, new_call)

# 4. _apply_field_fallback 添加 requirements 默认
old_fb = '            if not pos.get("major_required"):\n                pos["major_required"] = "无明确专业要求"'
new_fb = '            if not pos.get("major_required"):\n                pos["major_required"] = "无明确专业要求"\n            if not pos.get("requirements"):\n                pos["requirements"] = "详见招聘公告"\n            if not pos.get("bonus_points"):\n                pos["bonus_points"] = ""'
assert old_fb in src, "fb not found"
src = src.replace(old_fb, new_fb)

with open("llm_enricher.py", "w") as f:
    f.write(src)
print("OK: 全部修改完成")
