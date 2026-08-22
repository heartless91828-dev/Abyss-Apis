from __future__ import annotations


def ci_get(data, *keys):
    if not isinstance(data, dict):
        return None
    lower_map = {str(k).strip().lower(): v for k, v in data.items()}
    for key in keys:
        value = lower_map.get(str(key).strip().lower())
        if value not in (None, ""):
            return value
    return None


def unwrap_data(res):
    data = res
    while isinstance(data, dict):
        moved = False
        for key in ("result", "results", "data", "response", "payload", "output", "value", "content"):
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, dict):
                data = value
                moved = True
                break
            if isinstance(value, list):
                if value:
                    data = value[0] if isinstance(value[0], dict) else value[0]
                else:
                    return {}
                moved = True
                break
        if not moved:
            break
    if isinstance(data, list):
        if not data:
            return {}
        return data[0]
    return data if isinstance(data, dict) else {}
