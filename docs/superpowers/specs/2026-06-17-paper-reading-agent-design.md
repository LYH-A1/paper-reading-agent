# 论文阅读 Agent 设计文档

> 版本：v1.0 | 日期：2026-06-17 | 状态：已确认

---

## 一、项目概述

构建一个小型论文阅读 Agent 智能体，帮助研究人员高效阅读和理解学术论文。Agent 支持 PDF 上传、自动解析、智能问答、摘要生成、引用推荐等功能。

### 核心定位

- **真实 LLM 驱动**：接入 DeepSeek API（Anthropic 协议），不依赖第三方 Agent 框架
- **节点式工作流**：单 Agent + 工具调用，参考 LangGraph 图式设计
- **Streamlit Web 界面**：双栏布局（论文 + 对话），交互体验流畅
- **轻量级**：纯 Python 实现，无重型框架依赖

### 参考来源

- [Hello-Agents 第六章实验包](D:/下载/chapter6_framework_practice_lab/chapter6_framework_practice_lab/)：四类 Agent 框架教学实验（AutoGen/AgentScope/CAMEL/LangGraph）
- 原始需求分析：[paper-reading-agent.html](paper-reading-agent/paper-reading-agent.html)

---

## 二、项目结构

```
paper-reading-agent/
├── config.py                # 全局配置（API keys、路径、常量）
├── llm_client.py            # LLM API 封装（流式 + 重试 + 日志）
├── tools.py                 # 工具层：PDF解析、知识检索、引用推荐（懒加载）
├── prompts.py               # 提示词模板库 + 追问生成
├── agent_core.py            # Agent 状态机（图式工作流 + 回调钩子）
├── session_manager.py       # 会话持久化：对话历史、论文库、用户偏好
├── app.py                   # Streamlit 主界面（双栏布局）
├── components/              # UI 组件
│   ├── step_indicator.py    #   Show Your Work 步骤展示
│   ├── citation_tooltip.py  #   引用悬停预览
│   ├── skeleton.py          #   骨架屏
│   └── paper_viewer.py      #   论文阅读面板
├── utils/
│   ├── tfidf.py             #   手写 TF-IDF（去 sklearn 依赖）
│   └── text_splitter.py     #   智能文本分块
├── outputs/                 # 输出制品（执行轨迹、API日志、导出对话）
├── data/                    # 持久化数据
│   ├── paper_library.json   #   论文库元数据
│   ├── conversations.json   #   对话历史
│   └── preferences.json     #   用户偏好
└── requirements.txt         # 依赖清单（最小化）
```

---

## 三、Agent 核心状态机

### 3.1 核心数据结构

```python
@dataclass
class Paper:
    """论文对象"""
    title: str
    authors: list[str]
    abstract: str
    sections: list[Section]
    references: list[str]
    metadata: dict                # 期刊、年份、DOI等
    raw_text: str

@dataclass
class Section:
    """论文章节"""
    heading: str                  # 如 "3. Method"
    content: str
    page_range: tuple[int, int]

@dataclass
class AgentState:
    """Agent 工作流状态"""
    paper: Paper | None
    user_query: str
    intent: str                   # classify输出：summary / qa / compare / recommend
    retrieved_chunks: list[dict]  # [{text, source_page, relevance}, ...]
    answer: str
    citations: list[str]
    quality_score: int            # 0-10
    rewrite_count: int            # 上限 2
    trace: list[str]              # 节点执行轨迹
    error: str | None
```

### 3.2 七节点工作流

```
[parse] → [classify] → [retrieve] → [generate] → [reflect]
                                                      │
                                              score≥7 / score<7
                                                │         │
                                                ▼         ▼
                                             [output]  [rewrite]
                                                │         │
                                                │    (loop, max 2次)
                                                │         │
                                                ▼         ▼
                                          [save to    回跳至
                                           history]   [generate]
```

#### 节点 1：`parse` — PDF 解析

| 项    | 内容                                                                         |
| ---- | -------------------------------------------------------------------------- |
| 触发   | 用户上传 PDF 文件                                                                |
| 工具   | `pdfplumber`（主）+ `PyPDF2`（备选，自动切换）                                         |
| 逻辑   | 1) 逐页提取文本；2) 正则匹配标题（首行大字）；3) 正则匹配摘要（Abstract 段）；4) 按编号模式切分章节；5) 提取参考文献段    |
| 输出   | `Paper` 对象                                                                 |
| 错误处理 | 非 PDF → 报错；pdfplumber 失败 → 切 PyPDF2；两者均败 → 提示"无法解析"；文本 < 100字 → 提示"可能是扫描版" |
| 缓存   | 解析后存入 `data/papers/{paper_id}.json`，二次加载 < 0.2s                            |

