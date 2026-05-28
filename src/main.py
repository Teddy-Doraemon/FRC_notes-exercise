from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .file_utils import (
    extract_markdown_section,
    join_sections,
    read_utf8_file,
    replace_markdown_section,
    validate_exercises_markdown,
    validate_notes_markdown,
)
from .llm_client import LLMClient
from .pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input" / "screenshots"
OUTPUT_DIR = ROOT / "output"
PROMPTS_DIR = ROOT / "prompts"
SAMPLES_DIR = ROOT / "samples"
SKILLS_DIR = ROOT / "skills"


def main() -> None:
    load_dotenv(ROOT / ".env")
    outputs = run_pipeline(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        prompts_dir=PROMPTS_DIR,
        samples_dir=SAMPLES_DIR,
        skills_dir=SKILLS_DIR,
    )

    print("已生成文件：")
    for path in outputs.values():
        print(f"- {path}")


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
    sample_notes_text: str,
    draft: str,
    validation_errors: list[str],
) -> str:
    checklist = """
你现在要审查一份已经生成好的 unit_notes.md 草稿。

任务：
1. 先检查这份草稿是否符合 skill 规则和 sample 的结构/教学密度要求。
2. 如果已经完整合格，只输出一个词：PASS
3. 如果不完整、漏部分、结构不对、密度不足、缺少必要项目，直接输出“修订后的完整 markdown 正文”。

重点检查：
- 标题与主题信息是否存在
- 五个一级部分是否齐全且顺序正确
- 是否包含核心动词讲解、变位、固定搭配、例句、中文解释、半控制性写作
- 是否包含名词与词组分类表格
- 是否包含 2-4 篇话题短文且附中文翻译
- 是否包含 4-8 个语法点，并有结构、例句、中文解释、小练习片段
- 是否包含补充词组表格
- 补充词组必须主要来自课文/对话中的短语、小句、固定表达
- 补充词组要优先覆盖：动词词组、形容词/状态表达、名词词组/固定小句
- 是否主要基于 complete_texts.md
- 是否保持 sample 的教学密度
- 不要再写“控制在A1-A2”，允许适当拔高，但不能偏离本单元

输出要求：
- 如果修订，必须返回完整的 unit_notes.md，而不是只返回修改建议
- 不要使用代码块
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
    sample_exercises_text: str,
    draft: str,
    validation_errors: list[str],
) -> str:
    checklist = """
你现在要审查一份已经生成好的 unit_exercises.md 草稿。

任务：
1. 先检查这份草稿是否符合 skill 规则和 sample 的结构/题量/答案解析要求。
2. 如果已经完整合格，只输出一个词：PASS
3. 如果不完整、漏部分、题量不够、答案解析缺失、结构不对，直接输出“修订后的完整 markdown 正文”。

重点检查：
- 是否严格基于 unit_notes.md，而不是截图或 complete_texts.md
- 六个固定部分及【答案与解析】是否齐全且顺序正确
- 单选题是否 20 题且每题 A/B/C/D 四个选项
- 语法填空是否 1 篇 20 空，且 14 个有提示词、6 个无提示词
- 十一选十是否 2 篇，每篇 11 选 10，并标出多余词
- 阅读理解是否 2 篇，每篇 5 道选择题
- 概要写作与控制性写作是否齐全
- 【答案与解析】是否覆盖所有题型
- 允许适当拔高，但不能偏离本单元
- 程序报告的题量与格式错误必须全部修复

输出要求：
- 如果修订，必须返回完整的 unit_exercises.md，而不是只返回修改建议
- 不要使用代码块
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

硬性要求：
- 必须严格基于 unit_notes.md
- 必须修复以下程序检测问题：
{chr(10).join(f"- {msg}" for msg in error_messages)}
- 不要输出解释
- 不要使用代码块
""".strip()
    return join_sections(
        [
            instructions,
            "规则摘要：",
            build_exercises_review_rules(exercises_skill),
            "unit_notes.md 摘录：",
            shorten_for_review(unit_notes, 4500),
            "当前待修复的题目 section：",
            current_section,
            "当前待修复的答案 section：",
            current_answer_section,
        ]
    )


def review_notes_until_valid(
    client: LLMClient,
    complete_texts: str,
    notes_skill: str,
    sample_notes_text: str,
    draft: str,
) -> str:
    current = draft
    errors = validate_notes_markdown(current)
    if not errors:
        return current
    for _ in range(2):
        reviewed = client.review_notes(
            build_notes_review_prompt(
                complete_texts=complete_texts,
                notes_skill=notes_skill,
                sample_notes_text=sample_notes_text,
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
                    sample_exercises_text=sample_exercises_text,
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


def summarize_notes_sample(sample_notes_text: str) -> str:
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


if __name__ == "__main__":
    main()
