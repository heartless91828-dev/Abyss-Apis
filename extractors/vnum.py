from .common import ci_get, unwrap_data

def v_num_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    # First try result, then fallback to root
    result_data = ci_get(data, "result")

    if not isinstance(result_data, dict):
        result_data = data

    vehicle = ci_get(
        result_data,
        "vnum",
        "vehicle",
        "veh",
        "vehicle_number",
        "vehicleNumber",
        "registration_number",
        "regNo"
    )

    owner_number = ci_get(
        result_data,
        "mobile_no",
        "mobile",
        "owner_number",
        "ownerNumber",
        "number",
        "phone",
        "phone_number",
        "phoneNumber"
    )

    result = {}

    if vehicle:
        result["Vehicle"] = vehicle

    if owner_number:
        result["OwnerNumber"] = owner_number

    return result if result else None

__all__ = ["v_num_extract_data"]