#### 节点 2：`classify` — 意图分类

| 项   | 内容                                                  |
| --- | --------------------------------------------------- |
| 触发  | parse 完成，用户输入查询                                     |
| 逻辑  | 将用户查询 + 论文标题/摘要发 LLM，要求返回 JSON：`{"intent": "summary |
| 输出  | 更新 state.intent                                     |
| 降级  | LLM 返回不规范时，关键词规则兜底                                  |
| 性能  | 短 prompt，~30 tokens，< 2s                            |

#### 节点 3：`retrieve` — 上下文检索

| 项   | 内容                                                                              |
| --- | ------------------------------------------------------------------------------- |
| 触发  | classify 完成                                                                     |
| 逻辑  | 1) 论文全文滑动窗口分块（chunk=1000字，overlap=200字）；2) TF-IDF + 余弦相似度排序；3) 返回 top-5 片段 + 页码 |
| 输出  | `retrieved_chunks` 列表                                                           |
| 扩展点 | 接口兼容后续接入 arXiv / Semantic Scholar API                                           |
| 性能  | 手写 TF-IDF 无 sklearn 依赖，< 0.1s                                                   |

#### 节点 4：`generate` — LLM 生成回答

| 项   | 内容                                                                          |
| --- | --------------------------------------------------------------------------- |
| 触发  | retrieve 完成（或 rewrite 回跳后）                                                  |
| 逻辑  | 1) 根据 intent 选提示词模板；2) 组装 system + user prompt；3) 调用 LLM **流式**生成；4) 提取引用标注 |
| 流式  | 逐 token yield，UI 实时渲染，首 token < 1.5s                                        |
| 引用  | 要求 LLM 用 `[第X页]` / `[Section Y]` 标注来源                                       |

#### 节点 5：`reflect` — 质量评估

| 项    | 内容                                                                                             |
| ---- | ---------------------------------------------------------------------------------------------- |
| 评估维度 | relevance (0-3)：切题度；consistency (0-4)：原文一致性（无幻觉）；completeness (0-3)：关键信息覆盖率                    |
| 方式   | LLM 作为评判器，返回 JSON：`{"relevance": N, "consistency": N, "completeness": N, "deductions": [...]}` |
| 阈值   | score ≥ 7 → output；score < 7 → rewrite                                                         |
| 性能   | 短 prompt，~50 tokens，< 2s                                                                       |

#### 节点 6：`rewrite` — 重写策略

| 项   | 内容                                                                  |
| --- | ------------------------------------------------------------------- |
| 触发  | quality_score < 7 且 rewrite_count < 2                               |
| 逻辑  | 1) 将 reflect 扣分原因作为反馈注入 prompt；2) rewrite_count += 1；3) 回跳 generate |
| 上限  | 最多 2 次，超过强制进入 output                                                |

#### 节点 7：`output` — 格式化输出

| 项   | 内容                                                 |
| --- | -------------------------------------------------- |
| 逻辑  | 1) 打包最终回答 + 引用列表 + 论文元数据；2) 格式化为 Markdown；3) 附免责声明 |
| 内容  | 回答正文、引用来源、论文信息、质量评分、免责声明                           |

### 3.3 图执行器接口

```python
class PaperReadingAgent:
    def run(self, paper: Paper, query: str, on_step=None) -> Generator:
        """
        执行完整工作流。
        on_step(node_name, result_dict): 每节点完成时回调
        yield state: 最终状态
        """
```

### 3.4 4 种意图对应的提示词策略

| 意图          | 模板特点          | 输出格式                 |
| ----------- | ------------- | -------------------- |
| `summary`   | 学术分析专家角色      | 结构化：背景/方法/贡献/局限 + 引用 |
| `qa`        | 论文问答助手角色      | 自然语言 + 每观点标注页码       |
| `compare`   | 对比分析角色（多篇论文时） | 列表对比 + 引用            |
| `recommend` | 文献推荐角色        | 推荐列表 + 理由            |

---

## 四、工具层

### 4.1 统一接口

```python
class Tool(ABC):
    name: str
    description: str
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult: ...

@dataclass
class ToolResult:
    success: bool
    data: Any
    error: str | None
