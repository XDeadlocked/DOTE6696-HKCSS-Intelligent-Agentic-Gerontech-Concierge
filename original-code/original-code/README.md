# HKCSS Intelligent Agentic Gerontech Concierge

## 1. 项目概述

本项目对应课程项目 **DOTE6696 HKCSS: The "Intelligent Agentic Gerontech Concierge"**，目标是为 HKCSS / ERentEBuy 乐龄科技租赁与购买场景构建一个文字式智能顾问 Agent。

ERentEBuy 平台包含大量乐龄科技、复康设备、护理用品和辅助器具。现实使用中，长者或照顾者通常只知道自己的困难，例如“中风后手部不灵活”“爸爸经常从椅子滑下来”“家中门口很窄”，但未必知道应搜索“高背轮椅”“倾斜功能”“座宽”“承重”等专业术语。因此，本项目设计 Agent 扮演“虚拟社工 / 乐龄科技顾问”的角色，通过多轮问答、规则推理、产品资料检索和安全提醒，把模糊生活问题转化为具体产品建议。

项目当前版本主要由以下部分组成：

- 结构化产品主数据
- 产品详情 JSON
- 诊断式问答规则树
- 产品类别细化问答规则
- 护理知识 Chroma 向量库
- 主 Agent Notebook
- 产品数据同步与维护脚本

## 2. 与课程要求的对应关系

课程说明中要求最终系统覆盖三个核心能力。本项目当前实现与这些要求的对应关系如下。

### 2.1 Diagnostic Agent Workflow

课程要求系统具备主动聆听、意图识别和动态访谈能力，而不是简单关键词搜索。

本项目中的对应实现：

- `version_final.ipynb.ipynb` 中定义了初始引导和意图路由逻辑。
- 用户可进入护理咨询、问题解决型产品推荐、产品浏览三类路径。
- `02_LOGIC_RULE.json` 保存诊断式问答规则树。
- `LogicRuleEngine` 负责加载规则节点、判断节点类型、寻找后续节点并汇总推荐方向。
- 对于多选分支，系统会记录待处理分支并逐步询问，模拟人工顾问的评估流程。

### 2.2 Spec-Check RAG Architecture

课程要求系统能够从结构化库存和非结构化资料中检索事实，并根据用户约束进行判断。

本项目中的对应实现：

- `01_PRODUCT_MASTER_BASE.csv` 提供可维护的产品主数据。
- `03_PRODUCT_INFO.json` 提供更完整的产品详情、价格、库存和描述。
- `nursing_chroma_db/` 保存护理知识向量库。
- Notebook 中使用 `BAAI/bge-m3` embedding 和 Chroma 支持语义检索。
- 库存搜索函数会优先从真实产品目录中查找结果，避免输出不存在的产品。

### 2.3 Safety Guardrails & Hallucination Evaluation

课程特别强调医疗与照护场景中的安全性和防幻觉。

本项目中的对应实现：

- 护理咨询 prompt 要求回答必须基于参考知识，知识库没有的信息应明确说明。
- 推荐产品时通过库存 CSV / JSON 做约束，降低“编造产品”的风险。
- 输出中包含免责声明和专业人士咨询提醒。
- 对医疗、复康和护理问题，系统定位为辅助建议，不替代医生、物理治疗师、职业治疗师或社工的专业判断。

## 3. 目录结构

```text
.
|-- 01_PRODUCT_MASTER_BASE.csv
|-- 02_LOGIC_RULE.json
|-- 03_PRODUCT_INFO.json
|-- 04_PRODUCT_REFINE_LOGIC.json
|-- README.md
|-- update_product_data.py
|-- version_final.ipynb.ipynb
`-- nursing_chroma_db/
    |-- chroma.sqlite3
    `-- e4095800-e097-4ea8-a572-4f1c514ddf2d/
        |-- data_level0.bin
        |-- header.bin
        |-- length.bin
        `-- link_lists.bin
