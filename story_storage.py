# -*- coding: utf-8 -*-
"""
故事存储模块
将故事保存到 stories.json，支持完整字段：ID、主题、章节、剧情选择历史、生成时间、完整文本等
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

STORIES_FILE = "stories.json"


def _ensure_stories_file():
    if not os.path.exists(STORIES_FILE):
        _save_stories([])


def _load_stories() -> list:
    _ensure_stories_file()
    try:
        with open(STORIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_stories(stories: list) -> None:
    with open(STORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(stories, f, ensure_ascii=False, indent=2)


def build_full_text_from_chapters(chapters: List[Dict[str, Any]]) -> str:
    """
    将章节列表拼接为可阅读的完整故事文本（用于检索与导出）
    """
    lines = []
    for i, ch in enumerate(chapters or [], 1):
        lines.append(f"=== 第{i}章 ===\n{ch.get('content', '')}\n")
        ill = ch.get("illustration", "")
        if ill and ill != "（本章暂无插画描述）":
            lines.append(f"【插画】{ill}\n")
    return "\n".join(lines).strip()


def save_story(story_data: dict) -> str:
    """
    保存单个故事（完成态或草稿）

    story_data 建议包含:
        theme, protagonist, style, age_range, values,
        chapters, branch_history（用户每步选择的剧情分支列表）,
        status: completed | draft,
        full_content（可选，不传则自动拼接）
    """
    stories = _load_stories()
    story_id = story_data.get("id") or datetime.now().strftime("%Y%m%d%H%M%S")
    story_data["id"] = story_id
    if "created_at" not in story_data:
        story_data["created_at"] = datetime.now().isoformat()
    story_data["updated_at"] = datetime.now().isoformat()

    chapters = story_data.get("chapters") or []
    if not story_data.get("full_content"):
        story_data["full_content"] = build_full_text_from_chapters(chapters)

    if "branch_history" not in story_data:
        story_data["branch_history"] = []

    stories.append(story_data)
    _save_stories(stories)
    return story_id


def update_story(story_id: str, story_data: dict) -> bool:
    """更新已有故事（例如草稿续写）"""
    stories = _load_stories()
    for i, s in enumerate(stories):
        if s.get("id") == story_id:
            story_data["id"] = story_id
            story_data["updated_at"] = datetime.now().isoformat()
            if "created_at" not in story_data and s.get("created_at"):
                story_data["created_at"] = s["created_at"]
            chapters = story_data.get("chapters") or []
            if not story_data.get("full_content"):
                story_data["full_content"] = build_full_text_from_chapters(chapters)
            stories[i] = {**s, **story_data}
            _save_stories(stories)
            return True
    return False


def delete_story(story_id: str) -> bool:
    stories = _load_stories()
    new_list = [s for s in stories if s.get("id") != story_id]
    if len(new_list) == len(stories):
        return False
    _save_stories(new_list)
    return True


def get_all_stories() -> list:
    stories = _load_stories()
    result = []
    for s in stories:
        chapters = s.get("chapters") or []
        result.append({
            "id": s.get("id", ""),
            "theme": s.get("theme", "未命名"),
            "protagonist": s.get("protagonist", ""),
            "style": s.get("style", ""),
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", s.get("created_at", "")),
            "status": s.get("status", "completed"),
            "chapter_count": len(chapters),
            "branch_steps": len(s.get("branch_history") or []),
        })
    result.sort(
        key=lambda x: x.get("updated_at") or x.get("created_at") or "",
        reverse=True,
    )
    return result


def get_story_by_id(story_id: str) -> Optional[dict]:
    stories = _load_stories()
    for s in stories:
        if s.get("id") == story_id:
            return s
    return None
