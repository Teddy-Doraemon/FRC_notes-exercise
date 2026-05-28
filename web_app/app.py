from __future__ import annotations

import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.pipeline import build_exercises_prompt, review_exercises_until_valid, run_pipeline
from src.docx_writer import markdown_to_docx
from src.file_utils import (
    ensure_required_file,
    read_docx_text,
    read_utf8_file,
    validate_exercises_markdown,
    write_utf8_file,
)
from src.llm_client import LLMClient


RUNTIME_ROOT = APP_ROOT / "runtime"
INPUT_DIR = RUNTIME_ROOT / "input" / "screenshots"
OUTPUT_DIR = RUNTIME_ROOT / "output"


def main() -> None:
    st.set_page_config(page_title="法语截图资料生成器", layout="wide")
    st.title("法语截图资料生成器 · Web")
    st.caption("上传截图，填写 API 配置，生成 complete_texts / notes / exercises。")

    with st.sidebar:
        st.subheader("API 配置")
        api_type = st.selectbox("API 类型", ["OpenAI", "OpenRouter", "Custom"])
        api_key = st.text_input("OPENAI_API_KEY", type="password", help="必填")
        default_base_url = "https://openrouter.ai/api/v1" if api_type == "OpenRouter" else ""
        base_url = st.text_input("OPENAI_BASE_URL", value=default_base_url, help="可留空")
        vision_model = st.text_input("VISION_MODEL", value="openai/gpt-4o-mini")
        text_model = st.text_input("TEXT_MODEL", value="openai/gpt-4o-mini")

    mode = st.radio(
        "运行模式",
        ["完整流程", "只生成 exercises"],
        horizontal=True,
        help="完整流程会从截图开始；只生成 exercises 会直接基于 unit_notes.md 生成试卷。",
    )

    uploads = []
    notes_upload = None
    notes_text_input = ""
    if mode == "完整流程":
        uploads = st.file_uploader(
            "上传课文截图",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help="建议按页顺序上传，系统会按文件名排序处理。",
        )
    else:
        notes_upload = st.file_uploader(
            "上传 unit_notes.md",
            type=["md", "txt"],
            accept_multiple_files=False,
            help="直接上传已经整理好的 notes，只生成 exercises。",
        )
        notes_text_input = st.text_area(
            "或者直接粘贴 unit_notes.md 内容",
            height=320,
            help="如果这里有内容，系统会优先使用这里的文本；否则使用上面上传的文件。",
        )

    run_clicked = st.button("开始生成", type="primary", use_container_width=True)

    if run_clicked:
        if not api_key.strip():
            st.error("请先填写 OPENAI_API_KEY。")
            return

        prepare_runtime_dirs()

        llm_config = {
            "api_key": api_key.strip(),
            "base_url": base_url.strip() or None,
            "vision_model": vision_model.strip(),
            "text_model": text_model.strip(),
        }

        try:
            if mode == "完整流程":
                if not uploads:
                    st.error("请至少上传一张截图。")
                    return
                save_uploads(uploads)
                outputs = run_full_pipeline(llm_config)
            else:
                if not notes_text_input.strip() and notes_upload is None:
                    st.error("请上传 unit_notes.md，或者直接粘贴 notes 内容。")
                    return
                outputs = run_exercises_only(llm_config, notes_upload, notes_text_input)
        except Exception as exc:
            st.exception(exc)
            return

        st.success("已生成完成。")
        render_outputs(outputs, mode)


def run_full_pipeline(llm_config: dict) -> dict[str, Path]:
    with st.status("正在生成资料，请稍候...", expanded=True) as status:
        st.write("1. 读取截图并识别文本")
        outputs = run_pipeline(
            input_dir=INPUT_DIR,
            output_dir=OUTPUT_DIR,
            prompts_dir=PROJECT_ROOT / "prompts",
            samples_dir=PROJECT_ROOT / "samples",
            skills_dir=PROJECT_ROOT / "skills",
            llm_config=llm_config,
        )
        status.update(label="生成完成", state="complete")
    return outputs


