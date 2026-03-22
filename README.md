# AI 互动故事生成器

基于 Streamlit + 硅基流动 (SiliconFlow) DeepSeek-R1 的 AI 互动故事生成器。

## 功能特性

- 用户可选择：故事主题、主角、风格、年龄段、价值观
- AI 生成第一章，并给出 2～3 个剧情分支选择
- 用户选择分支后继续生成下一章，最多 5 章
- 每章可生成文字配图描述（文字插画描述）
- 敏感词过滤：开始前对故事设定做安全审核；生成章节若未通过审核会自动重试（最多 5 次）
- 故事保存到 `stories.json`：含 **故事 ID、主题、章节、剧情选择记录、生成/更新时间、完整拼接文本** 等
- **我的故事**：列表浏览、阅读全文、剧情选择记录、可复制完整文本、删除；**重新选分支**时可选择「保留第一章原文继续」或「沿用设定从第一章重新生成」（确认前会提示是否覆盖当前进度）
- **AI 创作控制**（侧边栏，有进行中故事时）：**暂停下一章生成** / **继续生成**；暂停期间不会自动请求 API，避免与「重新选分支」冲突
- 模型参数已适当收紧（如思维链预算）以加快响应；仍使用 DeepSeek-R1
- **家长模式**（侧边栏）：可开关「展示时过滤敏感词」「生成时严格审核（违规则自动重试）」
- 分支选项自动去掉「以下是第 X 章」等模型元信息，避免按钮文案错乱
- 代码结构清晰，分函数，中文注释

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置硅基流动 API Key

在运行前需设置环境变量 `SILICONFLOW_API_KEY`（或在项目根目录创建 `.env` 文件）：

**方式一：.env 文件（推荐）**
```
SILICONFLOW_API_KEY=你的API密钥
```

**方式二：环境变量**
- Windows PowerShell: `$env:SILICONFLOW_API_KEY = "your-api-key"`
- Linux/Mac: `export SILICONFLOW_API_KEY="your-api-key"`

API Key 在 [硅基流动控制台](https://cloud.siliconflow.cn/account/ak) 创建。

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器将自动打开应用页面。

## 项目结构

```
storyCraft/
├── app.py           # 主程序入口，Streamlit 界面
├── ai_story.py      # AI 故事生成逻辑
├── sensitive_filter.py  # 敏感词过滤
├── story_storage.py # 故事存储（stories.json）
├── requirements.txt
├── stories.json     # 故事数据（运行后自动生成）
└── README.md
```

## 使用说明

1. **创作新故事**：填写主题、主角、风格、年龄段、价值观，点击「开始创作第一章」
2. **选择分支**：每章结束后选择喜欢的剧情走向
3. **查看故事**：侧边栏「我的故事」→ 展开条目 →「阅读 / 继续阅读」
4. **家长模式**：建议保持开启；若关闭「生成时严格审核」，模型输出不再因本地敏感词而自动重试（请家长监护）

## 注意事项

- 需要有效的硅基流动 API Key（在 https://cloud.siliconflow.cn 注册并创建）
- 使用 DeepSeek-R1 推理模型，生成质量高
- 敏感词库可在 `sensitive_filter.py` 中自定义扩展
