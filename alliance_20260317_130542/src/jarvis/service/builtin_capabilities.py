"""Deterministic built-in capabilities for the menu bar service."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import html
import json
import math
import operator
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TIME_QUERY_RE = re.compile(
    r"(몇\s*시|지금\s*시간|현재\s*(?:시간|시각)|오늘\s*날짜|오늘\s*며칠|날짜\s*알려|시간\s*(?:알려|보여|확인|이야)|시각\s*(?:알려|보여|확인)|what\s+time|current\s+time|today'?s\s+date)",
    re.IGNORECASE,
)
_WEATHER_QUERY_RE = re.compile(
    r"(날씨|기온|비\s*오|눈\s*오|forecast|weather|temperature)",
    re.IGNORECASE,
)
_WEB_QUERY_RE = re.compile(
    r"(웹사이트|홈페이지|사이트|웹에서|웹\s*검색|사이트\s*찾|검색해|찾아줘|homepage|website|web\s+search|search)",
    re.IGNORECASE,
)
_CALC_HINT_RE = re.compile(
    r"(계산|더하기|빼기|곱하기|나누기|퍼센트|percent|calculate|what is|얼마)",
    re.IGNORECASE,
)
_DIRECT_URL_RE = re.compile(
    r"(?P<url>https?://[^\s]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_TIMEZONE_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("america/los_angeles", "America/Los_Angeles", "Los Angeles"),
    ("los angeles", "America/Los_Angeles", "Los Angeles"),
    ("la", "America/Los_Angeles", "Los Angeles"),
    ("미국 서부", "America/Los_Angeles", "미국 서부"),
    ("퍼시픽", "America/Los_Angeles", "Pacific"),
    ("america/new_york", "America/New_York", "New York"),
    ("new york", "America/New_York", "New York"),
    ("nyc", "America/New_York", "New York"),
    ("뉴욕", "America/New_York", "뉴욕"),
    ("미국 동부", "America/New_York", "미국 동부"),
    ("eastern", "America/New_York", "Eastern"),
    ("europe/london", "Europe/London", "London"),
    ("london", "Europe/London", "London"),
    ("런던", "Europe/London", "런던"),
    ("asia/seoul", "Asia/Seoul", "Seoul"),
    ("seoul", "Asia/Seoul", "Seoul"),
    ("서울", "Asia/Seoul", "서울"),
    ("한국", "Asia/Seoul", "한국"),
    ("asia/tokyo", "Asia/Tokyo", "Tokyo"),
    ("tokyo", "Asia/Tokyo", "Tokyo"),
    ("도쿄", "Asia/Tokyo", "도쿄"),
    ("japan", "Asia/Tokyo", "Japan"),
    ("utc", "UTC", "UTC"),
    ("gmt", "UTC", "UTC"),
)
_REFERENCE_CLOCKS: tuple[tuple[str, str], ...] = (
    ("Asia/Seoul", "서울"),
    ("UTC", "UTC"),
    ("America/New_York", "뉴욕"),
    ("Europe/London", "런던"),
    ("Asia/Tokyo", "도쿄"),
)
_DAY_NAMES = ("월", "화", "수", "목", "금", "토", "일")
_ALLOWED_BINARY_OPERATORS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPERATORS: dict[type[ast.AST], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def resolve_builtin_capability(query: str) -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None

    direct_url = _extract_direct_url(normalized)
    if direct_url is not None:
        return _build_direct_website_response(normalized, direct_url)

    if _TIME_QUERY_RE.search(normalized):
        return _build_time_response(normalized)

    if _WEATHER_QUERY_RE.search(normalized):
        return _build_weather_response(normalized)

    calculation = _build_calculation_response(normalized)
    if calculation is not None:
        return calculation

    if _WEB_QUERY_RE.search(normalized):
        return _build_web_search_response(normalized)

    return None


def _build_time_response(query: str) -> dict[str, object]:
    requested = _extract_requested_timezones(query)
    if requested:
        clocks = requested
    else:
        clocks = list(_REFERENCE_CLOCKS[:4])

    artifacts: list[dict[str, object]] = []
    selected_id = ""
    first_clock_text = ""
    for index, (zone_name, label) in enumerate(clocks, start=1):
        current = _now_in_zone(zone_name)
        formatted = _format_datetime(current, include_zone=True)
        if index == 1:
            first_clock_text = f"{label} 기준 현재 시간은 {formatted}입니다."
            selected_id = f"time_{index}"
        artifacts.append(
            _artifact(
                artifact_id=f"time_{index}",
                type_name="text",
                title=label,
                subtitle=zone_name,
                path=zone_name,
                preview="\n".join(
                    [
                        formatted,
                        f"24시간 표기: {current.strftime('%H:%M:%S')}",
                        f"날짜: {current.year}-{current.month:02d}-{current.day:02d}",
                    ]
                ),
            )
        )

    response_text = first_clock_text or "현재 시간을 확인했습니다."
    if len(artifacts) > 1:
        response_text += f" 함께 볼 수 있는 기준 시각 {len(artifacts)}개를 정리했습니다."

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="time_lookup",
        skill="builtin_time",
        source_profile="time",
        artifacts=artifacts,
        presentation=_presentation(
            layout="master_detail" if len(artifacts) > 1 else "stack",
            title="Time Workspace",
            subtitle=f"기준 시각 {len(artifacts)}개",
            selected_artifact_id=selected_id,
            blocks=_blocks_for_answer_list_detail(
                answer_title="현재 시각",
                list_title="시간대 목록",
                detail_title="시각 상세",
                artifact_ids=[artifact["id"] for artifact in artifacts],
                include_list=len(artifacts) > 1,
            ),
        ),
    )


def _build_weather_response(query: str) -> dict[str, object]:
    location = _extract_weather_location(query)
    weather_data, source_url = _fetch_weather(location)
    current_condition = ((weather_data.get("current_condition") or [{}])[0]) if isinstance(weather_data, dict) else {}
    nearest_area = ((weather_data.get("nearest_area") or [{}])[0]) if isinstance(weather_data, dict) else {}
    area_names = nearest_area.get("areaName") or []
    area_label = ""
    if area_names and isinstance(area_names[0], dict):
        area_label = str(area_names[0].get("value", "")).strip()
    if not area_label:
        area_label = location or "현재 위치"

    temp_c = str(current_condition.get("temp_C", "")).strip()
    feels_like = str(current_condition.get("FeelsLikeC", "")).strip()
    humidity = str(current_condition.get("humidity", "")).strip()
    wind_speed = str(current_condition.get("windspeedKmph", "")).strip()
    description = _weather_text(current_condition.get("weatherDesc"))

    artifacts: list[dict[str, object]] = [
        _artifact(
            artifact_id="weather_current",
            type_name="text",
            title=f"{area_label} 현재 날씨",
            subtitle="실시간 상태",
            path=source_url,
            preview="\n".join(
                filter(
                    None,
                    [
                        f"상태: {description}" if description else "",
                        f"기온: {temp_c}°C" if temp_c else "",
                        f"체감: {feels_like}°C" if feels_like else "",
                        f"습도: {humidity}%" if humidity else "",
                        f"풍속: {wind_speed} km/h" if wind_speed else "",
                    ],
                )
            ),
            source_type="weather",
        )
    ]

    weather_days = weather_data.get("weather") if isinstance(weather_data, dict) else []
    for index, item in enumerate(weather_days[:3], start=1):
        if not isinstance(item, dict):
            continue
        daily_label = _forecast_day_label(item.get("date", ""), index=index)
        artifacts.append(
            _artifact(
                artifact_id=f"weather_day_{index}",
                type_name="text",
                title=daily_label,
                subtitle="예보",
                path=source_url,
                preview="\n".join(
                    filter(
                        None,
                        [
                            f"상태: {_weather_text(((item.get('hourly') or [{}])[4]).get('weatherDesc'))}",
                            f"최고: {item.get('maxtempC', '')}°C" if item.get("maxtempC") else "",
                            f"최저: {item.get('mintempC', '')}°C" if item.get("mintempC") else "",
                            f"일평균: {item.get('avgtempC', '')}°C" if item.get("avgtempC") else "",
                            f"강수 확률: {item.get('daily_chance_of_rain', '')}%" if item.get("daily_chance_of_rain") else "",
                        ],
                    )
                ),
                source_type="weather",
            )
        )

    response_parts = [f"{area_label} 현재 날씨는 {description or '확인됨'}"]
    if temp_c:
        response_parts.append(f"기온은 {temp_c}도")
    if feels_like:
        response_parts.append(f"체감은 {feels_like}도")
    response_text = ", ".join(response_parts) + "입니다."
    if len(artifacts) > 1:
        response_text += " 오늘과 이후 예보도 함께 정리했습니다."

    citations = [
        {
            "label": "[날씨]",
            "source_path": source_url,
            "full_source_path": source_url,
            "source_type": "web",
            "quote": "Weather data from wttr.in",
            "state": "valid",
            "relevance_score": 1.0,
            "heading_path": area_label,
        }
    ]

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="weather_lookup",
        skill="builtin_weather",
        source_profile="weather",
        primary_source_type="web",
        citations=citations,
        artifacts=artifacts,
        presentation=_presentation(
            layout="master_detail",
            title="Weather Workspace",
            subtitle=f"{area_label} · 예보 {max(0, len(artifacts) - 1)}개",
            selected_artifact_id="weather_current",
            blocks=_blocks_for_answer_list_detail(
                answer_title="날씨 요약",
                list_title="날씨 카드",
                detail_title="날씨 상세",
                artifact_ids=[artifact["id"] for artifact in artifacts],
                include_evidence=True,
            ),
        ),
    )


def _build_web_search_response(query: str) -> dict[str, object]:
    search_term = _extract_search_term(query)
    if not search_term:
        search_term = query
    results = _search_web(search_term)
    if not results:
        response_text = f"\"{search_term}\"에 대한 웹 검색 결과를 찾지 못했습니다."
        return _response_payload(
            query=query,
            response_text=response_text,
            spoken_text=response_text,
            intent="web_search",
            skill="builtin_web_search",
            source_profile="web_search",
            primary_source_type="web",
            artifacts=[],
            presentation=_presentation(
                layout="stack",
                title="Web Workspace",
                subtitle="검색 결과 없음",
                selected_artifact_id="",
                blocks=[
                    _block(
                        block_id="answer",
                        kind="answer",
                        title="검색 결과",
                        subtitle="웹 검색 응답",
                    )
                ],
            ),
        )

    artifacts = [
        _artifact(
            artifact_id=f"web_{index}",
            type_name="web",
            title=result["title"],
            subtitle=result["domain"],
            path=result["url"],
            full_path=result["url"],
            preview=result["snippet"],
            source_type="web",
        )
        for index, result in enumerate(results[:6], start=1)
    ]
    top = results[0]
    response_text = (
        f"\"{search_term}\"에 대한 웹 결과 {len(artifacts)}개를 찾았습니다. "
        f"가장 관련성이 높은 결과는 {top['title']}입니다."
    )

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="web_search",
        skill="builtin_web_search",
        source_profile="web_search",
        primary_source_type="web",
        artifacts=artifacts,
        presentation=_presentation(
            layout="master_detail",
            title="Web Workspace",
            subtitle=f"검색 결과 {len(artifacts)}개",
            selected_artifact_id=artifacts[0]["id"],
            blocks=_blocks_for_answer_list_detail(
                answer_title="검색 요약",
                list_title="웹 결과",
                detail_title="웹 미리보기",
                artifact_ids=[artifact["id"] for artifact in artifacts],
            ),
        ),
    )


def _build_direct_website_response(query: str, direct_url: str) -> dict[str, object]:
    parsed = urlparse(direct_url)
    domain = parsed.netloc or parsed.path
    artifact = _artifact(
        artifact_id="web_direct",
        type_name="web",
        title=domain,
        subtitle="직접 지정한 웹사이트",
        path=direct_url,
        full_path=direct_url,
        preview=direct_url,
        source_type="web",
    )
    response_text = f"{domain} 사이트를 바로 열 수 있습니다."
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="open_website",
        skill="builtin_web_link",
        source_profile="web",
        primary_source_type="web",
        artifacts=[artifact],
        presentation=_presentation(
            layout="stack",
            title="Web Workspace",
            subtitle=domain,
            selected_artifact_id="web_direct",
            blocks=[
                _block(
                    block_id="answer",
                    kind="answer",
                    title="링크 열기",
                    subtitle="직접 지정한 사이트",
                ),
                _block(
                    block_id="detail",
                    kind="detail",
                    title="웹 미리보기",
                    subtitle="선택한 사이트",
                    artifact_ids=["web_direct"],
                    empty_state="열 수 있는 링크가 없습니다.",
                ),
            ],
        ),
    )


def _build_calculation_response(query: str) -> dict[str, object] | None:
    expression = _extract_math_expression(query)
    if not expression:
        return None
    try:
        result = _safe_eval(expression)
    except Exception:
        return None
    if not math.isfinite(result):
        return None

    result_text = _format_number(result)
    response_text = f"{expression}의 결과는 {result_text}입니다."
    artifact = _artifact(
        artifact_id="calc_result",
        type_name="text",
        title="계산 결과",
        subtitle="로컬 계산",
        preview=f"식: {expression}\n결과: {result_text}",
    )
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="calculation",
        skill="builtin_calculator",
        source_profile="calculator",
        artifacts=[artifact],
        presentation=_presentation(
            layout="stack",
            title="Calculation Workspace",
            subtitle="로컬 계산 결과",
            selected_artifact_id="calc_result",
            blocks=[
                _block(
                    block_id="answer",
                    kind="answer",
                    title="계산 결과",
                    subtitle="즉시 계산",
                ),
                _block(
                    block_id="detail",
                    kind="detail",
                    title="계산 상세",
                    subtitle="식과 결과",
                    artifact_ids=["calc_result"],
                    empty_state="계산 결과가 없습니다.",
                ),
            ],
        ),
    )


def _response_payload(
    *,
    query: str,
    response_text: str,
    spoken_text: str,
    intent: str,
    skill: str,
    source_profile: str,
    artifacts: list[dict[str, object]],
    presentation: dict[str, object],
    primary_source_type: str = "none",
    citations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "query": query,
        "response": response_text,
        "spoken_response": spoken_text,
        "has_evidence": bool(citations),
        "citations": citations or [],
        "status": {
            "mode": "builtin_capability",
            "safe_mode": False,
            "degraded_mode": False,
            "generation_blocked": False,
            "write_blocked": False,
            "rebuild_index_required": False,
        },
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": primary_source_type,
            "source_profile": source_profile,
            "interaction_mode": "general_query",
            "citation_count": len(citations or []),
            "truncated": False,
        },
        "exploration": {
            "mode": "general_query",
            "target_file": "",
            "target_document": "",
            "file_candidates": [],
            "document_candidates": [],
            "class_candidates": [],
            "function_candidates": [],
        },
        "guide_directive": {
            "intent": intent,
            "skill": skill,
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": [],
            "should_hold": False,
        },
        "builtin_artifacts": artifacts,
        "builtin_presentation": presentation,
    }


def _blocks_for_answer_list_detail(
    *,
    answer_title: str,
    list_title: str,
    detail_title: str,
    artifact_ids: list[str],
    include_list: bool = True,
    include_evidence: bool = False,
) -> list[dict[str, object]]:
    blocks = [
        _block(
            block_id="answer",
            kind="answer",
            title=answer_title,
            subtitle="현재 요청에 대한 요약",
        )
    ]
    if include_list:
        blocks.append(
            _block(
                block_id="list",
                kind="list",
                title=list_title,
                subtitle="항목을 선택하면 상세가 바뀝니다",
                artifact_ids=artifact_ids,
                empty_state="표시할 항목이 없습니다.",
            )
        )
    blocks.append(
        _block(
            block_id="detail",
            kind="detail",
            title=detail_title,
            subtitle="선택한 항목의 상세 정보",
            artifact_ids=artifact_ids[:1],
            empty_state="표시할 상세 정보가 없습니다.",
        )
    )
    if include_evidence:
        blocks.append(
            _block(
                block_id="evidence",
                kind="evidence",
                title="출처",
                subtitle="데이터 제공 출처",
            )
        )
    return blocks


def _presentation(
    *,
    layout: str,
    title: str,
    subtitle: str,
    selected_artifact_id: str,
    blocks: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "layout": layout,
        "title": title,
        "subtitle": subtitle,
        "selected_artifact_id": selected_artifact_id,
        "blocks": blocks,
    }


def _block(
    *,
    block_id: str,
    kind: str,
    title: str,
    subtitle: str,
    artifact_ids: list[str] | None = None,
    citation_labels: list[str] | None = None,
    empty_state: str = "",
) -> dict[str, object]:
    return {
        "id": block_id,
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "artifact_ids": artifact_ids or [],
        "citation_labels": citation_labels or [],
        "empty_state": empty_state,
    }


def _artifact(
    *,
    artifact_id: str,
    type_name: str,
    title: str,
    subtitle: str = "",
    path: str = "",
    full_path: str = "",
    preview: str = "",
    source_type: str = "builtin",
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "type": type_name,
        "title": title,
        "subtitle": subtitle,
        "path": path,
        "full_path": full_path,
        "preview": preview,
        "source_type": source_type,
        "viewer_kind": _viewer_kind(type_name),
    }


def _viewer_kind(type_name: str) -> str:
    normalized = type_name.strip().lower()
    if normalized in {"web", "html", "image", "video", "document", "code"}:
        return normalized
    return "text"


def _extract_requested_timezones(query: str) -> list[tuple[str, str]]:
    lowered = query.lower()
    seen: set[str] = set()
    zones: list[tuple[str, str]] = []
    for alias, zone_name, label in _TIMEZONE_ALIASES:
        if alias in lowered and zone_name not in seen:
            seen.add(zone_name)
            zones.append((zone_name, label))
    return zones


def _extract_weather_location(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    for pattern in (
        re.compile(r"(?P<location>.+?)\s*(?:의\s*)?(?:오늘\s*)?(?:내일\s*)?(?:현재\s*)?(?:날씨|기온|forecast|weather)", re.IGNORECASE),
        re.compile(r"(?:날씨|weather)\s*(?:를|를 좀|좀|좀요)?\s*(?:알려줘|보여줘|search|for|in)?\s*(?P<location>.+)$", re.IGNORECASE),
    ):
        match = pattern.search(normalized)
        if not match:
            continue
        candidate = match.group("location")
        cleaned = re.sub(
            r"\b(오늘|내일|현재|날씨|기온|forecast|weather|알려줘|보여줘|검색해줘|좀|좀요)\b",
            " ",
            candidate,
            flags=re.IGNORECASE,
        )
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" ,")
        if cleaned:
            return cleaned
    return ""


def _extract_search_term(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    direct_url = _extract_direct_url(normalized)
    if direct_url:
        return direct_url
    cleaned = re.sub(
        r"\b(웹사이트|홈페이지|사이트|웹에서|웹\s*검색|사이트\s*찾아줘|사이트\s*찾기|검색해줘|검색|찾아줘|search|website|homepage|web\s+search|open)\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(열어줘|보여줘|찾아|찾기|알려줘)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" ?")
    return cleaned


def _extract_direct_url(query: str) -> str | None:
    match = _DIRECT_URL_RE.search(query)
    if not match:
        return None
    candidate = match.group("url").rstrip(".,)")
    if " " in candidate:
        return None
    if candidate.lower().startswith(("http://", "https://")):
        return candidate
    if "." not in candidate:
        return None
    return f"https://{candidate}"


def _extract_math_expression(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return ""

    percent_match = re.search(
        r"(?P<base>-?\d+(?:\.\d+)?)\s*(?:의|of)\s*(?P<pct>-?\d+(?:\.\d+)?)\s*%",
        normalized,
        re.IGNORECASE,
    )
    if percent_match:
        base = percent_match.group("base")
        pct = percent_match.group("pct")
        return f"({base} * {pct} / 100)"

    transformed = normalized.lower()
    replacements = (
        ("더하기", "+"),
        ("플러스", "+"),
        ("빼기", "-"),
        ("마이너스", "-"),
        ("곱하기", "*"),
        ("x", "*"),
        ("나누기", "/"),
        ("나눠", "/"),
        ("퍼센트", "%"),
        ("percent", "%"),
        ("calculate", ""),
        ("what is", ""),
        ("계산", ""),
        ("얼마", ""),
        ("는", ""),
        ("은", ""),
        ("?", ""),
    )
    for old, new in replacements:
        transformed = transformed.replace(old, new)
    transformed = transformed.replace(" ", "")

    if transformed.count("%") == 1:
        percent_number = transformed.rstrip("%")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", percent_number):
            return f"({percent_number} / 100)"

    if re.fullmatch(r"[\d\.\+\-\*\/\(\)%]+", transformed) and any(char.isdigit() for char in transformed):
        return transformed

    if _CALC_HINT_RE.search(normalized):
        candidate = re.sub(r"[^0-9\.\+\-\*\/\(\)%]", "", transformed)
        if candidate and any(char.isdigit() for char in candidate):
            return candidate
    return ""


def _safe_eval(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return float(_eval_node(tree.body))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Num):  # pragma: no cover
        return float(node.n)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 8:
            raise ValueError("power too large")
        return float(_ALLOWED_BINARY_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
        return float(_ALLOWED_UNARY_OPERATORS[type(node.op)](_eval_node(node.operand)))
    raise ValueError("unsupported expression")


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def _fetch_weather(location: str) -> tuple[dict[str, object], str]:
    location_path = quote(location) if location else ""
    source_url = f"https://wttr.in/{location_path}?format=j1&lang=ko"
    try:
        data = _fetch_json(source_url)
    except Exception as exc:
        fallback_text = (
            f"{location or '현재 위치'} 날씨 데이터를 가져오지 못했습니다. "
            f"네트워크 상태를 확인한 뒤 다시 시도해 주세요."
        )
        return (
            {
                "current_condition": [
                    {
                        "weatherDesc": [{"value": fallback_text}],
                    }
                ],
                "nearest_area": [{"areaName": [{"value": location or "현재 위치"}]}],
                "weather": [],
            },
            source_url,
        )
    if not isinstance(data, dict):
        raise ValueError("weather response must be a dict")
    return data, source_url


def _search_web(query: str) -> list[dict[str, str]]:
    results = _search_web_json(query)
    if len(results) >= 3:
        return results[:6]
    html_results = _search_web_html(query)
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for result in results + html_results:
        url = result.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(result)
        if len(merged) >= 6:
            break
    return merged


def _search_web_json(query: str) -> list[dict[str, str]]:
    url = (
        "https://api.duckduckgo.com/"
        f"?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    )
    try:
        payload = _fetch_json(url)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []

    results: list[dict[str, str]] = []
    for raw_item in payload.get("Results", []):
        parsed = _instant_answer_item(raw_item)
        if parsed is not None:
            results.append(parsed)
    for raw_item in payload.get("RelatedTopics", []):
        parsed = _instant_answer_item(raw_item)
        if parsed is not None:
            results.append(parsed)
        elif isinstance(raw_item, dict):
            for nested in raw_item.get("Topics", []):
                parsed = _instant_answer_item(nested)
                if parsed is not None:
                    results.append(parsed)
    return results


def _instant_answer_item(raw_item: object) -> dict[str, str] | None:
    if not isinstance(raw_item, dict):
        return None
    url = str(raw_item.get("FirstURL", "")).strip()
    text = str(raw_item.get("Text", "")).strip()
    if not url or not text:
        return None
    title, _, snippet = text.partition(" - ")
    return {
        "title": title.strip() or text,
        "url": url,
        "domain": urlparse(url).netloc,
        "snippet": snippet.strip() or text,
    }


def _search_web_html(query: str) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        html_text = _fetch_text(url)
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for match in re.finditer(
        r'<a[^>]+class="(?:result__a|result-link)"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        href = _unwrap_duckduckgo_url(match.group("href"))
        if not href:
            continue
        title = _clean_html_text(match.group("title"))
        tail = html_text[match.end():match.end() + 600]
        snippet_match = re.search(
            r'<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>|<div[^>]+class="(?:result__snippet|result-snippet)"[^>]*>(?P<divsnippet>.*?)</div>',
            tail,
            re.IGNORECASE | re.DOTALL,
        )
        snippet = ""
        if snippet_match is not None:
            snippet = _clean_html_text(snippet_match.group("snippet") or snippet_match.group("divsnippet") or "")
        results.append(
            {
                "title": title or href,
                "url": href,
                "domain": urlparse(href).netloc,
                "snippet": snippet,
            }
        )
        if len(results) >= 6:
            break
    return results


def _unwrap_duckduckgo_url(raw_url: str) -> str:
    candidate = html.unescape(raw_url).strip()
    if not candidate:
        return ""
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    if candidate.startswith("/l/?") or "duckduckgo.com/l/?" in candidate:
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
    return candidate


def _clean_html_text(text: str) -> str:
    without_tags = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", html.unescape(without_tags)).strip()


def _fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "JarvisMenuBar/1.0"})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "JarvisMenuBar/1.0"})
    with urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", errors="replace")


def _weather_text(raw_value: object) -> str:
    if isinstance(raw_value, list) and raw_value:
        first = raw_value[0]
        if isinstance(first, dict):
            return str(first.get("value", "")).strip()
    if isinstance(raw_value, dict):
        return str(raw_value.get("value", "")).strip()
    return str(raw_value or "").strip()


def _forecast_day_label(raw_date: object, *, index: int) -> str:
    text = str(raw_date or "").strip()
    if not text:
        return f"예보 {index}"
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return text
    if index == 1:
        return "오늘"
    if index == 2:
        return "내일"
    return f"{parsed.month}월 {parsed.day}일"


def _now_in_zone(zone_name: str) -> datetime:
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.now(timezone.utc).astimezone(zone)


def _format_datetime(value: datetime, *, include_zone: bool) -> str:
    day_name = _DAY_NAMES[value.weekday()]
    prefix = "오전" if value.hour < 12 else "오후"
    hour = value.hour % 12
    if hour == 0:
        hour = 12
    base = (
        f"{value.year}년 {value.month}월 {value.day}일 "
        f"{day_name}요일 {prefix} {hour}:{value.minute:02d}"
    )
    if include_zone:
        abbreviation = value.tzname() or ""
        return f"{base} {abbreviation}".strip()
    return base
