from __future__ import annotations

from pathlib import Path
from typing import Any

from .docx_writer import markdown_to_docx
from .file_utils import (
    ensure_directory,
    ensure_required_file,
    join_sections,
    list_sorted_images,
    read_docx_text,
    read_utf8_file,
    extract_markdown_section,
    replace_markdown_section,
    validate_exercises_markdown,
    validate_notes_markdown,
    write_utf8_file,
)
from .llm_client import LLMClient


def run_pipeline(
    *,
    input_dir: Path,
    output_dir: Path,
    prompts_dir: Path,
    samples_dir: Path,
    skills_dir: Path,
    llm_config: dict[str, Any] | None = None,
) -> dict[str, Path]:
    ensure_directory(output_dir)

    images = list_sorted_images(input_dir)
    sample_notes_path = ensure_required_file(samples_dir / "sample_notes.docx")
    sample_exercises_path = ensure_required_file(samples_dir / "sample_exercises.docx")
    notes_skill_path = ensure_required_file(skills_dir / "vocab_notes_skill.md")
    exercises_skill_path = ensure_required_file(skills_dir / "vocab_test_skill.md")
    extract_prompt_path = ensure_required_file(prompts_dir / "extract_text.md")
    notes_prompt_path = ensure_required_file(prompts_dir / "notes_prompt.md")
    exercises_prompt_path = ensure_required_file(prompts_dir / "exercises_prompt.md")

    client = LLMClient(config=llm_config)

    complete_texts = client.extract_complete_texts(
        build_extract_prompt(
            base_prompt=read_utf8_file(extract_prompt_path),
            image_paths=images,
        ),
        images,
    )
    complete_texts_path = output_dir / "complete_texts.md"
    write_utf8_file(complete_texts_path, complete_texts)

    unit_notes = client.generate_notes(
        build_notes_prompt(
            base_prompt=read_utf8_file(notes_prompt_path),
            complete_texts=read_utf8_file(complete_texts_path),
            notes_skill=read_utf8_file(notes_skill_path),
            sample_notes_text=read_docx_text(sample_notes_path),
        )
    )
    unit_notes = review_notes_until_valid(
        client=client,
        complete_texts=read_utf8_file(complete_texts_path),
        notes_skill=read_utf8_file(notes_skill_path),
        sample_notes_text=read_docx_text(sample_notes_path),
        draft=unit_notes,
    )
    unit_notes_path = output_dir / "unit_notes.md"
    write_utf8_file(unit_notes_path, unit_notes)
    unit_notes_docx_path = output_dir / "unit_notes.docx"
    markdown_to_docx(unit_notes, unit_notes_docx_path)

    unit_exercises = client.generate_exercises(
        build_exercises_prompt(
            base_prompt=read_utf8_file(exercises_prompt_path),
            unit_notes=read_utf8_file(unit_notes_path),
            exercises_skill=read_utf8_file(exercises_skill_path),
            sample_exercises_text=read_docx_text(sample_exercises_path),
        )
    )
    unit_exercises = review_exercises_until_valid(
        client=client,
        unit_notes=read_utf8_file(unit_notes_path),
        exercises_skill=read_utf8_file(exercises_skill_path),
        sample_exercises_text=read_docx_text(sample_exercises_path),
        draft=unit_exercises,
    )
    unit_exercises_path = output_dir / "unit_exercises.md"
    write_utf8_file(unit_exercises_path, unit_exercises)
    unit_exercises_docx_path = output_dir / "unit_exercises.docx"
    markdown_to_docx(unit_exercises, unit_exercises_docx_path)

    return {
        "complete_texts_md": complete_texts_path,
        "unit_notes_md": unit_notes_path,
        "unit_notes_docx": unit_notes_docx_path,
        "unit_exercises_md": unit_exercises_path,
        "unit_exercises_docx": unit_exercises_docx_path,
    }


