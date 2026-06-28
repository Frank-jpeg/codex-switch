from __future__ import annotations

import binascii
import glob
import hashlib
import json
import os
import re
import shutil
import sqlite3
import socket
import subprocess
import tempfile
import threading
import tkinter as tk
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont, messagebox, scrolledtext, simpledialog, ttk
from urllib import error, request
from urllib.parse import urlsplit


USER_PROFILE = Path.home()
CODEX_DIR = USER_PROFILE / ".codex"
CONFIG_PATH = CODEX_DIR / "config.toml"
AUTH_PATH = CODEX_DIR / "auth.json"
PROFILES_PATH = CODEX_DIR / "provider_profiles.json"
CC_SWITCH_DB_PATH = USER_PROFILE / ".cc-switch" / "cc-switch.db"
NEW_DB_PATH = CODEX_DIR / "sqlite" / "state_5.sqlite"
OLD_DB_PATH = CODEX_DIR / "state_5.sqlite"
REPAIR_BACKUP_ROOT = CODEX_DIR / "backups" / "codex-session-repair"
REPAIR_REPORT_ROOT = CODEX_DIR / "reports" / "codex-session-repair"
SESSION_ID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f-]{27,})$", re.IGNORECASE)
WINDOW_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")
REPAIR_TARGET_SOURCE_LABELS = {
    "config": "配置",
    "rollout": "会话",
    "sqlite": "索引",
    "current": "当前",
}
PROBE_MODEL_PRIORITY = (
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4.1",
    "o4-mini",
    "o3-mini",
)
DATA_SCHEMA_VERSION = 2
PROFILE_MODE_OFFICIAL_ONLY = "official_only"
PROFILE_MODE_OFFICIAL_PLUS_PROXY = "official_plus_proxy"
PROFILE_MODE_PROXY_ONLY = "proxy_only"
PROFILE_MODE_LABELS = {
    PROFILE_MODE_OFFICIAL_ONLY: "纯官方",
    PROFILE_MODE_OFFICIAL_PLUS_PROXY: "官方+中转",
    PROFILE_MODE_PROXY_ONLY: "纯中转",
}
PROFILE_MODE_BADGES = {
    PROFILE_MODE_OFFICIAL_ONLY: "[纯官方]",
    PROFILE_MODE_OFFICIAL_PLUS_PROXY: "[官方+中转]",
    PROFILE_MODE_PROXY_ONLY: "[纯中转]",
}
VERIFICATION_NEVER = "never"
VERIFICATION_SUCCESS = "success"
VERIFICATION_FAILED = "failed"
VERIFICATION_LABELS = {
    VERIFICATION_NEVER: "未验证",
    VERIFICATION_SUCCESS: "已验证",
    VERIFICATION_FAILED: "上次失败",
}
AUTH_KIND_OFFICIAL = "official"
AUTH_KIND_APIKEY = "api_key"
AUTH_KIND_UNKNOWN = "unknown"
AUTH_KIND_LABELS = {
    AUTH_KIND_OFFICIAL: "官方登录",
    AUTH_KIND_APIKEY: "API Key",
    AUTH_KIND_UNKNOWN: "未知",
}
OFFICIAL_SNAPSHOT_SERVICE = "com.mini.codexswitcher.official-snapshot"
OFFICIAL_ONBOARDING_SERVICE = "com.mini.codexswitcher.official-onboarding"
OFFICIAL_ONBOARDING_ACCOUNT = "pending"
LIVE_BACKUP_ROOT = CODEX_DIR / "backups" / "codex-switcher-live"
PROVIDER_MODE_RESPONSES_DIRECT = "responses_direct"
KEYCHAIN_SECRET_HEX_PREFIX = "json-utf8-hex:"
# 使用更紧凑的缩放，避免主窗口占满屏幕。
UI_SCALING = 1.25
UI_FONT_FAMILY = "Microsoft YaHei UI"
SIDEBAR_BG = "#30231A"
SIDEBAR_PANEL = "#3B2B20"
SIDEBAR_FIELD = "#1B120D"
SIDEBAR_TEXT = "#F8ECDD"
SIDEBAR_MUTED = "#D8C1A1"
DARK_BG = "#EFE3D0"
DARK_PANEL = "#FBF6ED"
DARK_PANEL_ALT = "#E5D1B5"
DARK_FIELD = "#FFFDF8"
DARK_BORDER = "#B68F62"
DARK_TEXT = "#241A12"
DARK_MUTED = "#6D5945"
DARK_ACCENT = "#8A5427"
DARK_ACCENT_ACTIVE = "#6C3D1C"
DARK_SUCCESS = "#2F7D58"
DARK_DISABLED = "#B39A7D"
DARK_SELECT_BG = "#8A5427"
DARK_SELECT_FG = "#FFF9F0"
DARK_BUTTON = "#E6D2B8"
DARK_BUTTON_HOVER = "#D7B98E"
DARK_BUTTON_ACTIVE = "#C79A67"


def configure_tk_display(root: tk.Tk) -> None:
    try:
        root.tk.call("tk", "scaling", UI_SCALING)
    except tk.TclError:
        pass
    # 全局字体
    default_fonts = {
        "TkDefaultFont": 13,
        "TkTextFont": 13,
        "TkMenuFont": 13,
        "TkHeadingFont": 14,
        "TkCaptionFont": 13,
        "TkSmallCaptionFont": 12,
        "TkIconFont": 13,
        "TkTooltipFont": 12,
    }
    for font_name, size in default_fonts.items():
        try:
            tkfont.nametofont(font_name).configure(family=UI_FONT_FAMILY, size=size)
        except tk.TclError:
            pass


