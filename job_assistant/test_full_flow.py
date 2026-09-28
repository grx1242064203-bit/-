import sys
sys.path.insert(0, "/opt/job_assistant")
import os
os.environ["DATA_DIR"] = "/opt/job_assistant/data"

from content_fetcher import fetch_content_full
import requests

# 测试东吴证券
url = "https://mp.weixin.qq.com/s/nqP-jFgtwrG-ETi3BVAmMw"
print(f"=== 抓取: 东吴证券 ===")
result = fetch_content_full(url)
text = result.get("text", "")
images = result.get("images", [])
print(f"正文长度: {len(text)}")
print(f"图片数量: {len(images)}")

if text:
    print(f"正文前200字: {text[:200]}")
elif images:
    print("纯图片公告,下载第1张图并用 VL 识别...")
    img_url = images[0]
    print(f"图片URL: {img_url[:80]}")
    # 下载图片
    resp = requests.get(img_url, timeout=30, headers={"Referer": "https://mp.weixin.qq.com/"})
    print(f"图片下载: {len(resp.content)} bytes")
    # 保存临时文件
    img_path = "/tmp/test_article_img.jpg"
    with open(img_path, "wb") as f:
        f.write(resp.content)
    print(f"图片已保存: {img_path}")

    # 用 VL 识别
    import base64
    from llm_client import LLMClient
    llm = LLMClient()
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    vl_result = llm.chat_with_images(
        "请提取这张招聘公告图片中的所有文字内容,包括岗位名称、专业要求、学历要求、工作地点、职责要求等。直接输出文字,不要总结。",
        [f"data:image/jpeg;base64,{img_b64}"],
    )
    print(f"=== VL 识别结果({len(vl_result)}字) ===")
    print(vl_result[:500])
