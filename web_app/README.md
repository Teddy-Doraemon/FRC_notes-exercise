# Web 版本

这是独立于命令行版的网页入口。

## 启动

```bash
streamlit run web_app/app.py
```

## 页面里需要填写

- `API 类型`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `VISION_MODEL`
- `TEXT_MODEL`

示例：

```env
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
VISION_MODEL=openai/gpt-4o-mini
TEXT_MODEL=openai/gpt-4o-mini
```

说明：

- `OPENAI_BASE_URL` 可以为空
- `TEXT_MODEL` 会同时用于 notes 和 exercises
- `VISION_MODEL` 只用于图片识别

## 使用方式

1. 打开网页
2. 填写 API 配置
3. 选择运行模式：
   - `完整流程`
   - `只生成 exercises`
4. 上传截图，或上传/粘贴 `unit_notes.md`
4. 点击“开始生成”
5. 页面会展示并提供下载：
   - `complete_texts.md`
   - `unit_notes.md`
   - `unit_notes.docx`
   - `unit_exercises.md`
   - `unit_exercises.docx`

## 运行目录

网页版会把上传文件和生成文件写到：

- `web_app/runtime/input/screenshots/`
- `web_app/runtime/output/`
