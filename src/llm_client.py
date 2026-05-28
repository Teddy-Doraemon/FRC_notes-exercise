from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from .file_utils import image_to_data_url


DEFAULT_MODEL = "gpt-4o"


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("缺少 OPENAI_API_KEY，请先在 .env 中配置。")

        base_url = config.get("base_url")
        if base_url is None:
            base_url = os.getenv("OPENAI_BASE_URL") or None
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)
        self.vision_model = (
            config.get("vision_model")
            or os.getenv("VISION_MODEL")
            or DEFAULT_MODEL
        )
        default_text_model = config.get("text_model") or os.getenv("TEXT_MODEL")
        self.notes_model = (
            config.get("notes_model")
            or os.getenv("NOTES_MODEL")
            or default_text_model
            or DEFAULT_MODEL
        )
        self.exercises_model = (
            config.get("exercises_model")
            or os.getenv("EXERCISES_MODEL")
            or default_text_model
            or DEFAULT_MODEL
        )

    def extract_complete_texts(self, prompt: str, image_paths: list[Path]) -> str:
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_to_data_url(image_path)},
                }
            )

        return self._chat(model=self.vision_model, content=content, max_tokens=4000)

    def generate_notes(self, prompt: str) -> str:
        return self._chat(
            model=self.notes_model,
            content=[{"type": "text", "text": prompt}],
            max_tokens=7000,
        )

    def generate_exercises(self, prompt: str) -> str:
        return self._chat(
            model=self.exercises_model,
            content=[{"type": "text", "text": prompt}],
            max_tokens=9000,
        )

    def review_notes(self, prompt: str) -> str:
        return self._chat(
            model=self.notes_model,
            content=[{"type": "text", "text": prompt}],
            max_tokens=6000,
        )

    def review_exercises(self, prompt: str) -> str:
        return self._chat(
            model=self.exercises_model,
            content=[{"type": "text", "text": prompt}],
            max_tokens=8000,
        )

    def _chat(self, model: str, content: list[dict[str, object]], max_tokens: int) -> str:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是严谨的法语教材处理助手。"
                                "输出只返回最终 markdown 正文，不要额外寒暄，不要使用代码块包裹。"
                            ),
                        },
                        {"role": "user", "content": content},
                    ],
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt == 3:
                    raise RuntimeError(f"模型调用失败（model={model}）: {exc}") from exc
                time.sleep(2 * attempt)
        else:
            raise RuntimeError(f"模型调用失败（model={model}）: {last_error}")

        text = response.choices[0].message.content
        if not text or not text.strip():
            raise ValueError(f"模型返回了空内容（model={model}）。")
        return _clean_markdown_response(text)


def _clean_markdown_response(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned
