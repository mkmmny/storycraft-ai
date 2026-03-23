# -*- coding: utf-8 -*-
"""
AI 互动故事生成器 - 主程序
使用 Streamlit + 硅基流动 DeepSeek-R1 实现
"""

import re
import streamlit as st
from story_storage import (
    save_story,
    get_all_stories,
    get_story_by_id,
    delete_story,
    build_full_text_from_chapters,
)
from sensitive_filter import validate_story_settings
from ai_story import generate_chapter, normalize_chapter_for_replay
from dotenv import load_dotenv

load_dotenv()

# 侧边栏单选项与 session_state.nav_radio 绑定；不能在 radio 渲染后再改 nav_radio，需用 pending_nav 延后到下一轮、在创建 widget 前写入
_NAV_PAGES = ("✨ 创作新故事", "📚 我的故事")


def _schedule_pending_nav(target: str) -> None:
    """请求切换侧边栏页面；配合 _apply_pending_nav_before_widgets 在下一轮生效。"""
    if target in _NAV_PAGES:
        st.session_state.pending_nav = target


def _apply_pending_nav_before_widgets() -> None:
    """必须在 st.sidebar.radio(..., key='nav_radio') 之前调用。"""
    target = st.session_state.pop("pending_nav", None)
    if target in _NAV_PAGES:
        st.session_state.nav_radio = target


