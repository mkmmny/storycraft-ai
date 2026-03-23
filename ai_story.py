# -*- coding: utf-8 -*-
"""
AI 故事生成模块
使用硅基流动 (SiliconFlow) + DeepSeek-R1 生成互动故事内容
"""
import copy
import re
from dotenv import load_dotenv
import os
from openai import OpenAI
from sensitive_filter import contains_sensitive_content, filter_sensitive_content

# 硅基流动 API 配置
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Pro/deepseek-ai/DeepSeek-R1"

# 生成失败时自动重试次数（直到通过本地安全审核或达到上限）
MAX_GENERATION_RETRIES = 5


def _get_client() -> OpenAI:
    """获取硅基流动客户端（OpenAI 兼容接口）"""
    # 显式加载项目根目录 .env，避免从其他工作目录启动时读不到
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=env_path, override=False)

    api_key = os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_API_KEY")
    api_key = (api_key or "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError(
            "未检测到 API Key。请在项目根目录 .env 中设置 SILICONFLOW_API_KEY=你的密钥，然后重启应用。"
        )
    return OpenAI(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        timeout=120.0,
        max_retries=2,
    )


def _build_system_prompt(theme: str, protagonist: str, style: str, age_range: str, values: str) -> str:
    """
    构建系统提示词，定义AI的角色和约束
    """
    return f"""你是一位专业的儿童/青少年故事作家，擅长创作积极向上、富有教育意义的互动故事。

## 创作设定
- 故事主题：{theme}
- 主角：{protagonist}
- 写作风格：{style}
- 目标年龄段：{age_range}
- 价值观导向：{values}

## 严格约束（必须遵守）
1. 内容必须健康、积极、适合指定年龄段阅读
2. 禁止暴力、血腥、恐怖、色情、赌博、毒品等不良内容
3. 传递正能量和正确的价值观
4. 语言生动有趣，适合目标读者
5. 每章结尾提供2-3个剧情分支选择，格式为：
   【分支A】xxx
   【分支B】xxx
   【分支C】xxx（可选）
6. 每个【分支X】后面只写该选项的一句简短剧情描述（20-60字），同一行内写完；禁止在分支后写「以下是第X章」「第X章内容」等任何元说明或预告。
7. **禁止**在正文最开头写「好的」「这是为」「根据」「为您创作」「下面是为X岁小朋友」等寒暄或元说明；正文必须直接以「第X章：」标题或故事正文第一句开始。
"""


def _build_user_message(
    chapter_num: int,
    previous_chapters: list,
    chosen_branch: str,
    retry_suffix: str = "",
) -> str:
    """构建用户消息（可附加重试说明）"""
    base = ""
    if chapter_num == 1:
        base = """请创作第一章故事。

要求：
1. 开篇引人入胜，介绍主角和故事背景
2. 章节约300-500字
3. 章末提供2-3个【分支X】格式的剧情选择（分支后仅一句选项描述，勿写章节预告）
4. 单独一行给出本章的"文字插画描述"（50-80字，描述本章关键场景的画面，供读者想象），格式为：【插画】描述内容"""
    else:
        history = "\n\n".join(
            f"第{i}章：\n{ch.get('content', '')}"
            for i, ch in enumerate(previous_chapters, 1)
        )
        base = f"""以下是已有故事内容：
{history}

用户选择了：{chosen_branch}

请根据用户选择，继续创作第{chapter_num}章。
要求：
1. 承接上文，自然过渡
2. 章节约300-500字
3. 第5章为结局章，不需要分支选择
4. 非结局章末提供2-3个【分支X】格式的剧情选择（分支后仅一句选项描述，勿写章节预告）
5. 单独一行给出本章的"文字插画描述"（50-80字），格式为：【插画】描述内容"""

    if retry_suffix:
        base = base + "\n\n" + retry_suffix
    return base


RETRY_SUFFIX = (
    "【重要】上一次输出未通过内容安全审核。请完全重写本章，"
    "严禁出现：暴力、血腥、色情、赌博、毒品、自残、虐待等描写；"
    "用词温和、适合儿童；保持剧情有趣且积极。"
)

