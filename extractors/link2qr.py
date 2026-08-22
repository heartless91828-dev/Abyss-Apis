__all__ = ["is_qr_type"]

def is_qr_type(api_type: str) -> bool:
    return api_type.strip().lower() == "link2qr"
