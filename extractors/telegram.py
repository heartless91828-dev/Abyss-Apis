from .common import ci_get, unwrap_data

def telegram_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    number = ci_get(data, "number", "n", "num", "phone", "mobile")
    country = ci_get(data, "country", "c")
    country_code = ci_get(data, "country_code", "code", "cc", "ccode")

    if not number:
        return None

    return {
        "Number": number,
        "Country": country or "Unknown",
        "Country Code": country_code or "Unknown"
    }

__all__ = ["telegram_extract_data"]
