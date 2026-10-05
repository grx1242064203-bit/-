#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert clean records to lark-cli batch-create JSON format."""

import json

def to_lark_format(record):
    """Convert to lark-cli format: select fields as arrays, JD链接 as markdown."""
    out = {}
    for k, v in record.items():
        # Select fields need to be arrays
        if k in ["岗位类别", "平台层级", "综合推荐度", "申请状态", "应届窗口", "是否在招"]:
            if isinstance(v, str):
                out[k] = [v]
            else:
                out[k] = v
        elif k == "JD链接":
            # JD链接 is text type, use markdown format [text](url)
            if isinstance(v, dict):
                text = v.get("text", "查看JD")
                link = v.get("link", "")
                out[k] = f"[{text}]({link})"
            else:
                out[k] = v
        else:
            out[k] = v
    return out

def main():
    with open("/workspace/.cache/main_records_clean.json") as f:
        records = json.load(f)
    
    converted = [to_lark_format(r) for r in records]
    
    # Build the JSON for lark-cli
    batch_json = {"create_records": converted}
    
    # Write to file (for piping to --json @file)
    with open("/workspace/.cache/batch_create_payload.json", "w", encoding="utf-8") as f:
        json.dump(batch_json, f, ensure_ascii=False)
    
    print(f"Prepared {len(converted)} records for batch create")
    print(f"Payload size: {len(json.dumps(batch_json, ensure_ascii=False))} chars")
    
    # Show one sample
    print("\nSample record:")
    print(json.dumps(converted[0], ensure_ascii=False, indent=2)[:800])

if __name__ == "__main__":
    main()
