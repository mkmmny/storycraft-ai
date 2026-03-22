# -*- coding: utf-8 -*-
"""
敏感词过滤模块
用于检测和过滤不健康内容，确保生成的故事适合各年龄段阅读

注意：避免过短的子串（如单字「性」）导致「性格」「长大成人」等误判
"""

from typing import Tuple, Dict, Any, List

# 敏感词库 - 使用完整词组，减少误判
SENSITIVE_WORDS: List[str] = [
    "暴力", "血腥", "色情", "淫秽", "赌博", "毒品",
    "自杀", "自残", "虐待", "仇恨",
    "裸露", "谋杀", "黑社会",
    "恐怖组织", "恐怖袭击", "政治敏感",
    # 以下词易误判，改为更具体短语（不用单独「成人」「性」）
    "成人网站", "成人视频", "色情网站", "黄色小说",
]

# 需整词/短语匹配的敏感词（避免「长大成人」误匹配「成人」）
PHRASE_ONLY_WORDS: List[str] = [
    "恐怖片", "恐怖游戏", "性交易", "性暴力",
]

def contains_sensitive_content(text: str) -> bool:
    """
    检查文本是否包含敏感词

    Args:
        text: 待检查的文本

    Returns:
        True 表示包含敏感词，False 表示安全
    """
    if not text or not isinstance(text, str):
        return False

    for word in SENSITIVE_WORDS:
        if word in text:
            return True
    for phrase in PHRASE_ONLY_WORDS:
        if phrase in text:
            return True
    return False


def filter_sensitive_content(text: str) -> str:
    """
    将敏感词替换为***，返回过滤后的文本
    """
    if not text or not isinstance(text, str):
        return text

    result = text
    for word in SENSITIVE_WORDS + PHRASE_ONLY_WORDS:
        result = result.replace(word, "***")
    return result


def validate_user_input(text: str) -> Tuple[bool, str]:
    """
    验证用户输入是否安全
    """
    if not text or not text.strip():
        return False, "不能为空"

    if contains_sensitive_content(text):
        return False, "包含不适宜内容，请修改后重试"

    return True, ""


def validate_story_settings(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    在开始前对完整故事设定做安全审核（主题、主角、价值观、风格等）

    Args:
        config: 含 theme, protagonist, style, age_range, values

    Returns:
        (是否通过, 失败时的说明)
    """
    checks = [
        ("故事主题", config.get("theme", "")),
        ("主角设定", config.get("protagonist", "")),
        ("价值观导向", config.get("values", "")),
        ("写作风格", str(config.get("style", ""))),
    ]

    for label, field_text in checks:
        if not field_text or not str(field_text).strip():
            if label in ("故事主题", "主角设定"):
                return False, f"{label}不能为空"
            continue

        ok, msg = validate_user_input(str(field_text))
        if not ok:
            return False, f"{label}未通过安全审核：{msg}"

    return True, ""