```

### 4.2 内置工具

| 工具                    | 功能             | 实现                      | 懒加载 |
| --------------------- | -------------- | ----------------------- | --- |
| `PDFParser`           | PDF 文本提取 + 结构化 | pdfplumber + PyPDF2 双引擎 | ✅   |
| `KnowledgeRetriever`  | TF-IDF 上下文检索   | 手写 TF-IDF + 余弦相似度       | —   |
| `CitationRecommender` | 参考文献推荐         | 关键词匹配 + LLM 排序          | —   |

---

## 五、LLM 客户端

### 5.1 配置

```python
@dataclass
class LLMConfig:
    base_url: str       # ANTHROPIC_BASE_URL（DeepSeek 代理）
    auth_token: str     # ANTHROPIC_AUTH_TOKEN
    model: str          # deepseek-v4-pro[1m]
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 2
```

### 5.2 接口

| 方法                                                      | 说明       | 用途                    |
| ------------------------------------------------------- | -------- | --------------------- |
| `chat(messages, system, temperature, max_tokens) → str` | 标准调用     | 兜底                    |
| `chat_stream(messages, system) → Generator[str]`        | **流式输出** | 主要使用，generate 节点      |
| `chat_json(messages, system) → dict`                    | JSON 模式  | classify / reflect 节点 |

### 5.3 可靠性

- 网络错误/超时：自动重试 2 次，间隔 2s
- API 4xx：记录日志，返回友好错误
- API 5xx：重试后返回"服务暂时不可用"
- JSON 解析失败：重试一次 + 更强制格式要求
- 每次调用记录：时间戳、模型、token 用量、耗时 → `outputs/api_log.jsonl`

---

## 六、会话持久化

### 6.1 数据文件

| 文件                            | 内容                | 存储格式 |
| ----------------------------- | ----------------- | ---- |
| `data/paper_library.json`     | 论文库：所有上传论文的元数据    | JSON |
| `data/conversations.json`     | 对话历史：按论文分组的问答记录   | JSON |
| `data/preferences.json`       | 用户偏好：关注重点、阅读深度、语言 | JSON |
| `data/papers/{paper_id}.json` | 论文解析缓存            | JSON |

### 6.2 SessionManager 接口

```python
class SessionManager:
    # 论文库
    def add_paper(file_path) -> Paper          # 上传 + MD5去重
    def get_paper(paper_id) -> Paper           # 缓存优先
    def list_papers(tag, search) -> list       # 搜索/筛选
    def delete_paper(paper_id) -> bool
    def update_tags(paper_id, tags)

    # 对话
    def create_session(paper_id) -> str        # 新建会话
    def add_message(session_id, role, content, meta)
    def get_session(session_id) -> dict
    def list_sessions(paper_id) -> list
    def export_session_md(session_id) -> str   # 导出 Markdown
    def delete_session(session_id) -> bool

    # 偏好
    def get_preferences() -> dict
    def update_preferences(key, value)

    # 维护
    def cleanup_old_files() -> int             # 按配置清理