def run_exercises_only(llm_config: dict, notes_upload, notes_text_input: str) -> dict[str, Path]:
    unit_notes_path = OUTPUT_DIR / "unit_notes.md"
    if notes_text_input.strip():
        notes_content = notes_text_input
    else:
        notes_content = notes_upload.getvalue().decode("utf-8")
    write_utf8_file(unit_notes_path, notes_content)
    markdown_to_docx(read_utf8_file(unit_notes_path), OUTPUT_DIR / "unit_notes.docx")

    client = LLMClient(config=llm_config)
    exercises_skill_path = ensure_required_file(PROJECT_ROOT / "skills" / "vocab_test_skill.md")
    exercises_prompt_path = ensure_required_file(PROJECT_ROOT / "prompts" / "exercises_prompt.md")
    sample_exercises_path = ensure_required_file(PROJECT_ROOT / "samples" / "sample_exercises.docx")

    unit_notes = read_utf8_file(unit_notes_path)
    exercises_skill = read_utf8_file(exercises_skill_path)
    sample_exercises_text = read_docx_text(sample_exercises_path)
    base_prompt = read_utf8_file(exercises_prompt_path)

    with st.status("正在基于上传的 notes 生成 exercises...", expanded=True) as status:
        st.write("1. 读取 unit_notes.md")
        st.write("2. 生成 unit_exercises.md")
        unit_exercises = client.generate_exercises(
            build_exercises_prompt(
                base_prompt=base_prompt,
                unit_notes=unit_notes,
                exercises_skill=exercises_skill,
                sample_exercises_text=sample_exercises_text,
            )
        )
        st.write("3. 检查并修补 exercises")
        unit_exercises = review_exercises_until_valid(
            client=client,
            unit_notes=unit_notes,
            exercises_skill=exercises_skill,
            sample_exercises_text=sample_exercises_text,
            draft=unit_exercises,
        )
        errors = validate_exercises_markdown(unit_exercises)
        if errors:
            raise ValueError("Exercises 生成后仍未通过校验：\n" + "\n".join(errors))
        unit_exercises_path = OUTPUT_DIR / "unit_exercises.md"
        unit_exercises_docx_path = OUTPUT_DIR / "unit_exercises.docx"
        write_utf8_file(unit_exercises_path, unit_exercises)
        markdown_to_docx(unit_exercises, unit_exercises_docx_path)
        status.update(label="生成完成", state="complete")

    return {
        "unit_notes_md": unit_notes_path,
        "unit_notes_docx": OUTPUT_DIR / "unit_notes.docx",
        "unit_exercises_md": OUTPUT_DIR / "unit_exercises.md",
        "unit_exercises_docx": OUTPUT_DIR / "unit_exercises.docx",
    }


def prepare_runtime_dirs() -> None:
    if INPUT_DIR.exists():
        shutil.rmtree(INPUT_DIR)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_uploads(uploads: list) -> None:
    sorted_uploads = sorted(uploads, key=lambda item: item.name.lower())
    for index, upload in enumerate(sorted_uploads, start=1):
        suffix = Path(upload.name).suffix.lower() or ".png"
        target = INPUT_DIR / f"{index:02d}{suffix}"
        target.write_bytes(upload.getbuffer())


def render_outputs(outputs: dict[str, Path], mode: str) -> None:
    st.subheader("输出文件")
    cols = st.columns(2)
    left = cols[0]
    right = cols[1]

    unit_notes = outputs["unit_notes_md"].read_text(encoding="utf-8")
    unit_exercises = outputs["unit_exercises_md"].read_text(encoding="utf-8")

    with left:
        if mode == "完整流程":
            complete_texts = outputs["complete_texts_md"].read_text(encoding="utf-8")
            st.markdown("### complete_texts.md")
            st.text_area("complete_texts", complete_texts, height=320, label_visibility="collapsed")
            st.download_button(
                "下载 complete_texts.md",
                data=complete_texts,
                file_name="complete_texts.md",
                mime="text/markdown",
            )
        st.markdown("### unit_notes.md")
        st.text_area("unit_notes", unit_notes, height=420, label_visibility="collapsed")
        st.download_button(
            "下载 unit_notes.md",
            data=unit_notes,
            file_name="unit_notes.md",
            mime="text/markdown",
        )

    with right:
        st.markdown("### unit_exercises.md")
        st.text_area("unit_exercises", unit_exercises, height=760, label_visibility="collapsed")
        st.download_button(
            "下载 unit_exercises.md",
            data=unit_exercises,
            file_name="unit_exercises.md",
            mime="text/markdown",
        )

    st.markdown("### Docx 下载")
    st.download_button(
        "下载 unit_notes.docx",
        data=outputs["unit_notes_docx"].read_bytes(),
        file_name="unit_notes.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    st.download_button(
        "下载 unit_exercises.docx",
        data=outputs["unit_exercises_docx"].read_bytes(),
        file_name="unit_exercises.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


if __name__ == "__main__":
    main()