```

主 Notebook 文件为 `version_final.ipynb.ipynb`，与本目录中的代码、数据和向量库文件配套使用。

## 4. 文件说明

### 4.1 `version_final.ipynb.ipynb`

这是项目的主程序 Notebook，也是 Agent 的主要运行入口。它整合了环境初始化、向量库构建、LLM 初始化、规则树推理、产品浏览、护理咨询、库存搜索和主交互流程。

Notebook 当前共有 **17 个代码单元**，没有独立 markdown 单元，因此 README 中对代码结构进行集中说明。

### 4.2 `01_PRODUCT_MASTER_BASE.csv`

产品主数据表，是当前产品数据维护的 source of truth。经检查，该 CSV 当前包含 **516** 条产品记录。

主要字段包括：

- `product_name`: 产品名称
- `stock_status`: 库存状态
- `in_stock`: 是否有货
- `description`: 产品描述
- `net_weight`: 净重
- `dimension_height`: 产品高度
- `dimension_length`: 产品长度
- `dimension_width`: 产品宽度
- `category_name`: 产品类别名称
- `category_id`: 产品类别编号

该文件适合进行人工编辑和批量维护。修改后可通过 `update_product_data.py` 同步到产品详情 JSON。

### 4.3 `03_PRODUCT_INFO.json`

产品详情 JSON，目前包含 **529** 条产品详情记录。相比 CSV，该文件保留了更多电商和库存相关字段，例如：

- `Name`
- `Sales Price`
- `Quantity On Hand`
- `eCommerce Description`
- `Product/Description`
- `Net Weight`
- `Dimension Height`
- `Dimension Length`
- `Dimension Width`
- `Category Name`
- `Category ID`
- `Stock Status`
- `In Stock`

Agent 在展示产品详情、核对推荐结果、补充产品价格和库存信息时会使用该文件。

### 4.4 `02_LOGIC_RULE.json`

诊断式问答规则树，当前包含 **31** 个逻辑节点，起始节点为 `node_01_role`。

该文件的作用是模拟人工社工或照护顾问的问诊路径。系统会先识别用户身份，再根据疾病背景、生活困难、行动能力、照护风险等信息逐步分支，最后形成产品类别或设备方向建议。

典型节点类型包括：

- `single_choice`: 单选问题
- `multi_choice`: 多选问题
- `recommend`: 推荐结果节点

该文件是 Diagnostic Agent Workflow 的核心数据来源。

### 4.5 `04_PRODUCT_REFINE_LOGIC.json`

产品类别细化规则，当前覆盖 **18** 个产品类别。

当用户已经进入某个产品类别后，该文件用于继续缩小需求范围。例如用户被判断可能需要复康设备，系统会进一步询问是上肢训练、下肢助行、手部复康还是其他目标，再给出更具体的产品候选。

### 4.6 `nursing_chroma_db/`

护理知识相关的 Chroma 向量数据库。该目录包含：

- `chroma.sqlite3`: Chroma 元数据与存储文件
- `data_level0.bin`
- `header.bin`
- `length.bin`
- `link_lists.bin`

这些文件共同构成护理知识 RAG 检索库，用于回答长者护理、辅具使用和照护技巧相关问题。

### 4.7 `update_product_data.py`

产品数据同步脚本。它将 `01_PRODUCT_MASTER_BASE.csv` 视为主数据来源，可以检查 CSV 数据结构，并将更新同步到 `03_PRODUCT_INFO.json`。

主要功能：

- 校验 CSV 是否包含必要字段
- 检查产品名、库存字段、数值字段等常见问题
- 根据 CSV 更新 JSON 中的产品名称、描述、类别、库存和尺寸
- 保留 JSON 中已有的价格、库存数量、视频链接等补充信息
- 可选备份旧 JSON
- 可选重建产品向量库

常用命令：

```bash
python update_product_data.py --dry-run
python update_product_data.py
python update_product_data.py --prune-json
python update_product_data.py --rebuild-vector
```

当前数据同步状态如下：

- CSV 产品行数：516
- 原 JSON 产品数：529
- 从 CSV 更新的 JSON 产品数：516
- JSON 额外保留产品数：13
- 输出 JSON 产品数：529

## 5. `version_final.ipynb.ipynb` 代码结构说明

下面按 Notebook 的代码单元顺序说明主程序逻辑。

### Cell 1: 基础导入

该单元导入项目所需的基础库和 LangChain / LangGraph 相关模块。主要包括：

- 文件与路径处理：`os`, `Path`, `shutil`
- 数据处理：`json`, `csv`, `html`, `re`
- 类型定义：`TypedDict`, `List`, `Dict`, `Optional`, `Tuple`
- LangChain 文档对象、向量库、embedding、prompt 和 message 类型
- LangGraph 的 `StateGraph`, `START`, `END`

该单元是整个 Notebook 的依赖基础。

### Cell 2: 清理 Chroma 缓存

该单元会清理旧的 Chroma 缓存目录，避免历史运行产生的向量库与当前流程冲突。

涉及路径包括：

- `./chroma_db`
- `./chroma_db/product_vectors`
- `./chroma_db/rule_vectors`
- `./chroma_db/nursing_vectors`

清理后会调用垃圾回收，释放可能被占用的资源。

### Cell 3: Embedding 初始化

该单元初始化 embedding 模型：

```text
BAAI/bge-m3
```

并设置 Hugging Face 镜像与本地缓存目录。Embedding 用于将规则节点、护理知识或产品文本转换成向量，以支持语义检索。

### Cell 4: 逻辑规则加载与规则向量库构建

该单元定义 `load_logic_rules(json_path)`，负责读取 `02_LOGIC_RULE.json` 并将规则节点转换为 LangChain `Document`。

每个规则节点会包含：

- 节点 ID
- 节点类型
- 问题文本
- 选项
- 下一节点映射
- 推荐摘要

随后系统将规则节点写入 Chroma 向量库，方便后续根据语义或节点 ID 检索相关规则。

### Cell 5: LLM 初始化

该单元初始化大语言模型，默认使用 OpenRouter 兼容接口。

逻辑包括：

- 从环境变量 `OPENROUTER_API_KEY` 读取 API key
- 如果没有检测到有效 key，则提示并使用 mock fallback
- 准备候选模型列表
- 初始化 ChatOpenAI 兼容客户端

这部分使项目可以在真实 LLM 环境和无 key 的演示环境之间切换。

### Cell 6: 护理咨询 Prompt

该单元定义 `NURSING_CONSULT_SYSTEM_PROMPT`，用于护理咨询 RAG。

Prompt 的核心约束包括：

- 回答必须基于提供的参考知识
- 不允许引入未经证实的外部知识
- 如果知识库没有相关信息，需要明确说明
- 对医疗风险问题提醒用户咨询医生或复康护士
- 输出应面向长者和照顾者，语言清晰、稳妥

该单元是安全边界的重要组成部分。

### Cell 7: AgentState 与意图分类

该单元定义 `AgentState`，用于保存 Agent 对话状态。

主要字段包括：

- `messages`: 对话消息
- `user_input`: 当前用户输入
- `intent`: 用户意图
- `is_intent_clear`: 意图是否明确
- `logic_rule_qa_history`: 规则问答历史
- `collected_recommendations`: 已收集推荐
- `selected_category`: 已选产品类别
- `final_answer`: 最终回答

同时，该单元还定义意图分类 prompt，用于判断用户应进入护理咨询、产品问题解决还是产品浏览路径。

### Cell 8: `LogicRuleEngine`

`LogicRuleEngine` 是规则树推理的核心类。

主要方法：

- `__init__`: 加载 `02_LOGIC_RULE.json`
- `is_recommend_node`: 判断某个节点是否为推荐节点
- `get_question_node`: 读取问题节点内容
- `get_next_nodes`: 根据用户选择寻找后续节点
- `get_recommendation_summary`: 汇总推荐节点中的推荐内容

该类把 JSON 规则文件封装为可调用的推理引擎，使 Notebook 主流程不用直接操作复杂 JSON。

### Cell 9: 节点运行与用户选项匹配

该单元定义规则节点执行和选项匹配相关函数。

主要函数：

- `run_node_logic`: 根据节点类型和用户选择返回后续节点
- `get_next_node_id`: 读取某个选项对应的下一节点
- `llm_match_options`: 用 LLM 将自然语言回答匹配到可选项
- `is_numeric_input`: 判断用户是否输入数字
- `parse_number_input`: 将数字输入解析为选项
- `resolve_user_input`: 综合处理数字输入、文本输入和 LLM 匹配

这部分让系统既支持输入选项编号，也支持用户用自然语言回答。

### Cell 10: 规则树会话运行

该单元定义 `LogicRuleState` 和规则树会话函数。

主要函数：

- `init_logic_rule_state`: 初始化规则树状态
- `llm_present_question`: 用更自然的语言展示规则问题
- `llm_present_recommendation`: 整理推荐结果表达
- `run_logic_rule_session`: 运行完整规则树问答流程
- `_display_final_recommendations`: 展示最终收集到的推荐方向

该单元负责真正执行多轮诊断式问答。对于多选问题，它会把多个分支放入 `pending_branches`，逐个处理，最后收集推荐结果。

### Cell 11: `ProductBrowseEngine`

`ProductBrowseEngine` 负责产品浏览场景，即用户不是带着具体问题求解，而是想查看某类产品。

主要方法：

- `_load_product_details`: 读取 `03_PRODUCT_INFO.json`
- `_load_category_rows`: 读取产品 CSV
- `_build_catalog`: 构建按类别组织的产品目录
- `get_categories`: 返回可浏览类别
- `match_category`: 将用户输入匹配到产品类别
- `list_products`: 列出某类别下的产品
- `format_product_list`: 格式化产品列表
- `format_product_detail`: 格式化单个产品详情
- `select_product`: 根据编号或名称选择产品

该类对应课程中的 browsing intent，可让用户直接查看产品类别和型号。

### Cell 12: 产品浏览会话

该单元定义 `run_product_browse_session()`。

流程包括：

1. 展示产品类别
2. 用户选择类别
3. 系统列出该类别产品
4. 用户选择某个产品
5. 系统展示产品详情
6. 用户可继续浏览或退出

这部分用于处理“查看平台可提供哪些产品”这类浏览型意图。

### Cell 13: 护理咨询 RAG 会话

该单元定义 `run_nursing_consultation_session()`。

流程包括：

1. 用户输入护理、辅具使用或照护技巧问题
2. 系统从护理知识向量库检索相关资料
3. 将检索内容和用户问题放入护理咨询 prompt
4. LLM 生成基于参考资料的回答
5. 用户可继续追问或退出

这部分对应课程中“非结构化知识库”的使用。

### Cell 14: 初始引导与核心意图路由

该单元定义：

- `initial_guide_node`
- `handle_choice_node_v2`

系统启动后会先展示三个入口：

1. 护理咨询
2. 产品-问题解决型
3. 产品-浏览了解型

`handle_choice_node_v2` 根据用户选择调用不同子流程：

- 护理咨询 -> `run_nursing_consultation_session`
- 问题解决型 -> `run_logic_rule_session` 和后续产品推荐
- 浏览了解型 -> `run_product_browse_session`

这是整个 Agent 的顶层路由。

### Cell 15: 产品细化问答与设备跟进

该单元读取 `04_PRODUCT_REFINE_LOGIC.json`，并定义产品类别细化相关函数。

主要函数：

- `load_product_refine_logic`: 加载细化规则
- `_print_banner`: 打印会话标题
- `_parse_choice`: 解析用户选择
- `_prompt_custom_need`: 处理“其他需求”的自由输入
- `_trigger_inventory_search`: 根据推荐词触发库存搜索
- `_ask_and_recommend`: 执行某一类别下的细化问答
- `_handle_no_product`: 处理找不到产品时的情况
- `_handle_redirect`: 处理类别跳转
- `run_device_followup`: 根据规则树推荐结果继续追问并搜索库存

这部分连接“规则树推荐方向”和“真实库存产品”，是从诊断到产品落地的重要桥梁。

### Cell 16: 库存搜索函数

该单元实现产品目录加载、严格搜索、LLM 辅助搜索、产品详情匹配和结果展示。

主要函数：

- `load_product_catalog`: 从 `01_PRODUCT_MASTER_BASE.csv` 加载产品目录
- `_safe_text`: 安全处理空文本
- `_format_dimensions`: 格式化产品尺寸
- `_extract_recommend_tokens`: 从推荐语中提取候选关键词
- `search_inventory_strict`: 用产品名、类别、推荐词进行严格匹配
- `_summarize_row_for_llm`: 将产品行整理为 LLM 可读摘要
- `_extract_indices_from_text`: 从 LLM 输出中提取产品编号
- `_fallback_keyword_products`: 关键词兜底搜索
- `search_inventory_with_llm`: LLM 辅助匹配库存产品
- `_format_sales_price`: 格式化价格
- `_normalize_product_name`: 标准化产品名用于匹配
- `_strip_product_html`: 清理 HTML 描述
- `_load_inventory_product_details`: 加载 `03_PRODUCT_INFO.json`
- `_best_inventory_detail_match`: 匹配最接近的产品详情
- `_get_inventory_product_detail`: 获取产品详情
- `display_inventory_results`: 展示库存搜索结果
- `build_inventory_tasks`: 根据推荐方向生成库存搜索任务

这部分重点解决“推荐必须落在真实库存中”的问题，是防止产品幻觉的关键实现。

### Cell 17: 主程序入口

最后一个单元是主程序入口。

主要工作：

- 打印系统标题：智能助手 v3.0
- 检查必要函数和对象是否已定义
- 构建 LangGraph 状态图
- 添加初始引导节点和意图处理节点
- 设置 `START -> initial_guide -> handle_choice -> END`
- 编译 graph
- 进入循环式用户交互

用户运行到此单元后，即可在 Notebook 中体验完整 Agent 流程。

## 6. 核心数据流

项目的数据流可以概括为：

```text
用户输入
  |
  v