```

---

## 七、Streamlit 界面

### 7.1 双栏布局

```
┌────────────────────┬──────────────────────────────────────┐
│                    │                                      │
│    📄 论文阅读      │    💬 对话分析                        │
│                    │                                      │
│  ┌──────────────┐  │  ┌────────────────────────────────┐  │
│  │ 论文标题      │  │  │ [用户] 核心贡献是什么？          │  │
│  │ 作者/年份     │  │  │                                │  │
│  ├──────────────┤  │  │ [助手] 本文的核心贡献有三方面...  │  │
│  │              │  │  │ 🔗 来源: 第3页 Contributions    │  │
│  │  论文正文    │  │  │                                │  │
│  │  (可滚动)    │  │  │ 📊 评分 8/10 | 🔄 追问建议 ▼    │  │
│  │              │  │  │  ┌─────────────────────────┐   │  │
│  │              │  │  │  │ 💡 这个方法有什么局限？  │   │  │
│  │              │  │  │  │ 💡 和RNN/CNN的对比是什么?│   │  │
│  │              │  │  │  │ 💡 推荐相关论文          │   │  │
│  │              │  │  │  └─────────────────────────┘   │  │
│  └──────────────┘  │  └────────────────────────────────┘  │
│                    │  ┌────────────────────────────────┐  │
│  🔍 搜索正文...    │  │ 💬 输入问题...          [发送]  │  │
│  📑 章节导航      │  └────────────────────────────────┘  │
│    ▸ 1.Introduction│                                      │
│    ▸ 2.Background  │  ⚙️ 布局切换: [全宽对话] [双栏] [全宽论文] │
│    ▸ 3.Method      │                                      │
│    ▸ 4.Experiments │                                      │
│    ▸ 5.Conclusion  │                                      │
│                    │                                      │
└────────────────────┴──────────────────────────────────────┘
```

### 7.2 侧边栏

- **📚 论文库面板**：已上传论文列表 + 搜索 + 上传按钮 + 标签管理
- **📜 历史面板**：当前论文对话历史 + 导出 + 新建对话
- **⚙️ 设置面板**：关注重点 / 阅读深度 / 回答语言 / 自动清理天数

### 7.3 核心 UX 模式

#### Show Your Work（过程透明）

Agent 运行时每个节点状态实时展示，替换 spinner：

- "✅ 正在分析意图... 识别为问答 (qa)" — 0.8s
- "✅ 正在检索相关段落... 已匹配 5 个片段" — 0.1s，可展开预览
- "正在生成回答... {流式输出}" — 逐 token 渲染
- "✅ 质量评估 8/10" — 1.2s

#### 引用悬停预览

回答中的 `[¹]` 标记，鼠标悬停弹出原文片段 tooltip。

#### 快捷追问

每次回答后自动生成 3 个相关追问，以按钮形式展示，点击自动发送。

#### 思考链路

每条回答上方默认折叠，可展开查看 `classify → retrieve → generate → reflect → output` 完整链路。

#### 骨架屏

首屏加载时显示 placeholder 动画，0.5s 后被真实内容替换。

### 7.4 布局切换

支持三种布局模式（右上角按钮切换）：

- **双栏**（默认）：左论文 + 右对话
- **全宽对话**：论文折叠，对话占满
- **全宽论文**：对话折叠，沉浸式阅读论文

### 7.5 Streamlit 缓存策略

```python
@st.cache_resource     # 全局单例
def get_llm_client() -> LLMClient

@st.cache_resource
def get_session_manager() -> SessionManager

@st.cache_resource
def get_agent() -> PaperReadingAgent

@st.cache_data(ttl=30)  # 30s 刷新
def get_paper_list()

