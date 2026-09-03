from .common import ci_get, unwrap_data

def num_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    mobile = ci_get(data, "mobile", "number", "num")
    circle = ci_get(data, "circle")
    name = ci_get(data, "name", "name")
    father_name = ci_get(data, "fname", "father", "fathername")
    address = ci_get(data, "address")
    email = ci_get(data, "email")
    aadhar = ci_get(data, "aadhar", "id")
    alt_num = ci_get(data, "alt" , "alternate")
    if not mobile and not circle:
        return None

    return {
        "Name": name or "Unknown",
        "FatherName": father_name or "Unknown",
        "Address": address or "Unknown",
        "Circle": circle or "Unknown",
        "AlternateNum": alt_num or "Unknown",
        "MobileNum": mobile or "Unknown",
        "Aadhar": aadhar or "Unknown",
        "Email": email or "Unknown"
    }

__all__ = ["num_extract_data"]