初始引导与意图识别
  |
  |-- 护理咨询
  |     -> nursing_chroma_db 检索
  |     -> 护理咨询 prompt
  |     -> 基于知识库回答
  |
  |-- 问题解决型产品推荐
  |     -> 02_LOGIC_RULE.json 规则树问诊
  |     -> 04_PRODUCT_REFINE_LOGIC.json 类别细化
  |     -> 01_PRODUCT_MASTER_BASE.csv 库存搜索
  |     -> 03_PRODUCT_INFO.json 产品详情补充
  |     -> 推荐结果与安全提醒
  |
  `-- 产品浏览
        -> 产品类别列表
        -> 产品列表
        -> 产品详情展示
```

## 7. 如何运行

### 7.1 环境准备

建议使用 Python 3.10 或以上版本。主要依赖包括：

- `langchain`
- `langgraph`
- `langchain_chroma`
- `langchain_huggingface`
- `chromadb`
- `sentence-transformers`
- `pandas`
- `openai` 或兼容 OpenAI API 的客户端

如果使用 OpenRouter，需要设置环境变量：

```bash
set OPENROUTER_API_KEY=<OPENROUTER_API_KEY>
```

macOS / Linux 可使用：

```bash
export OPENROUTER_API_KEY=<OPENROUTER_API_KEY>
```

