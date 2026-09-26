# 招聘情报助手 — 产品化部署指南

**面向任意专业、任意职业阶段**的通用招聘情报助手。

每日自动采集岗位 → 基于用户自定义画像评分 → 写入用户飞书 → 微信推送日报。

> 📚 **完整开发文档**请参阅 [docs/ 目录](./docs/README.md)，包含项目架构、模块详解、接口规范、开发规范、部署 SOP、问题记录、对抗性审查报告等。

## 产品定位

- **不限行业**:金融、互联网、快消、咨询、制造业等全行业通用
- **不限阶段**:应届校招、管培生、社招跳槽、实习全覆盖
- **用户自定义**:每个用户自己配置目标方向、关键词、技能、公司、城市
- **AI 评分**:基于 JD 正文(非标题)匹配用户画像,输出相关性+难度+建议

## 架构

```
小红书获客 → 付费购买 → 用户安装飞书应用 → 绑定微信(WxPusher)
                                              ↓
每日9点定时任务 ── 遍历活跃用户 ── 采集+评分 ── 写飞书表格 ── 生成日报文档
                                                         ↓
                                              微信推送摘要+飞书文档链接
```

## 环境要求

- Python 3.10+
- 公网可访问的 HTTPS 地址(接收飞书回调,MVP 可用 ngrok)
- 飞书开发者账号(创建商店应用)
- WxPusher 账号(微信推送)
- 搜索 API Key(Tavily 免费额度 或 SerpAPI)

## 快速开始

### 1. 安装依赖

```bash
pip install requests beautifulsoup4
```

### 2. 配置环境变量

```bash
export FEISHU_APP_ID="cli_xxx"           # 飞书应用 App ID
export FEISHU_APP_SECRET="xxx"           # 飞书应用 App Secret
export WXPUSHER_APP_TOKEN="AT_xxx"       # WxPusher 应用 Token
export TAVILY_API_KEY="tvly-xxx"         # 搜索 API(或用 SERPAPI_KEY)
export DATA_DIR="./data"                 # 用户数据存储目录
```

### 3. 创建飞书商店应用(需手动操作)

1. 访问 https://open.feishu.cn 创建企业自建应用
2. 权限配置(需申请):
   - `bitable:app` — 多维表格读写
   - `docx:document` — 文档创建
   - `drive:drive` — 云空间权限(分享+转所有权)
3. 事件订阅 → 配置请求地址(公网 HTTPS)
   - 订阅事件: `app_open`(应用被打开)、`app_install`(应用被安装)
4. 发布版本 → 申请商店上架(或用测试企业安装)
5. 获取 App ID + App Secret

### 4. 注册 WxPusher

1. 访问 https://wxpusher.zjiecode.com 注册
2. 创建应用,获取 App Token
3. 记下应用 ID(用户扫码关注用)

### 5. 启动回调服务(接收飞书安装事件)

```python
# callback_server.py (MVP 用 Flask)
from flask import Flask, request
from onboarding import handle_feishu_callback

app = Flask(__name__)

@app.route("/feishu/callback", methods=["POST"])
def callback():
    return handle_feishu_callback(request.get_json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

```bash
# 用 ngrok 暴露到公网(MVP)
ngrok http 8080
# 将 https://xxx.ngrok.io/feishu/callback 填入飞书事件订阅地址
```

### 6. 配置定时任务

```bash
# 每日 9 点执行(北京时间)
crontab -e
0 9 * * * cd /path/to/job_assistant && /usr/bin/python3 main.py daily >> /var/log/job_assistant.log 2>&1
```

### 7. 绑定用户微信推送

用户安装飞书应用后,为其绑定 WxPusher:

```bash
python bind_wxpusher.py <user_id>
# 打印二维码 → 用户扫码 → 输入 uid → 绑定完成
```

## 项目结构

```
job_assistant/
├── config.py            # 全局配置(环境变量注入)
├── models.py            # 用户/数据模型 + JSON 存储
├── schema.py            # 多维表格字段定义
├── feishu_client.py      # 飞书 API(建表/写记录/建文档/分享转权)
├── wxpusher_client.py    # WxPusher 微信推送
├── collector.py          # 岗位采集(可插拔搜索提供者)
├── scorer.py             # JD 评分引擎(基于正文匹配)
├── onboarding.py         # 用户 onboarding(建表+转所有权)
├── daily_runner.py       # 单用户每日任务执行
├── main.py               # 多用户调度入口
├── bind_wxpusher.py      # 用户微信绑定脚本
└── data/                 # 用户数据(自动创建)
    ├── users.json
    └── hashes/
```

## 核心设计决策(对抗性审查后)

| 决策 | 原因 |
|------|------|
| 飞书资源由应用身份创建,再转所有权给用户 | 避免 user_access_token 刷新复杂性,用户真正拥有数据 |
| WxPusher 而非微信服务号 | 服务号模板消息每月仅4条,不够日推;WxPusher 无限制 |
| JSON 文件存储用户数据 | MVP 阶段用户量小,无需 DB;后期可平滑迁移 |
| 搜索提供者可插拔 | Tavily/SerpAPI 可切换,不锁死单一供应商 |
| 评分基于 JD 正文而非 title | 避免误判,提升用户信任 |
| 单用户失败不影响其他用户 | 外层捕获异常,保证整体可用性 |
| 关闭岗位归档到独立表 | 主表只保留在招岗位,清爽干净 |

## 定价建议

| 档位 | 价格 | 服务内容 |
|------|------|---------|
| 体验版 | 9.9元 | 3天日报推送 |
| 秋招版 | 199元 | 9-11月每日推送 |
| 春招版 | 149元 | 2-4月每日推送 |
| 全年版 | 399元 | 全年每日推送 |

## 风险与应对

| 风险 | 应对 |
|------|------|
| 飞书 API 限流(5次/秒) | 重试+退避+用户间间隔 |
| WxPusher 服务宕机 | 推送失败不影响飞书数据,降级处理 |
| 搜索 API 配额耗尽 | 多供应商切换(Tavily→SerpAPI) |
| JD 页面 JS 渲染抓取失败 | 搜索结果 snippet 兜底 + 标注抓取失败 |
| 用户 token 失效 | 应用身份创建资源,不依赖用户 token |

## 获客(小红书)

内容方向:
- 测评类:「我用AI筛了50家外资管培,这5家接受往届生」
- 干货类:「秋招信息差:这些官网岗位没人告诉你」
- 结果类:「日报推送第30天,我拿到了XX面试」

## 扩展方向

- 简历定制(根据目标JD自动优化简历)
- 模拟面试(AI 生成面试题)
- 内推对接(匹配已有用户的目标公司)
- 移动端(飞书小程序/微信小程序)
