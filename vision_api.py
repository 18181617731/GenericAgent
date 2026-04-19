from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image

DEFAULT_PROMPT = "详细描述这张图片的内容"
_CLAUDE_CFG_CANDIDATES = (
    "claude_config141",
    "native_claude_config141",
    "native_claude_config5535",
    "native_claude_config84",
    "native_claude_config2",
)
_OAI_CFG_CANDIDATES = (
    "oai_config_responses",
    "native_oai_config_responses",
    "native_oai_config",
    "oai_config",
)


def _load_dependencies():
    try:
        import mykey as mk
    except Exception as exc:
        return None, None, None, f"Error: failed to import mykey: {exc}"
    try:
        from llmcore import NativeClaudeSession, NativeOAISession
    except Exception as exc:
        return None, None, None, f"Error: failed to import llmcore sessions: {exc}"
    return mk, NativeClaudeSession, NativeOAISession, ""


def _pick_cfg(mk: Any):
    for name in _CLAUDE_CFG_CANDIDATES:
        cfg = getattr(mk, name, None)
        if isinstance(cfg, dict):
            picked = dict(cfg)
            picked.setdefault("api_mode", "chat_completions")
            return picked, name, "claude"
    for name in _OAI_CFG_CANDIDATES:
        cfg = getattr(mk, name, None)
        if isinstance(cfg, dict):
            picked = dict(cfg)
            picked.setdefault("api_mode", "responses")
            return picked, name, "oai"
    return None, "", ""


def _open_image(image_input):
    if isinstance(image_input, Image.Image):
        return image_input.copy()
    image = Image.open(Path(image_input))
    image.load()
    return image


def _resize_image(image: Image.Image, max_pixels: int):
    width, height = image.size
    if max_pixels <= 0 or width * height <= max_pixels:
        return image
    scale = (max_pixels / float(width * height)) ** 0.5
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def _to_rgb(image: Image.Image):
    if image.mode == "RGBA":
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[-1])
        return bg
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _image_to_png_bytes(image: Image.Image):
    image = _to_rgb(image)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _image_to_data_url(image: Image.Image):
    return "data:image/png;base64," + base64.b64encode(_image_to_png_bytes(image)).decode("ascii")


def _make_message(image: Image.Image, prompt: str, backend: str):
    if backend == "claude":
        png_bytes = _image_to_png_bytes(image)
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(png_bytes).decode("ascii"),
                    },
                },
            ],
        }
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _image_to_data_url(image)}},
        ],
    }


def ask_vision(image_input, prompt=None, timeout=60, max_pixels=1_440_000):
    prompt = prompt or DEFAULT_PROMPT
    mk, NativeClaudeSession, NativeOAISession, err = _load_dependencies()
    if err:
        return err
    cfg, cfg_name, backend = _pick_cfg(mk)
    if not cfg:
        tried = ", ".join(_CLAUDE_CFG_CANDIDATES + _OAI_CFG_CANDIDATES)
        return "Error: no usable config found. Tried: " + tried
    try:
        image = _resize_image(_open_image(image_input), int(max_pixels))
    except Exception as exc:
        return f"Error: failed to load image: {exc}"
    cfg["timeout"] = max(1, int(timeout))
    cfg["read_timeout"] = max(5, int(timeout))
    cfg.setdefault("max_retries", 1)
    session_cls = NativeClaudeSession if backend == "claude" else NativeOAISession
    session = session_cls(cfg)
    msg = _make_message(image, prompt, backend)
    try:
        text = "".join(chunk for chunk in session.ask(msg)).strip()
    except Exception as exc:
        return f"Error: {exc}"
    if not text:
        return f"Error: empty response from config {cfg_name}"
    return text


__all__ = ["DEFAULT_PROMPT", "ask_vision"]