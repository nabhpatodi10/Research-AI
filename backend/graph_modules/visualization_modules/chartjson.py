from __future__ import annotations

import json
import math
import re
from typing import Any

from .types import ValidationResult


FUNCTION_LIKE_PATTERN = re.compile(r"^\s*(?:function\s*\(|\(?\s*[\w$,\s]+\)?\s*=>)")
UNSAFE_KEYS = {"__proto__", "prototype", "constructor"}
CHART_ALLOWED_TOP_LEVEL_KEYS = {"title", "caption", "option"}
CHART_ALLOWED_AXIS_TYPES = {"category", "value", "time", "log"}
CHART_SUPPORTED_SERIES_TYPES = {
    "line",
    "bar",
    "pie",
    "scatter",
    "effectscatter",
    "radar",
    "tree",
    "treemap",
    "sunburst",
    "boxplot",
    "candlestick",
    "heatmap",
    "map",
    "parallel",
    "lines",
    "graph",
    "sankey",
    "funnel",
    "gauge",
    "pictorialbar",
    "themeriver",
    "custom",
}
CHART_AXIS_REQUIRED_SERIES_TYPES = {
    "line",
    "bar",
    "scatter",
    "effectscatter",
    "boxplot",
    "candlestick",
    "heatmap",
    "pictorialbar",
    "custom",
}
CHART_MAX_JSON_NODES = 15_000
CHART_MAX_JSON_DEPTH = 64


def _has_unsafe_keys_or_values(input_value: Any) -> bool:
    if input_value is None:
        return False

    if isinstance(input_value, str):
        return bool(FUNCTION_LIKE_PATTERN.search(input_value))

    if isinstance(input_value, list):
        return any(_has_unsafe_keys_or_values(item) for item in input_value)

    if isinstance(input_value, dict):
        for key, value in input_value.items():
            if str(key) in UNSAFE_KEYS:
                return True
            if _has_unsafe_keys_or_values(value):
                return True
        return False

    return False


def _json_shape_stats(input_value: Any, depth: int = 1) -> tuple[int, int]:
    total_nodes = 1
    max_depth = depth

    if isinstance(input_value, dict):
        for value in input_value.values():
            child_nodes, child_depth = _json_shape_stats(value, depth + 1)
            total_nodes += child_nodes
            max_depth = max(max_depth, child_depth)
        return total_nodes, max_depth

    if isinstance(input_value, list):
        for value in input_value:
            child_nodes, child_depth = _json_shape_stats(value, depth + 1)
            total_nodes += child_nodes
            max_depth = max(max_depth, child_depth)
        return total_nodes, max_depth

    return total_nodes, max_depth


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_axis_config(axis_value: Any, axis_name: str) -> str | None:
    axis_items: list[dict[str, Any]] = []
    if isinstance(axis_value, dict):
        axis_items = [axis_value]
    elif isinstance(axis_value, list):
        if not axis_value:
            return f'chartjson option "{axis_name}" cannot be an empty list.'
        if not all(isinstance(item, dict) for item in axis_value):
            return f'chartjson option "{axis_name}" list items must be objects.'
        axis_items = [item for item in axis_value if isinstance(item, dict)]
    else:
        return f'chartjson option "{axis_name}" must be an object or list of objects.'

    for axis_item in axis_items:
        axis_type = axis_item.get("type")
        if axis_type is not None:
            if not isinstance(axis_type, str):
                return f'chartjson option "{axis_name}.type" must be a string when provided.'
            if axis_type.lower() not in CHART_ALLOWED_AXIS_TYPES:
                return (
                    f'chartjson option "{axis_name}.type" has unsupported value "{axis_type}". '
                    f"Supported values: {sorted(CHART_ALLOWED_AXIS_TYPES)}."
                )

        axis_data = axis_item.get("data")
        if axis_data is not None and not isinstance(axis_data, list):
            return f'chartjson option "{axis_name}.data" must be a list when provided.'

        axis_name_value = axis_item.get("name")
        if axis_name_value is not None and not isinstance(axis_name_value, str):
            return f'chartjson option "{axis_name}.name" must be a string when provided.'

    return None