### 7.2 运行主 Notebook

打开并按顺序运行：

```text
version_final.ipynb.ipynb
```

运行到最后一个单元后，系统会进入交互模式。用户可以输入数字选择：

- `1`: 护理咨询
- `2`: 产品-问题解决型
- `3`: 产品-浏览了解型

### 7.3 更新产品数据

如果修改 `01_PRODUCT_MASTER_BASE.csv`，建议先检查：

```bash
python update_product_data.py --dry-run
```

确认没有必要字段错误后，再同步 JSON：

```bash
python update_product_data.py
```

如果需要重建产品向量库：

```bash
python update_product_data.py --rebuild-vector
```

## 8. 当前版本亮点

- 将课程要求拆分为护理咨询、问题解决型推荐和产品浏览三条路径。
- 使用规则树实现诊断式问答，避免只靠关键词搜索。
- 使用产品 CSV / JSON 约束推荐结果，降低产品幻觉。
- 用 Chroma 向量库支持护理知识 RAG。
- 引入产品类别细化问答，把大类推荐进一步落到具体产品。
- 提供产品数据同步脚本，方便维护 CSV 与 JSON 的一致性。
- Notebook 中保留完整可运行流程，便于复现系统的主要功能。

## 9. 当前限制与可改进方向

当前版本已形成可运行的 Agent 原型，同时仍有进一步完善空间：

- Notebook 目前没有 markdown 说明单元，代码解释主要依赖 README。
- 交互界面仍是 Notebook / 命令行形式，尚未封装为 Web UI。
- 课程说明中提到的 PDF manual 数值约束 benchmark 仍可进一步补充，例如门宽、承重、座宽、床宽等规格抽取准确率测试。
- 护理知识库和产品向量库如更换资料源，需要重新构建 Chroma 数据库。
- 部分原始产品数据存在繁体中文、HTML 描述和字段缺失情况，后续可继续清洗。
- 当前系统应定位为辅助推荐和演示原型，不应作为正式医疗或租赁决策系统直接使用。

## 10. 提交材料

本项目提交材料包括：

- `README.md`
- `version_final.ipynb.ipynb`
- `01_PRODUCT_MASTER_BASE.csv`
- `02_LOGIC_RULE.json`
- `03_PRODUCT_INFO.json`
- `04_PRODUCT_REFINE_LOGIC.json`
- `update_product_data.py`
- `nursing_chroma_db/`