# 分支选项后常见的模型元信息（需从选项正文中剔除）
_BRANCH_META_PATTERNS = [
    r"以下是第[一二三四五六七八九十0-9]+章[^【]*",
    r"以下是第\s*\d+\s*章[^【]*",
    r"第[一二三四五六七八九十0-9]+章内容[^【]*",
    r"下面(?:开始|为|是)[^【]{0,30}章[^【]*",
    r"请(?:继续|阅读|看)[^【]*",
    r"字数\s*[:：][^。\n]*",
    r"大纲\s*[:：][\s\S]{0,120}",
    r"确保每个选项[^。\n]*",
    r"现在\s*，?\s*写出章节[^。\n]*",
    r"</think>",
    r"^\s*[，,]\s*",
]


def _strip_think_blocks(text: str) -> str:
    if not text:
        return text
    t = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    t = re.sub(r"</?think>", "", t, flags=re.IGNORECASE)
    return t


def _strip_prompt_leak_lines(text: str) -> str:
    if not text:
        return text
    out = []
    in_outline = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            if not in_outline:
                out.append(raw_line)
            continue

        # 进入「模板/提纲」模式：后续项目符号与编号行直接跳过
        if re.match(r"^(大纲|完整第[一二三四五六七八九十0-9]+章|最终结构|写故事)\s*[:：]?\s*$", line):
            in_outline = True
            continue
        if in_outline:
            if re.match(r"^[•·\-*]\s+", line) or re.match(r"^\d+[\.|、]\s*", line):
                continue
            # 遇到正文标题/正文第一句时退出提纲模式
            if re.match(rf"^(?:第\s*f=[一二三四五六七八九十0-9]+\s*章|{protagonist}|从前|一天|阳光|月光|\"|“)", line):
                in_outline = False
            else:
                continue

        bad = [
            r"^字数\s*[:：]",
            r"^字数控制\s*[:：]",
            r"^分支选项\s*[:：]",
            r"^分支描述要简短\s*[:：]?",
            r"^确保每个选项",
            r"^现在\s*，?\s*写(?:出)?(?:故事)?正文",
            r"^直接开始\s*[:：]",
            r"^标题\s*[:：]",
            r"^开头\s*[:：]",
            r"^背景\s*[:：]",
            r"^事件\s*[:：]",
            r"^高潮\s*[:：]",
            r"^结尾\s*[:：]",
            r"^发现\s*[:：]",
            r"^以下是第\s*\d+\s*章",
            r"^第\s*\d+\s*章内容",
            r"^正文内容\s*[:：]",
            r"^\s*</think>\s*$",
        ]
        if any(re.search(p, line, flags=re.IGNORECASE) for p in bad):
            continue

        out.append(raw_line)

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_generated_text(text: str, keep_newlines: bool = True) -> str:
    """统一清洗模型输出中的 Markdown 残留与不合时宜标点。"""
    if not text or not isinstance(text, str):
        return ""

    s = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去除常见 markdown 残留符号（加粗、标题、列表、代码标记等）
    s = re.sub(r"\*\*+", "", s)
    s = re.sub(r"__+", "", s)
    s = re.sub(r"`+", "", s)
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*•·]\s+", "", s, flags=re.MULTILINE)

    # 清理开头/行首异常标点
    s = re.sub(r"^[\s\-—_~•·*#`，,。；;：:、|]+", "", s)
    s = re.sub(r"(?m)^\s*[\-—_~•·*#`，,。；;：:、|]+", "", s)

    # 标点规范化（合并重复标点）
    s = re.sub(r"([，。！？；：,.!?;:、])\1+", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)

    if keep_newlines:
        s = re.sub(r"\n{3,}", "\n\n", s)
    else:
        s = " ".join(seg.strip() for seg in s.split("\n") if seg.strip())

    return s.strip()


