from .common import ci_get, unwrap_data

def v_num_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    vehicle = ci_get(
        data,
        "vehicle",
        "veh",
        "vehicle_number",
        "vehicleNumber",
        "registration_number",
        "regNo"
    )

    owner_number = ci_get(
        data,
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