@st.cache_data(ttl=10)
def get_conversation_list(paper_id)
```

---

## 八、性能优化

### 8.1 性能预算

| 操作            | 目标耗时   | 优化手段           |
| ------------- | ------ | -------------- |
| 页面首次加载        | < 2s   | 懒加载 + 缓存资源     |
| 论文上传 + 首次解析   | < 5s   | 进度条 + 缓存写入     |
| 论文二次加载（缓存命中）  | < 0.2s | JSON 缓存读取      |
| 意图分类          | < 2s   | 短 prompt       |
| 上下文检索         | < 0.1s | 手写 TF-IDF 内存计算 |
| 回答生成（首 token） | < 1.5s | 流式 API         |
| 回答生成（完整）      | 5-15s  | 流式渲染           |
| 质量评估          | < 2s   | 短 prompt       |
| 切换论文          | < 0.5s | 缓存 + 懒加载       |

### 8.2 关键优化措施

| 优化点       | 方案                                    |
| --------- | ------------------------------------- |
| LLM 流式输出  | `chat_stream()` 逐 token yield，UI 实时渲染 |
| PDF 解析缓存  | 首次解析后存 JSON，二次加载 < 0.2s               |
| 懒加载       | pdfplumber、jieba 仅在工具调用时 import       |
| 手写 TF-IDF | 去掉 sklearn 依赖，免去 ~1s 导入时间             |
| 对话分页      | 历史 > 50 条默认展示最近 20 条                  |
| 论文列表分页    | > 20 篇时加分页                            |

### 8.3 依赖最小化

```
streamlit>=1.35.0
pdfplumber>=0.11.0       # 懒加载
PyPDF2>=3.0.0
httpx>=0.27.0
python-dotenv>=1.0.1
pydantic>=2.7.0
# jieba 作为可选依赖，中文检索时懒加载
# 无 sklearn / langgraph / autogen 等重型依赖
```

---

## 九、错误处理策略

| 层级       | 错误类型          | 处理方式                           |
| -------- | ------------- | ------------------------------ |
| PDF 解析   | 非 PDF 文件      | 立即报错，UI 红色提示"请上传 PDF 文件"       |
|          | pdfplumber 失败 | 自动切换到 PyPDF2                   |
|          | 双引擎均失败        | "无法解析此PDF，可能是扫描版或加密文件"         |
|          | 扫描版 PDF       | 检测文本量 < 100 字 → 提示"暂不支持扫描版PDF" |
| LLM 调用   | 网络超时          | 自动重试 2 次，间隔 2s                 |
|          | API 4xx       | "API 认证失败，请检查配置"               |
|          | API 5xx       | 重试后 → "模型服务暂时不可用，请稍后重试"        |
|          | JSON 解析失败     | 重试一次 + 规则兜底                    |
| 检索       | 全文为空          | 基于论文元数据回答                      |
|          | 无相关片段         | 返回论文摘要作为默认上下文                  |
| Agent 流程 | 重写超上限         | 强制进入 output，标注"质量可能偏低"         |
|          | 任意节点异常        | 捕获 → error 字段 → UI 显示友好信息      |
| 持久化      | JSON 损坏       | 备份 → 新建 → 提示"历史数据已重置"          |
|          | 磁盘不足          | 提示清理 data/                     |

### 降级展示

```
⚠️ PDF解析部分成功
第8-10页图表区域未能提取文字，但不影响整体阅读。
回答时可能缺少图表相关细节。
[重新解析] [忽略继续]
```

---

## 十、输出制品

| 文件                               | 内容           | 格式       | 生成时机        |
| -------------------------------- | ------------ | -------- | ----------- |
| `outputs/trace_{timestamp}.json` | 完整执行轨迹       | JSON     | 每次 Agent 运行 |
| `outputs/api_log.jsonl`          | LLM API 调用日志 | JSONL    | 每次 API 调用追加 |
| `outputs/session_export_{id}.md` | 用户导出的对话记录    | Markdown | 用户点击导出      |

---

## 十一、用户偏好配置

| 字段                  | 说明     | 可选值                                        |
| ------------------- | ------ | ------------------------------------------ |
| `focus_areas`       | 默认关注重点 | method / experiment / theory / application |
| `reading_level`     | 阅读深度   | beginner / researcher / expert             |
| `language`          | 回答语言   | zh / en / auto                             |
| `auto_cleanup_days` | 自动清理天数 | 1 / 3 / 7 / 30                             |

---

## 十二、UX 参考来源

| 产品                | 借鉴模式                    |
| ----------------- | ----------------------- |
| ChatGPT Canvas    | 双栏布局（内容 + 对话）           |
| Perplexity        | 内联引用标注、追问建议、搜索过程可见      |
| Claude Code       | 工具调用过程可见、节点状态实时展示       |
| Kimi              | 长文上下文 + 侧边目录导航          |
| OpenAI Assistants | Thread 式对话、Run Steps 可见 |

---

## 十三、模块依赖关系

```
app.py ───→ agent_core.py ───→ llm_client.py
   │              │                  │
   │              ├──→ tools.py      ├──→ config.py
   │              │                  │
   │              └──→ session_manager.py
   │
   └──→ components/
         ├── step_indicator.py
         ├── citation_tooltip.py
         ├── skeleton.py
         └── paper_viewer.py
```

**11 个 Python 文件，单一职责，清晰接口。**

---

## 十四、技术选型理由

| 选择                    | 理由                                             |
| --------------------- | ---------------------------------------------- |
| 不依赖 LangGraph/AutoGen | 项目定位为理解 Agent 原理后的小型自建实现，且去掉框架依赖可大幅减少启动时间      |
| 手写 TF-IDF             | sklearn 导入 ~1s，仅用 TfidfVectorizer，手写 ~50 行即可替代 |
| pdfplumber + PyPDF2   | 双引擎互备，pdfplumber 效果好但慢，PyPDF2 快但结构弱            |
| Streamlit             | 纯 Python UI，无需前后端分离，开发效率高，支持 st.cache 机制       |
| Anthropic 协议 API      | 用户已配置 DeepSeek 代理，直接复用                         |
| JSON 文件存储             | 对小型单用户场景足够，无需引入 SQLite/PostgreSQL              |

---

## 十五、待确认 / 未来扩展

- [ ] 多论文对比分析（当前设计预留接口，v1 先实现单篇）
- [ ] 图表/公式的 OCR 提取
- [ ] arXiv API / Semantic Scholar 外部检索接入
- [ ] Markdown 文件导入（非 PDF 论文）
- [ ] 导出为标准文献引用格式（BibTeX / APA）