def sanitize_choice_text(text: str) -> str:
    """
    清洗单个分支选项：去掉「以下是第X章」等无关元信息，避免按钮显示错乱。
    """
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()
    # 仅保留首行，避免后续多行提示词污染
    s = s.split("\n", 1)[0].strip()
    # 先按元信息截断（取最靠左的匹配之前的内容）
    cut_at = len(s)
    for pat in _BRANCH_META_PATTERNS:
        m = re.search(pat, s)
        if m:
            cut_at = min(cut_at, m.start())
    s = s[:cut_at].strip()
    # 再次去掉行内残留的「以下」
    m = re.search(r"(?:以下是|下面为|第\s*\d+\s*章)", s)
    if m:
        s = s[: m.start()].strip()
    s = re.sub(r"^[，,。；;：\s]+", "", s)
    s = re.sub(r"\s+[123]\.?\s*$", "", s)
    s = re.sub(r"[：:]\s*$", "", s).strip()
    s = _normalize_generated_text(s, keep_newlines=False)
    return s


def _is_preamble_line(s: str) -> bool:
    """是否为模型在正文前加的寒暄/元说明行"""
    if len(s) > 220:
        return False
    if re.match(r"^(好的|好呀|没问题|当然|根据|以下是|下面是为|请看).{0,15}", s):
        return True
    if "创作" in s and ("章" in s or "故事" in s) and any(
        x in s for x in ("岁", "小朋友", "主角", "为您", "探险", "童话")
    ):
        return True
    if re.search(r"(为您|为您量身|为您创作|请看以下|下面(?:开始|是))", s):
        return True
    return False


def strip_leading_llm_preamble(text: str) -> str:
    """
    去掉正文开头的寒暄、元说明（如「好的！这是为3-6岁小朋友创作的…第一章…」），
    从第一个「第X章」样式标题行开始保留。
    """
    if not text or not isinstance(text, str):
        return text
    lines = text.split("\n")
    title_re = re.compile(
        r"^(#{1,6}\s*)?(第[一二三四五六七八九十0-9]+章\s*[：:]|第\s*\d+\s*章\s*[：:])"
    )
    idx = 0
    while idx < len(lines):
        s = lines[idx].strip()
        if not s:
            idx += 1
            continue
        if title_re.search(s):
            break
        if _is_preamble_line(s):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip() if idx < len(lines) else text.strip()


