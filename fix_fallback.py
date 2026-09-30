#!/usr/bin/env python3
"""修改 _apply_field_fallback: requirements 空值填'详见招聘公告'"""

with open("llm_enricher.py") as f:
    src = f.read()

old_fb = """        ann_location = announcement.get("location", "") or ""
        ann_education = announcement.get("education_req", "") or ""
        for pos in positions:
            if not pos.get("city") and ann_location:
                pos["city"] = ann_location
            if not pos.get("min_education") and ann_education:
                pos["min_education"] = ann_education
            if not pos.get("major_required"):
                pos["major_required"] = "无明确专业要求\""""

new_fb = """        ann_location = announcement.get("location", "") or ""
        ann_education = announcement.get("education_req", "") or ""
        for pos in positions:
            if not pos.get("city") and ann_location:
                pos["city"] = ann_location
            if not pos.get("min_education") and ann_education:
                pos["min_education"] = ann_education
            if not pos.get("major_required"):
                pos["major_required"] = "无明确专业要求"
            if not pos.get("requirements"):
                pos["requirements"] = "详见招聘公告"
            if not pos.get("bonus_points"):
                pos["bonus_points"] = ""\""""

assert old_fb in src, "fallback not found"
src = src.replace(old_fb, new_fb)

with open("llm_enricher.py", "w") as f:
    f.write(src)
print("OK: _apply_field_fallback 已添加 requirements 默认值")