st.set_page_config(
    page_title="AI 互动故事生成器",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main-header {
        width: 100%;
        display: block;
        text-align: center;
        font-size: clamp(2.4rem, 4.2vw, 3.3rem) !important;
        font-weight: 800 !important;
        line-height: 1.15 !important;
        letter-spacing: 0.01em;
        color: #2c3e50 !important;
        margin: 0.35rem 0 1.2rem 0 !important;
    }

    /* 全局字体（不覆盖 main-header） */
    html, body, [class*="css"], .stApp {
        font-size: 19px !important;
        line-height: 1.66 !important;
    }

    /* 正文字号 */
    .stMarkdown, .stText, p, li, label, .stCaption {
        font-size: 1.12rem !important;
    }

    /* 表单与按钮 */
    .stTextInput label, .stSelectbox label, .stTextArea label, .stRadio label, .stCheckbox label {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
    }
    .stButton button {
        font-size: 1.1rem !important;
    }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
        font-size: 1.1rem !important;
        min-height: 2.85rem !important;
    }

    /* 图片中的文本框适当放大 */
    .stTextInput input {
        padding-top: 0.55rem !important;
        padding-bottom: 0.55rem !important;
    }
    .stSelectbox div[data-baseweb="select"] > div {
        min-height: 2.9rem !important;
    }

    /* 侧边栏字体 */
    section[data-testid="stSidebar"] * {
        font-size: 1.1rem !important;
        line-height: 1.6 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p strong {
        font-size: 1.2rem !important;
        font-weight: 700 !important;
    }

    /* 故事工坊标题更大（仅侧边栏） */
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] h1 {
        font-size: 1.65rem !important;
        font-weight: 800 !important;
        line-height: 1.25 !important;
        letter-spacing: 0.01em;
        margin-bottom: 0.6rem !important;
    }

    /* 导航小标题（选择功能） */
    section[data-testid="stSidebar"] .nav-section-title {
        display: block !important;
        margin: 0.32rem 0 0.65rem 0 !important;
        padding: 0 !important;
        color: #2c3e50 !important;
        font-size: 1.50rem !important;
        font-weight: 800 !important;
        line-height: 1.25 !important;
        letter-spacing: 0.01em !important;
    }

    /* checkbox 间距保持原有舒适度 */
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label {
        margin-bottom: 0.38rem !important;
    }

    /* 将「创作新故事 / 我的故事」两行间距调大 */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
        margin-bottom: 0.72rem !important;
    }

    /* 选择功能选项字号（低于小标题） */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
        font-size: 1.18rem !important;
        line-height: 1.5 !important;
    }

    .chapter-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        font-size: 1.18rem !important;
        font-weight: 700;
        line-height: 1.48;
    }
    .illustration-box {
        background: #f8f9fa;
        border-left: 4px solid #667eea;
        padding: 1rem;
        margin: 0.5rem 0;
        font-style: italic;
        font-size: 1.06rem !important;
        line-height: 1.62;
    }
    .parent-panel {
        background: #fff8e6;
        padding: 0.75rem;
        border-radius: 8px;
        border: 1px solid #f0d78c;
        font-size: 1rem !important;
        margin-bottom: 0.6rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


def init_session_state():
    if "story_config" not in st.session_state:
        st.session_state.story_config = None
    if "chapters" not in st.session_state:
        st.session_state.chapters = []
    if "current_chapter_num" not in st.session_state:
        st.session_state.current_chapter_num = 0
    if "selected_branch" not in st.session_state:
        st.session_state.selected_branch = None
    if "story_complete" not in st.session_state:
        st.session_state.story_complete = False
    if "branch_history" not in st.session_state:
        st.session_state.branch_history = []
    if "draft_story_id" not in st.session_state:
        st.session_state.draft_story_id = None
    if "generation_paused" not in st.session_state:
        st.session_state.generation_paused = False
    if "cancel_notice" not in st.session_state:
        st.session_state.cancel_notice = ""
    if "cancel_session_confirming" not in st.session_state:
        st.session_state.cancel_session_confirming = False
    if "pending_delete_story_id" not in st.session_state:
        st.session_state.pending_delete_story_id = None


def render_story_form():
    st.markdown('<h1 class="main-header">📖 AI 互动故事生成器</h1>', unsafe_allow_html=True)
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        theme = st.text_input(
            "故事主题",
            placeholder="例如：勇敢的小探险家、神秘的森林、太空冒险",
            help="你想讲什么样的故事？",
        )
        protagonist = st.text_input(
            "主角设定",
            placeholder="例如：一只名叫小橘的猫咪、一个喜欢科学的女孩小明",
            help="故事的主角是谁？",
        )
        style = st.selectbox(
            "写作风格",
            ["轻松幽默", "温馨治愈", "紧张刺激", "奇幻冒险", "日常校园", "童话寓言"],
            help="故事的整体风格",
        )

    with col2:
        age_range = st.selectbox(
            "目标年龄段",
            ["3-6岁（幼儿）", "7-12岁（儿童）", "13-18岁（青少年）", "全年龄"],
            help="故事适合谁阅读？",
        )
        values = st.text_input(
            "价值观导向",
            placeholder="例如：勇气、友谊、诚实、环保、探索精神",
            value="勇敢、善良、友爱",
            help="故事希望传递的价值观",
        )

    return {
        "theme": theme,
        "protagonist": protagonist,
        "style": style,
        "age_range": age_range,
        "values": values,
    }


def validate_config(config: dict) -> tuple:
    return validate_story_settings(config)


def _chapter_display_body(ch: dict, filter_on: bool) -> str:
    return ch.get("content", "") or ""


def _extract_title_and_clean_body(body: str, chapter_num: int) -> tuple[str, str]:
    """从正文中提取章节标题，并移除正文里的“第X章/标题”重复信息。"""
    text = (body or "").strip()
    if not text:
        return f"第{chapter_num}章", ""

    original_lines = text.split("\n")
    lines = original_lines.copy()

    # 只过滤非常明确的模板行，避免误删正文
    skip_prefix = re.compile(
        r"^(开头|背景|事件|高潮|结尾|分支选择|分支描述要简短|现在\s*，?\s*写(?:故事)?正文|字数控制|直接开始|最终结构|写故事)\s*[:：]"
    )
    while lines and skip_prefix.search(lines[0].strip()):
        lines.pop(0)

    if not lines:
        lines = original_lines.copy()

    first = lines[0].strip() if lines else ""

    m = re.match(
        r"^(?:#{1,6}\s*)?第\s*([一二三四五六七八九十0-9]+)\s*章\s*[：:]?\s*(.*)$",
        first,
    )
    if m:
        tail_raw = (m.group(2) or "").strip()
        title = f"第{chapter_num}章"

        # 标题判断规则：短长度（<=10字）+ 无句号（。或.）
        remainder_from_first = ""
        if tail_raw:
            maybe_title = tail_raw.strip(" ：:，,；;。!！?？\"'“”‘’")
            is_short_title = len(maybe_title) <= 10
            no_period = ("。" not in maybe_title) and ("." not in maybe_title)

            if maybe_title and is_short_title and no_period:
                title = maybe_title
            else:
                remainder_from_first = tail_raw

        body_lines = []
        if remainder_from_first:
            body_lines.append(remainder_from_first)
        body_lines.extend(lines[1:])
        cleaned = "\n".join(body_lines).strip()
    else:
        title = f"第{chapter_num}章"
        cleaned = "\n".join(lines).strip()

    # 去掉正文开头再次出现的“第X章 ...”行（避免正文重复标题）
    heading_line = re.compile(r"^(?:#{1,6}\s*)?第\s*[一二三四五六七八九十0-9]+\s*章(?:\s*[：:].*)?$")
    cleaned_split = cleaned.split("\n") if cleaned else []
    while cleaned_split and heading_line.match(cleaned_split[0].strip()):
        cleaned_split.pop(0)
    cleaned = "\n".join(cleaned_split).strip()

    # 若已识别出自定义短标题，则移除正文开头重复的同名标题行（标题只在紫色框显示）
    if title and title != f"第{chapter_num}章" and cleaned:
        title_line = re.compile(rf"^(?:#{1,6}\s*)?{re.escape(title)}\s*$")
        split2 = cleaned.split("\n")
        while split2 and title_line.match(split2[0].strip()):
            split2.pop(0)
        cleaned = "\n".join(split2).strip()

    # 二次过滤仅移除“明确模板行”
    cleaned_lines = []
    for ln in cleaned.split("\n"):
        s = ln.strip()
        if not s:
            cleaned_lines.append(ln)
            continue
        if skip_prefix.search(s):
            continue
        cleaned_lines.append(ln)

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return title, cleaned


def _sanitize_ui_text(text: str, single_line: bool = False) -> str:
    """展示层兜底清洗：去掉 markdown 残留与异常标点。"""
    if not text or not isinstance(text, str):
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\*\*+", "", s)
    s = re.sub(r"__+", "", s)
    s = re.sub(r"`+", "", s)
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*•·]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\s\-—_~•·*#`，,。；;：:、|]+", "", s)
    s = re.sub(r"(?m)^\s*[\-—_~•·*#`，,。；;：:、|]+", "", s)
    s = re.sub(r"([，。！？；：,.!?;:、])\1+", r"\1", s)
    if single_line:
        s = " ".join(seg.strip() for seg in s.split("\n") if seg.strip())
    else:
        s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _chapter_display_illustration(ch: dict, filter_on: bool) -> str:
    default_empty = "（本章暂无插画描述）"
    return _sanitize_ui_text(ch.get("illustration", default_empty), single_line=True)