def strip_embedded_branch_markers_from_body(text: str) -> str:
    """
    从章节叙事正文中移除与底部按钮重复的【分支A/B/C】整行或行内片段，
    保留章节标题与普通情节；分支文案仅以 choices / 按钮展示。
    """
    if not text or not isinstance(text, str):
        return text
    lines_out = []
    for line in text.split("\n"):
        s = line.strip()
        # 整行仅为分支选项时整行删除
        if re.match(r"^【分支\s*[ABC]\s*】", s):
            continue
        # 行内夹杂的分支标记（模型把选项写在正文里时）
        cleaned = re.sub(r"【分支\s*[ABC]\s*】[^\n【]*", "", line)
        lines_out.append(cleaned.rstrip())
    result = "\n".join(lines_out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def normalize_chapter_for_replay(ch: dict) -> dict:
    """
    从存档恢复章节时再次清理正文，兼容旧存档中正文仍含【分支】的情况。
    """
    out = copy.deepcopy(ch)
    for key in ("content", "content_raw"):
        if out.get(key):
            t = strip_embedded_branch_markers_from_body(out[key])
            out[key] = strip_leading_llm_preamble(t)
    return out


def _extract_branch_choices(raw_text: str) -> list:
    """
    从全文提取【分支A/B/C】选项，按 A→B→C 顺序，每个分支只保留首个匹配，并做清洗。
    """
    # 按「分支标记」切分，避免 [^【]+ 把多章内容吃进第一个分支
    pattern = r"【分支([ABC])】\s*([^【]*)"
    matches = list(re.finditer(pattern, raw_text))
    by_id: dict = {}
    for m in matches:
        letter = m.group(1)
        raw_opt = m.group(2)
        cleaned = sanitize_choice_text(raw_opt)
        if letter in by_id:
            continue
        if cleaned:
            by_id[letter] = cleaned
        elif raw_opt.strip():
            # 清洗后为空时保留截断原文，避免按钮无文案
            by_id[letter] = raw_opt.strip()[:120]
    choices = []
    for letter in ("A", "B", "C"):
        if letter in by_id:
            choices.append({"id": letter, "text": by_id[letter]})
    return choices


def _clean_illustration_text(text: str) -> str:
    """清洗插画描述，避免正文/大纲被误塞到插画字段里。"""
    if not text:
        return ""

    stop_patterns = [
        r"^第\s*[一二三四五六七八九十0-9]+\s*章",
        r"^正文内容\s*[:：]",
        r"^分支例子\s*[:：]",
        r"^字数控制\s*[:：]",
        r"^【分支",
        r"^大纲\s*[:：]",
    ]

    lines = []
    started = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            if started:
                break
            continue

        line = re.sub(r"^(插画描述|描述)\s*[:：]\s*", "", line)

        if any(re.search(p, line) for p in stop_patterns):
            if started:
                break
            continue

        lines.append(line)
        started = True

        if len("".join(lines)) >= 160:
            break

    result = " ".join(lines).strip()
    result = re.sub(r"\s{2,}", " ", result)
    return result


def _parse_chapter_response(raw_content: str) -> dict:
    """
    从模型原始输出解析章节结构
    """
    cleaned_all = _strip_think_blocks(raw_content or "")
    cleaned_all = _strip_prompt_leak_lines(cleaned_all)

    content = cleaned_all
    illustration = ""
    choices = []

    # 用“逐行定位【插画】”替代全局 split，防止正文中偶发字符串导致错位
    lines = cleaned_all.split("\n")
    ill_idx = -1
    for i, ln in enumerate(lines):
        if re.search(r"^\s*【插画】", ln):
            ill_idx = i
            break

    if ill_idx >= 0:
        content = "\n".join(lines[:ill_idx]).strip()
        rest = "\n".join(lines[ill_idx:]).strip()
        rest = re.sub(r"^\s*【插画】\s*", "", rest)
        if "【分支" in rest:
            ill_part, choice_part = rest.split("【分支", 1)
            illustration = ill_part.strip()
            choice_text = "【分支" + choice_part
        else:
            illustration = rest
            choice_text = ""
    else:
        choice_text = content

    choices = _extract_branch_choices(cleaned_all)
    if not choices and "【分支" in choice_text:
        choices = _extract_branch_choices(choice_text)

    # 正文中不再保留【分支A/B/C】，避免与下方按钮重复
    content = strip_embedded_branch_markers_from_body(content)
    content = _strip_prompt_leak_lines(content)
    content = strip_leading_llm_preamble(content)

    content_raw = content
    illustration_raw = _strip_prompt_leak_lines(illustration) if illustration else None
    illustration_raw = _clean_illustration_text(illustration_raw or "")

    content = _normalize_generated_text(filter_sensitive_content(content), keep_newlines=True)
    illustration = (
        _normalize_generated_text(filter_sensitive_content(illustration_raw), keep_newlines=False)
        if illustration_raw
        else "（本章暂无插画描述）"
    )

    return {
        "content": content,
        "content_raw": content_raw,
        "illustration": illustration,
        "illustration_raw": illustration_raw or "",
        "choices": choices,
        "error": False,
    }


def _content_passes_safety(raw_content: str) -> bool:
    """全文（含分支选项）均需通过检测"""
    if not raw_content or not raw_content.strip():
        return False
    return not contains_sensitive_content(raw_content)


def _contains_reasoning_leak(text: str) -> bool:
    """检测是否含有思考过程/提纲模板泄漏。"""
    if not text:
        return False
    t = text.strip()
    patterns = [
        r"<think>|</think>",
        r"(^|\n)\s*(开头|背景|事件|高潮|结尾|字数控制|最终结构|写故事|正文内容|分支例子)\s*[:：]",
        r"(^|\n)\s*现在\s*，?\s*草拟",
        r"(^|\n)\s*章节长度\s*[:：]",
        r"(^|\n)\s*完整第[一二三四五六七八九十0-9]+章",
        r"(^|\n)\s*分支选项示例",
    ]
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)


