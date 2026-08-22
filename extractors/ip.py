from .common import ci_get, unwrap_data

def ip_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    # IP API unsuccessful response
    if data.get("status") != "success":
        return None

    return {
        "Status": data.get("status", "Unknown"),
        "Country": data.get("country", "Unknown"),
        "CountryCode": data.get("countryCode", "Unknown"),
        "Region": data.get("region", "Unknown"),
        "RegionName": data.get("regionName", "Unknown"),
        "City": data.get("city", "Unknown"),
        "ZIP": data.get("zip", "Unknown"),
        "Latitude": data.get("lat", "Unknown"),
        "Longitude": data.get("lon", "Unknown"),
        "Timezone": data.get("timezone", "Unknown"),
        "ISP": data.get("isp", "Unknown"),
        "ORG": data.get("org", "Unknown"),
        "AS": data.get("as", "Unknown"),
        "IP": data.get("query", "Unknown")
    }

__all__ = ["ip_extract_data"]