def render_chapter(chapter_data: dict, chapter_num: int, filter_display: bool = True):
    body = _chapter_display_body(chapter_data, filter_display)

    heading = chapter_data.get("heading") or {}
    chapter_label = (heading.get("chapter_label") or f"第{chapter_num}章").strip()
    heading_title = (heading.get("title") or "").strip()

    if heading_title:
        title = heading_title
        cleaned_body = _extract_title_and_clean_body(body, chapter_num)[1]
    else:
        title, cleaned_body = _extract_title_and_clean_body(body, chapter_num)

    box_title = chapter_label if title == chapter_label else f"{chapter_label} · {title}"

    st.markdown(
        f'<div class="chapter-box">{box_title}</div>',
        unsafe_allow_html=True,
    )
    if chapter_data.get("retry_info"):
        st.caption(chapter_data["retry_info"])

    if cleaned_body:
        st.markdown(cleaned_body)

    ill = _chapter_display_illustration(chapter_data, filter_display)
    if ill:
        st.markdown(
            f'<div class="illustration-box">🖼️ 插画描述：{ill}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")


def _clear_active_story_session():
    """结束当前故事会话，回到空白创作表单"""
    st.session_state.story_config = None
    st.session_state.chapters = []
    st.session_state.current_chapter_num = 0
    st.session_state.selected_branch = None
    st.session_state.story_complete = False
    st.session_state.branch_history = []
    st.session_state.generation_paused = False
    st.session_state.cancel_session_confirming = False


def _clear_story_browse_state() -> bool:
    """清理「我的故事」浏览相关状态，避免回到创作页时残留。返回是否有状态被清除。"""
    cleared = False
    for k in ("viewing_story_id", "replay_pick_story_id", "replay_mode_choice"):
        if k in st.session_state:
            del st.session_state[k]
            cleared = True
    return cleared


def _apply_story_config_from_dict(cfg: dict):
    """从我的故事载入设定，清空章节，从第一章重新生成（全新开篇）"""
    st.session_state.story_config = {
        "theme": cfg.get("theme", ""),
        "protagonist": cfg.get("protagonist", ""),
        "style": cfg.get("style", "轻松幽默"),
        "age_range": cfg.get("age_range", "全年龄"),
        "values": cfg.get("values", "勇敢、善良、友爱"),
    }
    st.session_state.chapters = []
    st.session_state.current_chapter_num = 1
    st.session_state.selected_branch = None
    st.session_state.story_complete = False
    st.session_state.branch_history = []
    st.session_state.generation_paused = False


def _apply_replay_keep_chapter1(story: dict) -> tuple:
    """
    保留存档中第一章原文与分支选项，从选分支继续（第2章起重新生成）。
    返回 (成功, 错误说明)
    """
    chapters_saved = story.get("chapters") or []
    if not chapters_saved:
        return False, "存档中没有章节内容，无法保留第一章。"
    raw_ch1 = chapters_saved[0]
    opts = raw_ch1.get("choices") or []
    if not opts:
        return False, "第一章没有可用的分支选项，请改用「从第一章重新生成」。"

    # 与存档一致，但去掉正文里重复的【分支A/B/C】，分支仅保留在 choices 与按钮
    ch1 = normalize_chapter_for_replay(raw_ch1)
    body = (ch1.get("content") or "").strip()
    if not body:
        return False, "第一章正文在清理后为空，请改用「从第一章重新生成」。"

    st.session_state.story_config = {
        "theme": story.get("theme", ""),
        "protagonist": story.get("protagonist", ""),
        "style": story.get("style", "轻松幽默"),
        "age_range": story.get("age_range", "全年龄"),
        "values": story.get("values", "勇敢、善良、友爱"),
    }
    st.session_state.chapters = [ch1]
    st.session_state.current_chapter_num = 1
    st.session_state.selected_branch = None
    st.session_state.story_complete = False
    st.session_state.branch_history = []
    st.session_state.generation_paused = False
    return True, ""


def _render_replay_mode_dialog():
    """重新选分支：让用户选择「保留第一章」或「重新生成第一章」"""
    sid = st.session_state.get("replay_pick_story_id")
    if not sid:
        return

    story = get_story_by_id(sid)
    if not story:
        del st.session_state.replay_pick_story_id
        st.error("找不到该故事，请返回列表。")
        return

    st.subheader("🔁 重新选分支")
    st.caption(
        f"故事：**{story.get('theme', '未命名')}** · 主角：{story.get('protagonist', '')}"
    )
    mode = st.radio(
        "请选择体验方式：",
        options=["keep_ch1", "regen"],
        format_func=lambda x: (
            "保留第一章原文，从分支继续（第2～5章将按你的新选择重新生成）"
            if x == "keep_ch1"
            else "沿用原故事设定，从第一章重新生成（全新开篇，与旧第一章无关）"
        ),
        key="replay_mode_choice",
    )
    st.caption(
        "说明：第一种保留你已读过的第一章与分支按钮；第二种会重新调用 AI 写第一章。"
    )
    if st.session_state.get("story_config"):
        st.warning(
            "⚠️ 若当前有进行中的创作，确认后将**覆盖**未保存进度；"
            "若已点「暂停下一章」，请先决定是「继续生成」还是再选分支。"
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ 确认并开始", type="primary", key="replay_confirm"):
            if mode == "keep_ch1":
                ok, err = _apply_replay_keep_chapter1(story)
                if not ok:
                    st.error(err)
                    return
            else:
                _apply_story_config_from_dict(story)
            st.session_state.generation_paused = False
            if "replay_pick_story_id" in st.session_state:
                del st.session_state.replay_pick_story_id
            if "viewing_story_id" in st.session_state:
                del st.session_state.viewing_story_id
            _schedule_pending_nav("✨ 创作新故事")
            st.rerun()

    with c2:
        if st.button("取消", key="replay_cancel"):
            del st.session_state.replay_pick_story_id
            st.rerun()


def main_new_story():
    init_session_state()

    parent_mode = st.session_state.get("parent_mode", True)
    filter_display = st.session_state.get("filter_display", True)
    strict_gen = st.session_state.get("strict_generation", True)

    # 无进行中的故事：显示设定表单
    if not st.session_state.story_config:
        config = render_story_form()

        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        if st.button("开始创作第一章", type="primary", use_container_width=True):
            with st.spinner("正在对故事设定进行安全审核…"):
                valid, err_msg = validate_config(config)
            if not valid:
                st.error(f"❌ 故事设定未通过安全审核：{err_msg}")
                return
            st.success("✅ 故事设定已通过安全审核，开始生成第一章…")

            st.session_state.story_config = config
            st.session_state.chapters = []
            st.session_state.current_chapter_num = 1
            st.session_state.selected_branch = None
            st.session_state.story_complete = False
            st.session_state.branch_history = []
            st.session_state.generation_paused = False
            st.rerun()
        return

    # 已有进行中的故事
    config = st.session_state.story_config
    chapters = st.session_state.chapters
    current_num = st.session_state.current_chapter_num
    selected_branch = st.session_state.selected_branch

    with st.expander("📋 当前故事设定（可展开查看）", expanded=False):
        st.write(
            f"**主题**：{config.get('theme')}  \n"
            f"**主角**：{config.get('protagonist')}  \n"
            f"**风格**：{config.get('style')}  \n"
            f"**年龄段**：{config.get('age_range')}  \n"
            f"**价值观**：{config.get('values')}"
        )

    if st.session_state.get("cancel_notice"):
        st.success(st.session_state.cancel_notice)
        st.session_state.cancel_notice = ""

    c_cancel_1, c_cancel_2 = st.columns([1, 2])
    with c_cancel_1:
        if st.button("🧹 彻底取消这一次会话", key="cancel_story_session_btn"):
            st.session_state.cancel_session_confirming = True
            st.rerun()

    if st.session_state.get("cancel_session_confirming"):
        st.warning(
            "确认后将清空本次会话的章节、分支与暂停状态，且不会自动保存。"
        )
        d1, d2 = st.columns(2)
        with d1:
            if st.button(
                "✅ 确认彻底取消",
                type="primary",
                key="confirm_cancel_story_session",
            ):
                _clear_active_story_session()
                st.session_state.cancel_session_confirming = False
                st.session_state.cancel_notice = (
                    "已彻底取消本次会话。你现在可以重新选择选项，或用新设定创作新故事。"
                )
                st.rerun()
        with d2:
            if st.button("再想想", key="abort_cancel_story_session"):
                st.session_state.cancel_session_confirming = False
                st.rerun()

    for i, ch in enumerate(chapters, 1):
        render_chapter(ch, i, filter_display=filter_display)

    # ---------- 第五章已完结：后续操作（独立判断，避免被 current_num<=5 挡住）----------
    if st.session_state.story_complete and len(chapters) >= 5:
        st.success("🎉 全部 5 章已生成，本篇故事已完结！请选择下一步：")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("💾 保存并继续创建新故事", type="primary", use_container_width=True):
                full_content = build_full_text_from_chapters(chapters)
                story_data = {
                    "theme": config["theme"],
                    "protagonist": config["protagonist"],
                    "style": config["style"],
                    "age_range": config["age_range"],
                    "values": config["values"],
                    "chapters": chapters,
                    "branch_history": list(st.session_state.branch_history),
                    "status": "completed",
                    "full_content": full_content,
                    "parent_mode_snapshot": {
                        "filter_display": filter_display,
                        "strict_generation": strict_gen,
                    },
                }
                sid = save_story(story_data)
                st.success(f"已保存到「我的故事」，ID：`{sid}`")
                _clear_active_story_session()
                st.rerun()

        with c2:
            if st.button("🗑️ 不保存，直接开始新故事", use_container_width=True):
                st.warning("本篇未保存到「我的故事」。")
                _clear_active_story_session()
                st.rerun()

        with c3:
            if st.button("📚 保存并前往「我的故事」", use_container_width=True):
                full_content = build_full_text_from_chapters(chapters)
                story_data = {
                    "theme": config["theme"],
                    "protagonist": config["protagonist"],
                    "style": config["style"],
                    "age_range": config["age_range"],
                    "values": config["values"],
                    "chapters": chapters,
                    "branch_history": list(st.session_state.branch_history),
                    "status": "completed",
                    "full_content": full_content,
                    "parent_mode_snapshot": {
                        "filter_display": filter_display,
                        "strict_generation": strict_gen,
                    },
                }
                save_story(story_data)
                _clear_active_story_session()
                _schedule_pending_nav("📚 我的故事")
                st.rerun()

        return

    # ---------- 未完结：生成或选分支 ----------
    if current_num <= 5 and not st.session_state.story_complete:
        need_generate = (current_num == 1 and len(chapters) == 0) or (
            current_num > 1 and selected_branch and len(chapters) < current_num
        )

        if need_generate:
            if st.session_state.get("generation_paused"):
                st.warning(
                    "⏸ **已暂停自动生成。** 请稍后再点击「继续生成」（侧边栏或下方），"
                    "或「回到上一章重选分支」后再继续。"
                )
                rc1, rc2 = st.columns(2)
                with rc1:
                    if st.button("▶ 继续生成", type="primary", key="main_resume_gen"):
                        st.session_state.generation_paused = False
                        st.rerun()
                with rc2:
                    if st.button("↩ 回到上一章重选分支", key="main_back_branch"):
                        st.session_state.generation_paused = False
                        st.session_state.selected_branch = None
                        st.session_state.current_chapter_num = max(1, len(chapters))
                        if st.session_state.branch_history:
                            st.session_state.branch_history.pop()
                        st.rerun()
                return

            with st.spinner("AI 正在创作中，请稍候..."):
                result = generate_chapter(
                    theme=config["theme"],
                    protagonist=config["protagonist"],
                    style=config["style"],
                    age_range=config["age_range"],
                    values=config["values"],
                    chapter_num=current_num,
                    previous_chapters=chapters,
                    chosen_branch=selected_branch if current_num > 1 else None,
                    strict_generation=strict_gen,
                )

            if result.get("error"):
                st.error(result["content"])
                if strict_gen:
                    st.warning(
                        "家长模式：生成内容未通过审核时将自动重试。您也可在侧边栏暂时关闭「生成时严格审核」后重试（请家长监护）。"
                    )
                return

            chapters.append(result)
            st.session_state.chapters = chapters

            if current_num == 5:
                st.session_state.story_complete = True
                st.session_state.current_chapter_num = 6

            st.rerun()

        if chapters:
            last_chapter = chapters[-1]
            choices = last_chapter.get("choices", [])

            if choices and not st.session_state.story_complete:
                st.markdown("**选择剧情走向：**")
                for choice in choices:
                    btn_label = _sanitize_ui_text(choice.get("text") or "", single_line=True) or (
                        f"选项 {choice['id']}"
                    )
                    if st.button(
                        btn_label,
                        key=f"branch_{current_num}_{choice['id']}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        st.session_state.selected_branch = (
                            f"【分支{choice['id']}】 {btn_label}"
                        )
                        st.session_state.branch_history.append(
                            {
                                "after_chapter": current_num,
                                "choice_id": choice["id"],
                                "choice_text": choice["text"],
                            }
                        )
                        st.session_state.current_chapter_num = current_num + 1
                        st.rerun()


def main_my_stories():
    init_session_state()
    filter_display = st.session_state.get("filter_display", True)

    st.markdown('<h1 class="main-header">📚 我的故事</h1>', unsafe_allow_html=True)
    st.markdown("---")

    # 重新选分支：先让用户选择「保留第一章」或「重新生成第一章」
    if st.session_state.get("replay_pick_story_id"):
        _render_replay_mode_dialog()
        return

    if "viewing_story_id" in st.session_state:
        story_id = st.session_state.viewing_story_id
        story = get_story_by_id(story_id)
        if story:
            st.subheader(story.get("theme", "未命名"))
            meta = f"主角：{story.get('protagonist', '')} | 风格：{story.get('style', '')} | 保存时间：{str(story.get('created_at', ''))[:19]}"
            st.caption(meta)
            bh = story.get("branch_history") or []
            if bh:
                with st.expander("📜 本次游玩的剧情选择记录"):
                    for step in bh:
                        st.write(
                            f"第{step.get('after_chapter', '?')} 章后 → 分支 **{step.get('choice_id', '')}**：{step.get('choice_text', '')}"
                        )
            fc = story.get("full_content", "")
            if fc:
                with st.expander("📄 完整文本（可复制）"):
                    st.text_area("全文", fc, height=200, label_visibility="collapsed")

            st.markdown("---")
            for i, ch in enumerate(story.get("chapters", []), 1):
                render_chapter(ch, i, filter_display=filter_display)

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("← 返回列表", key="back_list"):
                    del st.session_state.viewing_story_id
                    st.rerun()
            with b2:
                if st.button("🔁 相同设定重新选分支", type="primary", key="replay_branches"):
                    st.session_state.replay_pick_story_id = story_id
                    st.rerun()
            with b3:
                is_pending = st.session_state.get("pending_delete_story_id") == story_id
                if not is_pending:
                    if st.button("🗑️ 删除此故事", key="del_this"):
                        st.session_state.pending_delete_story_id = story_id
                        st.rerun()
                else:
                    st.warning("确认删除后将无法恢复。")
                    c_del1, c_del2 = st.columns(2)
                    with c_del1:
                        if st.button("✅ 确认删除", key=f"confirm_del_{story_id}"):
                            if delete_story(story_id):
                                st.session_state.pending_delete_story_id = None
                                del st.session_state.viewing_story_id
                                st.success("已删除")
                                st.rerun()
                    with c_del2:
                        if st.button("取消", key=f"cancel_del_{story_id}"):
                            st.session_state.pending_delete_story_id = None
                            st.rerun()
        return

    stories = get_all_stories()
    if not stories:
        st.info("还没有保存过故事。完成 5 章后可在创作页选择「保存」到这里。")
        return

    for s in stories:
        status_badge = "📝 草稿" if s.get("status") == "draft" else "✅ 完结"
        line = f"{s['theme']} · {s['protagonist']} · {status_badge} · {s['chapter_count']}章 · {str(s.get('created_at', ''))[:16]}"
        with st.expander(line):
            st.caption(f"ID: `{s['id']}`")
            b1, b2, b3, b4 = st.columns(4)
            with b1:
                if st.button("📖 查看情节", key=f"read_{s['id']}"):
                    st.session_state.viewing_story_id = s["id"]
                    st.rerun()
            with b2:
                if st.button("🔁 重新选分支", key=f"replay_{s['id']}"):
                    st.session_state.replay_pick_story_id = s["id"]
                    st.rerun()
            with b3:
                sid = s["id"]
                is_pending = st.session_state.get("pending_delete_story_id") == sid
                if not is_pending:
                    if st.button("删除", key=f"del_{sid}"):
                        st.session_state.pending_delete_story_id = sid
                        st.rerun()
                else:
                    st.warning("确认删除后将无法恢复。")
                    c_del1, c_del2 = st.columns(2)
                    with c_del1:
                        if st.button("✅ 确认删除", key=f"confirm_del_{sid}"):
                            if delete_story(sid):
                                st.session_state.pending_delete_story_id = None
                                st.success("已删除")
                                st.rerun()
                    with c_del2:
                        if st.button("取消", key=f"cancel_del_{sid}"):
                            st.session_state.pending_delete_story_id = None
                            st.rerun()
            with b4:
                pass


def main():
    init_session_state()
    # 必须在创建 key=nav_radio 的 radio 之前应用待切换页面，否则会 StreamlitAPIException
    _apply_pending_nav_before_widgets()

    st.sidebar.title("📖 故事工坊")
    st.sidebar.markdown(
        '<div class="parent-panel"><b>👪 家长模式</b></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<div style="height: 6px;"></div>', unsafe_allow_html=True)
    st.session_state.parent_mode = st.sidebar.checkbox(
        "开启家长模式",
        value=st.session_state.get("parent_mode", True),
        help="关闭后部分保护选项将放开，请确保有家长监护。",
    )
    pm = st.session_state.parent_mode
    st.session_state.strict_generation = st.sidebar.checkbox(
        "生成时严格审核",
        value=st.session_state.get("strict_generation", True),
        disabled=not pm,
        help="关闭后不再因本地敏感词拦截而重试生成（不推荐儿童单独使用）。",
    )
    st.session_state.filter_display = st.sidebar.checkbox(
        "展示时过滤敏感词",
        value=st.session_state.get("filter_display", True),
        disabled=not pm,
        help="开启时用 *** 替换敏感词；关闭则显示原文（含未掩码，请谨慎）。",
    )
    if not pm:
        st.sidebar.warning("家长模式已关闭，请自行承担内容风险。")

    # 创作进行中：暂停 / 继续（避免与「重新选分支」等操作冲突）
    if st.session_state.get("story_config") and not st.session_state.get(
        "story_complete"
    ):
        st.sidebar.markdown("---")
        st.sidebar.markdown("**🤖 AI 创作**")
        st.sidebar.caption("暂停后不会自动请求下一章，需点「继续生成」。")
        if st.session_state.get("generation_paused"):
            if st.sidebar.button("▶ 继续生成", key="sidebar_resume_gen", type="primary"):
                st.session_state.generation_paused = False
                st.rerun()
        else:
            if st.sidebar.button("⏸ 暂停下一章生成", key="sidebar_pause_gen"):
                st.session_state.generation_paused = True
                st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown('<div class="nav-section-title">选择功能</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div style="height: 6px;"></div>', unsafe_allow_html=True)
    page = st.sidebar.radio(
        "",
        ["✨ 创作新故事", "📚 我的故事"],
        key="nav_radio",
        label_visibility="collapsed",
    )

    if page == "✨ 创作新故事":
        # 先清浏览态并立即重跑，避免本轮渲染中仍带出旧界面块
        if _clear_story_browse_state():
            st.rerun()
        main_new_story()
    else:
        main_my_stories()


if __name__ == "__main__":
    main()
