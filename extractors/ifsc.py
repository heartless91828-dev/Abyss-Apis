from .common import ci_get, unwrap_data

def ifsc_extract_data(res):
    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    result = {}

    def add_field(output_key, *source_keys):
        value = ci_get(data, *source_keys)

        # Empty string / None ko skip karega
        if value not in (None, ""):
            result[output_key] = value

    add_field("MICR", "MICR", "micr")
    add_field("Branch", "BRANCH", "branch")
    add_field("Address", "ADDRESS", "address")
    add_field("State", "STATE", "state")
    add_field("Contact", "CONTACT", "contact")
    add_field("UPI", "UPI", "upi")
    add_field("RTGS", "RTGS", "rtgs")
    add_field("City", "CITY", "city")
    add_field("Centre", "CENTRE", "centre", "center")
    add_field("District", "DISTRICT", "district")
    add_field("NEFT", "NEFT", "neft")
    add_field("IMPS", "IMPS", "imps")
    add_field("SWIFT", "SWIFT", "swift")
    add_field("ISO3166", "ISO3166", "iso3166")
    add_field("Bank", "BANK", "bank")
    add_field("BankCode", "BANKCODE", "bankcode", "bank_code")
    add_field("IFSC", "IFSC", "ifsc")

    return result if result else None

__all__ = ["ifsc_extract_data"]
