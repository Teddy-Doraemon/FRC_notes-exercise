# French Textbook Screenshot to Teaching Materials

一个面向法语教辅场景的固定流水线项目：把教材截图识别为文本，再生成词汇笔记、配套试卷和 `.docx` 文档。

## 适用场景

- 法语教材课文截图整理
- 词汇笔记生成
- 配套练习与试卷生成
- 视觉模型 + 文本模型串联工作流示例

这不是通用多 agent 框架，而是一个垂直、可运行、可修改的教学资料生成工具。

## 核心流程

```txt
input/screenshots/
-> output/complete_texts.md
-> output/unit_notes.md
-> output/unit_notes.docx
-> output/unit_exercises.md
-> output/unit_exercises.docx
```

## 项目结构

```txt
src/
  main.py
  pipeline.py
  llm_client.py
  docx_writer.py
  file_utils.py
web_app/
  app.py
prompts/
skills/
samples/
input/
  screenshots/
output/
```

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 环境变量

复制 `.env.example` 为 `.env`，再填写你自己的配置。

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=
VISION_MODEL=openai/gpt-4o-mini
TEXT_MODEL=openai/gpt-4o-mini
```

说明：

- `OPENAI_API_KEY` 必填
- `OPENAI_BASE_URL` 可为空
- `VISION_MODEL` 用于图片识别
- `TEXT_MODEL` 用于 notes 和 exercises
- 如需分开指定，也支持 `NOTES_MODEL` 和 `EXERCISES_MODEL`

## CLI 用法

把截图放进 `input/screenshots/` 后运行：

```bash
python -m src.main
```

如果系统里没有 `python` 命令，可改用：

```bash
python3 -m src.main
```

## Web 用法

启动网页：

```bash
streamlit run web_app/app.py
```

网页支持两种模式：

- `完整流程`：上传截图，生成完整资料
- `只生成 exercises`：上传或粘贴 `unit_notes.md`，只生成试卷

用户可在页面中自行填写：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `VISION_MODEL`
- `TEXT_MODEL`

## 输出文件

成功运行后会生成：

- `output/complete_texts.md`
- `output/unit_notes.md`
- `output/unit_notes.docx`
- `output/unit_exercises.md`
- `output/unit_exercises.docx`

## 工程特点

- 使用真实视觉模型做截图识别，不做 mock OCR
- `notes` 严格基于 `complete_texts.md`
- `exercises` 严格基于 `unit_notes.md`
- 本地程序先做结构校验，再决定是否触发模型修补
- `docx` 由本地 Python 转换，不额外消耗模型 token

## 已知限制

- 最适合单元式、排版相对清晰的教材截图
- 图片过多或分辨率过高时，视觉输入成本会明显上升
- exercises 是当前最重的一步，生成时间通常长于 notes
- 样例与 skill 当前是法语教学场景，迁移到其他语言前建议先改 prompts/skills
- 当前校验规则主要覆盖结构和题量，不等于对教学质量做全面自动评价

## 建议的截图规范

- 建议按顺序命名：`01.png`、`02.png`、`03.png`
- 每次新单元开始前，先清空旧截图
- 优先保证文字清晰、裁切完整、页码顺序正确