def fit_window_to_screen(
    window: tk.Misc,
    preferred_width: int,
    preferred_height: int,
    min_width: int,
    min_height: int,
    width_ratio: float = 0.88,
    height_ratio: float = 0.84,
    saved_geometry: str = "",
) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    max_width = max(760, screen_width - 60)
    max_height = max(560, screen_height - 80)
    width = min(max(preferred_width, int(screen_width * width_ratio)), max_width)
    height = min(max(preferred_height, int(screen_height * height_ratio)), max_height)
    x = max(30, (screen_width - width) // 2)
    y = max(40, (screen_height - height) // 3)

    match = WINDOW_GEOMETRY_RE.fullmatch(str(saved_geometry or "").strip())
    if match:
        saved_width, saved_height, saved_x, saved_y = (int(part) for part in match.groups())
        width = min(max(saved_width, min(min_width, max_width)), max_width)
        height = min(max(saved_height, min(min_height, max_height)), max_height)
        x = min(max(20, saved_x), max(20, screen_width - width - 20))
        y = min(max(40, saved_y), max(40, screen_height - height - 40))

    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(min(min_width, width), min(min_height, height))


class ApiProbeError(Exception):
    def __init__(self, message: str, status_code: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


def clip_preview(text: object, limit: int = 120) -> str:
    value = normalize_text(text)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def normalize_api_base_url(base_url: str) -> str:
    raw = base_url.strip()
    if not raw:
        raise ValueError("请先填写 Base URL。")
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.strip()
    if not netloc:
        raise ValueError("Base URL 格式不正确，请填写类似 https://example.com/v1 的地址。")
    path = re.sub(r"/+", "/", parsed.path or "").rstrip("/")
    return f"{scheme}://{netloc}{path}"


def extract_error_detail(body_text: str) -> str:
    text = body_text.strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        title_match = re.search(r"(?is)<title>(.*?)</title>", text)
        if title_match:
            return clip_preview(title_match.group(1))
        heading_match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", text)
        if heading_match:
            return clip_preview(re.sub(r"<[^>]+>", " ", heading_match.group(1)))
        return clip_preview(text)

    if isinstance(data, dict):
        error_info = data.get("error")
        if isinstance(error_info, dict):
            detail = error_info.get("message") or error_info.get("code") or error_info.get("type")
            if detail:
                return clip_preview(detail)
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return clip_preview(message)
    return clip_preview(text)


def describe_http_error(status_code: int, body_text: str) -> str:
    detail = extract_error_detail(body_text)
    body_lower = body_text.lower()
    if status_code == 401:
        message = "API Key 无效或权限不足"
    elif status_code == 403:
        if "cloudflare" in body_lower or "blocked" in body_lower:
            message = "可能被 Cloudflare 或上游风控拦截"
        else:
            message = "API Key 无效、权限不足，或被上游风控拦截"
    elif status_code == 404:
        message = "该站可能不是 OpenAI 兼容接口，或 Base URL 不是 /v1"
    elif 500 <= status_code < 600:
        message = "中转站后端线路不可用"
    else:
        message = f"请求失败，HTTP {status_code}"
    if detail:
        return f"{message}：{detail}"
    return message


def request_json(url: str, api_key: str, payload: dict | None = None, timeout: int = 15) -> object:
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body_text = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise ApiProbeError(describe_http_error(exc.code, body_text), status_code=exc.code, detail=body_text) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ApiProbeError("请求超时，可能是网络慢或服务端无响应") from exc
    except error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise ApiProbeError("请求超时，可能是网络慢或服务端无响应") from exc
        raise ApiProbeError(f"网络请求失败：{clip_preview(reason or exc)}") from exc

    try:
        return json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise ApiProbeError(f"接口返回格式异常：{clip_preview(body_text)}") from exc


def fetch_models(base_url: str, api_key: str) -> list[str]:
    data = request_json(f"{normalize_api_base_url(base_url)}/models", api_key)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ApiProbeError("接口返回格式异常：/models 未返回 data 列表")

    models: list[str] = []
    for item in data["data"]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id.strip():
            models.append(model_id.strip())

    if not models:
        raise ApiProbeError("接口返回格式异常：模型列表为空")
    return models


def pick_probe_model(models: list[str]) -> str:
    normalized = [item.strip() for item in models if item.strip()]
    if not normalized:
        raise ApiProbeError("模型列表为空，无法执行聊天检测")
    model_set = set(normalized)
    for candidate in PROBE_MODEL_PRIORITY:
        if candidate in model_set:
            return candidate
    return normalized[0]


def probe_chat(base_url: str, api_key: str, model: str) -> None:
    data = request_json(
        f"{normalize_api_base_url(base_url)}/chat/completions",
        api_key,
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        },
    )
    if not isinstance(data, dict):
        raise ApiProbeError("接口返回格式异常：聊天接口未返回 JSON 对象")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ApiProbeError("接口返回格式异常：聊天接口未返回 choices")


def assert_file_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")


def read_text(path: Path) -> str:
    assert_file_exists(path)
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(text: object) -> str:
    if text is None:
        return ""
    return " ".join(str(text).replace("\r", "").split()).strip()


def includes_query(haystack: object, query: str) -> bool:
    if not query:
        return True
    return query.lower() in normalize_text(haystack).lower()


def clip_text(text: object, query: str, radius: int = 48) -> str:
    raw = normalize_text(text)
    if not raw:
        return ""
    if not query:
        return raw[: radius * 2] + ("..." if len(raw) > radius * 2 else "")

    lower = raw.lower()
    needle = query.lower()
    index = lower.find(needle)
    if index == -1:
        return raw[: radius * 2] + ("..." if len(raw) > radius * 2 else "")

    start = max(0, index - radius)
    end = min(len(raw), index + len(needle) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(raw) else ""
    return f"{prefix}{raw[start:end]}{suffix}"


def within_date_range(iso_time: str | None, after: str, before: str) -> bool:
    day = iso_time[:10] if isinstance(iso_time, str) and len(iso_time) >= 10 else None
    if not day:
        return True
    if after and day < after:
        return False
    if before and day > before:
        return False
    return True


def should_ignore_message(text: str, role: str) -> bool:
    if role != "user":
        return False
    return text.startswith("# AGENTS.md instructions for ") or (
        "<environment_context>" in text and "<INSTRUCTIONS>" in text
    )


def shorten_title(text: object, limit: int = 28) -> str:
    title = normalize_text(text)
    if not title:
        return "(未命名线程)"
    if len(title) <= limit:
        return title
    return title[:limit].rstrip() + "..."


def extract_text_parts(content: object) -> list[str]:
    if not isinstance(content, list):
        return []

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        for key in ("text", "input_text", "output_text"):
            value = item.get(key)
            if isinstance(value, str):
                parts.append(value)
    return parts


def get_message_from_row(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    if row.get("type") != "response_item":
        return None

    payload = row.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None

    role = payload.get("role")
    if role not in {"user", "assistant"}:
        return None

    text = normalize_text("\n".join(extract_text_parts(payload.get("content"))))
    if not text or should_ignore_message(text, role):
        return None

    return {
        "role": role,
        "text": text,
        "timestamp": row.get("timestamp"),
    }


def load_session_index(root_dir: Path) -> dict[str, dict]:
    session_map: dict[str, dict] = {}
    index_file = root_dir / "session_index.jsonl"
    if not index_file.exists():
        return session_map

    with index_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = row.get("id")
            if not session_id:
                continue

            session_map[session_id] = {
                "threadName": row.get("thread_name") or "(未命名线程)",
                "updatedAt": row.get("updated_at"),
            }
    return session_map


def walk_session_files(session_dir: Path):
    for file_path in session_dir.rglob("*.jsonl"):
        if file_path.is_file():
            yield file_path


def extract_session_id_from_file(file_path: Path) -> str | None:
    match = SESSION_ID_RE.search(file_path.stem)
    return match.group(1) if match else None


def search_titles(
    session_map: dict[str, dict],
    query: str,
    limit: int,
    after: str,
    before: str,
) -> list[dict]:
    results: list[dict] = []
    for session_id, meta in session_map.items():
        if not within_date_range(meta.get("updatedAt"), after, before):
            continue
        if not includes_query(meta.get("threadName"), query):
            continue
        results.append(
            {
                "type": "title",
                "sessionId": session_id,
                "threadName": meta.get("threadName"),
                "updatedAt": meta.get("updatedAt"),
                "snippet": clip_text(meta.get("threadName"), query, 40),
            }
        )

    results.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return results[:limit]


def search_messages(
    root_dir: Path,
    session_map: dict[str, dict],
    query: str,
    role: str,
    limit: int,
    after: str,
    before: str,
) -> list[dict]:
    session_dir = root_dir / "sessions"
    if not session_dir.exists():
        raise FileNotFoundError(f"找不到会话目录: {session_dir}")

    results: list[dict] = []
    for file_path in walk_session_files(session_dir):
        session_id = extract_session_id_from_file(file_path)
        meta = session_map.get(session_id, {"threadName": "(未命名线程)", "updatedAt": None})
        thread_name = meta.get("threadName") or "(未命名线程)"
        fallback_title = None

        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = get_message_from_row(row)
                if not message:
                    continue

                if fallback_title is None and message["role"] == "user":
                    fallback_title = shorten_title(message["text"])
                    if thread_name == "(未命名线程)":
                        thread_name = fallback_title

                if role != "all" and message["role"] != role:
                    continue
                if not within_date_range(message.get("timestamp") or meta.get("updatedAt"), after, before):
                    continue
                if not includes_query(message["text"], query):
                    continue

                results.append(
                    {
                        "type": "message",
                        "sessionId": session_id,
                        "threadName": thread_name,
                        "role": message["role"],
                        "timestamp": message.get("timestamp") or meta.get("updatedAt"),
                        "snippet": clip_text(message["text"], query),
                        "filePath": str(file_path),
                    }
                )

    results.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return results[:limit]


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "没找到匹配结果。"

    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        when = item.get("timestamp") or item.get("updatedAt") or "(无时间)"
        role = f"[{item['role']}] " if item.get("role") else ""
        lines.append(f"{index}. {when} {role}{item.get('threadName')}")
        lines.append(f"   {item.get('snippet')}")
        if item.get("filePath"):
            lines.append(f"   {item['filePath']}")
        elif item.get("sessionId"):
            lines.append(f"   session: {item['sessionId']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def validate_date(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field_name} 格式必须是 YYYY-MM-DD")
    return value


def mask_secret(value: str, reveal: bool = False) -> str:
    value = value.strip()
    if not value:
        return "(空)"
    if reveal:
        return value
    return "••••••••"


def normalize_base_url_for_compare(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    elif scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]

    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    if path == "/v1":
        path = ""
    return f"{scheme}://{netloc}{path}".rstrip("/")


def profile_compare_key(profile: dict) -> tuple[str, str]:
    return (
        normalize_base_url_for_compare(profile.get("base_url", "")),
        profile.get("api_key", "").strip(),
    )


def profile_name_compare_key(name: object) -> str:
    return normalize_text(name).casefold()


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")


def json_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


def make_profile_id(name: str, existing_ids: set[str], current_id: str = "") -> str:
    value = name.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_\-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "profile"
    if current_id and current_id == value:
        return value
    candidate = value
    index = 2
    while candidate in existing_ids and candidate != current_id:
        candidate = f"{value}_{index}"
        index += 1
    return candidate


def get_current_provider_id(config_text: str | None = None) -> str:
    content = config_text if config_text is not None else read_text(CONFIG_PATH)
    match = re.search(r'(?m)^model_provider\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError("config.toml 里没找到 model_provider")
    return match.group(1)


def get_current_base_url(config_text: str | None = None) -> str:
    content = config_text if config_text is not None else read_text(CONFIG_PATH)
    provider_id = get_current_provider_id(content)
    pattern = re.compile(
        rf"(?ms)^\[model_providers\.{re.escape(provider_id)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(content)
    if not match:
        raise ValueError("config.toml 里没找到当前 provider 段")
    body = match.group("body")
    url_match = re.search(r'(?m)^\s*base_url\s*=\s*"([^"]*)"', body)
    if not url_match:
        raise ValueError("当前 provider 段里没找到 base_url")
    return url_match.group(1)


def get_current_provider_name(config_text: str | None = None) -> str:
    content = config_text if config_text is not None else read_text(CONFIG_PATH)
    provider_id = get_current_provider_id(content)
    return get_provider_name_by_id(provider_id, content)


def get_provider_name_by_id(provider_id: str, config_text: str | None = None) -> str:
    content = config_text if config_text is not None else read_text(CONFIG_PATH)
    pattern = re.compile(
        rf"(?ms)^\[model_providers\.{re.escape(provider_id)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(content)
    if not match:
        raise ValueError("config.toml 里没找到当前 provider 段")
    body = match.group("body")
    name_match = re.search(r'(?m)^\s*name\s*=\s*"([^"]*)"', body)
    if not name_match:
        return provider_id
    return name_match.group(1) or provider_id


def format_provider_label(provider_id: object, config_text: str | None = None) -> str:
    raw = str(provider_id or "").strip()
    if not raw:
        return "(空)"
    try:
        name = get_provider_name_by_id(raw, config_text)
    except Exception:
        name = raw
    if not name or name == raw:
        return raw
    return f"{name} ({raw})"


def get_current_api_key() -> str:
    content = read_text(AUTH_PATH)
    match = re.search(r'"OPENAI_API_KEY"\s*:\s*"([^"]*)"', content)
    if not match:
        raise ValueError("auth.json 里没找到 OPENAI_API_KEY")
    return match.group(1)


def replace_base_url(new_base_url: str) -> None:
    if not new_base_url.strip():
        raise ValueError("base_url 不能为空")
    config_text = read_text(CONFIG_PATH)
    provider_id = get_current_provider_id(config_text)
    pattern = re.compile(
        rf"(?ms)^(\[model_providers\.{re.escape(provider_id)}\]\s*\n)(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(config_text)
    if not match:
        raise ValueError("config.toml 里没找到当前 provider 段")
    body = match.group("body")
    updated_body, count = re.subn(
        r'(?m)^\s*base_url\s*=\s*"[^"]*"',
        f'base_url = "{toml_escape(new_base_url)}"',
        body,
        count=1,
    )
    if count == 0:
        raise ValueError("当前 provider 段里没找到 base_url")
    updated = config_text[: match.start("body")] + updated_body + config_text[match.end("body") :]
    write_text(CONFIG_PATH, updated)


def replace_provider_name(new_name: str) -> None:
    if not new_name.strip():
        raise ValueError("名称不能为空")
    config_text = read_text(CONFIG_PATH)
    provider_id = get_current_provider_id(config_text)
    pattern = re.compile(
        rf"(?ms)^(\[model_providers\.{re.escape(provider_id)}\]\s*\n)(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(config_text)
    if not match:
        raise ValueError("config.toml 里没找到当前 provider 段")
    body = match.group("body")
    updated_body, count = re.subn(
        r'(?m)^\s*name\s*=\s*"[^"]*"',
        f'name = "{toml_escape(new_name)}"',
        body,
        count=1,
    )
    if count == 0:
        raise ValueError("当前 provider 段里没找到 name")
    updated = config_text[: match.start("body")] + updated_body + config_text[match.end("body") :]
    write_text(CONFIG_PATH, updated)


def replace_api_key(new_api_key: str) -> None:
    if not new_api_key.strip():
        raise ValueError("API Key 不能为空")
    auth_text = read_text(AUTH_PATH)
    updated, count = re.subn(
        r'"OPENAI_API_KEY"\s*:\s*"[^"]*"',
        f'"OPENAI_API_KEY": "{json_escape(new_api_key)}"',
        auth_text,
        count=1,
    )
    if count == 0:
        raise ValueError("auth.json 里没找到 OPENAI_API_KEY")
    write_text(AUTH_PATH, updated)


def load_profiles() -> dict[str, dict]:
    if not PROFILES_PATH.exists():
        return {}
    data = json.loads(read_text(PROFILES_PATH))
    profiles = data.get("profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def save_profiles(profiles: dict[str, dict]) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(PROFILES_PATH, {"profiles": profiles})


def now_iso_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_snapshot_id(display_name: str, existing_ids: set[str], current_id: str = "") -> str:
    return make_profile_id(display_name or "official", existing_ids, current_id=current_id)


def default_settings() -> dict:
    return {
        "require_successful_verification_before_switch": False,
        "main_window_geometry": "",
    }


def default_official_onboarding() -> dict:
    return {
        "prepared_at": "",
        "prepared_from_mode": "",
        "prepared_from_provider_name": "",
        "prepared_from_profile_id": "",
        "prepared_from_auth_kind": "",
    }


def default_app_data() -> dict:
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "settings": default_settings(),
        "official_onboarding": default_official_onboarding(),
        "official_snapshots": {},
        "combo_profiles": {},
    }


def normalize_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def sanitize_settings(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    defaults = default_settings()
    main_window_geometry = str(data.get("main_window_geometry") or "").strip()
    if not WINDOW_GEOMETRY_RE.fullmatch(main_window_geometry):
        main_window_geometry = defaults["main_window_geometry"]
    return {
        "require_successful_verification_before_switch": normalize_bool(
            data.get("require_successful_verification_before_switch"),
            defaults["require_successful_verification_before_switch"],
        ),
        "main_window_geometry": main_window_geometry,
    }


def sanitize_official_onboarding(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    defaults = default_official_onboarding()
    return {
        "prepared_at": str(data.get("prepared_at") or defaults["prepared_at"]),
        "prepared_from_mode": str(data.get("prepared_from_mode") or defaults["prepared_from_mode"]),
        "prepared_from_provider_name": str(data.get("prepared_from_provider_name") or defaults["prepared_from_provider_name"]),
        "prepared_from_profile_id": str(data.get("prepared_from_profile_id") or defaults["prepared_from_profile_id"]),
        "prepared_from_auth_kind": str(data.get("prepared_from_auth_kind") or defaults["prepared_from_auth_kind"]),
    }


def sanitize_snapshot_meta(snapshot_id: str, raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    created_at = str(data.get("created_at") or now_iso_text())
    updated_at = str(data.get("updated_at") or created_at)
    return {
        "snapshot_id": snapshot_id,
        "display_name": str(data.get("display_name") or snapshot_id or "官方账号"),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_used_at": str(data.get("last_used_at") or ""),
        "notes": str(data.get("notes") or ""),
        "auth_hash": str(data.get("auth_hash") or ""),
        "baseline_hash": str(data.get("baseline_hash") or ""),
        "baseline_provider_id": str(data.get("baseline_provider_id") or ""),
        "identity_hint": str(data.get("identity_hint") or ""),
    }


def sanitize_combo_profile(profile_id: str, raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    created_at = str(data.get("created_at") or now_iso_text())
    updated_at = str(data.get("updated_at") or created_at)
    profile_type = str(data.get("profile_type") or PROFILE_MODE_PROXY_ONLY)
    if profile_type not in PROFILE_MODE_LABELS:
        profile_type = PROFILE_MODE_PROXY_ONLY
    verification_status = str(data.get("verification_status") or VERIFICATION_NEVER)
    if verification_status not in VERIFICATION_LABELS:
        verification_status = VERIFICATION_NEVER
    return {
        "profile_id": profile_id,
        "profile_type": profile_type,
        "display_name": str(data.get("display_name") or profile_id or "未命名档案"),
        "official_snapshot_id": str(data.get("official_snapshot_id") or ""),
        "provider_name": str(data.get("provider_name") or ""),
        "provider_base_url": str(data.get("provider_base_url") or "").strip(),
        "provider_api_key": str(data.get("provider_api_key") or "").strip(),
        "provider_mode": str(data.get("provider_mode") or PROVIDER_MODE_RESPONSES_DIRECT),
        "verification_status": verification_status,
        "last_verified_at": str(data.get("last_verified_at") or ""),
        "last_verified_summary": str(data.get("last_verified_summary") or ""),
        "notes": str(data.get("notes") or ""),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_used_at": str(data.get("last_used_at") or ""),
    }


def build_proxy_only_combo_from_legacy(profile_id: str, profile: object) -> dict | None:
    if not isinstance(profile, dict):
        return None
    name = str(profile.get("name") or "").strip()
    base_url = str(profile.get("base_url") or "").strip()
    api_key = str(profile.get("api_key") or "").strip()
    if not name or not base_url or not api_key:
        return None
    display_name = f"纯中转-{name}"
    return sanitize_combo_profile(
        profile_id,
        {
            "profile_type": PROFILE_MODE_PROXY_ONLY,
            "display_name": display_name,
            "official_snapshot_id": "",
            "provider_name": name,
            "provider_base_url": base_url,
            "provider_api_key": api_key,
            "provider_mode": PROVIDER_MODE_RESPONSES_DIRECT,
            "verification_status": VERIFICATION_NEVER,
            "notes": "从旧版线路数据自动迁移",
        },
    )


def sanitize_app_data(raw: object) -> dict:
    defaults = default_app_data()
    if not isinstance(raw, dict):
        return defaults

    if raw.get("schema_version") == DATA_SCHEMA_VERSION:
        official_snapshots = {}
        for snapshot_id, meta in (raw.get("official_snapshots") or {}).items():
            if not isinstance(snapshot_id, str):
                continue
            official_snapshots[snapshot_id] = sanitize_snapshot_meta(snapshot_id, meta)

        combo_profiles = {}
        for profile_id, profile in (raw.get("combo_profiles") or {}).items():
            if not isinstance(profile_id, str):
                continue
            combo_profiles[profile_id] = sanitize_combo_profile(profile_id, profile)

        return {
            "schema_version": DATA_SCHEMA_VERSION,
            "settings": sanitize_settings(raw.get("settings")),
            "official_onboarding": sanitize_official_onboarding(raw.get("official_onboarding")),
            "official_snapshots": official_snapshots,
            "combo_profiles": combo_profiles,
        }

    legacy_profiles = raw.get("profiles")
    if isinstance(legacy_profiles, dict):
        combo_profiles: dict[str, dict] = {}
        for legacy_id, legacy_profile in legacy_profiles.items():
            if not isinstance(legacy_id, str):
                continue
            migrated = build_proxy_only_combo_from_legacy(legacy_id, legacy_profile)
            if migrated:
                combo_profiles[legacy_id] = migrated
        return {
            "schema_version": DATA_SCHEMA_VERSION,
            "settings": default_settings(),
            "official_onboarding": default_official_onboarding(),
            "official_snapshots": {},
            "combo_profiles": combo_profiles,
        }

    return defaults


def save_app_data(app_data: dict) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(PROFILES_PATH, sanitize_app_data(app_data))


def load_app_data() -> dict:
    if not PROFILES_PATH.exists():
        return default_app_data()
    raw = json.loads(read_text(PROFILES_PATH))
    sanitized = sanitize_app_data(raw)
    if raw != sanitized:
        save_app_data(sanitized)
    return sanitized


def run_security_command(args: list[str]) -> str:
    completed = subprocess.run(
        ["security", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr_text = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(stderr_text or f"security 命令失败：{' '.join(args)}")
    return completed.stdout


def encode_keychain_secret(payload_json: str) -> str:
    return KEYCHAIN_SECRET_HEX_PREFIX + payload_json.encode("utf-8").hex()


def decode_keychain_secret(payload_text: str) -> str:
    text = payload_text.rstrip("\n")
    candidate_hex = ""
    if text.startswith(KEYCHAIN_SECRET_HEX_PREFIX):
        candidate_hex = text[len(KEYCHAIN_SECRET_HEX_PREFIX) :]
    elif re.fullmatch(r"[0-9a-fA-F]+", text) and len(text) % 2 == 0:
        candidate_hex = text

    if not candidate_hex:
        return text

    try:
        decoded = binascii.unhexlify(candidate_hex).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return text

    stripped = decoded.lstrip("\ufeff \t\r\n")
    if stripped.startswith("{") or stripped.startswith("["):
        return decoded
    return text


def save_keychain_secret(service: str, account: str, payload_json: str) -> None:
    run_security_command(
        [
            "add-generic-password",
            "-U",
            "-s",
            service,
            "-a",
            account,
            "-w",
            encode_keychain_secret(payload_json),
        ]
    )


def load_keychain_secret(service: str, account: str) -> str:
    return decode_keychain_secret(
        run_security_command(
        [
            "find-generic-password",
            "-w",
            "-s",
            service,
            "-a",
            account,
        ]
    ))


def delete_keychain_secret(service: str, account: str) -> None:
    try:
        run_security_command(
            [
                "delete-generic-password",
                "-s",
                service,
                "-a",
                account,
            ]
        )
    except RuntimeError as exc:
        if "could not be found" not in str(exc).lower():
            raise


def save_official_snapshot_secret(snapshot_id: str, payload_json: str) -> None:
    save_keychain_secret(OFFICIAL_SNAPSHOT_SERVICE, snapshot_id, payload_json)


def load_official_snapshot_secret(snapshot_id: str) -> str:
    return load_keychain_secret(OFFICIAL_SNAPSHOT_SERVICE, snapshot_id)


def delete_official_snapshot_secret(snapshot_id: str) -> None:
    delete_keychain_secret(OFFICIAL_SNAPSHOT_SERVICE, snapshot_id)


def parse_json_dict(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def detect_auth_kind(auth_text: str) -> str:
    data = parse_json_dict(auth_text)
    if not data:
        return AUTH_KIND_UNKNOWN

    auth_mode = str(data.get("auth_mode") or "").strip().lower()
    if auth_mode in {"apikey", "api_key", "api-key"}:
        return AUTH_KIND_APIKEY

    official_marker_keys = (
        "refresh_token",
        "refreshToken",
        "access_token",
        "accessToken",
        "id_token",
        "idToken",
        "session_token",
        "sessionToken",
        "account_id",
        "accountId",
        "user_id",
        "userId",
        "email",
        "username",
    )
    if auth_mode and auth_mode not in {"apikey", "api_key", "api-key"}:
        return AUTH_KIND_OFFICIAL
    for key in official_marker_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return AUTH_KIND_OFFICIAL
    for key in ("OPENAI_API_KEY", "api_key", "apiKey"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return AUTH_KIND_APIKEY
    return AUTH_KIND_UNKNOWN


def extract_api_key_from_auth_text(auth_text: str) -> str:
    data = parse_json_dict(auth_text)
    for key in ("OPENAI_API_KEY", "api_key", "apiKey"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_auth_text_for_proxy_only(api_key: str) -> str:
    if not api_key.strip():
        raise ValueError("API Key 不能为空")
    return json.dumps(
        {"OPENAI_API_KEY": api_key.strip(), "auth_mode": "apikey"},
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def build_auth_text_for_official_login() -> str:
    return json.dumps({}, ensure_ascii=False, indent=2) + "\n"


def detect_official_identity_hint(auth_text: str) -> str:
    data = parse_json_dict(auth_text)
    candidate_keys = (
        "email",
        "user_email",
        "username",
        "name",
        "account_id",
        "accountId",
        "user_id",
        "userId",
    )
    for key in candidate_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_toml_bool_value(content: str, key: str) -> bool | None:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*(true|false)\s*$", content, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def extract_provider_block(config_text: str, provider_id: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\[model_providers\.{re.escape(provider_id)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(config_text)
    return match.group("body") if match else ""


def extract_current_provider_info(config_text: str) -> dict:
    provider_id = get_current_provider_id(config_text)
    body = extract_provider_block(config_text, provider_id)
    return {
        "provider_id": provider_id,
        "provider_name": extract_toml_string_value(body, "name") or provider_id,
        "base_url": extract_toml_string_value(body, "base_url"),
        "wire_api": extract_toml_string_value(body, "wire_api"),
        "requires_openai_auth": extract_toml_bool_value(body, "requires_openai_auth"),
        "experimental_bearer_token": extract_toml_string_value(body, "experimental_bearer_token"),
    }


def render_toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f'"{toml_escape(str(value))}"'


def set_root_toml_string_value(config_text: str, key: str, value: str) -> str:
    line = f'{key} = "{toml_escape(value)}"'
    pattern = re.compile(rf'(?m)^\s*{re.escape(key)}\s*=\s*"[^"]*"\s*$')
    if pattern.search(config_text):
        return pattern.sub(line, config_text, count=1)
    return line + "\n" + config_text


def remove_toml_key_from_block(block_text: str, key: str) -> str:
    return re.sub(rf"(?m)^\s*{re.escape(key)}\s*=\s*.*\n?", "", block_text)


def upsert_toml_key_in_block(block_text: str, key: str, value: object) -> str:
    line = f"{key} = {render_toml_scalar(value)}"
    pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=\s*.*$")
    if pattern.search(block_text):
        return pattern.sub(line, block_text, count=1)
    if block_text and not block_text.endswith("\n"):
        block_text += "\n"
    return block_text + line + "\n"


def set_provider_section(
    config_text: str,
    provider_id: str,
    settings: dict[str, object],
    remove_keys: list[str] | tuple[str, ...] = (),
) -> str:
    pattern = re.compile(
        rf"(?ms)^\[model_providers\.{re.escape(provider_id)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(config_text)
    if match:
        body = match.group("body")
        for key in remove_keys:
            body = remove_toml_key_from_block(body, key)
        for key, value in settings.items():
            body = upsert_toml_key_in_block(body, key, value)
        if body and not body.endswith("\n"):
            body += "\n"
        return config_text[: match.start("body")] + body + config_text[match.end("body") :]

    block_lines = [f"[model_providers.{provider_id}]"]
    for key, value in settings.items():
        block_lines.append(f"{key} = {render_toml_scalar(value)}")
    appended = "\n".join(block_lines) + "\n"
    if not config_text.endswith("\n"):
        config_text += "\n"
    return config_text.rstrip("\n") + "\n\n" + appended


def remove_key_from_all_provider_sections(config_text: str, key: str) -> str:
    section_pattern = re.compile(r"(?ms)^\[model_providers\.(?P<provider>[^\]]+)\]\s*\n(?P<body>.*?)(?=^\[|\Z)")
    pieces: list[str] = []
    last_end = 0
    for match in section_pattern.finditer(config_text):
        pieces.append(config_text[last_end: match.start("body")])
        body = remove_toml_key_from_block(match.group("body"), key)
        if body and not body.endswith("\n"):
            body += "\n"
        pieces.append(body)
        last_end = match.end("body")
    pieces.append(config_text[last_end:])
    return "".join(pieces)


def config_provider_family(provider_id: str) -> str:
    return "custom" if provider_id.strip() == "custom" else "official"


def infer_live_mode(auth_text: str, config_text: str) -> str:
    auth_kind = detect_auth_kind(auth_text)
    provider_info = extract_current_provider_info(config_text)
    has_proxy_token = bool(provider_info["experimental_bearer_token"].strip())
    if auth_kind == AUTH_KIND_OFFICIAL:
        return PROFILE_MODE_OFFICIAL_PLUS_PROXY if has_proxy_token else PROFILE_MODE_OFFICIAL_ONLY
    if auth_kind == AUTH_KIND_APIKEY:
        return PROFILE_MODE_PROXY_ONLY
    return ""


def find_matching_snapshot_id(official_snapshots: dict[str, dict], auth_text: str) -> str:
    auth_hash = text_sha256(auth_text)
    for snapshot_id, meta in official_snapshots.items():
        if meta.get("auth_hash") == auth_hash:
            return snapshot_id
    return ""


def describe_snapshot(meta: dict) -> str:
    display_name = str(meta.get("display_name") or meta.get("snapshot_id") or "官方账号")
    identity_hint = str(meta.get("identity_hint") or "").strip()
    if identity_hint:
        return f"{display_name} ({identity_hint})"
    return display_name


def snapshot_payload_bundle(auth_text: str, baseline_config_text: str) -> str:
    return json.dumps(
        {
            "version": 1,
            "auth_text": auth_text,
            "baseline_config_text": baseline_config_text,
        },
        ensure_ascii=False,
    )


def load_snapshot_bundle(snapshot_id: str) -> dict:
    payload = load_official_snapshot_secret(snapshot_id)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"官方快照内容损坏：{snapshot_id}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"官方快照格式不正确：{snapshot_id}")
    auth_text = data.get("auth_text")
    baseline_config_text = data.get("baseline_config_text")
    if not isinstance(auth_text, str) or not isinstance(baseline_config_text, str):
        raise ValueError(f"官方快照缺少正文：{snapshot_id}")
    return {
        "auth_text": auth_text,
        "baseline_config_text": baseline_config_text,
    }


def onboarding_payload_bundle(auth_text: str, config_text: str) -> str:
    return json.dumps(
        {
            "version": 1,
            "auth_text": auth_text,
            "config_text": config_text,
        },
        ensure_ascii=False,
    )


def save_official_onboarding_secret(payload_json: str) -> None:
    save_keychain_secret(OFFICIAL_ONBOARDING_SERVICE, OFFICIAL_ONBOARDING_ACCOUNT, payload_json)


def load_official_onboarding_bundle() -> dict:
    payload = load_keychain_secret(OFFICIAL_ONBOARDING_SERVICE, OFFICIAL_ONBOARDING_ACCOUNT)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("官方接入备份内容损坏。") from exc
    if not isinstance(data, dict):
        raise ValueError("官方接入备份格式不正确。")
    auth_text = data.get("auth_text")
    config_text = data.get("config_text")
    if not isinstance(auth_text, str) or not isinstance(config_text, str):
        raise ValueError("官方接入备份缺少正文。")
    return {
        "auth_text": auth_text,
        "config_text": config_text,
    }


def delete_official_onboarding_secret() -> None:
    delete_keychain_secret(OFFICIAL_ONBOARDING_SERVICE, OFFICIAL_ONBOARDING_ACCOUNT)


def has_official_onboarding_session(app_data: dict) -> bool:
    onboarding = app_data.get("official_onboarding") if isinstance(app_data, dict) else {}
    if not isinstance(onboarding, dict):
        return False
    return bool(str(onboarding.get("prepared_at") or "").strip())


def is_live_state_in_official_onboarding(state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    return (
        str(state.get("provider_id") or "").strip() == "openai"
        and not str(state.get("base_url") or "").strip()
        and not str(state.get("experimental_bearer_token") or "").strip()
    )


def has_active_official_onboarding_session(app_data: dict, live_state: dict | None = None) -> bool:
    if not has_official_onboarding_session(app_data):
        return False
    state = live_state if isinstance(live_state, dict) else live_state_from_files(app_data)
    return is_live_state_in_official_onboarding(state)


def is_codex_running() -> bool:
    completed = subprocess.run(
        ["pgrep", "-f", "/Applications/Codex.app/Contents/MacOS/Codex"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def ensure_codex_not_running(action_text: str) -> None:
    if is_codex_running():
        raise ValueError(
            f"请先完全退出 Codex 再{action_text}。Mac 上关窗口不等于退出，像 Windows 缩到托盘一样，还要在 Dock 里退出或按 Command+Q。"
        )


def save_current_official_snapshot(app_data: dict, display_name: str, notes: str = "") -> dict:
    auth_text = read_text(AUTH_PATH)
    config_text = read_text(CONFIG_PATH)
    auth_kind = detect_auth_kind(auth_text)
    if auth_kind != AUTH_KIND_OFFICIAL:
        raise ValueError("当前 auth.json 不是官方登录态，不能保存为官方账号。")

    provider_info = extract_current_provider_info(config_text)
    if provider_info["provider_id"] == "custom" or provider_info["experimental_bearer_token"].strip():
        raise ValueError("请先切回纯官方，再保存当前官方账号。")

    display_name = display_name.strip()
    if not display_name:
        raise ValueError("官方账号名称不能为空。")

    existing_snapshots = app_data["official_snapshots"]
    current_id = ""
    normalized_name = display_name.casefold()
    for snapshot_id, meta in existing_snapshots.items():
        if str(meta.get("display_name") or "").casefold() == normalized_name:
            current_id = snapshot_id
            break

    snapshot_id = make_snapshot_id(display_name, set(existing_snapshots.keys()), current_id=current_id)
    payload_json = snapshot_payload_bundle(auth_text, config_text)
    save_official_snapshot_secret(snapshot_id, payload_json)

    created_at = (
        existing_snapshots.get(snapshot_id, {}).get("created_at")
        if snapshot_id in existing_snapshots
        else now_iso_text()
    )
    meta = sanitize_snapshot_meta(
        snapshot_id,
        {
            "display_name": display_name,
            "created_at": created_at,
            "updated_at": now_iso_text(),
            "last_used_at": existing_snapshots.get(snapshot_id, {}).get("last_used_at", ""),
            "notes": notes.strip(),
            "auth_hash": text_sha256(auth_text),
            "baseline_hash": text_sha256(config_text),
            "baseline_provider_id": provider_info["provider_id"],
            "identity_hint": detect_official_identity_hint(auth_text),
        },
    )
    app_data["official_snapshots"][snapshot_id] = meta
    save_app_data(app_data)
    return meta


def build_official_plus_proxy_config(
    baseline_config_text: str,
    baseline_provider_id: str,
    provider_name: str,
    base_url: str,
    bearer_token: str,
) -> str:
    if not baseline_provider_id.strip():
        raise ValueError("官方基线配置缺少 provider id。")
    config_text = set_root_toml_string_value(baseline_config_text, "model_provider", baseline_provider_id)
    config_text = set_provider_section(
        config_text,
        baseline_provider_id,
        {
            "name": provider_name.strip() or "官方+中转",
            "wire_api": "responses",
            "requires_openai_auth": True,
            "base_url": normalize_api_base_url(base_url),
            "experimental_bearer_token": bearer_token.strip(),
        },
    )
    return config_text


def build_proxy_only_config(base_config_text: str, provider_name: str, base_url: str) -> str:
    config_text = remove_key_from_all_provider_sections(base_config_text, "experimental_bearer_token")
    config_text = set_root_toml_string_value(config_text, "model_provider", "custom")
    config_text = set_provider_section(
        config_text,
        "custom",
        {
            "name": provider_name.strip() or "纯中转",
            "wire_api": "responses",
            "requires_openai_auth": True,
            "base_url": normalize_api_base_url(base_url),
        },
        remove_keys=["experimental_bearer_token"],
    )
    return config_text


def build_official_login_prep_config(base_config_text: str) -> str:
    config_text = remove_key_from_all_provider_sections(base_config_text, "experimental_bearer_token")
    config_text = set_root_toml_string_value(config_text, "model_provider", "openai")
    config_text = set_provider_section(
        config_text,
        "openai",
        {
            "name": "OpenAI Official",
            "wire_api": "responses",
            "requires_openai_auth": True,
        },
        remove_keys=["base_url", "experimental_bearer_token"],
    )
    return config_text


def build_target_state(profile: dict, app_data: dict, current_config_text: str) -> dict:
    profile_type = profile["profile_type"]
    provider_name = profile.get("provider_name", "")
    provider_base_url = profile.get("provider_base_url", "")
    provider_api_key = profile.get("provider_api_key", "")

    if profile_type == PROFILE_MODE_OFFICIAL_ONLY:
        snapshot_id = profile.get("official_snapshot_id", "").strip()
        if not snapshot_id:
            raise ValueError("纯官方档案必须选择官方账号。")
        bundle = load_snapshot_bundle(snapshot_id)
        meta = app_data["official_snapshots"].get(snapshot_id, {})
        baseline_provider_id = str(meta.get("baseline_provider_id") or get_current_provider_id(bundle["baseline_config_text"]))
        return {
            "auth_text": bundle["auth_text"],
            "config_text": bundle["baseline_config_text"],
            "target_provider_id": baseline_provider_id,
            "provider_family": config_provider_family(baseline_provider_id),
            "official_snapshot_id": snapshot_id,
        }

    if profile_type == PROFILE_MODE_OFFICIAL_PLUS_PROXY:
        snapshot_id = profile.get("official_snapshot_id", "").strip()
        if not snapshot_id:
            raise ValueError("官方+中转档案必须选择官方账号。")
        if not provider_base_url.strip() or not provider_api_key.strip():
            raise ValueError("官方+中转档案缺少 Base URL 或 API Key。")
        bundle = load_snapshot_bundle(snapshot_id)
        meta = app_data["official_snapshots"].get(snapshot_id, {})
        baseline_provider_id = str(meta.get("baseline_provider_id") or get_current_provider_id(bundle["baseline_config_text"]))
        config_text = build_official_plus_proxy_config(
            bundle["baseline_config_text"],
            baseline_provider_id,
            provider_name,
            provider_base_url,
            provider_api_key,
        )
        return {
            "auth_text": bundle["auth_text"],
            "config_text": config_text,
            "target_provider_id": baseline_provider_id,
            "provider_family": config_provider_family(baseline_provider_id),
            "official_snapshot_id": snapshot_id,
        }

    if profile_type == PROFILE_MODE_PROXY_ONLY:
        if not provider_base_url.strip() or not provider_api_key.strip():
            raise ValueError("纯中转档案缺少 Base URL 或 API Key。")
        return {
            "auth_text": build_auth_text_for_proxy_only(provider_api_key),
            "config_text": build_proxy_only_config(current_config_text, provider_name, provider_base_url),
            "target_provider_id": "custom",
            "provider_family": "custom",
            "official_snapshot_id": "",
        }

    raise ValueError("未知档案模式。")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def resolve_user_path(raw: str) -> Path:
    text = raw.strip()
    if not text:
        return Path(text)
    if text == "~":
        return USER_PROFILE
    if text.startswith("~/"):
        return USER_PROFILE / text[2:]
    return Path(text).expanduser()


def codex_state_db_paths(config_text: str | None = None) -> list[Path]:
    content = config_text if config_text is not None else (read_text(CONFIG_PATH) if CONFIG_PATH.exists() else "")
    paths: list[Path] = []

    def add_path(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in paths:
            paths.append(resolved)

    if NEW_DB_PATH.exists():
        add_path(NEW_DB_PATH)
    if OLD_DB_PATH.exists():
        add_path(OLD_DB_PATH)

    sqlite_home = extract_toml_string_value(content, "sqlite_home")
    if sqlite_home:
        candidate = resolve_user_path(sqlite_home) / "state_5.sqlite"
        if candidate.exists():
            add_path(candidate)
    else:
        env_sqlite_home = os.environ.get("CODEX_SQLITE_HOME", "").strip()
        if env_sqlite_home:
            candidate = resolve_user_path(env_sqlite_home) / "state_5.sqlite"
            if candidate.exists():
                add_path(candidate)

    return paths


def backup_live_state(auth_text: str, config_text: str) -> Path:
    LIVE_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{text_sha256(auth_text + config_text)[:8]}"
    backup_dir = LIVE_BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    write_text(backup_dir / "auth.json", auth_text)
    write_text(backup_dir / "config.toml", config_text)
    return backup_dir


def restore_live_state(auth_text: str, config_text: str) -> None:
    atomic_write_text(AUTH_PATH, auth_text)
    atomic_write_text(CONFIG_PATH, config_text)


def write_live_state_with_rollback(
    current_auth_text: str,
    current_config_text: str,
    target_auth_text: str,
    target_config_text: str,
) -> None:
    try:
        atomic_write_text(AUTH_PATH, target_auth_text)
        atomic_write_text(CONFIG_PATH, target_config_text)

        written_auth = read_text(AUTH_PATH)
        written_config = read_text(CONFIG_PATH)
        if written_auth != target_auth_text or written_config != target_config_text:
            raise RuntimeError("写入后核对失败，已停止。")
    except Exception as exc:
        rollback_error = None
        try:
            restore_live_state(current_auth_text, current_config_text)
        except Exception as restore_exc:
            rollback_error = restore_exc
        if rollback_error:
            raise RuntimeError(f"{exc}\n\n回滚也失败了：{rollback_error}") from exc
        raise


def apply_combo_profile(profile: dict, app_data: dict) -> dict:
    current_auth_text = read_text(AUTH_PATH)
    current_config_text = read_text(CONFIG_PATH)
    current_provider_id = get_current_provider_id(current_config_text)
    target = build_target_state(profile, app_data, current_config_text)
    backup_dir = backup_live_state(current_auth_text, current_config_text)

    write_live_state_with_rollback(
        current_auth_text,
        current_config_text,
        target["auth_text"],
        target["config_text"],
    )

    return {
        "backup_dir": backup_dir,
        "current_provider_id": current_provider_id,
        "current_provider_family": config_provider_family(current_provider_id),
        "target_provider_id": target["target_provider_id"],
        "target_provider_family": target["provider_family"],
        "official_snapshot_id": target.get("official_snapshot_id", ""),
    }


def clear_official_onboarding(app_data: dict) -> None:
    delete_official_onboarding_secret()
    app_data["official_onboarding"] = default_official_onboarding()
    save_app_data(app_data)


def prepare_live_state_for_official_login(app_data: dict) -> dict:
    current_state = live_state_from_files(app_data)
    if has_official_onboarding_session(app_data):
        if has_active_official_onboarding_session(app_data, current_state):
            raise ValueError("当前已经处于官方接入流程中。请先完成保存，或点“恢复接入前状态”。")
        clear_official_onboarding(app_data)
        current_state = live_state_from_files(app_data)

    if (
        current_state["auth_kind"] == AUTH_KIND_OFFICIAL
        and current_state["mode"] == PROFILE_MODE_OFFICIAL_ONLY
        and not current_state["experimental_bearer_token"].strip()
    ):
        raise ValueError("当前已经是纯官方登录态，直接点“保存当前官方账号”即可。")

    ensure_codex_not_running("准备接入官方账号")

    previous_onboarding = app_data.get("official_onboarding", default_official_onboarding())
    onboarding_meta = sanitize_official_onboarding(
        {
            "prepared_at": now_iso_text(),
            "prepared_from_mode": current_state["mode"],
            "prepared_from_provider_name": current_state["provider_name"],
            "prepared_from_profile_id": current_state["active_profile_id"],
            "prepared_from_auth_kind": current_state["auth_kind"],
        }
    )

    live_switched = False
    try:
        save_official_onboarding_secret(
            onboarding_payload_bundle(current_state["auth_text"], current_state["config_text"])
        )
        write_live_state_with_rollback(
            current_state["auth_text"],
            current_state["config_text"],
            build_auth_text_for_official_login(),
            build_official_login_prep_config(current_state["config_text"]),
        )
        live_switched = True
        prepared_state = live_state_from_files(app_data)
        if not is_live_state_in_official_onboarding(prepared_state):
            raise RuntimeError("官方接入准备态写入后校验失败，已停止。")
        app_data["official_onboarding"] = onboarding_meta
        save_app_data(app_data)
    except Exception:
        if live_switched:
            try:
                restore_live_state(current_state["auth_text"], current_state["config_text"])
            except Exception:
                pass
        app_data["official_onboarding"] = sanitize_official_onboarding(previous_onboarding)
        try:
            save_app_data(app_data)
        except Exception:
            pass
        try:
            delete_official_onboarding_secret()
        except Exception:
            pass
        raise

    return app_data["official_onboarding"]


def restore_live_state_from_official_onboarding(app_data: dict) -> dict:
    if not has_official_onboarding_session(app_data):
        raise ValueError("当前没有可恢复的官方接入流程。")

    ensure_codex_not_running("恢复接入前状态")

    try:
        bundle = load_official_onboarding_bundle()
    except Exception as exc:
        clear_official_onboarding(app_data)
        state = summarize_live_state(app_data)
        state["restore_warning"] = f"接入前备份不可用，已清理残留接入状态。当前配置未改动，现在可以继续切换其他配置。{exc}"
        return state

    current_auth_text = read_text(AUTH_PATH)
    current_config_text = read_text(CONFIG_PATH)
    write_live_state_with_rollback(
        current_auth_text,
        current_config_text,
        bundle["auth_text"],
        bundle["config_text"],
    )
    clear_official_onboarding(app_data)
    state = summarize_live_state(app_data)
    state["restore_warning"] = ""
    return state


def ensure_official_only_profile_for_snapshot(app_data: dict, snapshot_meta: dict) -> tuple[str, bool]:
    snapshot_id = str(snapshot_meta.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("官方快照缺少 snapshot_id。")

    for profile_id, profile in app_data["combo_profiles"].items():
        if (
            profile.get("profile_type") == PROFILE_MODE_OFFICIAL_ONLY
            and str(profile.get("official_snapshot_id") or "").strip() == snapshot_id
        ):
            return profile_id, False

    display_name = f"纯官方-{snapshot_meta.get('display_name') or snapshot_id}"
    profile_id = make_profile_id(display_name, set(app_data["combo_profiles"].keys()))
    app_data["combo_profiles"][profile_id] = sanitize_combo_profile(
        profile_id,
        {
            "profile_type": PROFILE_MODE_OFFICIAL_ONLY,
            "display_name": display_name,
            "official_snapshot_id": snapshot_id,
            "provider_name": "官方直连",
            "provider_base_url": "",
            "provider_api_key": "",
            "provider_mode": PROVIDER_MODE_RESPONSES_DIRECT,
            "verification_status": VERIFICATION_SUCCESS,
            "last_verified_summary": "纯官方无需线路检测",
            "notes": "由接入官方账号流程自动创建",
        },
    )
    save_app_data(app_data)
    return profile_id, True


def live_state_from_files(app_data: dict) -> dict:
    auth_text = read_text(AUTH_PATH)
    config_text = read_text(CONFIG_PATH)
    provider_info = extract_current_provider_info(config_text)
    auth_kind = detect_auth_kind(auth_text)
    mode = infer_live_mode(auth_text, config_text)
    api_key = extract_api_key_from_auth_text(auth_text)
    snapshot_id = find_matching_snapshot_id(app_data["official_snapshots"], auth_text) if auth_kind == AUTH_KIND_OFFICIAL else ""
    current_token = provider_info["experimental_bearer_token"].strip()
    active_profile_id = ""

    for profile_id, profile in app_data["combo_profiles"].items():
        profile_type = profile.get("profile_type")
        if profile_type == PROFILE_MODE_OFFICIAL_ONLY:
            if mode == PROFILE_MODE_OFFICIAL_ONLY and snapshot_id and profile.get("official_snapshot_id") == snapshot_id:
                active_profile_id = profile_id
                break
        elif profile_type == PROFILE_MODE_OFFICIAL_PLUS_PROXY:
            if (
                mode == PROFILE_MODE_OFFICIAL_PLUS_PROXY
                and snapshot_id
                and profile.get("official_snapshot_id") == snapshot_id
                and normalize_base_url_for_compare(profile.get("provider_base_url", "")) == normalize_base_url_for_compare(provider_info["base_url"])
                and profile.get("provider_api_key", "").strip() == current_token
            ):
                active_profile_id = profile_id
                break
        elif profile_type == PROFILE_MODE_PROXY_ONLY:
            if (
                mode == PROFILE_MODE_PROXY_ONLY
                and normalize_base_url_for_compare(profile.get("provider_base_url", "")) == normalize_base_url_for_compare(provider_info["base_url"])
                and profile.get("provider_api_key", "").strip() == api_key
            ):
                active_profile_id = profile_id
                break

    return {
        "auth_text": auth_text,
        "config_text": config_text,
        "auth_kind": auth_kind,
        "auth_api_key": api_key,
        "mode": mode,
        "provider_id": provider_info["provider_id"],
        "provider_name": provider_info["provider_name"],
        "base_url": provider_info["base_url"],
        "experimental_bearer_token": current_token,
        "official_snapshot_id": snapshot_id,
        "active_profile_id": active_profile_id,
    }


def summarize_live_state(app_data: dict) -> dict:
    state = live_state_from_files(app_data)
    snapshot_meta = app_data["official_snapshots"].get(state["official_snapshot_id"], {})
    active_profile = app_data["combo_profiles"].get(state["active_profile_id"], {})
    mode_label = PROFILE_MODE_LABELS.get(state["mode"], "未识别")
    current_line = "官方直连"
    if state["mode"] == PROFILE_MODE_OFFICIAL_PLUS_PROXY:
        current_line = state["provider_name"] or "第三方线路"
    elif state["mode"] == PROFILE_MODE_PROXY_ONLY:
        current_line = state["provider_name"] or "纯中转"
    elif active_profile:
        current_line = active_profile.get("provider_name") or current_line

    state.update(
        {
            "mode_label": mode_label,
            "official_account_label": describe_snapshot(snapshot_meta) if snapshot_meta else "-",
            "current_line_label": current_line,
            "auth_kind_label": AUTH_KIND_LABELS.get(state["auth_kind"], "未知"),
            "base_url_label": state["base_url"] or "-",
        }
    )
    return state


def build_profile_signature(profile: dict) -> tuple[str, str, str, str]:
    return (
        str(profile.get("profile_type") or ""),
        str(profile.get("official_snapshot_id") or ""),
        normalize_base_url_for_compare(profile.get("provider_base_url", "")),
        str(profile.get("provider_api_key") or "").strip(),
    )


def build_profile_from_live_state(app_data: dict) -> dict:
    state = live_state_from_files(app_data)
    if not state["mode"]:
        raise ValueError("当前 live 配置无法识别，不能直接生成组合档案。")

    if state["mode"] == PROFILE_MODE_OFFICIAL_ONLY:
        if not state["official_snapshot_id"]:
            raise ValueError("当前是官方状态，但还没保存成官方账号。请先点“保存当前官方账号”。")
        snapshot_meta = app_data["official_snapshots"].get(state["official_snapshot_id"], {})
        display_name = f"纯官方-{snapshot_meta.get('display_name') or '官方'}"
        return sanitize_combo_profile(
            "",
            {
                "profile_type": PROFILE_MODE_OFFICIAL_ONLY,
                "display_name": display_name,
                "official_snapshot_id": state["official_snapshot_id"],
                "provider_name": "",
                "provider_base_url": "",
                "provider_api_key": "",
            },
        )

    if state["mode"] == PROFILE_MODE_OFFICIAL_PLUS_PROXY:
        if not state["official_snapshot_id"]:
            raise ValueError("当前是官方+中转，但没匹配到已保存的官方账号。请先保存当前官方账号。")
        snapshot_meta = app_data["official_snapshots"].get(state["official_snapshot_id"], {})
        line_name = state["provider_name"] or "中转"
        display_name = f"{snapshot_meta.get('display_name') or '官方'}+{line_name}"
        return sanitize_combo_profile(
            "",
            {
                "profile_type": PROFILE_MODE_OFFICIAL_PLUS_PROXY,
                "display_name": display_name,
                "official_snapshot_id": state["official_snapshot_id"],
                "provider_name": line_name,
                "provider_base_url": state["base_url"],
                "provider_api_key": state["experimental_bearer_token"],
            },
        )

    return sanitize_combo_profile(
        "",
        {
            "profile_type": PROFILE_MODE_PROXY_ONLY,
            "display_name": f"纯中转-{state['provider_name'] or '当前线路'}",
            "official_snapshot_id": "",
            "provider_name": state["provider_name"] or "当前线路",
            "provider_base_url": state["base_url"],
            "provider_api_key": state["auth_api_key"],
        },
    )


def analyze_session_health() -> tuple[bool, str]:
    try:
        diagnosis = build_repair_diagnosis()
    except Exception as exc:
        return False, f"会话异常扫描失败：{exc}"

    issue_counts = diagnosis["issue_counts"]
    issue_count = sum(issue_counts.values())
    if issue_count == 0:
        return False, "会话元数据正常"
    hints: list[str] = []
    if issue_counts["missing_files"]:
        hints.append(f"缺文件 {issue_counts['missing_files']}")
    if issue_counts["provider_mismatch"]:
        hints.append(f"分桶不一致 {issue_counts['provider_mismatch']}")
    if issue_counts["path_mismatch"]:
        hints.append(f"路径失配 {issue_counts['path_mismatch']}")
    if issue_counts["wrong_archived"]:
        hints.append(f"归档异常 {issue_counts['wrong_archived']}")
    if issue_counts["missing_in_db"]:
        hints.append(f"索引缺失 {issue_counts['missing_in_db']}")
    if issue_counts["bad_rollouts"]:
        hints.append(f"坏文件 {issue_counts['bad_rollouts']}")
    return True, f"发现会话异常：{'，'.join(hints[:3])}，可打开会话修复"


def extract_toml_string_value(content: str, key: str) -> str:
    match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', content)
    return match.group(1).strip() if match else ""


def get_model_provider_body(config_text: str) -> str:
    provider_id = extract_toml_string_value(config_text, "model_provider")
    if not provider_id:
        return config_text
    pattern = re.compile(
        rf"(?ms)^\[model_providers\.{re.escape(provider_id)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = pattern.search(config_text)
    return match.group("body") if match else config_text


def extract_openai_api_key(auth_config: object) -> str:
    if isinstance(auth_config, dict):
        for key in ("OPENAI_API_KEY", "api_key", "apiKey"):
            value = auth_config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    if isinstance(auth_config, str) and auth_config.strip():
        try:
            parsed = json.loads(auth_config)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            return extract_openai_api_key(parsed)
        match = re.search(r'"OPENAI_API_KEY"\s*:\s*"([^"]+)"', auth_config)
        return match.group(1).strip() if match else ""

    return ""


def load_cc_switch_codex_profiles() -> tuple[list[dict], int]:
    assert_file_exists(CC_SWITCH_DB_PATH)
    db_uri = f"file:{CC_SWITCH_DB_PATH.as_posix()}?mode=ro"
    imported: list[dict] = []
    skipped = 0

    with sqlite3.connect(db_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, name, settings_config
            FROM providers
            WHERE app_type = ?
            ORDER BY sort_index, name
            """,
            ("codex",),
        ).fetchall()

    for row in rows:
        try:
            settings = json.loads(row["settings_config"])
        except (TypeError, json.JSONDecodeError):
            skipped += 1
            continue

        config_text = settings.get("config", "")
        if not isinstance(config_text, str):
            skipped += 1
            continue

        provider_body = get_model_provider_body(config_text)
        base_url = extract_toml_string_value(provider_body, "base_url")
        api_key = extract_openai_api_key(settings.get("auth"))
        if not base_url or not api_key:
            skipped += 1
            continue

        config_name = extract_toml_string_value(provider_body, "name")
        row_name = str(row["name"] or "").strip()
        if row_name.lower() in {"default", "custom"} and config_name:
            name = config_name
        else:
            name = row_name or config_name or str(row["id"])

        imported.append({"name": name, "base_url": base_url, "api_key": api_key})

    return imported, skipped


def repair_now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def repair_db_path() -> Path:
    paths = codex_state_db_paths()
    if paths:
        return paths[0]
    if NEW_DB_PATH.exists():
        return NEW_DB_PATH
    return OLD_DB_PATH


def existing_repair_db_paths() -> list[Path]:
    return codex_state_db_paths()


def format_epoch_time(value: object) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def read_first_json_line(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                return json.loads(line)
    except Exception:
        return None
    return None


def extract_rollout_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("input_text") or item.get("output_text")
        if isinstance(text, str) and not is_bootstrap_text(text):
            parts.append(text)
    return "\n".join(parts).strip()


def find_first_user_message_in_rollout(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                payload = row.get("payload") or {}
                if row.get("type") == "response_item" and payload.get("role") == "user":
                    text = extract_rollout_text(payload.get("content"))
                    if text and not is_bootstrap_text(text):
                        return text[:300]
                if row.get("type") == "event_msg":
                    message = payload.get("message")
                    if payload.get("type") == "user_message" and message and not is_bootstrap_text(str(message)):
                        return str(message)[:300]
    except Exception:
        return ""
    return ""


def rollout_files() -> list[Path]:
    patterns = [
        str(CODEX_DIR / "sessions" / "**" / "rollout-*.jsonl"),
        str(CODEX_DIR / "archived_sessions" / "rollout-*.jsonl"),
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(Path(item).resolve() for item in glob.glob(pattern, recursive=True))
    return sorted(set(files))


def parse_rollout(path: Path) -> dict | None:
    first = read_first_json_line(path)
    if not first or first.get("type") != "session_meta":
        return None

    payload = first.get("payload") or {}
    thread_id = payload.get("id")
    if not thread_id:
        return None

    ts_text = payload.get("timestamp") or first.get("timestamp")
    if ts_text:
        created_at = int(datetime.fromisoformat(ts_text.replace("Z", "+00:00")).timestamp())
    else:
        created_at = int(path.stat().st_mtime)

    first_user = find_first_user_message_in_rollout(path)
    title = first_user.splitlines()[0].strip() if first_user else thread_id
    if len(title) > 100:
        title = title[:100]

    return {
        "id": thread_id,
        "rollout_path": str(path),
        "created_at": created_at,
        "updated_at": int(path.stat().st_mtime),
        "source": payload.get("source") or "vscode",
        "model_provider": payload.get("model_provider") or "",
        "cwd": payload.get("cwd") or str(USER_PROFILE),
        "title": title or thread_id,
        "sandbox_policy": json.dumps(payload.get("sandbox_policy") or {"type": "disabled"}, ensure_ascii=False),
        "approval_mode": payload.get("approval_policy") or "never",
        "cli_version": payload.get("cli_version") or "",
        "first_user_message": first_user or "",
        "memory_mode": "enabled",
        "model": payload.get("model"),
        "reasoning_effort": payload.get("reasoning_effort"),
        "created_at_ms": created_at * 1000,
        "updated_at_ms": int(path.stat().st_mtime) * 1000,
        "thread_source": payload.get("thread_source") or "user",
        "preview": first_user[:300] if first_user else "",
        "archived": 1 if "/archived_sessions/" in str(path) else 0,
    }


def repair_connect() -> sqlite3.Connection:
    path = repair_db_path()
    if not path.exists():
        raise FileNotFoundError(f"找不到数据库：{path}")
    return sqlite3.connect(path)


def backup_repair_db() -> list[Path]:
    REPAIR_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = repair_now_stamp()
    targets: list[Path] = []
    for path in existing_repair_db_paths():
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target = REPAIR_BACKUP_ROOT / f"{path.parent.name}-state_5-{stamp}.sqlite"
        src = sqlite3.connect(path)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        targets.append(target)
    return targets


def repair_active_provider() -> str:
    with repair_connect() as connection:
        row = connection.execute(
            """
            select model_provider
            from threads
            where coalesce(model_provider, '') != ''
            order by updated_at desc
            limit 1
            """
        ).fetchone()
    return row[0] if row else "custom"


def get_repair_target_provider() -> str:
    try:
        return get_current_provider_id()
    except Exception:
        return repair_active_provider()


def rollout_provider(path: Path) -> str:
    first = read_first_json_line(path)
    payload = (first or {}).get("payload") or {}
    return payload.get("model_provider") or ""


def split_line_ending(segment: str) -> tuple[str, str]:
    if segment.endswith("\r\n"):
        return segment[:-2], "\r\n"
    if segment.endswith("\n"):
        return segment[:-1], "\n"
    return segment, ""


def has_user_event_in_rollout(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return '"user_message"' in text or '"user_input"' in text or '"role":"user"' in text or '"role": "user"' in text


def restore_file_mtime(path: Path, modified_at: float | None) -> None:
    if modified_at is None:
        return
    try:
        stat = path.stat()
        os.utime(path, (stat.st_atime, modified_at))
    except OSError:
        pass


def rewrite_rollout_session_meta_providers(path: Path, provider: str) -> tuple[bool, bool]:
    old_content = path.read_text(encoding="utf-8")
    modified_at = path.stat().st_mtime
    changed = False
    has_encrypted_content = "encrypted_content" in old_content
    new_parts: list[str] = []

    for segment in old_content.splitlines(keepends=True):
        line, line_ending = split_line_ending(segment)
        next_line = line
        if line.strip():
            try:
                obj = json.loads(line)
            except Exception:
                obj = None
            if isinstance(obj, dict) and obj.get("type") == "session_meta":
                payload = obj.get("payload")
                if isinstance(payload, dict) and payload.get("model_provider") != provider:
                    payload["model_provider"] = provider
                    next_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
                    changed = True
        new_parts.append(next_line + line_ending)

    if not changed:
        return False, has_encrypted_content

    path.write_text("".join(new_parts), encoding="utf-8")
    restore_file_mtime(path, modified_at)
    return True, has_encrypted_content


def update_rollout_provider(path: Path, provider: str) -> bool:
    changed, _has_encrypted_content = rewrite_rollout_session_meta_providers(path, provider)
    return changed


def sync_old_db_from_new() -> None:
    if NEW_DB_PATH.exists() and OLD_DB_PATH.exists():
        with sqlite3.connect(NEW_DB_PATH) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(NEW_DB_PATH, OLD_DB_PATH)


def repair_db_threads() -> list[dict]:
    with repair_connect() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "select id,title,cwd,rollout_path,archived,created_at,updated_at,source,thread_source,model_provider from threads order by updated_at desc"
        ).fetchall()
    return [dict(row) for row in rows]


def display_provider_name(value: object) -> str:
    text = str(value or "").strip()
    return text or "(空)"


def format_provider_counter(counter: Counter[str], empty_text: str = "无", config_text: str | None = None) -> str:
    if not counter:
        return empty_text
    parts = [f"{format_provider_label(name, config_text)} x{counter[name]}" for name in sorted(counter)]
    return "；".join(parts)


def build_repair_provider_summary(
    rows: list[dict],
    parsed: list[dict],
    current_provider: str,
) -> dict[str, str]:
    config_text = read_text(CONFIG_PATH) if CONFIG_PATH.exists() else None
    current_name = display_provider_name(current_provider)
    current_label = format_provider_label(current_provider, config_text)
    db_counter = Counter(display_provider_name(row.get("model_provider")) for row in rows)
    rollout_counter = Counter(display_provider_name(item.get("model_provider")) for item in parsed)

    db_normal = db_counter.get(current_name, 0)
    rollout_normal = rollout_counter.get(current_name, 0)
    normal_text = f"{current_label}（数据库 {db_normal}，rollout {rollout_normal}）"

    db_abnormal = Counter(
        name for name, count in db_counter.items() for _ in range(count) if name != current_name
    )
    rollout_abnormal = Counter(
        name for name, count in rollout_counter.items() for _ in range(count) if name != current_name
    )

    abnormal_keys = sorted(set(db_abnormal) | set(rollout_abnormal))
    abnormal_parts: list[str] = []
    for name in abnormal_keys:
        counts: list[str] = []
        if db_abnormal.get(name):
            counts.append(f"数据库 {db_abnormal[name]}")
        if rollout_abnormal.get(name):
            counts.append(f"rollout {rollout_abnormal[name]}")
        abnormal_parts.append(f"{format_provider_label(name, config_text)}（{'，'.join(counts)}）")

    return {
        "current": current_label,
        "normal": normal_text,
        "abnormal": "；".join(abnormal_parts) if abnormal_parts else "无",
        "db_distribution": format_provider_counter(db_counter, config_text=config_text),
        "rollout_distribution": format_provider_counter(rollout_counter, config_text=config_text),
    }


def provider_bucket_family(provider_id: object) -> str:
    value = str(provider_id or "").strip()
    if not value:
        return "empty"
    if value == "openai":
        return "openai"
    if value == "custom":
        return "custom"
    return "other"


def describe_bucket(provider_id: object, config_text: str | None = None) -> str:
    raw = str(provider_id or "").strip()
    family = provider_bucket_family(raw)
    if family == "openai":
        return f"官方桶 {format_provider_label(raw, config_text)}"
    if family == "custom":
        return f"共享桶 {format_provider_label(raw, config_text)}"
    if family == "empty":
        return "空桶"
    return f"其他桶 {format_provider_label(raw, config_text)}"


def preferred_provider_for_mode(mode: str, provider_id: str) -> str:
    if mode == PROFILE_MODE_OFFICIAL_ONLY:
        return provider_id.strip() or "openai"
    if mode == PROFILE_MODE_OFFICIAL_PLUS_PROXY:
        return provider_id.strip() or "openai"
    if mode == PROFILE_MODE_PROXY_ONLY:
        return "custom"
    return provider_id.strip() or "custom"


def expected_provider_from_live_state() -> str:
    try:
        state = live_state_from_files(load_app_data())
        return preferred_provider_for_mode(state.get("mode", ""), state.get("provider_id", ""))
    except Exception:
        try:
            return get_current_provider_id()
        except Exception:
            return repair_active_provider()


def summarize_repair_issue_counts(diagnosis: dict) -> dict[str, int]:
    return {
        "missing_in_db": len(diagnosis["missing_in_db"]),
        "missing_files": len(diagnosis["missing_files"]),
        "wrong_archived": len(diagnosis["wrong_archived"]),
        "provider_mismatch": len(diagnosis["provider_mismatch"]),
        "path_mismatch": len(diagnosis["path_mismatch"]),
        "bad_rollouts": len(diagnosis["bad_rollouts"]),
    }


def format_bucket_counter(counter: Counter[str], config_text: str | None = None) -> str:
    if not counter:
        return "无"
    parts: list[str] = []
    for provider_id in sorted(counter):
        parts.append(f"{describe_bucket(provider_id, config_text)} x{counter[provider_id]}")
    return "；".join(parts)


def build_bucket_summary(rows: list[dict], parsed: list[dict], config_text: str | None = None) -> dict[str, str]:
    db_counter = Counter(str(row.get("model_provider") or "").strip() for row in rows)
    rollout_counter = Counter(str(item.get("model_provider") or "").strip() for item in parsed)
    db_archived = Counter()
    rollout_archived = Counter()

    for row in rows:
        if int(row.get("archived") or 0) == 1:
            db_archived[str(row.get("model_provider") or "").strip()] += 1
    for item in parsed:
        if int(item.get("archived") or 0) == 1:
            rollout_archived[str(item.get("model_provider") or "").strip()] += 1

    return {
        "db_total": format_bucket_counter(db_counter, config_text),
        "rollout_total": format_bucket_counter(rollout_counter, config_text),
        "db_archived": format_bucket_counter(db_archived, config_text),
        "rollout_archived": format_bucket_counter(rollout_archived, config_text),
    }


def discover_repair_target_options(
    rows: list[dict],
    parsed: list[dict],
    config_text: str | None,
    current_provider: str,
) -> list[dict]:
    discovered: dict[str, set[str]] = defaultdict(set)

    if current_provider.strip():
        discovered[current_provider.strip()].add("current")

    if config_text:
        configured_ids = re.findall(r"(?m)^\[model_providers\.([^\]]+)\]\s*$", config_text)
        for provider_id in configured_ids:
            provider_id = provider_id.strip()
            if provider_id:
                discovered[provider_id].add("config")
        root_provider = extract_toml_string_value(config_text, "model_provider").strip()
        if root_provider:
            discovered[root_provider].add("config")

    for row in rows:
        provider_id = str(row.get("model_provider") or "").strip()
        if provider_id:
            discovered[provider_id].add("sqlite")

    for item in parsed:
        provider_id = str(item.get("model_provider") or "").strip()
        if provider_id:
            discovered[provider_id].add("rollout")

    options: list[dict] = []
    for provider_id, source_set in discovered.items():
        source_order = sorted(source_set, key=lambda key: ("current" not in key, key))
        label_parts = [REPAIR_TARGET_SOURCE_LABELS.get(source, source) for source in source_order]
        label = format_provider_label(provider_id, config_text)
        if label_parts:
            label = f"{label}（{' / '.join(label_parts)}）"
        options.append(
            {
                "id": provider_id,
                "sources": source_order,
                "label": label,
                "is_current": provider_id == current_provider,
            }
        )

    options.sort(key=lambda item: (0 if item["is_current"] else 1, item["id"]))
    return options


def repair_analyze() -> tuple[list[dict], list[dict], list[Path], list[dict], list[dict], list[tuple[dict, int]], list[tuple[dict, str, str, str]], dict[str, dict]]:
    rows = repair_db_threads()
    by_id = {row["id"]: row for row in rows}
    parsed: list[dict] = []
    bad: list[Path] = []

    for path in rollout_files():
        item = parse_rollout(path)
        if item:
            parsed.append(item)
        else:
            bad.append(path)

    rollout_by_id = {item["id"]: item for item in parsed}
    missing_in_db = [item for item in parsed if item["id"] not in by_id]
    missing_files = [row for row in rows if not Path(row["rollout_path"]).exists()]
    provider = expected_provider_from_live_state()
    wrong_provider: list[tuple[dict, str, str, str]] = []
    path_mismatch: list[tuple[dict, str]] = []

    for row in rows:
        db_provider = str(row.get("model_provider") or "").strip()
        if db_provider and db_provider != provider:
            wrong_provider.append((row, provider, "database", db_provider))
        path = Path(row["rollout_path"])
        if path.exists():
            file_provider = rollout_provider(path)
            if file_provider and file_provider != provider:
                wrong_provider.append((row, provider, "rollout", file_provider))
            parsed_rollout = rollout_by_id.get(row["id"])
            if parsed_rollout and str(parsed_rollout.get("rollout_path") or "") != str(path):
                path_mismatch.append((row, parsed_rollout["rollout_path"]))

    wrong_archived: list[tuple[dict, int]] = []
    for row in rows:
        rollout_path = str(row["rollout_path"])
        should = 1 if "/archived_sessions/" in rollout_path else 0
        if Path(rollout_path).exists() and int(row["archived"]) != should:
            wrong_archived.append((row, should))

    return rows, parsed, bad, missing_in_db, missing_files, wrong_archived, wrong_provider, rollout_by_id


def build_repair_diagnosis() -> dict:
    rows, parsed, bad, missing_in_db, missing_files, wrong_archived, wrong_provider, rollout_by_id = repair_analyze()
    config_text = read_text(CONFIG_PATH) if CONFIG_PATH.exists() else None
    expected_provider = expected_provider_from_live_state()
    provider_summary = build_repair_provider_summary(rows, parsed, expected_provider)
    bucket_summary = build_bucket_summary(rows, parsed, config_text)

    rows_by_id = {row["id"]: row for row in rows}
    path_mismatch: list[tuple[dict, str]] = []
    provider_mismatch_rows: list[dict] = []
    provider_mismatch_ids: set[str] = set()
    continuation_risk: list[dict] = []
    file_only_ids: set[str] = set()
    db_only_ids: set[str] = set()

    for item in missing_in_db:
        file_only_ids.add(item["id"])

    for row in missing_files:
        db_only_ids.add(row["id"])

    for row_id, rollout in rollout_by_id.items():
        row = rows_by_id.get(row_id)
        if not row:
            continue
        db_path = str(row.get("rollout_path") or "")
        file_path = str(rollout.get("rollout_path") or "")
        if db_path != file_path:
            path_mismatch.append((row, file_path))

    for row, expected, place, actual in wrong_provider:
        if row["id"] in provider_mismatch_ids:
            continue
        provider_mismatch_ids.add(row["id"])
        provider_mismatch_rows.append(
            {
                "row": row,
                "expected_provider": expected,
                "actual_provider": actual,
                "place": place,
            }
        )

    current_live_provider = ""
    current_live_mode = ""
    try:
        live_state = live_state_from_files(load_app_data())
        current_live_provider = live_state.get("provider_id", "")
        current_live_mode = live_state.get("mode", "")
    except Exception:
        live_state = None

    for row in rows:
        path = Path(str(row.get("rollout_path") or ""))
        if not path.exists():
            continue
        db_provider = str(row.get("model_provider") or "").strip()
        file_provider = rollout_provider(path).strip()
        if not db_provider or not file_provider:
            continue
        if current_live_provider and provider_bucket_family(db_provider) != provider_bucket_family(current_live_provider):
            continuation_risk.append(
                {
                    "id": row["id"],
                    "title": row.get("title") or row["id"],
                    "db_provider": db_provider,
                    "file_provider": file_provider,
                    "live_provider": current_live_provider,
                    "live_mode": current_live_mode,
                }
            )

    return {
        "rows": rows,
        "parsed": parsed,
        "bad_rollouts": bad,
        "missing_in_db": missing_in_db,
        "missing_files": missing_files,
        "wrong_archived": wrong_archived,
        "wrong_provider": wrong_provider,
        "rollout_by_id": rollout_by_id,
        "path_mismatch": path_mismatch,
        "provider_mismatch": provider_mismatch_rows,
        "provider_summary": provider_summary,
        "bucket_summary": bucket_summary,
        "expected_provider": expected_provider,
        "current_live_provider": current_live_provider,
        "current_live_mode": current_live_mode,
        "db_paths": existing_repair_db_paths(),
        "issue_counts": summarize_repair_issue_counts(
            {
                "missing_in_db": missing_in_db,
                "missing_files": missing_files,
                "wrong_archived": wrong_archived,
                "provider_mismatch": provider_mismatch_rows,
                "path_mismatch": path_mismatch,
                "bad_rollouts": bad,
            }
        ),
        "file_only_ids": file_only_ids,
        "db_only_ids": db_only_ids,
        "continuation_risk": continuation_risk,
        "config_text": config_text,
    }


def format_repair_scan_report() -> str:
    diagnosis = build_repair_diagnosis()
    rows = diagnosis["rows"]
    parsed = diagnosis["parsed"]
    bad = diagnosis["bad_rollouts"]
    missing_in_db = diagnosis["missing_in_db"]
    missing_files = diagnosis["missing_files"]
    wrong_archived = diagnosis["wrong_archived"]
    wrong_provider = diagnosis["provider_mismatch"]
    path_mismatch = diagnosis["path_mismatch"]
    config_text = diagnosis["config_text"]
    provider_summary = diagnosis["provider_summary"]
    bucket_summary = diagnosis["bucket_summary"]
    expected_provider = diagnosis["expected_provider"]
    live_provider = diagnosis["current_live_provider"] or expected_provider
    lines = [
        f"数据库：{repair_db_path()}",
        f"当前 live 桶：{describe_bucket(live_provider, config_text)}",
        f"期望目标桶：{describe_bucket(expected_provider, config_text)}",
        f"当前供应商：{provider_summary['current']}",
        f"正常供应商：{provider_summary['normal']}",
        f"异常供应商：{provider_summary['abnormal']}",
        f"数据库供应商分布：{provider_summary['db_distribution']}",
        f"rollout 供应商分布：{provider_summary['rollout_distribution']}",
        f"数据库桶分布：{bucket_summary['db_total']}",
        f"rollout 桶分布：{bucket_summary['rollout_total']}",
        f"数据库归档桶分布：{bucket_summary['db_archived']}",
        f"rollout 归档桶分布：{bucket_summary['rollout_archived']}",
        f"数据库会话：{len(rows)}",
        f"本地 rollout 文件：{len(parsed)}",
        f"无法解析的 rollout：{len(bad)}",
        f"文件存在但数据库缺记录：{len(missing_in_db)}",
        f"数据库记录指向的文件不存在：{len(missing_files)}",
        f"归档状态可能不一致：{len(wrong_archived)}",
        f"供应商字段可能不一致：{len(wrong_provider)}",
        f"数据库路径可能失配：{len(path_mismatch)}",
        "",
        "说明：会话看不到不一定只是供应商名字不一样，也可能是数据库缺记录、路径失配、归档标记错，或者 rollout 文件本身丢了。",
        "",
    ]

    if missing_in_db:
        lines.append("可修复：文件存在但数据库缺记录")
        for row in missing_in_db:
            lines.append(
                f"  {row['id']}  {row['title']}  [rollout供应商: {format_provider_label(row.get('model_provider'), config_text)}]  {row['rollout_path']}"
            )

    if missing_files:
        lines.append("")
        lines.append("需人工确认：数据库记录指向的文件不存在")
        for row in missing_files:
            lines.append(
                f"  {row['id']}  {row['title']}  [数据库供应商: {format_provider_label(row.get('model_provider'), config_text)}]  {row['rollout_path']}"
            )

    if path_mismatch:
        lines.append("")
        lines.append("可修复：数据库路径和实际 rollout 文件路径不一致")
        for row, actual_path in path_mismatch:
            lines.append(
                f"  {row['id']}  {row['title']}  数据库: {row['rollout_path']}  ->  实际: {actual_path}"
            )

    if wrong_archived:
        lines.append("")
        lines.append("可修复：归档状态不一致")
        for row, should in wrong_archived:
            lines.append(f"  {row['id']}  {row['title']}  archived {row['archived']} -> {should}")

    if wrong_provider:
        lines.append("")
        lines.append("可修复：供应商字段不一致")
        for item in wrong_provider:
            row = item["row"]
            provider = item["expected_provider"]
            place = item["place"]
            actual_provider = item["actual_provider"]
            place_name = "数据库供应商" if place == "database" else "rollout供应商"
            lines.append(
                f"  {row['id']}  {row['title']}  {place_name} {format_provider_label(actual_provider, config_text)} -> {format_provider_label(provider, config_text)}"
            )

    if diagnosis["continuation_risk"]:
        lines.append("")
        lines.append("续聊风险提示：以下会话即使能显示，也可能因为跨供应商桶位不同而续聊失败")
        for item in diagnosis["continuation_risk"][:12]:
            lines.append(
                f"  {item['id']}  {item['title']}  当前 live: {describe_bucket(item['live_provider'], config_text)}  会话: {describe_bucket(item['db_provider'], config_text)}"
            )

    return "\n".join(lines).rstrip()


def format_repair_list_report() -> str:
    rows = repair_db_threads()
    config_text = read_text(CONFIG_PATH) if CONFIG_PATH.exists() else None
    lines = [
        f"数据库：{repair_db_path()}",
        f"会话数量：{len(rows)}",
        "-" * 100,
    ]
    for row in rows:
        exists = "存在" if Path(row["rollout_path"]).exists() else "缺文件"
        archived = "已归档" if row["archived"] else "正常"
        file_provider = "-"
        if Path(row["rollout_path"]).exists():
            file_provider = format_provider_label(rollout_provider(Path(row["rollout_path"])), config_text)
        lines.append(f"{format_epoch_time(row['updated_at'])}  {archived}  {exists}")
        lines.append(f"  标题：{row['title']}")
        lines.append(f"  ID：{row['id']}")
        lines.append(f"  数据库供应商：{format_provider_label(row.get('model_provider'), config_text)}")
        lines.append(f"  数据库桶：{describe_bucket(row.get('model_provider'), config_text)}")
        lines.append(f"  rollout供应商：{file_provider}")
        lines.append(f"  目录：{row['cwd']}")
        lines.append(f"  文件：{row['rollout_path']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def repair_insert_thread(connection: sqlite3.Connection, row: dict) -> None:
    if not row["model_provider"]:
        row["model_provider"] = get_repair_target_provider()
    if not row.get("cwd"):
        row["cwd"] = str(USER_PROFILE)
    if "first_user_message" not in row:
        row["first_user_message"] = find_first_user_message_in_rollout(Path(row["rollout_path"]))
    if "preview" not in row:
        row["preview"] = row["first_user_message"][:300] if row["first_user_message"] else ""
    connection.execute(
        """
        insert into threads (
            id, rollout_path, created_at, updated_at, source, model_provider, cwd, title,
            sandbox_policy, approval_mode, tokens_used, has_user_event, archived,
            cli_version, first_user_message, memory_mode, model, reasoning_effort,
            created_at_ms, updated_at_ms, thread_source, preview
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row["rollout_path"],
            row["created_at"],
            row["updated_at"],
            row["source"],
            row["model_provider"],
            row["cwd"],
            row["title"],
            row["sandbox_policy"],
            row["approval_mode"],
            1 if row["first_user_message"] else 0,
            row["archived"],
            row["cli_version"],
            row["first_user_message"],
            row["memory_mode"],
            row["model"],
            row["reasoning_effort"],
            row["created_at_ms"],
            row["updated_at_ms"],
            row["thread_source"],
            row["preview"],
        ),
    )


def run_repair_fix(provider_override: str = "") -> tuple[str, list[Path], Path | None]:
    diagnosis = build_repair_diagnosis()
    missing_in_db = diagnosis["missing_in_db"]
    missing_files = diagnosis["missing_files"]
    wrong_archived = diagnosis["wrong_archived"]
    wrong_provider = diagnosis["provider_mismatch"]
    path_mismatch = diagnosis["path_mismatch"]
    config_text = diagnosis["config_text"]
    provider = provider_override.strip() or diagnosis["expected_provider"]

    if not missing_in_db and not wrong_archived and not wrong_provider and not path_mismatch:
        return "没有发现可自动修复的问题。", [], None

    backups = backup_repair_db()
    rollout_backup_dir = REPAIR_BACKUP_ROOT / f"rollouts-{repair_now_stamp()}"
    rollout_backup_dir.mkdir(parents=True, exist_ok=True)
    logs: list[str] = []
    rewritten_rollouts: list[tuple[Path, Path]] = []

    try:
        with repair_connect() as connection:
            for row in missing_in_db:
                if not row["model_provider"]:
                    row["model_provider"] = provider
                repair_insert_thread(connection, row)
                logs.append(f"已补回索引：{row['id']}  {row['title']}")

            for row, should in wrong_archived:
                connection.execute("update threads set archived = ? where id = ?", (should, row["id"]))
                logs.append(f"已修复归档状态：{row['id']} -> {should}")

            for row, actual_path in path_mismatch:
                connection.execute("update threads set rollout_path = ? where id = ?", (actual_path, row["id"]))
                should_archived = 1 if "/archived_sessions/" in actual_path else 0
                connection.execute("update threads set archived = ? where id = ?", (should_archived, row["id"]))
                logs.append(f"已修复数据库路径：{row['id']} -> {actual_path}")

            seen_provider_ids: set[tuple[str, str]] = set()
            for item in wrong_provider:
                row = item["row"]
                target_provider = item["expected_provider"]
                place = item["place"]
                path = Path(row["rollout_path"])
                if place == "database":
                    key = (row["id"], "database")
                    if key not in seen_provider_ids:
                        connection.execute("update threads set model_provider = ? where id = ?", (target_provider, row["id"]))
                        seen_provider_ids.add(key)
                        logs.append(f"已修复数据库供应商：{row['id']} -> {target_provider}")
                elif place == "rollout" and path.exists():
                    backup_path = rollout_backup_dir / path.name
                    if not backup_path.exists():
                        shutil.copy2(path, backup_path)
                    if update_rollout_provider(path, target_provider):
                        rewritten_rollouts.append((path, backup_path))
                        logs.append(f"已修复 rollout 供应商：{row['id']} -> {target_provider}")
            connection.commit()
    except Exception:
        for path, backup_path in rewritten_rollouts:
            try:
                shutil.copy2(backup_path, path)
            except OSError:
                pass
        raise

    sync_old_db_from_new()

    report_lines = [
        "修复完成。",
        f"数据库：{repair_db_path()}",
        f"使用供应商：{format_provider_label(provider, config_text)}",
        f"期望桶：{describe_bucket(provider, config_text)}",
        "",
        "数据库备份：",
    ]
    report_lines.extend(f"  {path}" for path in backups)
    if missing_files:
        report_lines.append("")
        report_lines.append("以下问题未自动修：")
        for row in missing_files:
            report_lines.append(f"  缺文件：{row['id']}  {row['title']}  {row['rollout_path']}")
    if logs:
        report_lines.append("")
        report_lines.append("处理结果：")
        report_lines.extend(f"  {item}" for item in logs)
    return "\n".join(report_lines).rstrip(), backups, rollout_backup_dir


class SessionRepairWindow:
    def __init__(self, master: tk.Misc) -> None:
        self.window = tk.Toplevel(master)
        self.window.title("Codex 会话修复")
        fit_window_to_screen(self.window, 1120, 780, 960, 660)
        self.window.configure(bg=DARK_BG)

        self.provider_var = tk.StringVar()
        self.status_var = tk.StringVar(value=f"数据库位置: {repair_db_path()}")
        self.current_provider_name_var = tk.StringVar(value="-")
        self.normal_provider_name_var = tk.StringVar(value="-")
        self.abnormal_provider_name_var = tk.StringVar(value="-")
        self.live_bucket_var = tk.StringVar(value="-")
        self.expected_bucket_var = tk.StringVar(value="-")
        self.db_bucket_var = tk.StringVar(value="-")
        self.rollout_bucket_var = tk.StringVar(value="-")
        self.issue_summary_var = tk.StringVar(value="-")
        self.target_options: list[dict] = []
        self.target_label_to_id: dict[str, str] = {}
        self.provider_combo: ttk.Combobox | None = None
        self.result_text: scrolledtext.ScrolledText | None = None

        self.build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.refresh_provider_summary()

    def build_ui(self) -> None:
        outer = tk.Frame(self.window, bg=DARK_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        control_card = tk.Frame(outer, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        control_card.pack(fill="x")

        control_frame = tk.Frame(control_card, bg=DARK_PANEL)
        control_frame.pack(fill="x", padx=20, pady=20)

        tk.Label(control_frame, text="会话修复管理", bg=DARK_PANEL, fg=DARK_TEXT, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Label(
            control_frame,
            text="建议修复前先完全退出 Codex App。扫描和列表是只读的，备份和修复会写入数据库。",
            bg=DARK_PANEL,
            fg=DARK_MUTED,
            font=("Microsoft YaHei UI", 13),
        ).pack(anchor="w", pady=(0, 15))

        # 按钮行
        action_row = tk.Frame(control_frame, bg=DARK_PANEL)
        action_row.pack(fill="x", pady=(0, 15))

        ttk.Button(action_row, text="🔍 扫描问题", command=self.run_scan, style="Primary.TButton").pack(side="left")
        ttk.Button(action_row, text="列出会话", command=self.run_list).pack(side="left", padx=(10, 0))
        ttk.Button(action_row, text="备份数据库", command=self.run_backup).pack(side="left", padx=(10, 0))
        ttk.Button(action_row, text="🛠️ 一键修复", command=self.run_repair).pack(side="left", padx=(10, 0))
        ttk.Button(action_row, text="复制结果", command=self.copy_results).pack(side="right")

        # 选项行
        option_row = tk.Frame(control_frame, bg=DARK_PANEL)
        option_row.pack(fill="x", pady=(0, 15))

        tk.Label(option_row, text="同步目标桶", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left")
        self.provider_combo = ttk.Combobox(option_row, textvariable=self.provider_var, state="readonly", width=36, font=("Microsoft YaHei UI", 13))
        self.provider_combo.pack(side="left", padx=(10, 10))
        tk.Label(option_row, text="优先用下拉目标；留空时自动按当前 live 状态判断。", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 13)).pack(side="left")
        
        ttk.Button(option_row, text="打开备份目录", command=lambda: self.open_path(REPAIR_BACKUP_ROOT)).pack(side="right")
        ttk.Button(option_row, text="打开报告目录", command=lambda: self.open_path(REPAIR_REPORT_ROOT)).pack(side="right", padx=(0, 10))

        # 卡片行：更紧凑的显示
        summary_row = tk.Frame(control_frame, bg=DARK_PANEL)
        summary_row.pack(fill="x", pady=(0, 10))

        self.build_summary_card(summary_row, "当前供应商", self.current_provider_name_var).pack(side="left", fill="both", expand=True)
        self.build_summary_card(summary_row, "正常供应商", self.normal_provider_name_var).pack(side="left", fill="both", expand=True, padx=(10, 10))
        self.build_summary_card(summary_row, "异常供应商", self.abnormal_provider_name_var).pack(side="left", fill="both", expand=True)

        bucket_row = tk.Frame(control_frame, bg=DARK_PANEL)
        bucket_row.pack(fill="x", pady=(0, 10))
        self.build_summary_card(bucket_row, "当前 live 桶", self.live_bucket_var).pack(side="left", fill="both", expand=True)
        self.build_summary_card(bucket_row, "期望目标桶", self.expected_bucket_var).pack(side="left", fill="both", expand=True, padx=(10, 10))
        self.build_summary_card(bucket_row, "异常摘要", self.issue_summary_var).pack(side="left", fill="both", expand=True)

        distribution_row = tk.Frame(control_frame, bg=DARK_PANEL)
        distribution_row.pack(fill="x", pady=(0, 4))
        self.build_summary_card(distribution_row, "数据库桶分布", self.db_bucket_var).pack(side="left", fill="both", expand=True)
        self.build_summary_card(distribution_row, "rollout 桶分布", self.rollout_bucket_var).pack(side="left", fill="both", expand=True, padx=(10, 0))

        result_card = tk.Frame(outer, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        result_card.pack(fill="both", expand=True, pady=(15, 0))

        result_head = tk.Frame(result_card, bg=DARK_PANEL)
        result_head.pack(fill="x", padx=20, pady=(15, 5))

        tk.Label(result_head, text="执行结果", bg=DARK_PANEL, fg=DARK_TEXT, font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        tk.Label(result_head, textvariable=self.status_var, bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 13)).pack(side="right")

        self.result_text = scrolledtext.ScrolledText(
            result_card,
            wrap="word",
            font=("Microsoft YaHei UI", 14),
            bg=DARK_FIELD,
            fg=DARK_TEXT,
            insertbackground=DARK_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=DARK_BORDER,
            padx=12,
            pady=10,
        )
        self.result_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.set_result_text("点“扫描问题”先做只读检查。")

    def build_summary_card(self, master: tk.Misc, title: str, value_var: tk.StringVar) -> tk.Frame:
        card = tk.Frame(master, bg=DARK_PANEL_ALT, highlightbackground=DARK_BORDER, highlightthickness=1)
        tk.Label(card, text=title, bg=DARK_PANEL_ALT, fg=DARK_MUTED, font=("Microsoft YaHei UI", 13)).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(
            card,
            textvariable=value_var,
            bg=DARK_PANEL_ALT,
            fg=DARK_TEXT,
            font=("Microsoft YaHei UI", 15, "bold"),
            justify="left",
            wraplength=280,
        ).pack(anchor="w", padx=12, pady=(0, 10))
        return card

    def is_alive(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def set_result_text(self, content: str) -> None:
        if not self.result_text:
            return
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", content)
        self.result_text.configure(state="disabled")

    def write_report(self, action: str, content: str) -> Path:
        REPAIR_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
        report_path = REPAIR_REPORT_ROOT / f"{repair_now_stamp()}-{action}.txt"
        report_path.write_text(content, encoding="utf-8")
        return report_path

    def open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(path)], check=False)

    def refresh_provider_summary(self) -> None:
        try:
            diagnosis = build_repair_diagnosis()
            provider_summary = diagnosis["provider_summary"]
            bucket_summary = diagnosis["bucket_summary"]
            counts = diagnosis["issue_counts"]
            self.target_options = discover_repair_target_options(
                diagnosis["rows"],
                diagnosis["parsed"],
                diagnosis["config_text"],
                diagnosis["current_live_provider"] or diagnosis["expected_provider"],
            )
            self.target_label_to_id = {item["label"]: item["id"] for item in self.target_options}
            if self.provider_combo is not None:
                labels = [item["label"] for item in self.target_options]
                self.provider_combo.configure(values=labels)
                current_value = self.provider_var.get().strip()
                if not current_value and labels:
                    default_label = next((item["label"] for item in self.target_options if item["is_current"]), labels[0])
                    self.provider_var.set(default_label)
                elif current_value and current_value not in self.target_label_to_id and labels:
                    self.provider_var.set(labels[0])
            self.current_provider_name_var.set(provider_summary["current"])
            self.normal_provider_name_var.set(provider_summary["normal"])
            self.abnormal_provider_name_var.set(provider_summary["abnormal"])
            self.live_bucket_var.set(describe_bucket(diagnosis["current_live_provider"], diagnosis["config_text"]))
            self.expected_bucket_var.set(describe_bucket(diagnosis["expected_provider"], diagnosis["config_text"]))
            self.db_bucket_var.set(bucket_summary["db_total"])
            self.rollout_bucket_var.set(bucket_summary["rollout_total"])
            summary_parts: list[str] = []
            if counts["missing_files"]:
                summary_parts.append(f"缺文件 {counts['missing_files']}")
            if counts["provider_mismatch"]:
                summary_parts.append(f"分桶异常 {counts['provider_mismatch']}")
            if counts["path_mismatch"]:
                summary_parts.append(f"路径失配 {counts['path_mismatch']}")
            if counts["wrong_archived"]:
                summary_parts.append(f"归档 {counts['wrong_archived']}")
            if counts["missing_in_db"]:
                summary_parts.append(f"缺索引 {counts['missing_in_db']}")
            if counts["bad_rollouts"]:
                summary_parts.append(f"坏文件 {counts['bad_rollouts']}")
            self.issue_summary_var.set("；".join(summary_parts) if summary_parts else "未发现异常")
        except Exception as exc:
            error_text = f"读取失败: {exc}"
            self.current_provider_name_var.set(error_text)
            self.normal_provider_name_var.set("-")
            self.abnormal_provider_name_var.set("-")
            self.live_bucket_var.set("-")
            self.expected_bucket_var.set("-")
            self.db_bucket_var.set("-")
            self.rollout_bucket_var.set("-")
            self.issue_summary_var.set("-")

    def selected_target_provider_id(self) -> str:
        value = self.provider_var.get().strip()
        if not value:
            return ""
        return self.target_label_to_id.get(value, value)

    def copy_results(self) -> None:
        try:
            if not self.result_text:
                return
            content = self.result_text.get("1.0", tk.END).strip()
            if not content:
                raise ValueError("当前没有可复制的内容")
            self.window.clipboard_clear()
            self.window.clipboard_append(content)
            self.status_var.set("结果已复制到剪贴板")
        except Exception as exc:
            self.status_var.set(f"复制失败: {exc}")
            messagebox.showerror("复制失败", str(exc), parent=self.window)

    def run_scan(self) -> None:
        try:
            report = format_repair_scan_report()
            report_path = self.write_report("scan", report)
            self.set_result_text(report)
            self.refresh_provider_summary()
            self.status_var.set(f"扫描完成，报告已保存到: {report_path.name}")
        except Exception as exc:
            self.status_var.set(f"扫描失败: {exc}")
            messagebox.showerror("扫描失败", str(exc), parent=self.window)

    def run_list(self) -> None:
        try:
            report = format_repair_list_report()
            report_path = self.write_report("list", report)
            self.set_result_text(report)
            self.refresh_provider_summary()
            self.status_var.set(f"列表已生成，报告已保存到: {report_path.name}")
        except Exception as exc:
            self.status_var.set(f"列出失败: {exc}")
            messagebox.showerror("列出失败", str(exc), parent=self.window)

    def run_backup(self) -> None:
        try:
            backups = backup_repair_db()
            if not backups:
                raise FileNotFoundError("没有找到可备份的 state_5.sqlite")
            report = "已备份：\n" + "\n".join(f"  {path}" for path in backups)
            report_path = self.write_report("backup", report)
            self.set_result_text(report)
            self.refresh_provider_summary()
            self.status_var.set(f"备份完成，报告已保存到: {report_path.name}")
        except Exception as exc:
            self.status_var.set(f"备份失败: {exc}")
            messagebox.showerror("备份失败", str(exc), parent=self.window)

    def run_repair(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                "确认修复",
                "一键修复会按最小修改原则处理：补索引、修归档、修路径、修明确的桶位不一致。\n\n缺文件不会乱造，会只提示你人工处理。\n\n建议先按 Command + Q 完全退出 Codex，再继续。\n\n现在继续吗？",
                parent=self.window,
            )
            if not confirmed:
                self.status_var.set("已取消修复")
                return

            report, backups, rollout_backup_dir = run_repair_fix(self.selected_target_provider_id())
            report_path = self.write_report("repair", report)
            self.set_result_text(report)
            self.refresh_provider_summary()

            status = f"修复完成，数据库备份 {len(backups)} 份"
            if rollout_backup_dir is not None:
                status += f"，rollout 备份目录: {rollout_backup_dir.name}"
            status += f"，报告: {report_path.name}"
            self.status_var.set(status)
        except Exception as exc:
            self.status_var.set(f"修复失败: {exc}")
            messagebox.showerror("修复失败", str(exc), parent=self.window)


class ChatSearchWindow:
    def __init__(self, master: tk.Misc) -> None:
        self.window = tk.Toplevel(master)
        self.window.title("Codex 聊天记录搜索")
        fit_window_to_screen(self.window, 1080, 760, 920, 620)
        self.window.configure(bg=DARK_BG)

        self.query_var = tk.StringVar()
        self.role_var = tk.StringVar(value="all")
        self.limit_var = tk.StringVar(value="20")
        self.after_var = tk.StringVar()
        self.before_var = tk.StringVar()
        self.titles_only_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=f"搜索目录: {CODEX_DIR}")

        self.result_text: scrolledtext.ScrolledText | None = None

        self.build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

    def build_ui(self) -> None:
        outer = tk.Frame(self.window, bg=DARK_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        control_card = tk.Frame(outer, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        control_card.pack(fill="x")

        control_frame = tk.Frame(control_card, bg=DARK_PANEL)
        control_frame.pack(fill="x", padx=20, pady=15)

        tk.Label(control_frame, text="🔍 搜索聊天记录", bg=DARK_PANEL, fg=DARK_TEXT, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", pady=(0, 10))

        # 搜索输入及操作按键行
        query_row = tk.Frame(control_frame, bg=DARK_PANEL)
        query_row.pack(fill="x", pady=(0, 10))

        tk.Label(query_row, text="关键词", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left", padx=(0, 10))
        query_entry = ttk.Entry(query_row, textvariable=self.query_var, font=("Microsoft YaHei UI", 15))
        query_entry.pack(side="left", fill="x", expand=True)
        query_entry.bind("<Return>", lambda _event: self.run_search())
        
        ttk.Button(query_row, text="搜索", command=self.run_search, style="Primary.TButton").pack(side="left", padx=(10, 0))
        ttk.Button(query_row, text="清空", command=self.clear_form).pack(side="left", padx=(10, 0))
        ttk.Button(query_row, text="复制结果", command=self.copy_results).pack(side="left", padx=(10, 0))

        # 过滤选项行
        filter_row = tk.Frame(control_frame, bg=DARK_PANEL)
        filter_row.pack(fill="x", pady=(0, 10))

        tk.Label(filter_row, text="角色:", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left")
        ttk.Combobox(filter_row, textvariable=self.role_var, values=("all", "user", "assistant"), state="readonly", width=8, font=("Microsoft YaHei UI", 14)).pack(side="left", padx=(5, 15))

        tk.Label(filter_row, text="条数:", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left")
        ttk.Entry(filter_row, textvariable=self.limit_var, width=6, font=("Consolas", 14)).pack(side="left", padx=(5, 15))

        tk.Label(filter_row, text="起始:", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left")
        ttk.Entry(filter_row, textvariable=self.after_var, width=11, font=("Consolas", 14)).pack(side="left", padx=(5, 15))

        tk.Label(filter_row, text="结束:", bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 14)).pack(side="left")
        ttk.Entry(filter_row, textvariable=self.before_var, width=11, font=("Consolas", 14)).pack(side="left", padx=(5, 15))

        ttk.Checkbutton(filter_row, text="仅搜索标题", variable=self.titles_only_var).pack(side="left", padx=(10, 0))

        result_card = tk.Frame(outer, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        result_card.pack(fill="both", expand=True, pady=(15, 0))

        result_head = tk.Frame(result_card, bg=DARK_PANEL)
        result_head.pack(fill="x", padx=20, pady=(15, 5))

        tk.Label(result_head, text="搜索结果", bg=DARK_PANEL, fg=DARK_TEXT, font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        tk.Label(result_head, textvariable=self.status_var, bg=DARK_PANEL, fg=DARK_MUTED, font=("Microsoft YaHei UI", 13)).pack(side="right")

        self.result_text = scrolledtext.ScrolledText(
            result_card,
            wrap="word",
            font=("Microsoft YaHei UI", 14),
            bg=DARK_FIELD,
            fg=DARK_TEXT,
            insertbackground=DARK_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=DARK_BORDER,
            padx=12,
            pady=10,
        )
        self.result_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.set_result_text("输入关键词后点“搜索”。")

    def is_alive(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def set_result_text(self, content: str) -> None:
        if not self.result_text:
            return
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", content)
        self.result_text.configure(state="disabled")

    def clear_form(self) -> None:
        self.query_var.set("")
        self.role_var.set("all")
        self.limit_var.set("20")
        self.after_var.set("")
        self.before_var.set("")
        self.titles_only_var.set(False)
        self.status_var.set(f"搜索目录: {CODEX_DIR}")
        self.set_result_text("输入关键词后点“搜索”。")

    def copy_results(self) -> None:
        try:
            if not self.result_text:
                return
            content = self.result_text.get("1.0", tk.END).strip()
            if not content:
                raise ValueError("当前没有可复制的内容")
            self.window.clipboard_clear()
            self.window.clipboard_append(content)
            self.status_var.set("结果已复制到剪贴板")
        except Exception as exc:
            self.status_var.set(f"复制失败: {exc}")
            messagebox.showerror("复制失败", str(exc), parent=self.window)

    def run_search(self) -> None:
        try:
            query = self.query_var.get().strip()
            if not query:
                raise ValueError("请输入搜索关键词")

            limit = int(self.limit_var.get().strip())
            if limit <= 0:
                raise ValueError("条数必须大于 0")

            after = validate_date(self.after_var.get(), "起始日期")
            before = validate_date(self.before_var.get(), "结束日期")
            if after and before and after > before:
                raise ValueError("起始日期不能晚于结束日期")

            if not CODEX_DIR.exists():
                raise FileNotFoundError(f"找不到 Codex 数据目录: {CODEX_DIR}")

            session_map = load_session_index(CODEX_DIR)
            if self.titles_only_var.get():
                results = search_titles(session_map, query, limit, after, before)
            else:
                results = search_messages(CODEX_DIR, session_map, query, self.role_var.get(), limit, after, before)

            self.set_result_text(format_search_results(results))
            self.status_var.set(f"搜索完成，共 {len(results)} 条")
        except Exception as exc:
            self.status_var.set(f"搜索失败: {exc}")
            messagebox.showerror("搜索失败", str(exc), parent=self.window)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CODEX 配置切换中心")
        fit_window_to_screen(self.root, 1360, 820, 1180, 760, width_ratio=0.78, height_ratio=0.76)
        self.root.configure(bg=DARK_BG)

        self.profiles: dict[str, dict] = {}
        self.active_profile_id = ""
        self.search_window: ChatSearchWindow | None = None
        self.repair_window: SessionRepairWindow | None = None
        self.current_api_key_value = ""

        self.current_provider_var = tk.StringVar()
        self.current_url_var = tk.StringVar()
        self.current_key_var = tk.StringVar()
        self.current_name_var = tk.StringVar()
        self.status_var = tk.StringVar(value="系统就绪")
        self.search_query_var = tk.StringVar()
        self.search_tip_var = tk.StringVar(value="输入关键词后按回车，直接搜索聊天记录")

        self.name_var = tk.StringVar()
        self.base_url_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.api_key_visible_var = tk.BooleanVar(value=False)
        self.form_profile_id = ""
        self.model_check_status_var = tk.StringVar(value="未检测")
        self.model_check_summary_var = tk.StringVar(value="填写 Base URL 和 API Key 后，点击上方按钮开始检测。")
        self.model_result_text: scrolledtext.ScrolledText | None = None
        self.api_key_entry: ttk.Entry | None = None
        self.api_key_toggle_btn: ttk.Button | None = None
        self.fetch_models_btn: ttk.Button | None = None
        self.health_check_btn: ttk.Button | None = None
        self.copy_models_btn: ttk.Button | None = None
        self.clear_models_btn: ttk.Button | None = None
        self.is_checking_models = False
        self.model_task_serial = 0

        self.setup_styles()
        self.build_ui()
        self.register_macos_reopen_handler()
        self.refresh(select_current=True)

    def register_macos_reopen_handler(self) -> None:
        try:
            self.root.createcommand("::tk::mac::ReopenApplication", self.show_main_window)
        except tk.TclError:
            pass

    def show_main_window(self, *_args: object) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def setup_styles(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.root.option_add("*TCombobox*Listbox.background", DARK_FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", DARK_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", DARK_SELECT_BG)
        self.root.option_add("*TCombobox*Listbox.selectForeground", DARK_SELECT_FG)

        style.configure("TButton", font=("Microsoft YaHei UI", 14), padding=(12, 6), background=DARK_PANEL_ALT, foreground=DARK_TEXT, bordercolor=DARK_BORDER, lightcolor=DARK_BORDER, darkcolor=DARK_BORDER, focuscolor="")
        style.map("TButton", background=[("pressed", DARK_BORDER), ("active", "#273449"), ("disabled", DARK_PANEL)], foreground=[("disabled", DARK_DISABLED)])
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 14, "bold"), background=DARK_ACCENT, foreground=DARK_SELECT_FG, bordercolor=DARK_ACCENT, lightcolor=DARK_ACCENT, darkcolor=DARK_ACCENT, focuscolor="")
        style.map("Primary.TButton", background=[("pressed", DARK_ACCENT_ACTIVE), ("active", DARK_ACCENT_ACTIVE), ("disabled", DARK_PANEL_ALT)], foreground=[("disabled", DARK_DISABLED)])
        style.configure("Icon.TButton", font=("Microsoft YaHei UI", 14), padding=(8, 6), background=DARK_PANEL_ALT, foreground=DARK_TEXT, bordercolor=DARK_BORDER, focuscolor="")
        style.map("Icon.TButton", background=[("pressed", DARK_BORDER), ("active", "#273449")])

        style.configure("TEntry", font=("Microsoft YaHei UI", 14), fieldbackground=DARK_FIELD, foreground=DARK_TEXT, insertcolor=DARK_TEXT, bordercolor=DARK_BORDER, lightcolor=DARK_BORDER, darkcolor=DARK_BORDER)
        style.map("TEntry", fieldbackground=[("disabled", DARK_PANEL_ALT), ("readonly", DARK_FIELD)], foreground=[("disabled", DARK_DISABLED)])
        style.configure("TCombobox", fieldbackground=DARK_FIELD, foreground=DARK_TEXT, background=DARK_PANEL_ALT, arrowcolor=DARK_TEXT, bordercolor=DARK_BORDER, lightcolor=DARK_BORDER, darkcolor=DARK_BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", DARK_FIELD)], foreground=[("readonly", DARK_TEXT)], selectbackground=[("readonly", DARK_FIELD)], selectforeground=[("readonly", DARK_TEXT)])
        style.configure("TCheckbutton", background=DARK_PANEL, foreground=DARK_TEXT, focuscolor="", font=("Microsoft YaHei UI", 14))
        style.map("TCheckbutton", background=[("active", DARK_PANEL)], foreground=[("disabled", DARK_DISABLED)])

        style.configure("Vertical.TScrollbar", background=DARK_PANEL_ALT, bordercolor=DARK_BG, arrowcolor=DARK_MUTED, troughcolor=DARK_BG)
        style.configure("Horizontal.TScrollbar", background=DARK_PANEL_ALT, bordercolor=DARK_BG, arrowcolor=DARK_MUTED, troughcolor=DARK_BG)

        style.configure("Treeview", background=DARK_FIELD, fieldbackground=DARK_FIELD, foreground=DARK_TEXT, bordercolor=DARK_BORDER, rowheight=34)
        style.map("Treeview", background=[("selected", DARK_SELECT_BG)], foreground=[("selected", DARK_SELECT_FG)])
        style.configure("Treeview.Heading", background=DARK_PANEL_ALT, foreground=DARK_TEXT, bordercolor=DARK_BORDER, font=("Microsoft YaHei UI", 13, "bold"))

        style.configure("TNotebook", background=DARK_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 14), padding=(15, 8), background=DARK_PANEL_ALT, foreground=DARK_MUTED, bordercolor=DARK_BORDER)
        style.map("TNotebook.Tab", background=[("selected", DARK_PANEL)], foreground=[("selected", DARK_ACCENT), ("active", DARK_TEXT)])

    def build_ui(self) -> None:
        # 采用左右分栏的 PanedWindow 来提高空间利用率
        main_paned = ttk.PanedWindow(self.root, orient="horizontal")
        main_paned.pack(fill="both", expand=True, padx=12, pady=12)

        # ================= 左侧：线路列表 =================
        left_frame = tk.Frame(main_paned, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        main_paned.add(left_frame, weight=1)

        left_top = tk.Frame(left_frame, bg=DARK_PANEL)
        left_top.pack(fill="x", padx=15, pady=(15, 10))
        tk.Label(left_top, text="📋 线路列表", font=("Microsoft YaHei UI", 19, "bold"), bg=DARK_PANEL, fg=DARK_TEXT).pack(side="left")
        ttk.Button(left_top, text="📥 导入 CC", command=self.import_cc_switch_profiles).pack(side="right")

        list_frame = tk.Frame(left_frame, bg=DARK_PANEL)
        list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame, font=("Microsoft YaHei UI", 19),
            bg=DARK_FIELD, fg=DARK_TEXT,
            selectbackground=DARK_SELECT_BG, selectforeground=DARK_SELECT_FG,
            relief="flat", highlightthickness=1, highlightbackground=DARK_BORDER,
            yscrollcommand=scrollbar.set, activestyle="none", exportselection=False
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.switch_selected())
        self.listbox.bind("<Delete>", lambda _e: self.delete_selected_profile())

        left_bottom = tk.Frame(left_frame, bg=DARK_PANEL)
        left_bottom.pack(fill="x", padx=15, pady=(0, 15))
        ttk.Button(left_bottom, text="切换选中", command=self.switch_selected, style="Primary.TButton").pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(left_bottom, text="新建", command=self.clear_form).pack(side="left", expand=True, fill="x", padx=(5, 5))
        ttk.Button(left_bottom, text="删除", command=self.delete_selected_profile).pack(side="left", expand=True, fill="x", padx=(5, 0))
        self.root.after_idle(lambda: main_paned.sashpos(0, 410))

        # ================= 右侧：详细内容区 =================
        right_frame = tk.Frame(main_paned, bg=DARK_BG)
        main_paned.add(right_frame, weight=3)

        # -- 右侧顶部：当前生效状态 (Dashboard) --
        dash_card = tk.Frame(right_frame, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        dash_card.pack(fill="x", pady=(0, 10))

        dash_head = tk.Frame(dash_card, bg=DARK_PANEL)
        dash_head.pack(fill="x", padx=20, pady=(15, 5))
        tk.Label(dash_head, text="🟢 当前生效环境", font=("Microsoft YaHei UI", 17, "bold"), bg=DARK_PANEL, fg=DARK_SUCCESS).pack(side="left")
        ttk.Button(dash_head, text="🔄 刷新状态", command=lambda: self.refresh(select_current=False)).pack(side="right")
        ttk.Button(dash_head, text="🛠️ 会话修复", command=self.open_repair_window).pack(side="right", padx=(0, 10))
        ttk.Button(dash_head, text="🔍 高级搜索", command=self.open_search_window).pack(side="right", padx=(0, 10))

        dash_body = tk.Frame(dash_card, bg=DARK_PANEL)
        dash_body.pack(fill="x", padx=20, pady=(0, 15))
        
        # 采用 Grid 进行整齐的布局
        tk.Label(dash_body, text="模型提供商:", font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=0, column=0, sticky="e", pady=3)
        tk.Label(dash_body, textvariable=self.current_provider_var, font=("Microsoft YaHei UI", 15), bg=DARK_PANEL, fg=DARK_TEXT).grid(row=0, column=1, sticky="w", padx=10, pady=3)
        
        tk.Label(dash_body, text="线路名称:", font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=1, column=0, sticky="e", pady=3)
        tk.Label(dash_body, textvariable=self.current_name_var, font=("Microsoft YaHei UI", 17, "bold"), bg=DARK_PANEL, fg=DARK_ACCENT).grid(row=1, column=1, sticky="w", padx=10, pady=3)

        tk.Label(dash_body, text="Base URL:", font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=2, column=0, sticky="e", pady=3)
        tk.Label(dash_body, textvariable=self.current_url_var, font=("Consolas", 15), bg=DARK_PANEL, fg=DARK_TEXT).grid(row=2, column=1, sticky="w", padx=10, pady=3)

        tk.Label(dash_body, text="API Key:", font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=3, column=0, sticky="e", pady=3)
        tk.Label(dash_body, textvariable=self.current_key_var, font=("Consolas", 15), bg=DARK_PANEL, fg=DARK_TEXT).grid(row=3, column=1, sticky="w", padx=10, pady=3)

        # -- 右侧中部：编辑表单 --
        edit_card = tk.Frame(right_frame, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        edit_card.pack(fill="x", pady=(0, 10))

        edit_head = tk.Frame(edit_card, bg=DARK_PANEL)
        edit_head.pack(fill="x", padx=20, pady=(15, 5))
        tk.Label(edit_head, text="✏️ 编辑配置", font=("Microsoft YaHei UI", 17, "bold"), bg=DARK_PANEL, fg=DARK_TEXT).pack(side="left")
        ttk.Button(edit_head, text="读取当前生效配置", command=self.load_current_to_form).pack(side="right")

        edit_form = tk.Frame(edit_card, bg=DARK_PANEL)
        edit_form.pack(fill="x", padx=20, pady=(0, 15))
        
        edit_form.columnconfigure(1, weight=1)
        tk.Label(edit_form, text="名称:", font=("Microsoft YaHei UI", 15), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(edit_form, textvariable=self.name_var, font=("Microsoft YaHei UI", 16)).grid(row=0, column=1, sticky="we", padx=(10, 0), pady=8)

        tk.Label(edit_form, text="Base URL:", font=("Microsoft YaHei UI", 15), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(edit_form, textvariable=self.base_url_var, font=("Consolas", 16)).grid(row=1, column=1, sticky="we", padx=(10, 0), pady=8)

        tk.Label(edit_form, text="API Key:", font=("Microsoft YaHei UI", 15), bg=DARK_PANEL, fg=DARK_MUTED).grid(row=2, column=0, sticky="w", pady=8)
        api_key_row = tk.Frame(edit_form, bg=DARK_PANEL)
        api_key_row.grid(row=2, column=1, sticky="we", padx=(10, 0), pady=8)
        api_key_row.columnconfigure(0, weight=1)
        self.api_key_entry = ttk.Entry(api_key_row, textvariable=self.api_key_var, font=("Consolas", 16), show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="we")
        self.api_key_toggle_btn = ttk.Button(api_key_row, text="👁", width=3, command=self.toggle_api_key_visibility, style="Icon.TButton")
        self.api_key_toggle_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        edit_actions = tk.Frame(edit_card, bg=DARK_PANEL)
        edit_actions.pack(fill="x", padx=20, pady=(0, 15))
        ttk.Button(edit_actions, text="✅ 保存并应用 (切换)", command=self.save_and_switch, style="Primary.TButton").pack(side="right")
        ttk.Button(edit_actions, text="💾 仅保存", command=self.save_profile).pack(side="right", padx=(0, 10))
        tk.Label(edit_actions, text="* 仅应用 base_url 与 API Key 核心字段", bg=DARK_PANEL, fg=DARK_DISABLED, font=("Microsoft YaHei UI", 13)).pack(side="left", pady=(5, 0))

        # -- 右侧下半：测试工具与快捷搜索 (Notebook 选项卡) --
        tools_notebook = ttk.Notebook(right_frame)
        tools_notebook.pack(fill="both", expand=True)

        # Tab 1: 连通性测试
        probe_tab = tk.Frame(tools_notebook, bg=DARK_PANEL)
        tools_notebook.add(probe_tab, text="📡 连通性测试")

        probe_head = tk.Frame(probe_tab, bg=DARK_PANEL)
        probe_head.pack(fill="x", padx=15, pady=(15, 5))
        self.fetch_models_btn = ttk.Button(probe_head, text="获取模型列表", command=self.start_fetch_models)
        self.fetch_models_btn.pack(side="left")
        self.health_check_btn = ttk.Button(probe_head, text="一键连通性检测", command=self.start_health_check, style="Primary.TButton")
        self.health_check_btn.pack(side="left", padx=(10, 0))
        self.copy_models_btn = ttk.Button(probe_head, text="复制结果", command=self.copy_model_results)
        self.copy_models_btn.pack(side="left", padx=(10, 0))
        self.clear_models_btn = ttk.Button(probe_head, text="清空", command=lambda: self.clear_model_results(cancel_running=True))
        self.clear_models_btn.pack(side="left", padx=(10, 0))

        tk.Label(probe_head, textvariable=self.model_check_status_var, font=("Microsoft YaHei UI", 15, "bold"), bg=DARK_PANEL, fg=DARK_ACCENT).pack(side="right")
        tk.Label(probe_tab, textvariable=self.model_check_summary_var, font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).pack(anchor="w", padx=15, pady=(5, 5))

        self.model_result_text = scrolledtext.ScrolledText(
            probe_tab, font=("Microsoft YaHei UI", 15), bg=DARK_FIELD, fg=DARK_TEXT,
            insertbackground=DARK_TEXT, relief="flat", highlightthickness=1, highlightbackground=DARK_BORDER
        )
        self.model_result_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.set_model_result_text("填写上方 Base URL 和 API Key 后，点击“获取模型列表”或“一键连通性检测”。")

        # Tab 2: 快捷搜索
        search_tab = tk.Frame(tools_notebook, bg=DARK_PANEL)
        tools_notebook.add(search_tab, text="💬 快捷搜索")
        
        search_wrap = tk.Frame(search_tab, bg=DARK_PANEL)
        search_wrap.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(search_wrap, text="快速查找聊天记录", font=("Microsoft YaHei UI", 16, "bold"), bg=DARK_PANEL, fg=DARK_TEXT).pack(anchor="w", pady=(0, 15))
        
        search_row = tk.Frame(search_wrap, bg=DARK_PANEL)
        search_row.pack(fill="x")
        search_entry = ttk.Entry(search_row, textvariable=self.search_query_var, font=("Microsoft YaHei UI", 16))
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _event: self.run_quick_search())
        ttk.Button(search_row, text="搜索", command=self.run_quick_search, style="Primary.TButton").pack(side="left", padx=(10, 0))
        
        tk.Label(search_wrap, textvariable=self.search_tip_var, font=("Microsoft YaHei UI", 14), bg=DARK_PANEL, fg=DARK_MUTED).pack(anchor="w", pady=(15, 0))

        # ================= 底部状态栏 =================
        status_bar = tk.Label(self.root, textvariable=self.status_var, anchor="w", bg=DARK_PANEL_ALT, fg=DARK_MUTED, font=("Microsoft YaHei UI", 13), padx=15, pady=6)
        status_bar.pack(side="bottom", fill="x")
        self.update_api_key_visibility()

    def refresh(self, select_current: bool, target_profile_id: str = "") -> None:
        config_text = read_text(CONFIG_PATH)
        current_base_url = get_current_base_url()
        current_api_key = get_current_api_key()
        current_provider_id = get_current_provider_id(config_text)
        current_provider_name = get_current_provider_name(config_text)

        self.profiles = load_profiles()
        self.active_profile_id = self.find_active_profile(current_base_url, current_api_key)
        current_name = self.profiles.get(self.active_profile_id, {}).get("name", "未保存线路")

        self.current_provider_var.set(f"{current_provider_name} ({current_provider_id})")
        self.current_name_var.set(current_name)
        self.current_url_var.set(current_base_url)
        self.current_api_key_value = current_api_key
        self.update_current_key_display()

        previous_id = self.get_selected_profile_id()
        ordered_ids = self.get_ordered_profile_ids()
        self.listbox.delete(0, tk.END)
        for profile_id in ordered_ids:
            profile = self.profiles[profile_id]
            prefix = "★ " if profile_id == self.active_profile_id else "   "
            self.listbox.insert(tk.END, f"{prefix}{profile.get('name', profile_id)}")

        target_id = self.active_profile_id if select_current else (target_profile_id or previous_id)
        if target_id and target_id in self.profiles:
            index = ordered_ids.index(target_id)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
            self.load_profile_to_form(target_id)
        else:
            self.form_profile_id = ""
            self.set_form_values()

        self.status_var.set("已刷新最新配置状态")

    def find_active_profile(self, base_url: str, api_key: str) -> str:
        for profile_id, profile in self.profiles.items():
            if profile.get("base_url", "").strip() == base_url.strip() and profile.get("api_key", "").strip() == api_key.strip():
                return profile_id
        return ""

    def get_ordered_profile_ids(self) -> list[str]:
        return sorted(self.profiles)

    def get_selected_profile_id(self) -> str:
        selection = self.listbox.curselection()
        if not selection:
            return ""
        ordered_ids = self.get_ordered_profile_ids()
        if selection[0] >= len(ordered_ids):
            return ""
        return ordered_ids[selection[0]]

    def on_select(self, _event: object) -> None:
        profile_id = self.get_selected_profile_id()
        if profile_id:
            self.load_profile_to_form(profile_id)
            self.clear_model_results(cancel_running=True)

    def set_form_values(self, name: str = "", base_url: str = "", api_key: str = "") -> None:
        self.name_var.set(name)
        self.base_url_var.set(base_url)
        self.api_key_var.set(api_key)

    def update_current_key_display(self) -> None:
        self.current_key_var.set(mask_secret(self.current_api_key_value, self.api_key_visible_var.get()))

    def update_api_key_visibility(self) -> None:
        visible = self.api_key_visible_var.get()
        if self.api_key_entry is not None:
            self.api_key_entry.configure(show="" if visible else "*")
        if self.api_key_toggle_btn is not None:
            self.api_key_toggle_btn.configure(text="🙈" if visible else "👁")
        self.update_current_key_display()

    def toggle_api_key_visibility(self) -> None:
        self.api_key_visible_var.set(not self.api_key_visible_var.get())
        self.update_api_key_visibility()

    def load_profile_to_form(self, profile_id: str) -> None:
        profile = self.profiles.get(profile_id)
        if not profile:
            return
        self.form_profile_id = profile_id
        self.set_form_values(
            profile.get("name", ""),
            profile.get("base_url", ""),
            profile.get("api_key", ""),
        )

    def load_current_to_form(self) -> None:
        current_name = self.profiles.get(self.active_profile_id, {}).get("name", "") or get_current_provider_name()
        self.form_profile_id = self.active_profile_id
        self.set_form_values(current_name, get_current_base_url(), get_current_api_key())
        self.listbox.selection_clear(0, tk.END)
        if self.active_profile_id:
            ordered_ids = self.get_ordered_profile_ids()
            if self.active_profile_id in ordered_ids:
                index = ordered_ids.index(self.active_profile_id)
                self.listbox.selection_set(index)
                self.listbox.activate(index)
                self.listbox.see(index)
        self.status_var.set("已读取当前运行中的配置")
        self.clear_model_results(cancel_running=True)

    def clear_form(self) -> None:
        self.form_profile_id = ""
        self.listbox.selection_clear(0, tk.END)
        self.set_form_values()
        self.status_var.set("表单已清空，可填写新线路")
        self.clear_model_results(cancel_running=True)

    def run_quick_search(self) -> None:
        try:
            query = self.search_query_var.get().strip()
            if not query:
                raise ValueError("请输入搜索关键词")
            self.open_search_window()
            if not self.search_window:
                return
            self.search_window.query_var.set(query)
            self.search_window.focus()
            self.search_window.run_search()
            self.search_tip_var.set(f"已搜索: {query}")
        except Exception as exc:
            self.search_tip_var.set(f"搜索失败: {exc}")
            messagebox.showerror("搜索失败", str(exc), parent=self.root)

    def open_search_window(self) -> None:
        if self.search_window and self.search_window.is_alive():
            self.search_window.focus()
            return
        self.search_window = ChatSearchWindow(self.root)

    def open_repair_window(self) -> None:
        if self.repair_window and self.repair_window.is_alive():
            self.repair_window.focus()
            return
        self.repair_window = SessionRepairWindow(self.root)

    def collect_form(self) -> tuple[str, dict]:
        name = self.name_var.get().strip()
        base_url = self.base_url_var.get().strip()
        api_key = self.api_key_var.get().strip()
        if not name:
            raise ValueError("名称不能为空")
        if not base_url:
            raise ValueError("base_url 不能为空")
        if not api_key:
            raise ValueError("API Key 不能为空")
        profile = {"name": name, "base_url": base_url, "api_key": api_key}
        profile_id = self.resolve_profile_id_for_save(name, profile)
        return profile_id, profile

    def pick_profile_match(self, candidates: list[str]) -> str:
        candidates = [profile_id for profile_id in candidates if profile_id in self.profiles]
        if not candidates:
            return ""
        preferred_ids = [
            self.form_profile_id,
            self.get_selected_profile_id(),
            self.active_profile_id,
        ]
        for preferred_id in preferred_ids:
            if preferred_id and preferred_id in candidates:
                return preferred_id
        return candidates[0] if len(candidates) == 1 else ""

    def resolve_profile_id_for_save(self, name: str, profile: dict) -> str:
        if self.form_profile_id and self.form_profile_id in self.profiles:
            return self.form_profile_id

        selected_id = self.get_selected_profile_id()
        if selected_id and selected_id in self.profiles:
            return selected_id

        name_key = profile_name_compare_key(name)
        name_matches = [
            profile_id
            for profile_id, existing_profile in self.profiles.items()
            if profile_name_compare_key(existing_profile.get("name", "")) == name_key
        ]
        matched_id = self.pick_profile_match(name_matches)
        if matched_id:
            return matched_id

        compare_key = profile_compare_key(profile)
        pair_matches = [
            profile_id
            for profile_id, existing_profile in self.profiles.items()
            if profile_compare_key(existing_profile) == compare_key
        ]
        matched_id = self.pick_profile_match(pair_matches)
        if matched_id:
            return matched_id

        return make_profile_id(name, set(self.profiles.keys()))

    def persist_profiles(self) -> None:
        save_profiles(self.profiles)

    def set_model_result_text(self, content: str) -> None:
        if not self.model_result_text:
            return
        self.model_result_text.configure(state="normal")
        self.model_result_text.delete("1.0", tk.END)
        self.model_result_text.insert("1.0", content)
        self.model_result_text.configure(state="disabled")

    def copy_model_results(self) -> None:
        try:
            if not self.model_result_text:
                return
            content = self.model_result_text.get("1.0", tk.END).strip()
            if not content:
                raise ValueError("当前没有可复制的检测结果")
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("检测结果已复制到剪贴板")
        except Exception as exc:
            self.status_var.set(f"复制失败: {exc}")
            messagebox.showerror("复制失败", str(exc), parent=self.root)

    def clear_model_results(self, cancel_running: bool = False) -> None:
        if cancel_running:
            self.model_task_serial += 1
            self.is_checking_models = False
            self.set_model_buttons_state(False)
        self.model_check_status_var.set("未检测")
        self.model_check_summary_var.set("填写 Base URL 和 API Key 后，点击上方按钮开始检测。")
        self.set_model_result_text("填写上方 Base URL 和 API Key 后，点击“获取模型列表”或“一键连通性检测”。")

    def set_model_buttons_state(self, disabled: bool) -> None:
        state = "disabled" if disabled else "normal"
        for widget in (self.fetch_models_btn, self.health_check_btn, self.copy_models_btn, self.clear_models_btn):
            if widget is not None:
                widget.configure(state=state)

    def validate_probe_inputs(self) -> tuple[str, str]:
        base_url = self.base_url_var.get().strip()
        api_key = self.api_key_var.get().strip()
        if not base_url:
            raise ValueError("请先填写 Base URL。")
        if not api_key:
            raise ValueError("请先填写 API Key。")
        return normalize_api_base_url(base_url), api_key

    def start_fetch_models(self) -> None:
        if self.is_checking_models:
            self.status_var.set("已有检测任务在进行中")
            return
        try:
            base_url, api_key = self.validate_probe_inputs()
        except Exception as exc:
            self.model_check_status_var.set("不可用")
            self.model_check_summary_var.set(str(exc))
            self.set_model_result_text(str(exc))
            self.status_var.set(f"检测失败: {exc}")
            return
        self.is_checking_models = True
        self.model_task_serial += 1
        task_id = self.model_task_serial
        self.set_model_buttons_state(True)
        self.model_check_status_var.set("检测中")
        self.model_check_summary_var.set("正在获取模型列表...")
        self.set_model_result_text("正在请求 /models，请稍候...")
        self.status_var.set("正在获取模型列表")
        threading.Thread(target=self.run_model_fetch_worker, args=(base_url, api_key, task_id), daemon=True).start()

    def start_health_check(self) -> None:
        if self.is_checking_models:
            self.status_var.set("已有检测任务在进行中")
            return
        try:
            base_url, api_key = self.validate_probe_inputs()
        except Exception as exc:
            self.model_check_status_var.set("不可用")
            self.model_check_summary_var.set(str(exc))
            self.set_model_result_text(str(exc))
            self.status_var.set(f"检测失败: {exc}")
            return
        self.is_checking_models = True
        self.model_task_serial += 1
        task_id = self.model_task_serial
        self.set_model_buttons_state(True)
        self.model_check_status_var.set("检测中")
        self.model_check_summary_var.set("正在执行模型列表和聊天双重检测...")
        self.set_model_result_text("步骤 1/2：请求 /models\n步骤 2/2：最小聊天请求\n\n请稍候...")
        self.status_var.set("正在检测线路是否可用")
        threading.Thread(target=self.run_health_check_worker, args=(base_url, api_key, task_id), daemon=True).start()

    def finish_model_task(self) -> None:
        self.is_checking_models = False
        self.set_model_buttons_state(False)

    def update_model_panel(self, status_text: str, summary_text: str, body_text: str, ok: bool, status_bar_text: str, task_id: int) -> None:
        if task_id != self.model_task_serial:
            return
        self.model_check_status_var.set(status_text)
        self.model_check_summary_var.set(summary_text)
        self.set_model_result_text(body_text)
        self.status_var.set(status_bar_text)
        self.finish_model_task()

    def handle_model_task_error(self, exc: Exception, action_label: str, task_id: int) -> None:
        message = str(exc)
        def _apply() -> None:
            self.update_model_panel("不可用", message, f"{action_label}失败\n\n{message}", False, f"{action_label}失败: {message}", task_id)
        self.root.after(0, _apply)

    def run_model_fetch_worker(self, base_url: str, api_key: str, task_id: int) -> None:
        try:
            models = fetch_models(base_url, api_key)
            lines = [
                "模型列表获取成功",
                "",
                f"Base URL: {base_url}",
                f"模型数量: {len(models)}",
                "",
                "模型列表：",
                *models,
            ]
            summary = f"获取到 {len(models)} 个模型"
            self.root.after(0, lambda: self.update_model_panel("可用", summary, "\n".join(lines), True, "模型列表获取成功", task_id))
        except Exception as exc:
            self.handle_model_task_error(exc, "获取模型列表", task_id)

    def run_health_check_worker(self, base_url: str, api_key: str, task_id: int) -> None:
        try:
            models = fetch_models(base_url, api_key)
            probe_model = pick_probe_model(models)
            try:
                probe_chat(base_url, api_key, probe_model)
            except Exception as exc:
                lines = [
                    "双重检测未通过",
                    "",
                    "步骤 1/2：/models 成功",
                    f"模型数量: {len(models)}",
                    "",
                    f"步骤 2/2：/chat/completions 失败（检测模型：{probe_model}）",
                    str(exc),
                    "",
                    "模型列表：",
                    *models,
                ]
                summary = "模型列表可获取，但聊天线路不可用"
                self.root.after(0, lambda: self.update_model_panel("不可用", summary, "\n".join(lines), False, f"线路检测失败: {exc}", task_id))
                return
            lines = [
                "双重检测通过",
                "",
                "步骤 1/2：/models 成功",
                f"模型数量: {len(models)}",
                "",
                "步骤 2/2：/chat/completions 成功",
                f"检测模型: {probe_model}",
                "",
                "模型列表：",
                *models,
            ]
            summary = f"获取到 {len(models)} 个模型，聊天检测成功"
            self.root.after(0, lambda: self.update_model_panel("可用", summary, "\n".join(lines), True, "线路检测通过", task_id))
        except Exception as exc:
            self.handle_model_task_error(exc, "线路检测", task_id)

    def save_profile(self) -> None:
        try:
            profile_id, profile = self.collect_form()
            was_existing = profile_id in self.profiles
            self.profiles[profile_id] = profile
            self.form_profile_id = profile_id
            self.persist_profiles()
            self.refresh(select_current=False, target_profile_id=profile_id)
            self.status_var.set("配置更新成功" if was_existing else "配置保存成功")
            messagebox.showinfo("成功", "配置已成功更新" if was_existing else "配置已成功保存")
        except Exception as exc:
            self.status_var.set(f"保存失败: {exc}")
            messagebox.showerror("保存失败", str(exc))

    def apply_profile(self, profile: dict) -> None:
        original_config = read_text(CONFIG_PATH)
        original_auth = read_text(AUTH_PATH)
        try:
            replace_provider_name(profile["name"])
            replace_base_url(profile["base_url"])
            replace_api_key(profile["api_key"])
        except Exception:
            write_text(CONFIG_PATH, original_config)
            write_text(AUTH_PATH, original_auth)
            raise

    def switch_selected(self) -> None:
        try:
            profile_id = self.get_selected_profile_id()
            if not profile_id:
                raise ValueError("请先选中一条线路")
            profile = self.profiles.get(profile_id)
            if not profile:
                raise ValueError("线路不存在")
            self.apply_profile(profile)
            self.refresh(select_current=True)
            self.status_var.set("切换成功")
            messagebox.showinfo("切换成功", "线路已切换！")
        except Exception as exc:
            self.status_var.set(f"切换失败: {exc}")
            messagebox.showerror("切换失败", str(exc))

    def delete_selected_profile(self) -> None:
        try:
            profile_id = self.get_selected_profile_id()
            if not profile_id:
                raise ValueError("请先选中一条线路")

            profile = self.profiles.get(profile_id)
            if not profile:
                raise ValueError("线路不存在")

            profile_name = profile.get("name", profile_id)
            extra_tip = ""
            if profile_id == self.active_profile_id:
                extra_tip = "\n当前正在使用这条线路，删除只会移除保存记录，不会改动当前生效配置。"

            confirmed = messagebox.askyesno(
                "确认删除",
                f"确定删除线路“{profile_name}”吗？{extra_tip}",
                parent=self.root,
            )
            if not confirmed:
                self.status_var.set("已取消删除")
                return

            self.profiles.pop(profile_id, None)
            self.persist_profiles()
            self.refresh(select_current=False)
            self.status_var.set("线路已删除")
            messagebox.showinfo("删除成功", f"已删除线路：{profile_name}", parent=self.root)
        except Exception as exc:
            self.status_var.set(f"删除失败: {exc}")
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def choose_cc_switch_profiles(self, cc_profiles: list[dict], skipped_invalid: int) -> list[dict] | None:
        existing_pairs = {profile_compare_key(profile) for profile in self.profiles.values()}
        candidates = []
        for index, profile in enumerate(cc_profiles):
            pair = profile_compare_key(profile)
            duplicate = pair in existing_pairs
            candidates.append(
                {
                    "index": index,
                    "profile": profile,
                    "duplicate": duplicate,
                    "status": "已存在" if duplicate else "可导入",
                }
            )

        result: dict[str, list[dict] | None] = {"profiles": None}
        dialog = tk.Toplevel(self.root)
        dialog.title("导入 CC Switch 线路")
        dialog.geometry("860x460")
        dialog.minsize(760, 380)
        dialog.configure(bg=DARK_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = tk.Frame(dialog, bg=DARK_BG)
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            outer,
            text=f"选择要导入的 CC Switch 线路（无效跳过 {skipped_invalid} 条）",
            bg=DARK_BG,
            fg=DARK_TEXT,
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        table_frame = tk.Frame(outer, bg=DARK_PANEL, highlightbackground=DARK_BORDER, highlightthickness=1)
        table_frame.pack(fill="both", expand=True)

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        y_scroll.pack(side="right", fill="y")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")
        x_scroll.pack(side="bottom", fill="x")

        tree = ttk.Treeview(
            table_frame,
            columns=("status", "name", "base_url", "api_key"),
            show="headings",
            selectmode="extended",
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        tree.heading("status", text="状态")
        tree.heading("name", text="名称")
        tree.heading("base_url", text="Base URL")
        tree.heading("api_key", text="API Key")
        tree.column("status", width=80, anchor="center", stretch=False)
        tree.column("name", width=210, anchor="w")
        tree.column("base_url", width=350, anchor="w")
        tree.column("api_key", width=130, anchor="w", stretch=False)
        tree.tag_configure("duplicate", foreground=DARK_DISABLED)
        tree.pack(side="left", fill="both", expand=True)
        y_scroll.config(command=tree.yview)
        x_scroll.config(command=tree.xview)

        importable_ids = []
        for candidate in candidates:
            profile = candidate["profile"]
            item_id = str(candidate["index"])
            tag = "duplicate" if candidate["duplicate"] else ""
            tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    candidate["status"],
                    profile["name"],
                    profile["base_url"],
                    mask_secret(profile["api_key"]),
                ),
                tags=(tag,) if tag else (),
            )
            if not candidate["duplicate"]:
                importable_ids.append(item_id)

        if importable_ids:
            tree.selection_set(*importable_ids)

        summary_var = tk.StringVar()

        def selected_importable_profiles() -> list[dict]:
            selected = []
            for item_id in tree.selection():
                candidate = candidates[int(item_id)]
                if not candidate["duplicate"]:
                    selected.append(candidate["profile"])
            return selected

        def update_summary(_event: object | None = None) -> None:
            summary_var.set(
                f"已选 {len(selected_importable_profiles())} 条 / 可导入 {len(importable_ids)} 条"
            )

        def select_all_importable() -> None:
            if importable_ids:
                tree.selection_set(*importable_ids)
            update_summary()

        def clear_selection() -> None:
            current_selection = tree.selection()
            if current_selection:
                tree.selection_remove(*current_selection)
            update_summary()

        def cancel() -> None:
            result["profiles"] = None
            dialog.destroy()

        def confirm() -> None:
            selected = selected_importable_profiles()
            if not selected:
                messagebox.showwarning("未选择", "请至少选择一条可导入线路", parent=dialog)
                return
            confirmed = messagebox.askyesno(
                "确认导入",
                f"确定导入选中的 {len(selected)} 条线路吗？",
                parent=dialog,
            )
            if not confirmed:
                return
            result["profiles"] = selected
            dialog.destroy()

        tree.bind("<<TreeviewSelect>>", update_summary)

        action_frame = tk.Frame(outer, bg=DARK_BG)
        action_frame.pack(fill="x", pady=(12, 0))
        tk.Label(action_frame, textvariable=summary_var, bg=DARK_BG, fg=DARK_MUTED, font=("Microsoft YaHei UI", 12)).pack(side="left")
        ttk.Button(action_frame, text="全选可导入", command=select_all_importable).pack(side="left", padx=(16, 0))
        ttk.Button(action_frame, text="清空选择", command=clear_selection).pack(side="left", padx=(8, 0))
        ttk.Button(action_frame, text="取消", command=cancel).pack(side="right")
        ttk.Button(action_frame, text="导入选中", command=confirm, style="Primary.TButton").pack(side="right", padx=(0, 8))

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        update_summary()
        dialog.wait_window()
        return result["profiles"]

    def import_cc_switch_profiles(self) -> None:
        try:
            cc_profiles, skipped_invalid = load_cc_switch_codex_profiles()
            if not cc_profiles:
                raise ValueError("CC Switch 里没有可导入的 Codex API 供应商")

            selected_profiles = self.choose_cc_switch_profiles(cc_profiles, skipped_invalid)
            if selected_profiles is None:
                self.status_var.set("已取消导入")
                return

            existing_pairs = {profile_compare_key(profile) for profile in self.profiles.values()}

            imported_count = 0
            skipped_duplicate = 0
            for profile in selected_profiles:
                pair = profile_compare_key(profile)
                if pair in existing_pairs:
                    skipped_duplicate += 1
                    continue

                profile_id = make_profile_id(profile["name"], set(self.profiles.keys()))
                self.profiles[profile_id] = profile
                existing_pairs.add(pair)
                imported_count += 1

            if imported_count == 0:
                self.status_var.set("未导入新线路")
                messagebox.showinfo(
                    "无需导入",
                    f"选中的线路没有新内容。\n重复跳过：{skipped_duplicate} 条\n无效跳过：{skipped_invalid} 条",
                    parent=self.root,
                )
                return

            self.persist_profiles()
            self.refresh(select_current=False)
            self.status_var.set(f"已从 CC Switch 导入 {imported_count} 条线路")
            messagebox.showinfo(
                "导入成功",
                f"已导入：{imported_count} 条\n重复跳过：{skipped_duplicate} 条\n无效跳过：{skipped_invalid} 条",
                parent=self.root,
            )
        except Exception as exc:
            self.status_var.set(f"导入失败: {exc}")
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def save_and_switch(self) -> None:
        try:
            profile_id, profile = self.collect_form()
            was_existing = profile_id in self.profiles
            self.profiles[profile_id] = profile
            self.form_profile_id = profile_id
            self.persist_profiles()
            self.apply_profile(profile)
            self.refresh(select_current=True)
            self.status_var.set("更新并切换成功" if was_existing else "保存并切换成功")
            messagebox.showinfo("成功", "已更新并切换至该线路！" if was_existing else "已保存并切换至新线路！")
        except Exception as exc:
            self.status_var.set(f"操作失败: {exc}")
            messagebox.showerror("操作失败", str(exc))


def main() -> None:
    assert_file_exists(CONFIG_PATH)
    assert_file_exists(AUTH_PATH)
    root = tk.Tk()
    configure_tk_display(root)
    from codex_switcher_v2_app import App as SwitcherApp

    SwitcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        messagebox.showerror("系统启动失败", str(exc))
