#!/usr/bin/env python3
"""解析 to_archive.ndjson,构建归档到"已关闭岗位"表的 payload。
保留原 22 个字段值,修改: 是否在招=["否"], 关闭日期="2026-10-26 09:30:00"。"""
import json

records = []
with open("/workspace/.run/to_archive.ndjson", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

print(f"Loaded {len(records)} records to archive")
for r in records:
    print(f"  record_id={r.get('record_id')}")
    print(f"  fields: {list(r.keys())}")
    # 打印关键字段确认
    print(f"  去重hash: {r.get('去重hash')}")
    print(f"  公司: {r.get('公司')}")
    print(f"  是否在招(原): {r.get('是否在招')!r}")
    print()

# 构建归档 payload
CLOSE_DATE = "2026-10-26 09:30:00"
create_records = []
for r in records:
    # 复制所有字段(排除 record_id 元数据)
    new_rec = {}
    for k, v in r.items():
        if k == "record_id":
            continue
        new_rec[k] = v
    # 修改 是否在招 -> ["否"]
    new_rec["是否在招"] = ["否"]
    # 设置 关闭日期
    new_rec["关闭日期"] = CLOSE_DATE
    create_records.append(new_rec)

payload = {"create_records": create_records}
out_path = "/workspace/.run/archive_payload.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"\nPayload written to {out_path}")
print(f"Record count: {len(create_records)}")
for i, rec in enumerate(create_records):
    print(f"  [{i}] 公司={rec.get('公司')} hash={rec.get('去重hash')} 是否在招={rec.get('是否在招')} 关闭日期={rec.get('关闭日期')}")
