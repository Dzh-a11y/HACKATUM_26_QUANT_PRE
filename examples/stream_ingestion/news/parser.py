"""新闻头部解析和字段映射。"""

from datetime import datetime
import re


def extract_symbols(header_lines, *, params):
    values = []
    for line in header_lines:
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == params.symbols_field.lower():
            values.append(value.strip())
    if not values:
        return [], "missing", []
    if len(values) != 1:
        return [], "malformed", []
    if not values[0]:
        return [], "empty", []
    candidates = [part.strip() for part in values[0].split(",")]
    if any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", code) is None for code in candidates):
        return [], "malformed", []
    candidates = list(dict.fromkeys(candidates))
    known = [code for code in candidates if code in params.known_symbols]
    unknown = [code for code in candidates if code not in params.known_symbols]
    return known, "unknown_symbols" if unknown else "ok", unknown


def parse_record(raw, *, tick, received_at, ingested_at, params):
    """在这里适配官方新闻头部。正文中的 Symbols 不参与代码提取。"""
    lines = raw.splitlines(keepends=True)
    headers, header_lines, body = {}, [], ""
    for index, line in enumerate(lines):
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "body":
            body = value.lstrip(" \t") + "".join(lines[index + 1:])
            break
        header_lines.append(line)
        if separator:
            headers[key.strip().lower()] = value.strip()
    published_at = datetime.fromisoformat(headers["published-at"].replace("Z", "+00:00"))
    if published_at.tzinfo is None:
        raise ValueError("新闻发布时间必须带时区")
    symbols, status, unknown = extract_symbols(header_lines, params=params)
    return {
        "news_id": headers["news-id"], "tick": tick, "source": params.source,
        "published_at": published_at.isoformat(), "received_at": received_at.isoformat(),
        "ingested_at": ingested_at.isoformat(), "title": headers["title"], "body": body,
        "symbols": symbols, "symbol_status": status, "unrecognized_symbols": unknown,
        "symbol_method": "symbols_header_v1", "raw_text": raw,
    }