def build_extract_prompt(base_prompt: str, image_paths: list[Path]) -> str:
    ordered_names = "\n".join(f"- {path.name}" for path in image_paths)
    return join_sections(
        [
            base_prompt,
            "以下图片已按文件名排序，请严格按照这个顺序整合教材内容：",
            ordered_names,
        ]
    )


def build_notes_prompt(
    base_prompt: str,
    complete_texts: str,
    notes_skill: str,
    sample_notes_text: str,
) -> str:
    return join_sections(
        [
            base_prompt,
            "以下是必须遵守的技能规则：",
            shorten_for_review(notes_skill, 2600),
            "以下是 sample_notes.docx 的本地结构摘要，仅用于学习结构、教学密度和版式语气，不得照抄内容：",
            summarize_notes_sample(sample_notes_text),
            "以下是 complete_texts.md 正文，请严格基于它生成词汇笔记：",
            complete_texts,
        ]
    )


def build_exercises_prompt(
    base_prompt: str,
    unit_notes: str,
    exercises_skill: str,
    sample_exercises_text: str,
) -> str:
    return join_sections(
        [
            base_prompt,
            "以下是必须遵守的技能规则：",
            shorten_for_review(exercises_skill, 3200),
            "以下是 sample_exercises.docx 的本地结构摘要，仅用于学习题型结构、题量和解析风格，不得照抄题目：",
            summarize_exercises_sample(sample_exercises_text),
            "以下是 unit_notes.md 正文。请严格只基于它命题，不要引用截图或 complete_texts.md：",
            unit_notes,
        ]
    )


def build_notes_review_prompt(
    complete_texts: str,
    notes_skill: str,
    draft: str,
    validation_errors: list[str],
) -> str:
    checklist = """
你现在要审查一份已经生成好的 unit_notes.md 草稿。

任务：
1. 先检查这份草稿是否符合 skill 规则和 sample 的结构/教学密度要求。
2. 如果已经完整合格，只输出一个词：PASS
3. 如果不完整、漏部分、结构不对、密度不足、缺少必要项目，直接输出“修订后的完整 markdown 正文”。
""".strip()
    return join_sections(
        [
            checklist,
            "以下是本次复查必须遵守的规则摘要：",
            build_notes_review_rules(notes_skill),
            "以下是 complete_texts.md 的关键信息摘录：",
            shorten_for_review(complete_texts, 3500),
            "以下是程序检测到的硬性问题，请全部修复：",
            "\n".join(f"- {error}" for error in validation_errors) if validation_errors else "- 无",
            "以下是当前 unit_notes.md 草稿：",
            draft,
        ]
    )


def build_exercises_review_prompt(
    unit_notes: str,
    exercises_skill: str,
    draft: str,
    validation_errors: list[str],
) -> str:
    checklist = """
你现在要审查一份已经生成好的 unit_exercises.md 草稿。

任务：
1. 先检查这份草稿是否符合 skill 规则和 sample 的结构/题量/答案解析要求。
2. 如果已经完整合格，只输出一个词：PASS
3. 如果不完整、漏部分、题量不够、答案解析缺失、结构不对，直接输出“修订后的完整 markdown 正文”。
""".strip()
    return join_sections(
        [
            checklist,
            "以下是本次复查必须遵守的规则摘要：",
            build_exercises_review_rules(exercises_skill),
            "以下是 unit_notes.md 的关键信息摘录：",
            shorten_for_review(unit_notes, 4500),
            "以下是程序检测到的硬性问题，请全部修复：",
            "\n".join(f"- {error}" for error in validation_errors) if validation_errors else "- 无",
            "以下是当前 unit_exercises.md 草稿：",
            draft,
        ]
    )


def build_notes_review_rules(notes_skill: str) -> str:
    return join_sections(
        [
            "必须保留五个固定大部分，顺序不能改。",
            "第五部分补充词组必须主要来自课文/对话里的短语、小句、固定表达。",
            "第五部分优先覆盖：动词词组、形容词/状态表达、名词词组/固定小句。",
            "不要扩展到其他单元。",
            "以下是完整 skill 供参考：",
            shorten_for_review(notes_skill, 2500),
        ]
    )