def _validate_option_title(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return None
    if isinstance(value, dict):
        title_text = value.get("text")
        if title_text is not None and not isinstance(title_text, str):
            return 'chartjson option "title.text" must be a string when provided.'
        title_subtext = value.get("subtext")
        if title_subtext is not None and not isinstance(title_subtext, str):
            return 'chartjson option "title.subtext" must be a string when provided.'
        return None
    if isinstance(value, list):
        if not value:
            return 'chartjson option "title" cannot be an empty list.'
        for item in value:
            if not isinstance(item, dict):
                return 'chartjson option "title" list items must be objects.'
            title_text = item.get("text")
            if title_text is not None and not isinstance(title_text, str):
                return 'chartjson option "title[].text" must be a string when provided.'
        return None
    return 'chartjson option "title" must be a string, object, or list of objects.'


def _validate_option_object(option: dict[str, Any]) -> str | None:
    if not option:
        return 'chartjson option object cannot be empty.'

    title_error = _validate_option_title(option.get("title"))
    if title_error:
        return title_error

    for key in ("tooltip", "legend", "grid", "dataset", "visualMap", "dataZoom"):
        value = option.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            continue
        return f'chartjson option "{key}" must be an object or list of objects when provided.'

    x_axis = option.get("xAxis")
    if x_axis is not None:
        axis_error = _validate_axis_config(x_axis, "xAxis")
        if axis_error:
            return axis_error

    y_axis = option.get("yAxis")
    if y_axis is not None:
        axis_error = _validate_axis_config(y_axis, "yAxis")
        if axis_error:
            return axis_error

    series = option.get("series")
    if not isinstance(series, list) or len(series) == 0:
        return 'chartjson option must include a non-empty array field named "series".'

    has_axis_series = False
    for index, series_item in enumerate(series):
        if not isinstance(series_item, dict):
            return f'chartjson option "series[{index}]" must be an object.'

        series_type = series_item.get("type")
        if not isinstance(series_type, str) or not series_type.strip():
            return f'chartjson option "series[{index}].type" must be a non-empty string.'

        normalized_series_type = series_type.strip().lower()
        if not re.match(r"^[a-z][a-z0-9_-]*$", normalized_series_type):
            return (
                f'chartjson option "series[{index}].type" contains unsupported characters: '
                f'"{series_type}".'
            )
        if normalized_series_type not in CHART_SUPPORTED_SERIES_TYPES:
            return (
                f'chartjson option "series[{index}].type" unsupported value "{series_type}". '
                f"Supported values include: {sorted(CHART_SUPPORTED_SERIES_TYPES)}."
            )

        if normalized_series_type in CHART_AXIS_REQUIRED_SERIES_TYPES:
            has_axis_series = True

        series_data = series_item.get("data")
        if series_data is not None and not isinstance(series_data, list):
            return f'chartjson option "series[{index}].data" must be a list when provided.'

        series_name = series_item.get("name")
        if series_name is not None and not isinstance(series_name, str):
            return f'chartjson option "series[{index}].name" must be a string when provided.'

        encode = series_item.get("encode")
        if encode is not None and not isinstance(encode, dict):
            return f'chartjson option "series[{index}].encode" must be an object when provided.'

        if "barWidth" in series_item and not (
            isinstance(series_item.get("barWidth"), str)
            or _is_finite_number(series_item.get("barWidth"))
        ):
            return (
                f'chartjson option "series[{index}].barWidth" must be a string or finite number '
                "when provided."
            )

    if has_axis_series:
        if x_axis is None or y_axis is None:
            return (
                'chartjson option with axis-based series types must include both '
                '"xAxis" and "yAxis".'
            )

    return None


def validate_chartjson(block_text: str) -> ValidationResult:
    raw = str(block_text or "").strip()
    if not raw:
        return ValidationResult(False, "Empty chartjson block.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        return ValidationResult(False, f"Invalid chartjson JSON: {error.msg}.")

    if not isinstance(payload, dict):
        return ValidationResult(False, "chartjson payload root must be an object.")

    unknown_top_level_keys = sorted(set(payload.keys()) - CHART_ALLOWED_TOP_LEVEL_KEYS)
    if unknown_top_level_keys:
        return ValidationResult(
            False,
            (
                "chartjson payload has unsupported top-level keys: "
                f"{unknown_top_level_keys}. Allowed keys: {sorted(CHART_ALLOWED_TOP_LEVEL_KEYS)}."
            ),
        )

    if _has_unsafe_keys_or_values(payload):
        return ValidationResult(
            False,
            "chartjson payload contains unsafe keys or function-like values.",
        )

    total_nodes, max_depth = _json_shape_stats(payload)
    if total_nodes > CHART_MAX_JSON_NODES:
        return ValidationResult(
            False,
            (
                "chartjson payload is too large for safe validation "
                f"({total_nodes} nodes > {CHART_MAX_JSON_NODES})."
            ),
        )
    if max_depth > CHART_MAX_JSON_DEPTH:
        return ValidationResult(
            False,
            (
                "chartjson payload is too deeply nested for safe validation "
                f"(depth {max_depth} > {CHART_MAX_JSON_DEPTH})."
            ),
        )

    option = payload.get("option")
    if not isinstance(option, dict):
        return ValidationResult(False, 'chartjson payload must include an object field named "option".')

    title = payload.get("title")
    if title is not None and not isinstance(title, str):
        return ValidationResult(False, 'chartjson field "title" must be a string when provided.')

    caption = payload.get("caption")
    if caption is not None and not isinstance(caption, str):
        return ValidationResult(False, 'chartjson field "caption" must be a string when provided.')

    option_error = _validate_option_object(option)
    if option_error:
        return ValidationResult(False, option_error)

    return ValidationResult(True, None)