def _parsed_chapter_is_valid(parsed: dict, chapter_num: int) -> bool:
    """解析结果校验：正文必须可读，且不含思考/模板污染。"""
    content = (parsed.get("content_raw") or parsed.get("content") or "").strip()
    if not content:
        return False
    if _contains_reasoning_leak(content):
        return False

    # 非极端短文本：避免被清洗后只剩一两句模板残片
    min_len = 60 if chapter_num <= 2 else 80
    if len(content) < min_len:
        return False

    # 第5章可无分支，其余章节至少2个分支
    choices = parsed.get("choices") or []
    if chapter_num < 5 and len(choices) < 2:
        return False

    return True


def generate_chapter(
    theme: str,
    protagonist: str,
    style: str,
    age_range: str,
    values: str,
    chapter_num: int,
    previous_chapters: list = None,
    chosen_branch: str = None,
    strict_generation: bool = True,
) -> dict:
    """
    生成故事章节；若未通过安全审核则自动重试，最多 MAX_GENERATION_RETRIES 次。

    Returns:
        包含 content、illustration、choices 的字典；多次失败则 error=True
    """
    if previous_chapters is None:
        previous_chapters = []

    def _passes_safety(raw: str) -> bool:
        if not raw or not str(raw).strip():
            return False
        if not strict_generation:
            return True
        return _content_passes_safety(raw)

    try:
        client = _get_client()
    except Exception as e:
        return {
            "content": f"生成失败：{e}",
            "illustration": "",
            "choices": [],
            "error": True,
        }

    system_prompt = _build_system_prompt(theme, protagonist, style, age_range, values)

    last_error = ""
    for attempt in range(1, MAX_GENERATION_RETRIES + 1):
        retry_suffix = RETRY_SUFFIX if attempt > 1 else ""
        user_message = _build_user_message(
            chapter_num, previous_chapters, chosen_branch, retry_suffix=retry_suffix
        )

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.65,
                top_p=0.95,
                max_tokens=1200,
                extra_body={"thinking_budget": 512},
            )

            msg = response.choices[0].message
            raw_content = (msg.content or "").strip()

            if not _passes_safety(raw_content):
                last_error = f"第 {attempt} 次生成未通过安全审核，正在重试…"
                continue

            parsed = _parse_chapter_response(raw_content)
            if not _parsed_chapter_is_valid(parsed, chapter_num):
                last_error = f"第 {attempt} 次生成包含模板/思考过程污染，正在重试…"
                continue

            parsed["retry_info"] = f"（本章节经 {attempt} 次生成后通过审核）" if attempt > 1 else ""
            return parsed

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_GENERATION_RETRIES:
                continue

            lower_err = last_error.lower()
            if any(k in lower_err for k in ["connection", "timeout", "timed out", "network"]):
                msg = (
                    "生成失败：网络连接到硅基流动接口异常。"
                    "请检查当前网络、代理/VPN、防火墙后重试。"
                )
            elif any(k in lower_err for k in ["401", "unauthorized", "invalid api key", "authentication"]):
                msg = "生成失败：API Key 无效或已过期，请检查 SILICONFLOW_API_KEY。"
            elif any(k in lower_err for k in ["429", "rate", "quota", "insufficient_quota"]):
                msg = "生成失败：请求过于频繁或额度不足，请稍后重试。"
            else:
                msg = f"生成失败：{last_error}"

            return {
                "content": msg,
                "illustration": "",
                "choices": [],
                "error": True,
            }

    return {
        "content": (
            f"抱歉，已自动重试 {MAX_GENERATION_RETRIES} 次，内容仍无法通过本地安全审核。"
            "请稍后再试或微调故事设定。"
        ),
        "illustration": "（插画暂时不可用）",
        "choices": [],
        "error": True,
    }
