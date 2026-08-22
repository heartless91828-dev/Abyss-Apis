
from .telegram import telegram_extract_data
from .num import num_extract_data
from .vehicle import vehicle_extract_data
from .vnum import v_num_extract_data
from .family import aadhar_fam_extract_data
from .ip import ip_extract_data
from .vinfo import v_info_extract_data
from .ifsc import ifsc_extract_data

EXTRACTORS = {
    "telegram": telegram_extract_data,
    "num": num_extract_data,
    "vehicle": vehicle_extract_data,
    "vnum": v_num_extract_data,
    "family": aadhar_fam_extract_data,
    "ip": ip_extract_data,
    "vinfo": v_info_extract_data,
    "ifsc": ifsc_extract_data,
}