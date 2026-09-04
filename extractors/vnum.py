from .common import ci_get, unwrap_data


def v_num_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    # First try result, then fallback to root
    result_data = ci_get(data, "result")

    if not isinstance(result_data, dict):
        result_data = data

    # =========================
    # CURRENT / OLD API SUPPORT
    # =========================
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

    # ==========================================
    # EXTRA SUPPORT FOR LITE_ULTRA_SPEED_CORE API
    # ==========================================

    lite_data = ci_get(data, "LITE_ULTRA_SPEED_CORE")

    if isinstance(lite_data, dict):

        if not vehicle:
            vehicle = ci_get(
                lite_data,
                "vehicle_number",
                "vehicle",
                "vnum",
                "veh",
                "registration_number",
                "regNo"
            )

        if not owner_number:
            owner_number = ci_get(
                lite_data,
                "mobile_number",
                "mobile_no",
                "mobile",
                "owner_number",
                "ownerNumber",
                "number",
                "phone",
                "phone_number",
                "phoneNumber"
            )

    # =========================
    # FINAL RESULT
    # =========================
    result = {}

    if vehicle:
        result["Vehicle"] = vehicle

    if owner_number:
        result["OwnerNumber"] = owner_number

    return result if result else None


__all__ = ["v_num_extract_data"]