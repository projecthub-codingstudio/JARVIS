"""Deterministic built-in capabilities for the menu bar service."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import html
import json
import math
import operator
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jarvis.service.intent_skill_registry import IntentSkillEntry, load_intent_skill_registry

_TIME_QUERY_RE = re.compile(
    r"(몇\s*시|지금\s*시간|현재\s*(?:시간|시각)|오늘\s*날짜|오늘\s*며칠|날짜\s*알려|시간\s*(?:알려|보여|확인|이야)|시각\s*(?:알려|보여|확인)|what\s+time|current\s+time|today'?s\s+date)",
    re.IGNORECASE,
)
_DATE_QUERY_HINT_RE = re.compile(
    r"(며칠|몇일|날짜|요일|언제|what\s+date|which\s+date|day\s+of\s+week)",
    re.IGNORECASE,
)
_WEATHER_QUERY_RE = re.compile(
    r"(날씨|기온|비\s*오|눈\s*오|forecast|weather|temperature)",
    re.IGNORECASE,
)
_WEB_QUERY_RE = re.compile(
    r"(웹사이트|홈페이지|사이트|웹에서|웹\s*검색|사이트\s*찾|검색해\s*줘|homepage|website|web\s+search|search\s+the\s+web)",
    re.IGNORECASE,
)
_DOC_FIND_RE = re.compile(
    r"(문서.*찾|파일.*찾|책.*찾|자료.*찾|문서.*검색|파일.*검색|책.*검색|자료.*검색"
    r"|관련\s*문서|관련\s*책|관련\s*자료|문서.*목록|문서.*리스트|문서.*있"
    r"|찾아\s*줘|find\s+doc|list\s+doc|search\s+doc|find\s+file|find\s+book)",
    re.IGNORECASE,
)
_CALC_HINT_RE = re.compile(
    r"(계산|더하기|빼기|곱하기|나누기|퍼센트|percent|calculate|what is|얼마)",
    re.IGNORECASE,
)
_HELP_QUERY_RE = re.compile(
    r"(무엇을\s*할\s*수\s*있어|뭘\s*할\s*수\s*있어|어떤\s*기능|가능한\s*기능|예시\s*질문|도움말|help)",
    re.IGNORECASE,
)
_RUNTIME_STATUS_QUERY_RE = re.compile(
    r"(백엔드\s*상태|런타임\s*상태|시스템\s*상태|인덱스\s*상태|현재\s*모델|health|runtime\s*state)",
    re.IGNORECASE,
)
_CALENDAR_QUERY_RE = re.compile(
    r"(일정|캘린더|calendar|schedule|meeting|event|예약|회의)",
    re.IGNORECASE,
)
_CALENDAR_CREATE_QUERY_RE = re.compile(
    r"((?:일정|캘린더|calendar|schedule|meeting|event|예약|회의)(?:에)?\s*(?:잡아줘|잡아|잡기|잡|생성해줘|생성|만들어줘|만들|추가해줘|추가|등록해줘|등록)|(?:create|add|schedule|book)\s+(?:a\s+)?(?:meeting|event|calendar))",
    re.IGNORECASE,
)
_CALENDAR_UPDATE_QUERY_RE = re.compile(
    r"((?:일정|캘린더|calendar|schedule|meeting|event|예약|회의)?\s*(?:수정해줘|수정|변경해줘|변경|옮겨줘|옮겨|미뤄줘|미뤄|연기해줘|update|move|reschedule))",
    re.IGNORECASE,
)
_CALENDAR_VIEW_QUERY_RE = re.compile(
    r"((?:오늘|내일|모레|글피|이번\s*주|다음\s*주|이번\s*달|다음\s*달|이번달|다음달)\s*일정|일정\s*(?:보여|알려|확인|브리핑)|캘린더\s*(?:보여|알려|확인)|agenda|brief)",
    re.IGNORECASE,
)
_CALENDAR_DATE_MENTION_RE = re.compile(
    r"(\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}-\d{1,2}-\d{1,2}|오늘|내일|모레|글피|어제|엊그제|그제|하루\s*(?:후|뒤|전)|이틀\s*(?:후|뒤|전)|사흘\s*(?:후|뒤|전)|\d+\s*일\s*(?:후|뒤|전))",
    re.IGNORECASE,
)
_DOC_SUMMARY_QUERY_RE = re.compile(
    r"(요약|정리|개요|핵심\s*(?:만|포인트)?)",
    re.IGNORECASE,
)
_DOC_EXPLAIN_QUERY_RE = re.compile(
    r"(설명|소개|종합|개괄|기술\s*사양|사양|스펙|spec(?:ification)?|overall|overview)",
    re.IGNORECASE,
)
_DOC_OUTLINE_QUERY_RE = re.compile(
    r"(목차|아웃라인|outline|슬라이드\s*제목|헤딩|heading|챕터|구성)",
    re.IGNORECASE,
)
_DOC_STRUCTURE_QUERY_RE = re.compile(
    r"(전체\s*(?:코드\s*)?구조|코드\s*구조|기본\s*구조|아키텍처|architecture|structure|구조)",
    re.IGNORECASE,
)
_DOC_SHEET_LIST_QUERY_RE = re.compile(
    r"((?:sheet|시트|탭)\s*(?:목록|리스트|list|들)|(?:목록|리스트|list)\s*(?:sheet|시트|탭))",
    re.IGNORECASE,
)
_DOC_SHEET_QUERY_RE = re.compile(
    r"((?:sheet|시트|탭)\s*(?:\d+|[A-Za-z0-9가-힣._-]+)|(?:\d+|[A-Za-z0-9가-힣._-]+)\s*(?:번째\s*)?(?:sheet|시트|탭))",
    re.IGNORECASE,
)
_DOC_SECTION_QUERY_RE = re.compile(
    r"((?:슬라이드|slide|페이지|page)\s*\d+|\d+\s*(?:번째\s*)?(?:슬라이드|slide|페이지|page)|(?:다음|next|이전|previous|prev)\s*(?:슬라이드|slide|페이지|page)|(?:슬라이드|slide|페이지|page)\s*(?:다음|next|이전|previous|prev))",
    re.IGNORECASE,
)
_RECENT_CONTEXT_QUERY_RE = re.compile(
    r"(방금\s*(?:본|봤던)|최근\s*(?:문서|자료|근거)|마지막\s*(?:문서|자료|근거)|다시\s*(?:열어|보여)|previous\s+(?:document|evidence)|last\s+(?:document|evidence)|recent\s+(?:document|evidence))",
    re.IGNORECASE,
)
_DOCUMENT_OPEN_QUERY_RE = re.compile(
    r"(열어\s*줘|열어줘|열기|열어|보여\s*줘|보여줘|띄워\s*줘|띄워줘|open|show)",
    re.IGNORECASE,
)
_DIRECT_URL_RE = re.compile(
    r"(?P<url>https?://[^\s]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_FILE_LIKE_TOKEN_RE = re.compile(
    r"^[\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx)$",
    re.IGNORECASE,
)

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
_RELATIVE_DAY_LABELS: tuple[tuple[str, int], ...] = (
    ("엊저께", -2),
    ("엊그제", -2),
    ("그제", -2),
    ("어제", -1),
    ("오늘", 0),
    ("내일", 1),
    ("모레", 2),
    ("글피", 3),
)
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
_UNIT_CONVERSION_FACTORS: dict[str, tuple[str, float, str]] = {
    "b": ("storage", 1.0, "B"),
    "byte": ("storage", 1.0, "B"),
    "bytes": ("storage", 1.0, "B"),
    "바이트": ("storage", 1.0, "B"),
    "kb": ("storage", 1_000.0, "KB"),
    "kilobyte": ("storage", 1_000.0, "KB"),
    "킬로바이트": ("storage", 1_000.0, "KB"),
    "mb": ("storage", 1_000_000.0, "MB"),
    "megabyte": ("storage", 1_000_000.0, "MB"),
    "메가바이트": ("storage", 1_000_000.0, "MB"),
    "gb": ("storage", 1_000_000_000.0, "GB"),
    "gigabyte": ("storage", 1_000_000_000.0, "GB"),
    "기가바이트": ("storage", 1_000_000_000.0, "GB"),
    "tb": ("storage", 1_000_000_000_000.0, "TB"),
    "terabyte": ("storage", 1_000_000_000_000.0, "TB"),
    "테라바이트": ("storage", 1_000_000_000_000.0, "TB"),
    "mm": ("length", 0.001, "mm"),
    "밀리미터": ("length", 0.001, "mm"),
    "cm": ("length", 0.01, "cm"),
    "센티미터": ("length", 0.01, "cm"),
    "m": ("length", 1.0, "m"),
    "meter": ("length", 1.0, "m"),
    "metre": ("length", 1.0, "m"),
    "미터": ("length", 1.0, "m"),
    "km": ("length", 1_000.0, "km"),
    "kilometer": ("length", 1_000.0, "km"),
    "kilometre": ("length", 1_000.0, "km"),
    "킬로미터": ("length", 1_000.0, "km"),
    "mg": ("mass", 0.001, "mg"),
    "밀리그램": ("mass", 0.001, "mg"),
    "g": ("mass", 1.0, "g"),
    "gram": ("mass", 1.0, "g"),
    "그램": ("mass", 1.0, "g"),
    "kg": ("mass", 1_000.0, "kg"),
    "kilogram": ("mass", 1_000.0, "kg"),
    "킬로그램": ("mass", 1_000.0, "kg"),
    "초": ("time", 1.0, "초"),
    "sec": ("time", 1.0, "초"),
    "second": ("time", 1.0, "초"),
    "s": ("time", 1.0, "초"),
    "분": ("time", 60.0, "분"),
    "minute": ("time", 60.0, "분"),
    "min": ("time", 60.0, "분"),
    "시간": ("time", 3_600.0, "시간"),
    "hour": ("time", 3_600.0, "시간"),
    "hr": ("time", 3_600.0, "시간"),
    "h": ("time", 3_600.0, "시간"),
    "일": ("time", 86_400.0, "일"),
    "day": ("time", 86_400.0, "일"),
}
_HELP_CATEGORY_TITLES: dict[str, str] = {
    "basic_task": "기본 작업",
    "system_help": "시스템 안내",
    "web_task": "웹 작업",
    "document_task": "문서/코드",
    "live_task": "실시간 기능",
    "automation_task": "자동화",
}
_IMPLEMENTATION_SUFFIXES: dict[str, str] = {
    "implemented": "",
    "implemented_gap": " (연결 대기)",
    "planned": " (예정)",
}


def resolve_builtin_capability(
    query: str,
    *,
    runtime_status_resolver: Callable[[], dict[str, object]] | None = None,
    calendar_view_resolver: Callable[[str], dict[str, object] | None] | None = None,
    calendar_update_resolver: Callable[[str], dict[str, object] | None] | None = None,
    calendar_create_resolver: Callable[[str], dict[str, object] | None] | None = None,
    calendar_followup_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_open_resolver: Callable[[str], dict[str, object] | None] | None = None,
    recent_context_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_summary_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_outline_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_sheet_list_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_sheet_resolver: Callable[[str], dict[str, object] | None] | None = None,
    document_section_resolver: Callable[[str], dict[str, object] | None] | None = None,
) -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None
    has_document_explain_query = _looks_like_document_explain_query(normalized)
    has_document_structure_query = bool(_DOC_STRUCTURE_QUERY_RE.search(normalized))
    wants_document_summary = bool(_DOC_SUMMARY_QUERY_RE.search(normalized)) or (
        has_document_explain_query and not has_document_structure_query
    )
    wants_document_outline = bool(_DOC_OUTLINE_QUERY_RE.search(normalized)) or (
        has_document_explain_query and has_document_structure_query
    )
    wants_document_sheet_list = bool(_DOC_SHEET_LIST_QUERY_RE.search(normalized))
    wants_document_sheet = bool(_DOC_SHEET_QUERY_RE.search(normalized)) and not wants_document_sheet_list
    wants_document_section = bool(_DOC_SECTION_QUERY_RE.search(normalized))
    direct_url = _extract_direct_url(normalized)
    requested_timezones = _extract_requested_timezones(normalized)
    has_time_query = bool(_TIME_QUERY_RE.search(normalized))

    def _handle_datetime_now() -> dict[str, object] | None:
        if not has_time_query or requested_timezones:
            return None
        return _build_time_response(normalized)

    def _handle_timezone_now() -> dict[str, object] | None:
        if not has_time_query or not requested_timezones:
            return None
        return _build_time_response(normalized)

    def _handle_calendar_create() -> dict[str, object] | None:
        if not _CALENDAR_CREATE_QUERY_RE.search(normalized) or not callable(calendar_create_resolver):
            return None
        return calendar_create_resolver(normalized)

    def _handle_calendar_view() -> dict[str, object] | None:
        if not _CALENDAR_VIEW_QUERY_RE.search(normalized) or not callable(calendar_view_resolver):
            return None
        return calendar_view_resolver(normalized)

    def _handle_calendar_update() -> dict[str, object] | None:
        if not (_CALENDAR_QUERY_RE.search(normalized) or _CALENDAR_DATE_MENTION_RE.search(normalized)):
            return None
        if not _CALENDAR_UPDATE_QUERY_RE.search(normalized) or not callable(calendar_update_resolver):
            return None
        return calendar_update_resolver(normalized)

    def _handle_calendar_followup() -> dict[str, object] | None:
        if not _CALENDAR_QUERY_RE.search(normalized) or not callable(calendar_followup_resolver):
            return None
        return calendar_followup_resolver(normalized)

    def _handle_runtime_status() -> dict[str, object] | None:
        if not _RUNTIME_STATUS_QUERY_RE.search(normalized) or not callable(runtime_status_resolver):
            return None
        return _build_runtime_status_response(normalized, runtime_status_resolver())

    def _handle_recent_context() -> dict[str, object] | None:
        if (
            wants_document_summary
            or wants_document_outline
            or wants_document_sheet_list
            or wants_document_sheet
            or wants_document_section
            or not _RECENT_CONTEXT_QUERY_RE.search(normalized)
            or not callable(recent_context_resolver)
        ):
            return None
        return recent_context_resolver(normalized)

    def _handle_doc_summary() -> dict[str, object] | None:
        if not wants_document_summary or not callable(document_summary_resolver):
            return None
        return document_summary_resolver(normalized)

    def _handle_doc_outline() -> dict[str, object] | None:
        if not wants_document_outline or not callable(document_outline_resolver):
            return None
        return document_outline_resolver(normalized)

    def _handle_sheet_list() -> dict[str, object] | None:
        if not wants_document_sheet_list or not callable(document_sheet_list_resolver):
            return None
        return document_sheet_list_resolver(normalized)

    def _handle_doc_sheet() -> dict[str, object] | None:
        if not wants_document_sheet or not callable(document_sheet_resolver):
            return None
        return document_sheet_resolver(normalized)

    def _handle_doc_section() -> dict[str, object] | None:
        if not wants_document_section or not callable(document_section_resolver):
            return None
        return document_section_resolver(normalized)

    def _handle_open_document() -> dict[str, object] | None:
        if not _looks_like_document_open_query(normalized) or not callable(document_open_resolver):
            return None
        return document_open_resolver(normalized)

    handler_map: dict[str, Callable[[], dict[str, object] | None]] = {
        "datetime_now": _handle_datetime_now,
        "timezone_now": _handle_timezone_now,
        "calendar_today": _handle_calendar_view,
        "calendar_update": _handle_calendar_update,
        "calendar_create": _handle_calendar_create,
        "relative_date": lambda: _build_relative_date_response(normalized),
        "math_eval": lambda: _build_calculation_response(normalized),
        "unit_convert": lambda: _build_unit_conversion_response(normalized),
        "capability_help": lambda: _build_help_response(normalized) if _HELP_QUERY_RE.search(normalized) else None,
        "runtime_status": _handle_runtime_status,
        "open_website": lambda: _build_direct_website_response(normalized, direct_url) if direct_url is not None else None,
        "doc_find": lambda: _build_doc_find_response(normalized) if _DOC_FIND_RE.search(normalized) else None,
        "web_search": lambda: _build_web_search_response(normalized) if _WEB_QUERY_RE.search(normalized) else None,
        "open_document": _handle_open_document,
        "recent_context": _handle_recent_context,
        "doc_summary": _handle_doc_summary,
        "doc_outline": _handle_doc_outline,
        "sheet_list": _handle_sheet_list,
        "doc_sheet": _handle_doc_sheet,
        "doc_section": _handle_doc_section,
        "calendar_followup": _handle_calendar_followup,
        "weather_now": lambda: _build_weather_response(normalized) if _WEATHER_QUERY_RE.search(normalized) else None,
    }

    # Mixed scheduling queries such as "3일 후 회의 잡아줘" should create/clarify an event
    # before the relative-date utility handler consumes the query.
    followup_response = _handle_calendar_followup()
    if followup_response is not None:
        return followup_response
    update_response = _handle_calendar_update()
    if update_response is not None:
        return update_response
    create_response = _handle_calendar_create()
    if create_response is not None:
        return create_response
    view_response = _handle_calendar_view()
    if view_response is not None:
        return view_response

    for entry in load_intent_skill_registry().dispatchable_entries():
        handler = handler_map.get(entry.intent_id)
        if handler is None:
            continue
        response = handler()
        if response is not None:
            return response

    planned_gap_response = _build_registry_capability_gap_response(normalized)
    if planned_gap_response is not None:
        return planned_gap_response

    return None


def _build_time_response(query: str) -> dict[str, object]:
    requested = _extract_requested_timezones(query)
    if requested:
        clocks = requested
    else:
        clocks = list(_REFERENCE_CLOCKS[:4])

    clocks_payload: list[dict[str, str]] = []
    first_clock_text = ""
    for index, (zone_name, label) in enumerate(clocks, start=1):
        current = _now_in_zone(zone_name)
        formatted = _format_datetime(current, include_zone=True)
        if index == 1:
            first_clock_text = f"{label} 기준 현재 시간은 {formatted}입니다."
        clocks_payload.append(
            {
                "label": label,
                "timezone": zone_name,
                "formatted": formatted,
                "time_24h": current.strftime("%H:%M:%S"),
                "date": f"{current.year}-{current.month:02d}-{current.day:02d}",
            }
        )

    response_text = first_clock_text or "현재 시간을 확인했습니다."
    if len(clocks_payload) > 1:
        response_text += f" 함께 볼 수 있는 기준 시각 {len(clocks_payload)}개를 정리했습니다."

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="time_lookup",
        skill="builtin_time",
        source_profile="time",
        answer_kind="utility_result",
        task_id="timezone_now" if requested else "datetime_now",
        structured_payload={
            "clocks": clocks_payload,
            "requested": bool(requested),
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _build_relative_date_response(query: str) -> dict[str, object] | None:
    anchor = _extract_relative_day_anchor(query)
    delta_days = _extract_relative_day_delta(query)
    has_date_hint = bool(_DATE_QUERY_HINT_RE.search(query))
    if anchor is None and delta_days is None:
        return None
    if not has_date_hint and delta_days is None:
        if anchor is None or not _is_relative_day_only_query(query, anchor[0]):
            return None
    if anchor is not None and anchor[0] == "오늘" and delta_days is None and not has_date_hint:
        return None

    now = _now_in_zone("Asia/Seoul")
    if anchor is None:
        anchor_label, anchor_offset = "오늘", 0
    else:
        anchor_label, anchor_offset = anchor
    anchor_date = now + timedelta(days=anchor_offset)
    target_date = anchor_date + timedelta(days=delta_days or 0)
    anchor_formatted = _format_date(anchor_date)
    target_formatted = _format_date(target_date)
    anchor_iso = anchor_date.strftime("%Y-%m-%d")
    target_iso = target_date.strftime("%Y-%m-%d")

    if delta_days is None:
        response_text = f"서울 기준 {anchor_label}는 {target_formatted}입니다."
    elif delta_days > 0:
        if anchor_label == "오늘":
            response_text = f"서울 기준 오늘부터 {delta_days}일 후는 {target_formatted}입니다."
        else:
            response_text = f"서울 기준 {anchor_label}({anchor_formatted})부터 {delta_days}일 후는 {target_formatted}입니다."
    else:
        if anchor_label == "오늘":
            response_text = f"서울 기준 오늘부터 {abs(delta_days)}일 전은 {target_formatted}입니다."
        else:
            response_text = f"서울 기준 {anchor_label}({anchor_formatted})부터 {abs(delta_days)}일 전은 {target_formatted}입니다."

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="date_relative",
        skill="builtin_date_relative",
        source_profile="date",
        answer_kind="utility_result",
        task_id="relative_date",
        structured_payload={
            "anchor_label": anchor_label,
            "anchor_date": anchor_iso,
            "anchor_formatted": anchor_formatted,
            "offset_days": delta_days or 0,
            "target_date": target_iso,
            "target_formatted": target_formatted,
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _build_runtime_status_response(query: str, health_result: dict[str, object]) -> dict[str, object]:
    status_level = str(health_result.get("status_level", "")).strip() or "unknown"
    chunk_count = int(health_result.get("chunk_count", 0) or 0)
    failed_checks = [
        str(item).strip()
        for item in (health_result.get("failed_checks") or [])
        if str(item).strip()
    ]
    details = health_result.get("details") if isinstance(health_result.get("details"), dict) else {}
    failed_documents = str(details.get("index_failures", "0")).strip() if isinstance(details, dict) else "0"
    response_text = (
        f"현재 런타임 상태는 {status_level}입니다. "
        f"인덱스 청크 {chunk_count}개, 실패 문서 {failed_documents}개가 확인됩니다."
    )
    if failed_checks:
        response_text += f" 점검 필요 항목은 {', '.join(failed_checks)}입니다."

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="runtime_status",
        skill="builtin_runtime_status",
        source_profile="runtime",
        answer_kind="utility_result",
        task_id="runtime_status",
        structured_payload={
            "status_level": status_level,
            "chunk_count": chunk_count,
            "failed_checks": failed_checks,
            "details": details,
            "bridge_mode": str(health_result.get("bridge_mode", "")).strip(),
            "knowledge_base_path": str(health_result.get("knowledge_base_path", "")).strip(),
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _capability_group_title(category: str) -> str:
    return _HELP_CATEGORY_TITLES.get(category, category.replace("_", " ").strip().title() or "기타")


def _example_query_label(entry: IntentSkillEntry) -> str:
    example = entry.example_queries[0] if entry.example_queries else entry.intent_id
    suffix = _IMPLEMENTATION_SUFFIXES.get(entry.implementation_status, "")
    return f"{example}{suffix}"


def _capability_groups_from_registry() -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = {}
    for entry in load_intent_skill_registry().entries:
        if not entry.example_queries:
            continue
        title = _capability_group_title(entry.category)
        grouped.setdefault(title, []).append(_example_query_label(entry))
    return [{"title": title, "items": items[:4]} for title, items in grouped.items() if items]


def _build_help_response(query: str) -> dict[str, object]:
    registry = load_intent_skill_registry()
    implemented_count = len([entry for entry in registry.entries if entry.implementation_status == "implemented"])
    backlog_count = len(registry.backlog_entries())
    capability_groups = _capability_groups_from_registry()
    response_text = (
        f"현재 skill map 기준으로 {implemented_count}개 작업이 바로 실행 가능하고, "
        f"{backlog_count}개는 연결 대기 또는 개발 예정입니다."
    )
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="capability_help",
        skill="builtin_help",
        source_profile="help",
        answer_kind="utility_result",
        task_id="capability_help",
        structured_payload={
            "registry_version": registry.version,
            "implemented_count": implemented_count,
            "backlog_count": backlog_count,
            "groups": capability_groups,
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _select_registry_gap_entry(query: str) -> IntentSkillEntry | None:
    if not _CALENDAR_QUERY_RE.search(query):
        return None
    registry = load_intent_skill_registry()
    if _CALENDAR_CREATE_QUERY_RE.search(query):
        return registry.get("calendar_create")
    if _CALENDAR_VIEW_QUERY_RE.search(query):
        return registry.get("calendar_today")
    return None


def _build_registry_capability_gap_response(query: str) -> dict[str, object] | None:
    entry = _select_registry_gap_entry(query)
    if entry is None:
        return None
    response_text = (
        f"'{entry.intent_id}' skill은 intent map에 등록돼 있지만 아직 {entry.implementation_status} 상태입니다. "
        "현재 런타임에서는 바로 실행할 수 없어 개발 또는 연결 작업이 필요합니다."
    )
    related_examples = list(entry.example_queries[:3])
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent=entry.intent_id,
        skill=entry.skill_id,
        source_profile="capability_gap",
        answer_kind="utility_result",
        task_id="capability_gap",
        structured_payload={
            "requested_intent": entry.intent_id,
            "skill_id": entry.skill_id,
            "category": entry.category,
            "implementation_status": entry.implementation_status,
            "requires_live_data": entry.requires_live_data,
            "automation_ready": entry.automation_ready,
            "example_queries": related_examples,
            "registry_version": load_intent_skill_registry().version,
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _build_weather_response(query: str) -> dict[str, object]:
    location = _extract_weather_location(query)
    weather_lookup_target = _resolve_weather_lookup_target(location)
    weather_data, source_url = _fetch_weather(
        weather_lookup_target or location,
        fallback_label=location or "현재 위치",
    )
    current_condition = ((weather_data.get("current_condition") or [{}])[0]) if isinstance(weather_data, dict) else {}
    nearest_area = ((weather_data.get("nearest_area") or [{}])[0]) if isinstance(weather_data, dict) else {}
    area_names = nearest_area.get("areaName") or []
    provider_area_label = ""
    if area_names and isinstance(area_names[0], dict):
        provider_area_label = str(area_names[0].get("value", "")).strip()
    area_label = location.strip() if location.strip() else provider_area_label
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

    if "날씨 데이터를 가져오지 못했습니다" in description:
        response_text = description
    else:
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


def _build_doc_find_response(query: str) -> dict[str, object] | None:
    """Search local knowledge base documents by filename/path keywords (direct DB query)."""
    # Extract search terms
    search_term = query
    for filler in ("문서", "파일", "책", "자료", "찾아", "줘", "검색", "해줘", "해주", "주세요",
                   "모두", "모든", "관련", "전부", "있는", "보여", "알려", "목록", "리스트",
                   "들을", "들이", "들의", "들은", "들도", "들",
                   "을", "를", "의", "에", "은", "는", "이", "가", "로", "으로", "에서",
                   "언어", "프로그래밍", "관한", "대한", "해서", "하는", "된", "있나", "있어"):
        search_term = search_term.replace(filler, " ")
    search_term = " ".join(search_term.split()).strip()
    if not search_term:
        return None

    try:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig
        from jarvis.app.runtime_context import resolve_knowledge_base_path
        from jarvis.runtime_paths import resolve_menubar_data_dir

        data_dir = resolve_menubar_data_dir()
        kb_path = resolve_knowledge_base_path()
        db = init_database(JarvisConfig(data_dir=data_dir))
    except Exception:
        return None

    try:
        terms = search_term.lower().split()

        # 1) Path/filename match (ANY term)
        all_docs = db.execute(
            "SELECT document_id, path, size_bytes, indexing_status FROM documents "
            "WHERE indexing_status IN ('INDEXED', 'FAILED') ORDER BY path"
        ).fetchall()

        results: list[dict] = []
        for doc_id, doc_path, size_bytes, status in all_docs:
            path_lower = doc_path.lower()
            hits = sum(1 for t in terms if t in path_lower)
            if hits == 0:
                continue
            rel = doc_path
            try:
                rel = str(Path(doc_path).relative_to(kb_path.resolve()))
            except (ValueError, Exception):
                pass
            chunk_count = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,)
            ).fetchone()[0]
            results.append({
                "name": Path(doc_path).name,
                "path": rel,
                "full_path": doc_path,
                "chunk_count": chunk_count,
                "status": status,
                "match_type": "path",
                "score": hits,
            })

        # 2) FTS content match
        fts_query = " AND ".join(f'"{t}"' for t in terms if len(t) >= 2)
        if fts_query:
            try:
                matched_ids = {r["full_path"] for r in results}
                fts_rows = db.execute(
                    "SELECT c.document_id, COUNT(*) as hits "
                    "FROM chunks_fts fts JOIN chunks c ON c.rowid = fts.rowid "
                    "WHERE chunks_fts MATCH ? GROUP BY c.document_id ORDER BY hits DESC LIMIT 10",
                    (fts_query,),
                ).fetchall()
                for doc_id, hits in fts_rows:
                    doc_row = db.execute(
                        "SELECT path, size_bytes, indexing_status FROM documents WHERE document_id = ?",
                        (doc_id,),
                    ).fetchone()
                    if not doc_row or doc_row[0] in matched_ids:
                        continue
                    rel = doc_row[0]
                    try:
                        rel = str(Path(doc_row[0]).relative_to(kb_path.resolve()))
                    except (ValueError, Exception):
                        pass
                    results.append({
                        "name": Path(doc_row[0]).name,
                        "path": rel,
                        "full_path": doc_row[0],
                        "chunk_count": hits,
                        "status": doc_row[2],
                        "match_type": "content",
                        "score": 0,
                    })
            except Exception:
                pass

        results.sort(key=lambda m: (-m["score"], m["path"]))

        if not results:
            return None
    finally:
        db.close()

    # Build artifacts
    artifacts = []
    for i, doc in enumerate(results[:15]):
        name = doc["name"]
        ext = Path(name).suffix.lower() if name else ""
        if ext in (".pdf", ".xlsx", ".xls", ".csv", ".pptx", ".docx", ".hwp", ".hwpx"):
            viewer = "document"
        elif ext in (".md", ".txt", ".json", ".yaml", ".yml", ".xml", ".html"):
            viewer = "text"
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            viewer = "image"
        else:
            viewer = "code"

        status_label = "" if doc["status"] == "INDEXED" else " [인덱싱 실패]"
        match_label = "경로 일치" if doc["match_type"] == "path" else "내용 일치"

        artifacts.append(_artifact(
            artifact_id=f"doc_find_{i}",
            type_name="document",
            title=name,
            subtitle=f"{match_label} · {doc['chunk_count']} chunks{status_label}",
            path=doc["path"],
            full_path=doc["full_path"],
            preview=doc["path"],
            source_type="document",
            viewer_kind=viewer,
        ))

    path_count = sum(1 for r in results[:15] if r["match_type"] == "path")
    content_count = len(artifacts) - path_count
    parts = []
    if path_count:
        parts.append(f"파일명/경로 일치 {path_count}개")
    if content_count:
        parts.append(f"내용 일치 {content_count}개")

    response_text = f"\"{search_term}\" 관련 문서 {len(artifacts)}개를 지식베이스에서 찾았습니다 ({', '.join(parts)})."

    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="doc_find",
        skill="builtin_doc_find",
        source_profile="knowledge_base",
        primary_source_type="document",
        artifacts=artifacts,
        presentation=_presentation(
            layout="master_detail",
            title="Document Search",
            subtitle=f"{len(artifacts)}개 결과",
            selected_artifact_id=artifacts[0]["id"] if artifacts else "",
            blocks=_blocks_for_answer_list_detail(
                answer_title="검색 결과",
                list_title="문서 목록",
                detail_title="문서 미리보기",
                artifact_ids=[a["id"] for a in artifacts],
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
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="calculation",
        skill="builtin_calculator",
        source_profile="calculator",
        answer_kind="utility_result",
        task_id="math_eval",
        structured_payload={
            "expression": expression,
            "result": result_text,
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
    )


def _build_unit_conversion_response(query: str) -> dict[str, object] | None:
    parsed = _extract_unit_conversion(query)
    if parsed is None:
        return None

    value, from_unit, to_unit = parsed
    from_spec = _UNIT_CONVERSION_FACTORS.get(from_unit)
    to_spec = _UNIT_CONVERSION_FACTORS.get(to_unit)
    if from_spec is None or to_spec is None:
        return None

    from_category, from_factor, from_label = from_spec
    to_category, to_factor, to_label = to_spec
    if from_category != to_category:
        return None

    converted = (value * from_factor) / to_factor
    source_value = _format_number(value)
    converted_value = _format_number(converted)
    response_text = f"{source_value}{from_label}는 {converted_value}{to_label}입니다."
    return _response_payload(
        query=query,
        response_text=response_text,
        spoken_text=response_text,
        intent="unit_conversion",
        skill="builtin_unit_converter",
        source_profile="converter",
        answer_kind="utility_result",
        task_id="unit_convert",
        structured_payload={
            "value": source_value,
            "from_unit": from_label,
            "to_unit": to_label,
            "result": converted_value,
            "category": from_category,
        },
        ui_hints={
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
        artifacts=[],
        presentation=None,
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
    presentation: dict[str, object] | None,
    primary_source_type: str = "none",
    citations: list[dict[str, object]] | None = None,
    answer_kind: str = "retrieval_result",
    task_id: str = "",
    structured_payload: dict[str, object] | None = None,
    ui_hints: dict[str, object] | None = None,
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
        "answer_kind": answer_kind,
        "task_id": task_id,
        "structured_payload": structured_payload or {},
        "ui_hints": ui_hints or {},
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


def _extract_relative_day_anchor(query: str) -> tuple[str, int] | None:
    normalized = " ".join(query.split()).strip()
    for label, offset in _RELATIVE_DAY_LABELS:
        if label in normalized:
            return label, offset
    return None


def _is_relative_day_only_query(query: str, anchor_label: str) -> bool:
    normalized = re.sub(r"[\s\?\!\.,]+", "", query.lower())
    anchor_normalized = anchor_label.lower()
    if not normalized.startswith(anchor_normalized):
        return False
    remainder = normalized[len(anchor_normalized):]
    return bool(
        re.fullmatch(
            r"(?:은|는|이|가|야|이야|였지|였더라|지|인가|인가요|일까|일까요|날짜야|며칠이야|며칠이지|며칠이었지|언제야|언제지)?",
            remainder,
        )
    )


def _extract_relative_day_delta(query: str) -> int | None:
    normalized = " ".join(query.split()).strip()
    match = re.search(
        r"(?P<days>\d+)\s*일\s*(?P<direction>후|뒤|전)",
        normalized,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"(?P<direction>after|before)\s*(?P<days>\d+)\s*days?",
            normalized,
            re.IGNORECASE,
        )
    if match is None:
        return None
    try:
        value = int(match.group("days"))
    except (TypeError, ValueError):
        return None
    direction = str(match.group("direction") or "").strip().lower()
    if direction in {"전", "before"}:
        return -value
    return value


def _clean_weather_location_candidate(candidate: str) -> str:
    cleaned = re.sub(
        r"\b(오늘|내일|현재|날씨|기온|forecast|weather|알려줘|보여줘|검색해줘|좀|좀요)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[?!]+", " ", cleaned)
    cleaned = re.sub(r"^(?:의|은|는|이|가|을|를|에|에서|로|으로|와|과|도|만)\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:의|은|는|이|가|을|를|에|에서|로|으로|와|과|도|만)$", "", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip(" ,.?")


def _extract_weather_location(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    for pattern in (
        re.compile(r"(?P<location>.+?)\s*(?:의\s*)?(?:오늘\s*)?(?:내일\s*)?(?:현재\s*)?(?:날씨|기온|forecast|weather)", re.IGNORECASE),
        re.compile(r"(?:날씨|weather)\s*(?:은|는|이|가)?\s*(?:를|를 좀|좀|좀요)?\s*(?:알려줘|보여줘|search|for|in)?\s*(?P<location>.+)$", re.IGNORECASE),
    ):
        match = pattern.search(normalized)
        if not match:
            continue
        cleaned = _clean_weather_location_candidate(match.group("location"))
        if cleaned:
            return cleaned
    return ""


def _resolve_weather_lookup_target(location: str) -> str:
    normalized = " ".join(location.split()).strip()
    if not normalized:
        return ""
    if re.fullmatch(r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?", normalized):
        return normalized.replace(" ", "")

    geocode_url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={quote_plus(normalized)}&format=jsonv2&limit=1&accept-language=ko"
    )
    try:
        data = _fetch_json(geocode_url)
    except Exception:
        return normalized
    if not isinstance(data, list):
        return normalized

    for item in data:
        if not isinstance(item, dict):
            continue
        lat = str(item.get("lat", "")).strip()
        lon = str(item.get("lon", "")).strip()
        if lat and lon:
            return f"{lat},{lon}"
    return normalized


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
    if _FILE_LIKE_TOKEN_RE.fullmatch(candidate):
        return None
    return f"https://{candidate}"


def _looks_like_document_open_query(query: str) -> bool:
    if not _DOCUMENT_OPEN_QUERY_RE.search(query):
        return False
    lowered = query.lower()
    file_hint = bool(
        re.search(r"\.(?:md|txt|pdf|docx?|pptx?|xlsx|csv|hwp|hwpx|sql|py|ts|tsx|js|jsx|json|ya?ml)\b", lowered)
    )
    keyword_hint = any(
        token in lowered
        for token in (
            "readme",
            "브로셔",
            "brochure",
            "문서",
            "파일",
            "슬라이드",
            "ppt",
            "pdf",
            "sheet",
            "스프레드시트",
            "보고서",
            "가이드",
            "manual",
        )
    )
    detail_hint = any(
        token in lowered
        for token in (
            "컬럼",
            "요약",
            "목차",
            "메뉴",
            "페이지",
            "슬라이드 제목",
            "어떤",
            "무엇",
            "알려",
            "설명",
            "내용",
            "기능",
        )
    )
    return (file_hint or keyword_hint) and not detail_hint


def _looks_like_document_explain_query(query: str) -> bool:
    if not (_DOC_EXPLAIN_QUERY_RE.search(query) or _DOC_STRUCTURE_QUERY_RE.search(query)):
        return False
    lowered = query.lower()
    if any(
        token in lowered
        for token in (
            "이 문서",
            "이 파일",
            "그 문서",
            "그 파일",
            "저 문서",
            "저 파일",
            "readme",
            "projecthub",
            "브로셔",
            "brochure",
            "코드",
            "문서",
            "파일",
            "가이드",
            "manual",
        )
    ):
        return True
    if _FILE_LIKE_TOKEN_RE.search(query):
        return True
    return bool(re.search(r"(에서|에\s*대해|관련(?:해서)?|기준으로)", query, re.IGNORECASE))


def _extract_unit_conversion(query: str) -> tuple[float, str, str] | None:
    normalized = " ".join(query.split()).strip().rstrip("?.!")
    patterns = (
        re.compile(
            r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<from>[A-Za-z가-힣]+)\s*(?:는|은|을|를)?\s*몇\s*(?P<to>[A-Za-z가-힣]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"convert\s+(?P<value>-?\d+(?:\.\d+)?)\s*(?P<from>[A-Za-z]+)\s+to\s+(?P<to>[A-Za-z]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<from>[A-Za-z가-힣]+)\s*(?:to|->|→)\s*(?P<to>[A-Za-z가-힣]+)",
            re.IGNORECASE,
        ),
    )
    for pattern in patterns:
        match = pattern.search(normalized)
        if match is None:
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            return None
        from_unit = _normalize_unit_token(match.group("from"))
        to_unit = _normalize_unit_token(match.group("to"))
        if from_unit == to_unit:
            return None
        if from_unit in _UNIT_CONVERSION_FACTORS and to_unit in _UNIT_CONVERSION_FACTORS:
            return value, from_unit, to_unit
    return None


def _normalize_unit_token(token: str) -> str:
    normalized = token.strip().lower()
    normalized = re.sub(r"(이야|야|인가요|인가|입니까|입니다)$", "", normalized)
    normalized = re.sub(r"(은|는|을|를|이|가)$", "", normalized)
    return normalized


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


def _fetch_weather(location: str, *, fallback_label: str | None = None) -> tuple[dict[str, object], str]:
    display_label = fallback_label or location or "현재 위치"
    location_path = quote(location, safe=",") if location else ""
    source_url = f"https://wttr.in/{location_path}?format=j1&lang=ko"
    try:
        data = _fetch_json(source_url)
    except Exception as exc:
        fallback_text = (
            f"{display_label} 날씨 데이터를 가져오지 못했습니다. "
            f"네트워크 상태를 확인한 뒤 다시 시도해 주세요."
        )
        return (
            {
                "current_condition": [
                    {
                        "weatherDesc": [{"value": fallback_text}],
                    }
                ],
                "nearest_area": [{"areaName": [{"value": display_label}]}],
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


def _format_date(value: datetime) -> str:
    day_name = _DAY_NAMES[value.weekday()]
    return f"{value.year}년 {value.month}월 {value.day}일 {day_name}요일"


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
