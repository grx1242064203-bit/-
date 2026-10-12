"""批量标注 25 条评测集 — 基于 GLM 对公告原文的人工分析。"""
import json
from pathlib import Path

EVALSET_PATH = Path(__file__).resolve().parent / "evalset_positions.json"

with open(EVALSET_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# 25 条标注结果
annotations = {
    "EVAL-001": {
        "correct_position_count": 4,
        "split_verdict": "under_split",
        "missed_positions": ["模拟设计", "数字设计", "数字验证"],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "产品工程师", "field": "min_education", "wrong": "本科", "correct": "硕士"},
            {"position_title": "产品工程师", "field": "city", "wrong": "上海", "correct": "昆山,西安,南京"},
        ],
        "overall_score": 1,
        "bad_case_type": "missed",
        "notes": "标题含4个岗位名（模拟设计/数字设计/数字验证/产品工程师）无分隔符，LLM只取最后一个。学历填本科但标题写硕士起。城市幻觉为上海但实际昆山/西安/南京。正文几乎为空（仅推广信息），LLM缺乏正文依据。",
    },
    "EVAL-002": {
        "correct_position_count": 6,
        "split_verdict": "under_split",
        "missed_positions": ["算法", "芯片", "软件", "硬件", "测试"],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 2,
        "bad_case_type": "missed",
        "notes": "标题列出6个岗位方向（算法/芯片/软件/硬件/测试/业务拓展），LLM只取最后一个'业务拓展'。与EVAL-001同类问题：标题多岗位无分隔符时LLM倾向只取末尾。",
    },
    "EVAL-003": {
        "correct_position_count": 1,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "标题虽列多个专业类（电子信息/机械/材料等），但正文表明这些是投资经理需覆盖的行业领域，非独立岗位。LLM正确判断为1个岗位，归类为金融/股权投资准确。",
    },
    "EVAL-004": {
        "correct_position_count": 6,
        "split_verdict": "under_split",
        "missed_positions": ["动力电池系统开发", "世界模型", "数据科学", "车载数字人大模型", "智慧底盘系统架构"],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "VLM/VLA大模型算法工程师", "field": "city", "wrong": "武汉,北京", "correct": "武汉"},
        ],
        "overall_score": 2,
        "bad_case_type": "missed",
        "notes": "标题列6个博士岗位方向，LLM只拆出1个并自作主张添加'算法工程师'后缀。城市多加了北京（正文未提北京）。再次印证：标题多岗位无分隔符时LLM严重漏拆。",
    },
    "EVAL-005": {
        "correct_position_count": 1,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "单岗位公告（助理咨询顾问），LLM拆岗正确。归类为金融/行业研究略有偏差（咨询行业更适合归为'职能/咨询'但岗位树可能无此子类），硬技能提取合理。",
    },
    "EVAL-006": {
        "correct_position_count": 2,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "2026-2027年安永秋季应届毕业生校园招聘项目", "field": "city", "wrong": "", "correct": "北京,上海,香港,深圳,广州等19城"},
            {"position_title": "2026-2027年安永审计寒假实习生", "field": "city", "wrong": "", "correct": "北京,上海,香港,深圳,广州等19城"},
        ],
        "overall_score": 4,
        "bad_case_type": "wrong_field",
        "notes": "2个项目（全职校招+审计寒假实习）拆分正确。但城市字段全空，实际标题列了19个城市。硬技能(Tableau/Power BI/R/Python/SAS/SQL)是从正文提取的，合理但不确定是否两个岗位都适用同样技能。",
    },
    "EVAL-007": {
        "correct_position_count": 8,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "标题8个岗位（功率硬件/控制硬件/电力电子软件/嵌入式ARM-DSP/算法数据/算法/AI/后端EMS）全拆出。归类合理（研发大类下细分），城市杭州+苏州正确，专业要求提取准确。标杆案例。",
    },
    "EVAL-008": {
        "correct_position_count": 7,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "全部7个岗位", "field": "city", "wrong": "深圳", "correct": "深圳,苏州,西安"},
        ],
        "overall_score": 3,
        "bad_case_type": "wrong_field",
        "notes": "标题7个岗位全拆出，但正文几乎为空（视频内容OCR），LLM仅凭标题拆分。城市只填深圳漏了苏州和西安。硬技能和职责为LLM推测生成，非正文提取。",
    },
    "EVAL-009": {
        "correct_position_count": 4,
        "split_verdict": "over_split",
        "missed_positions": [],
        "hallucinated_positions": ["AI算法实习生", "适航实习生", "嵌入式软件实习生"],
        "category_errors": [],
        "field_errors": [
            {"position_title": "飞控算法工程师-飞控软件/控制律方向", "field": "city", "wrong": "南京", "correct": "深圳,南京,西安"},
            {"position_title": "嵌入式软件工程师", "field": "city", "wrong": "西安", "correct": "深圳,南京,西安"},
        ],
        "overall_score": 2,
        "bad_case_type": "hallucinated",
        "notes": "标题仅4个全职岗位（AI算法/适航/飞控算法/嵌入式软件），LLM额外幻觉3个'实习生'岗位（正文未见实习招聘信息）。城市拆分错误：将多城市分配到不同岗位，而非所有岗位都可选多城市。",
    },
    "EVAL-010": {
        "correct_position_count": 7,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [
            {"position_title": "税务服务岗", "wrong": "职能/财务", "correct": "金融/税务（岗位树无税务子类，财务为最近似）"},
            {"position_title": "科技咨询-技术咨询方向岗", "wrong": "开发/开发", "correct": "职能/咨询或IT咨询"},
        ],
        "field_errors": [
            {"position_title": "税务服务岗", "field": "city", "wrong": "", "correct": "上海,成都,重庆,北京,深圳,广州"},
            {"position_title": "风险咨询-治理风险和合规服务岗", "field": "city", "wrong": "", "correct": "上海,成都,重庆,北京,深圳,广州"},
            {"position_title": "科技咨询-技术咨询方向岗", "field": "city", "wrong": "", "correct": "上海,成都,重庆,北京,深圳,广州"},
            {"position_title": "科技咨询-财务咨询方向岗", "field": "city", "wrong": "", "correct": "上海,成都,重庆,北京,深圳,广州"},
        ],
        "overall_score": 3,
        "bad_case_type": "wrong_field",
        "notes": "7个岗位拆出正确。但4个岗位城市字段为空（实际6城可选）。科技咨询岗归类为'开发/开发'明显不当。部分岗位职责描述过于笼统（'负责XX相关工作'）。",
    },
    "EVAL-011": {
        "correct_position_count": 9,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "全部9个岗位", "field": "city", "wrong": "", "correct": "杭州"},
        ],
        "overall_score": 4,
        "bad_case_type": "wrong_field",
        "notes": "9个岗位全拆出正确（AI应用算法/NLP算法/ML算法/数据分析/行业运营/AI产品经理/AI数据工程/市场营销/商家商品运营）。但所有岗位城市字段为空，实际应为杭州。归类整体合理。",
    },
    "EVAL-012": {
        "correct_position_count": 3,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [
            {"position_title": "科研岗", "wrong": "算法/理工科博士研究岗", "correct": "研究类/科研岗（岗位树无科研子类）"},
        ],
        "field_errors": [
            {"position_title": "技术岗", "field": "min_education", "wrong": "本科", "correct": "硕士"},
            {"position_title": "管理岗", "field": "min_education", "wrong": "本科", "correct": "硕士"},
        ],
        "overall_score": 3,
        "bad_case_type": "wrong_field",
        "notes": "3个岗位（科研/技术/管理）拆出正确。但公告实为'校园交流日'活动通知而非正式招聘，LLM仍按招聘处理。学历：标题写硕士起，但LLM将技术岗和管理岗填为本科。科研岗归类为'算法/理工科博士研究岗'不当。",
    },
    "EVAL-013": {
        "correct_position_count": 7,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [
            {"position_title": "品牌经理助理实习生", "wrong": "设计与内容/内容创意", "correct": "商业(销售与市场)/市场营销"},
            {"position_title": "电商互金助理实习生", "wrong": "运营与供应链/用户运营", "correct": "运营与供应链/产品运营或电商运营"},
        ],
        "field_errors": [],
        "overall_score": 4,
        "bad_case_type": "wrong_category",
        "notes": "7个岗位拆出正确（交易员助理/合规助理/审计助理/基金会计/品牌助理/电商互金助理/综合人力助理）。品牌经理助理归类为内容创意不当，应为市场营销。学历区分正确（全职硕士/实习本科）。",
    },
    "EVAL-014": {
        "correct_position_count": 3,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [
            {"position_title": "科研岗", "wrong": "算法/理工科博士研究岗", "correct": "研究类/科研岗"},
        ],
        "field_errors": [
            {"position_title": "技术岗", "field": "min_education", "wrong": "本科", "correct": "硕士"},
            {"position_title": "管理岗", "field": "min_education", "wrong": "本科", "correct": "硕士"},
        ],
        "overall_score": 3,
        "bad_case_type": "wrong_field",
        "notes": "与EVAL-012为同一公告（中科院空天院），重复采集。问题相同：学历填错（本科→应为硕士），科研岗归类不当。",
    },
    "EVAL-015": {
        "correct_position_count": 4,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "4个岗位（算法研发/仿真算法-器件/仿真算法-电路/仿真算法-AI模型）全拆出。归类合理（算法/芯片半导体），城市正确（北京/成都/重庆），学历硕士正确。标杆案例。",
    },
    "EVAL-016": {
        "correct_position_count": 12,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 4,
        "bad_case_type": "none",
        "notes": "标题仅2大类（芯片硬件类/芯片软件类），正文细分12个方向，LLM全拆出。归类合理（芯片半导体/AI工程/开发）。岗位名过于简短（如'验证'、'推理'、'算子'），缺少完整岗位名。城市4城正确。",
    },
    "EVAL-017": {
        "correct_position_count": 14,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "标题14个岗位全拆出（模拟IC设计/数字IC设计/数字验证/工艺开发/版图设计/版图/PDK/测试研发/项目管理/TPE/PCB Layout/应用/销售/现场应用）。归类准确，城市12城全填。标杆案例。",
    },
    "EVAL-018": {
        "correct_position_count": 16,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "全部16个岗位", "field": "city", "wrong": "", "correct": "上海,常州,深圳"},
        ],
        "overall_score": 4,
        "bad_case_type": "wrong_field",
        "notes": "标题16个岗位全拆出，归类合理（机器人/开发/硬件/算法/管培）。但所有岗位城市字段为空，实际为上海/常州/深圳。学历区分正确（算法岗硕士/其余本科/研究员博士）。",
    },
    "EVAL-019": {
        "correct_position_count": 18,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 5,
        "bad_case_type": "none",
        "notes": "标题18个岗位全拆出（信动力M/T计划系列）。归类合理（运营/商业/硬件/开发/产品），城市正确（青岛/佛山等）。岗位名保留完整前缀（信动力M/T计划-），便于用户识别。标杆案例。",
    },
    "EVAL-020": {
        "correct_position_count": 11,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [
            {"position_title": "销售经理岗（外贸总监）", "wrong": "商业(销售与市场)/海外销售", "correct": "商业(销售与市场)/销售管理或总监"},
        ],
        "field_errors": [],
        "overall_score": 4,
        "bad_case_type": "wrong_category",
        "notes": "标题11个岗位全拆出。归类基本合理。'销售经理岗（外贸总监）'归类为海外销售有偏差，实际是销售总监级别。城市成都正确。",
    },
    "EVAL-021": {
        "correct_position_count": 39,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "全部39个岗位", "field": "city", "wrong": "武汉", "correct": "武汉,北京,上海,宁波,乌鲁木齐,深圳,石家庄,厦门,济南,广州,郑州等12城"},
        ],
        "overall_score": 3,
        "bad_case_type": "wrong_field",
        "notes": "标题列5大领域，正文细分39个岗位，LLM全拆出。拆岗数量正确。但所有岗位城市统一填武汉，实际标题列了12城可选。部分岗位（党群工作/纪检监察/公司办公室）虽在正文列出，但非典型校招岗位。归类整体合理。",
    },
    "EVAL-022": {
        "correct_position_count": 20,
        "split_verdict": "over_split",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "全部31个岗位", "field": "city", "wrong": "上海", "correct": "上海,杭州"},
        ],
        "overall_score": 2,
        "bad_case_type": "hallucinated",
        "notes": "标题仅3-4个大方向（空间智能/机器人动力模组/雷达研发/智能制造&质量），正文细分多个岗位。LLM拆出31个但存在问题：部分岗位是合并形式（如'FPGA/数字设计/模拟设计/IC验证工程师'应拆为4个却合为1个，'光学/机械/材料/工艺/仿真设计工程师'应拆为5个却合为1个）。实际独立岗位约20个。城市只填上海漏了杭州。正文明确说'尚未包含具体专业要求及学历要求'，但LLM仍填了专业和学历（幻觉）。",
    },
    "EVAL-023": {
        "correct_position_count": 24,
        "split_verdict": "under_split",
        "missed_positions": ["热设计工程师(已在)", "产品制造工程师", "AI应用开发工程师", "微组装工程师", "知识分享工程师", "实习生", "现场应用工程师", "IT开发工程师", "供应链管培生", "射频IC工程师", "模拟IC工程师", "半导体工艺工程师", "LTCC工艺工程师", "FPGA工程师"],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 2,
        "bad_case_type": "missed",
        "notes": "正文标注共24个岗位（'开启新的工作（24）'），LLM仅拆出10个，漏拆14个。标题列了15+岗位名，LLM遗漏大部分。严重漏拆案例。",
    },
    "EVAL-024": {
        "correct_position_count": 1,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [],
        "overall_score": 3,
        "bad_case_type": "none",
        "notes": "标题'管培生'单一岗位，LLM拆出1个正确。但公告实为2026届管培生入职培训回顾（非正式招聘公告），LLM仍按招聘处理。场景理解偏差但拆岗结果无错。",
    },
    "EVAL-025": {
        "correct_position_count": 2,
        "split_verdict": "correct",
        "missed_positions": [],
        "hallucinated_positions": [],
        "category_errors": [],
        "field_errors": [
            {"position_title": "总行科技专培生", "field": "city", "wrong": "湛江", "correct": "湛江（总行）"},
            {"position_title": "分行校招生", "field": "city", "wrong": "湛江,广州,深圳,重庆,东莞,肇庆,江门,中山", "correct": "东莞,中山,广州,江门,深圳,湛江,肇庆,重庆（8城）"},
        ],
        "overall_score": 4,
        "bad_case_type": "none",
        "notes": "2个岗位（总行科技专培生/分行校招生）拆出正确。城市基本正确但总行专培生可能也分配到总行所在地湛江。学历本科正确，专业要求提取合理。",
    },
}

# 写入标注
for item in data:
    eid = item["id"]
    if eid in annotations:
        item["annotation"] = annotations[eid]
    else:
        print(f"WARNING: {eid} not found in annotations dict")

with open(EVALSET_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 统计
done = sum(1 for i in data if i.get("annotation", {}).get("correct_position_count") is not None)
print(f"已标注: {done}/{len(data)} 条")

# 输出摘要
print("\n标注摘要:")
print(f"{'ID':<10} {'分层':<10} {'LLM拆':<6} {'实际':<6} {'判定':<12} {'评分':<4} {'BadCase':<15}")
print("-" * 70)
for item in data:
    ann = item.get("annotation", {})
    print(f"{item['id']:<10} {item['bucket']:<10} {item['llm_position_count']:<6} {ann.get('correct_position_count','?'):<6} {ann.get('split_verdict','?'):<12} {ann.get('overall_score','?'):<4} {ann.get('bad_case_type','?'):<15}")
