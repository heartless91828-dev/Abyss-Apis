from .vehicle import vehicle_extract_data

def v_info_extract_data(res):
    # v_info responses are normalized through the same vehicle schema.
    return vehicle_extract_data(res)

__all__ = ["v_info_extract_data"]