def build_exercises_review_rules(exercises_skill: str) -> str:
    return join_sections(
        [
            "练习题必须严格基于 unit_notes.md。",
            "单选题必须 20 题。",
            "语法填空必须 20 空，其中 14 个有提示词、6 个无提示词。",
            "十一选十必须 2 篇，每篇 11 个词填 10 个空，并有 1 个多余词。",
            "阅读理解必须 2 篇，每篇 5 题。",
            "答案与解析必须完整。",
            "以下是完整 skill 供参考：",
            shorten_for_review(exercises_skill, 3000),
        ]
    )


def shorten_for_review(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n\n[以下内容已截断，用于控制复查上下文长度]"


def review_notes_until_valid(
    client: LLMClient,
    complete_texts: str,
    notes_skill: str,
    sample_notes_text: str,
    draft: str,
) -> str:
    del sample_notes_text
    current = draft
    errors = validate_notes_markdown(current)
    if not errors:
        return current
    for _ in range(2):
        reviewed = client.review_notes(
            build_notes_review_prompt(
                complete_texts=complete_texts,
                notes_skill=notes_skill,
                draft=current,
                validation_errors=errors,
            )
        )
        current = current if reviewed.strip().upper() == "PASS" else reviewed
        errors = validate_notes_markdown(current)
        if not errors:
            return current
    return current


def review_exercises_until_valid(
    client: LLMClient,
    unit_notes: str,
    exercises_skill: str,
    sample_exercises_text: str,
    draft: str,
) -> str:
    del sample_exercises_text
    current = draft
    errors = validate_exercises_markdown(current)
    if not errors:
        return current
    for _ in range(2):
        section_pairs = determine_exercise_repairs(errors)
        if not section_pairs:
            reviewed = client.review_exercises(
                build_exercises_review_prompt(
                    unit_notes=unit_notes,
                    exercises_skill=exercises_skill,
                    draft=current,
                    validation_errors=errors,
                )
            )
            current = current if reviewed.strip().upper() == "PASS" else reviewed
        else:
            for section_heading, next_heading, answer_heading, next_answer_heading in section_pairs:
                related_errors = [
                    error for error in errors if error_matches_section(error, section_heading, answer_heading)
                ]
                repaired = client.review_exercises(
                    build_exercise_section_repair_prompt(
                        unit_notes=unit_notes,
                        exercises_skill=exercises_skill,
                        current_section=extract_markdown_section(current, section_heading, next_heading),
                        current_answer_section=extract_markdown_section(current, answer_heading, next_answer_heading),
                        error_messages=related_errors or errors,
                        target_section_heading=section_heading,
                        target_answer_heading=answer_heading,
                    )
                )
                new_section, new_answer = parse_repaired_sections(repaired)
                if new_section:
                    current = replace_markdown_section(current, section_heading, new_section, next_heading)
                if new_answer:
                    current = replace_markdown_section(current, answer_heading, new_answer, next_answer_heading)
        errors = validate_exercises_markdown(current)
        if not errors:
            return current
    return current


def build_exercise_section_repair_prompt(
    unit_notes: str,
    exercises_skill: str,
    current_section: str,
    current_answer_section: str,
    error_messages: list[str],
    target_section_heading: str,
    target_answer_heading: str,
) -> str:
    instructions = f"""
你现在只需要修复一份配套测试卷中的局部内容，而不是重写整份试卷。

目标：
1. 只重写 `{target_section_heading}` 这一整段。
2. 同时重写答案区里对应的 `{target_answer_heading}` 这一整段。
3. 其他部分不要输出。

输出格式必须严格如下：

<<<SECTION>>>
这里放修复后的题目 section 完整 markdown
<<<ANSWER_SECTION>>>
这里放修复后的答案 section 完整 markdown
""".strip()
    return join_sections(
        [
            instructions,
            "规则摘要：",
            build_exercises_review_rules(exercises_skill),
            "必须修复以下程序检测问题：",
            "\n".join(f"- {msg}" for msg in error_messages),
            "unit_notes.md 摘录：",
            shorten_for_review(unit_notes, 4500),
            "当前待修复的题目 section：",
            current_section,
            "当前待修复的答案 section：",
            current_answer_section,
        ]
    )


def summarize_notes_sample(sample_notes_text: str) -> str:
    del sample_notes_text
    return join_sections(
        [
            "标题风格：教材单元 + 法语主题 + 中文“词汇笔记 · Notes de vocabulaire”。",
            "整体结构：5 个固定大部分，顺序为核心动词、名词与词组、话题写作、语法结构、补充词组。",
            "核心动词部分：每个动词含变位表、固定搭配、例句中文解释、半控制性写作。",
            "名词与词组部分：按主题分类，用表格列词汇/中文/用法示例。",
            "话题写作部分：2-4 篇短文，法语后附中文翻译。",
            "语法部分：4-8 个点，每个点含结构、例句、说明、小练习片段。",
            "补充词组部分：10-20 条，优先课文短语、小句、固定表达，服务作文与口语。",
        ]
    )


def summarize_exercises_sample(sample_exercises_text: str) -> str:
    del sample_exercises_text
    return join_sections(
        [
            "标题风格：教材单元 + 配套测试卷 + 主题 + 姓名/日期/得分栏。",
            "固定结构：单选题、语法填空、十一选十、阅读理解、概要写作、控制性写作、答案与解析。",
            "题量要求：单选 20 题；语法填空 20 空；十一选十 2 篇；阅读 2 篇各 5 题。",
            "答案区风格：单选有简要解析，其余题型给标准答案或参考范文与评分点。",
            "整体语气：可直接发给学生使用，格式清楚，不要写成说明文。",
        ]
    )


def determine_exercise_repairs(errors: list[str]) -> list[tuple[str, str, str, str | None]]:
    pairs: list[tuple[str, str, str, str | None]] = []
    if any("语法填空" in error for error in errors):
        pairs.append(
            (
                "## 二、语法填空 Complétez le texte",
                "## 三、十一选十 Choix de mots",
                "### 二、语法填空答案",
                "### 三、十一选十答案",
            )
        )
    if any("十一选十" in error for error in errors):
        pairs.append(
            (
                "## 三、十一选十 Choix de mots",
                "## 四、阅读理解 Compréhension écrite",
                "### 三、十一选十答案",
                "### 四、阅读理解答案",
            )
        )
    if any("单选题" in error for error in errors):
        pairs.append(
            (
                "## 一、单选题 Choix multiples",
                "## 二、语法填空 Complétez le texte",
                "### 一、单选题答案",
                "### 二、语法填空答案",
            )
        )
    if any("阅读理解" in error for error in errors):
        pairs.append(
            (
                "## 四、阅读理解 Compréhension écrite",
                "## 五、概要写作 Résumé",
                "### 四、阅读理解答案",
                "### 五、概要写作参考要点",
            )
        )
    return pairs


def error_matches_section(error: str, section_heading: str, answer_heading: str) -> bool:
    if "语法填空" in error and "语法填空" in section_heading:
        return True
    if "十一选十" in error and "十一选十" in section_heading:
        return True
    if "单选题" in error and "单选题" in section_heading:
        return True
    if "阅读理解" in error and "阅读理解" in section_heading:
        return True
    if "缺少必需部分" in error and answer_heading.replace("### ", "") in error:
        return True
    return False


def parse_repaired_sections(text: str) -> tuple[str, str]:
    if "<<<SECTION>>>" not in text or "<<<ANSWER_SECTION>>>" not in text:
        return "", ""
    section_part = text.split("<<<SECTION>>>", 1)[1]
    if "<<<ANSWER_SECTION>>>" not in section_part:
        return "", ""
    section_body, answer_body = section_part.split("<<<ANSWER_SECTION>>>", 1)
    return section_body.strip(), answer_body.strip()
