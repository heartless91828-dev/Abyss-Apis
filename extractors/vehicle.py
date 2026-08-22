from .common import ci_get, unwrap_data

def vehicle_extract_data(res):
    """
    Extract vehicle information from multiple API response formats.

    Supported formats:
    1. Nested/flat response:
       {
           "success": true,
           "data": {
               "data": {
                   "regNo": "...",
                   ...
               }
           }
       }

    2. Section-based response:
       {
           "Ownership Details": {...},
           "Vehicle Details": {...},
           "Insurance Information": {...},
           ...
       }

    Missing, NA, N/A, Unknown, null and empty fields are removed.
    Valid False and 0 values are preserved.
    """

    # =========================================================
    # HELPER FUNCTIONS
    # =========================================================

    def clean_value(value):
        """
        Return None for missing/unavailable values.
        Preserve valid False and numeric/string zero.
        """
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

            if value.lower() in {
                "null",
                "none",
                "unknown",
                "not available",
                "not_available",
                "n/a",
                "na",
                "nil",
                "-",
                "--",
                "---"
            }:
                return None

            return value

        if isinstance(value, list):
            cleaned_items = []

            for item in value:
                cleaned = clean_value(item)

                if cleaned is not None:
                    cleaned_items.append(cleaned)

            return cleaned_items if cleaned_items else None

        if isinstance(value, dict):
            cleaned_dict = {}

            for key, item in value.items():
                cleaned = clean_value(item)

                if cleaned is not None:
                    cleaned_dict[key] = cleaned

            return cleaned_dict if cleaned_dict else None

        # False and 0 reach here and remain valid.
        return value

    def first_value(*values):
        """
        Return the first valid value.
        """
        for value in values:
            cleaned = clean_value(value)

            if cleaned is not None:
                return cleaned

        return None

    def get_dict(parent, key):
        """
        Safely return a nested dictionary using exact key.
        """
        if not isinstance(parent, dict):
            return {}

        value = parent.get(key)

        return value if isinstance(value, dict) else {}

    def get_ci(parent, *keys):
        """
        Case-insensitive dictionary lookup.
        """
        if not isinstance(parent, dict):
            return None

        lower_map = {
            str(key).strip().lower(): value
            for key, value in parent.items()
        }

        for key in keys:
            value = lower_map.get(str(key).strip().lower())

            if clean_value(value) is not None:
                return value

        return None

    def find_insurance_validity(insurance_data):
        """
        Handle changing insurance keys such as:
        'Insurance Valid Upto 2 years, 2 months...'
        """
        if not isinstance(insurance_data, dict):
            return None

        direct_value = get_ci(
            insurance_data,
            "Insurance Expiry",
            "Insurance Upto",
            "Insurance Valid Upto",
            "Insurance Validity"
        )

        if clean_value(direct_value) is not None:
            return direct_value

        for key, value in insurance_data.items():
            normalized_key = str(key).strip().lower()

            if (
                "insurance valid upto" in normalized_key
                or "insurance expiry" in normalized_key
                or "insurance upto" in normalized_key
                or "insurance validity" in normalized_key
            ):
                if clean_value(value) is not None:
                    return value

        return None

    def get_best_mmv(parent):
        """
        Return the highest-scored valid item from mmvResponse.
        """
        if not isinstance(parent, dict):
            return {}

        mmv_response = get_ci(
            parent,
            "mmvResponse",
            "mmv_response"
        )

        if not isinstance(mmv_response, list):
            return {}

        valid_items = [
            item
            for item in mmv_response
            if isinstance(item, dict)
        ]

        if not valid_items:
            return {}

        def get_score(item):
            try:
                return float(item.get("score") or 0)
            except (TypeError, ValueError):
                return 0.0

        return max(valid_items, key=get_score)

    def add_field(result, name, value):
        """
        Add field only when a valid value exists.
        """
        cleaned = clean_value(value)

        if cleaned is not None:
            result[name] = cleaned

    # =========================================================
    # UNWRAP RESPONSE
    # =========================================================

    data = unwrap_data(res)

    if not isinstance(data, dict):
        return None

    # Handles cases where unwrap_data did not fully reach the
    # vehicle object because of an uncommon wrapper structure.
    for _ in range(5):
        nested_data = get_ci(
            data,
            "data",
            "result",
            "response",
            "payload",
            "output"
        )

        if not isinstance(nested_data, dict):
            break

        # Do not unwrap section-based vehicle response.
        if any(
            key in data
            for key in (
                "Ownership Details",
                "Vehicle Details",
                "registration_number",
                "regNo",
                "vehicleNumber"
            )
        ):
            break

        data = nested_data

    # =========================================================
    # SECTION-BASED RESPONSE OBJECTS
    # =========================================================

    ownership = get_dict(data, "Ownership Details")
    vehicle = get_dict(data, "Vehicle Details")
    insurance = get_dict(data, "Insurance Information")
    dates = get_dict(data, "Important Dates & Validity")
    other = get_dict(data, "Other Information")
    basic = get_dict(data, "Basic Card Info")
    insurance_alert = get_dict(data, "Insurance Alert")

    best_mmv = get_best_mmv(data)

    # =========================================================
    # REGISTRATION DETAILS
    # =========================================================

    registration_number = first_value(
        get_ci(
            data,
            "registration_number",
            "registrationNumber",
            "regNo",
            "reg_no",
            "vehicleNumber",
            "vehicle_number",
            "rcNumber",
            "rc_number"
        ),
        get_ci(
            ownership,
            "Registration Number",
            "RegistrationNumber",
            "Reg No"
        )
    )

    if registration_number is None:
        return None

    registration_date = first_value(
        get_ci(
            data,
            "regDate",
            "reg_date",
            "registrationDate",
            "registration_date"
        ),
        get_ci(
            dates,
            "Registration Date"
        )
    )

    registered_rto = first_value(
        get_ci(
            data,
            "regAuthority",
            "reg_authority",
            "registeredRTO",
            "registered_rto",
            "RTO",
            "rto"
        ),
        get_ci(
            ownership,
            "Registered RTO"
        ),
        get_ci(
            basic,
            "RTO"
        )
    )

    rto_code = first_value(
        get_ci(
            data,
            "rtoCode",
            "rto_code"
        ),
        get_ci(
            basic,
            "Code"
        )
    )

    rc_expiry_date = first_value(
        get_ci(
            data,
            "rcExpiryDate",
            "rc_expiry_date",
            "fitnessValidity",
            "fitness_validity",
            "fitnessUpto",
            "fitness_upto"
        ),
        get_ci(
            dates,
            "Fitness Upto",
            "Fitness Validity",
            "RC Expiry Date"
        )
    )

    vehicle_age = first_value(
        get_ci(
            data,
            "vehicleAge",
            "vehicle_age"
        ),
        get_ci(
            dates,
            "Vehicle Age"
        )
    )

    manufacturing_month_year = first_value(
        get_ci(
            data,
            "vehicleManufacturingMonthYear",
            "vehicle_manufacturing_month_year",
            "manufacturingMonthYear",
            "manufacturing_month_year"
        ),
        get_ci(
            vehicle,
            "Manufacturing Month Year",
            "Manufacturing Date",
            "Manufacturing Year"
        )
    )

    # =========================================================
    # OWNER DETAILS
    # =========================================================

    owner_name = first_value(
        get_ci(
            data,
            "ownerName",
            "owner_name"
        ),
        get_ci(
            ownership,
            "Owner Name"
        ),
        get_ci(
            basic,
            "Owner Name"
        )
    )

    owner_father_name = first_value(
        get_ci(
            data,
            "ownerFatherName",
            "owner_father_name",
            "fatherName",
            "father_name",
            "fathersName",
            "fathers_name"
        ),
        get_ci(
            ownership,
            "Owner Father Name",
            "Father Name",
            "Father's Name",
            "Fathers Name"
        )
    )

    owner_number = first_value(
        get_ci(
            data,
            "ownerNumber",
            "owner_number",
            "mobileNumber",
            "mobile_number",
            "phoneNumber",
            "phone_number",
            "ownerMobile",
            "owner_mobile"
        )
    )

    owner_count = first_value(
        get_ci(
            data,
            "ownerCount",
            "owner_count",
            "numberOfOwners",
            "number_of_owners"
        ),
        get_ci(
            ownership,
            "Owner Count"
        )
    )

    owner_serial_number = first_value(
        get_ci(
            data,
            "ownerSerialNo",
            "ownerSerialNumber",
            "owner_serial_no",
            "owner_serial_number"
        ),
        get_ci(
            ownership,
            "Owner Serial No",
            "Owner Serial Number"
        )
    )

    # =========================================================
    # FINANCE DETAILS
    # =========================================================

    financier_name = first_value(
        get_ci(
            data,
            "rcFinancer",
            "rc_financer",
            "financierName",
            "financerName",
            "financier_name",
            "financer_name"
        ),
        get_ci(
            ownership,
            "Financier Name",
            "Financer Name"
        ),
        get_ci(
            other,
            "Financier Name",
            "Financer Name"
        )
    )

    financed = first_value(
        get_ci(
            data,
            "financed",
            "isFinanced",
            "is_financed"
        )
    )

    # =========================================================
    # VEHICLE DETAILS
    # =========================================================

    manufacturer_name = first_value(
        get_ci(
            data,
            "vehicleManufacturerName",
            "vehicle_manufacturer_name",
            "manufacturerName",
            "manufacturer_name",
            "maker",
            "make"
        ),
        get_ci(
            vehicle,
            "Model Name",
            "Manufacturer Name",
            "Maker Name"
        ),
        get_ci(
            best_mmv,
            "make_display_name",
            "makeDisplayName"
        )
    )

    model_name = first_value(
        get_ci(
            data,
            "model",
            "modelName",
            "model_name"
        ),
        get_ci(
            vehicle,
            "Maker Model",
            "Model"
        ),
        get_ci(
            basic,
            "Modal Name",
            "Model Name"
        ),
        get_ci(
            best_mmv,
            "model_display_name",
            "modelDisplayName"
        )
    )

    variant_name = first_value(
        get_ci(
            data,
            "variant",
            "variantName",
            "variant_name"
        ),
        get_ci(
            best_mmv,
            "variant_display_name",
            "variantDisplayName"
        )
    )

    vehicle_class = first_value(
        get_ci(
            data,
            "vehicleClass",
            "vehicle_class",
            "class"
        ),
        get_ci(
            vehicle,
            "Vehicle Class"
        )
    )

    vehicle_category = first_value(
        get_ci(
            data,
            "vehicleCategory",
            "vehicle_category",
            "category"
        ),
        get_ci(
            best_mmv,
            "vehicle_type",
            "vehicleType"
        )
    )

    body_type = first_value(
        get_ci(
            data,
            "bodyType",
            "body_type"
        ),
        get_ci(
            vehicle,
            "Body Type"
        )
    )

    vehicle_colour = first_value(
        get_ci(
            data,
            "vehicleColour",
            "vehicleColor",
            "vehicle_colour",
            "vehicle_color",
            "colour",
            "color"
        ),
        get_ci(
            vehicle,
            "Vehicle Colour",
            "Vehicle Color",
            "Colour",
            "Color"
        )
    )

    fuel_type = first_value(
        get_ci(
            data,
            "type",
            "fuelType",
            "fuel_type"
        ),
        get_ci(
            vehicle,
            "Fuel Type"
        ),
        get_ci(
            best_mmv,
            "fuelType",
            "fuel_type"
        )
    )

    fuel_norms = first_value(
        get_ci(
            data,
            "normsType",
            "norms_type",
            "fuelNorms",
            "fuel_norms",
            "emissionNorms",
            "emission_norms"
        ),
        get_ci(
            vehicle,
            "Fuel Norms",
            "Emission Norms"
        )
    )

    chassis_number = first_value(
        get_ci(
            data,
            "chassis",
            "chassisNumber",
            "chassis_number"
        ),
        get_ci(
            vehicle,
            "Chassis Number"
        )
    )

    engine_number = first_value(
        get_ci(
            data,
            "engine",
            "engineNumber",
            "engine_number"
        ),
        get_ci(
            vehicle,
            "Engine Number"
        )
    )

    # =========================================================
    # VEHICLE STATUS
    # =========================================================

    vehicle_status = first_value(
        get_ci(
            data,
            "status",
            "vehicleStatus",
            "vehicle_status"
        ),
        get_ci(
            vehicle,
            "Status",
            "Vehicle Status"
        )
    )

    status_as_on = first_value(
        get_ci(
            data,
            "statusAsOn",
            "status_as_on"
        )
    )

    blacklist_status = first_value(
        get_ci(
            data,
            "blacklistStatus",
            "blacklist_status"
        ),
        get_ci(
            other,
            "Blacklist Status"
        )
    )

    blacklist_details = first_value(
        get_ci(
            data,
            "blacklistDetails",
            "blacklist_details"
        ),
        get_ci(
            other,
            "Blacklist Details"
        )
    )

    non_use_status = first_value(
        get_ci(
            data,
            "nonUseStatus",
            "non_use_status"
        )
    )

    # =========================================================
    # INSURANCE DETAILS
    # =========================================================

    insurance_company = first_value(
        get_ci(
            data,
            "vehicleInsuranceCompanyName",
            "vehicle_insurance_company_name",
            "insuranceCompany",
            "insurance_company"
        ),
        get_ci(
            insurance,
            "Insurance Company"
        )
    )

    insurance_number = first_value(
        get_ci(
            data,
            "vehicleInsurancePolicyNumber",
            "vehicle_insurance_policy_number",
            "insurancePolicyNumber",
            "insurance_policy_number"
        ),
        get_ci(
            insurance,
            "Insurance No",
            "Insurance Number",
            "Policy Number"
        )
    )

    insurance_upto = first_value(
        get_ci(
            data,
            "vehicleInsuranceUpto",
            "vehicle_insurance_upto",
            "insuranceValidity",
            "insurance_validity",
            "insuranceUpto",
            "insurance_upto"
        ),
        get_ci(
            dates,
            "Insurance Upto",
            "Insurance Expiry",
            "Insurance Validity"
        ),
        find_insurance_validity(insurance)
    )

    insurance_expiry_in = first_value(
        get_ci(
            data,
            "insuranceExpiryIn",
            "insurance_expiry_in"
        ),
        get_ci(
            dates,
            "Insurance Expiry In"
        )
    )

    insurance_expired_days = first_value(
        get_ci(
            data,
            "insuranceExpiredDays",
            "insurance_expired_days"
        ),
        get_ci(
            insurance_alert,
            "Expired Days",
            "Insurance Expired Days"
        )
    )

    # =========================================================
    # PUC / PUCC DETAILS
    # =========================================================

    pucc_number = first_value(
        get_ci(
            data,
            "puccNumber",
            "pucc_number",
            "pucNumber",
            "puc_number",
            "pucNo",
            "puc_no"
        ),
        get_ci(
            dates,
            "PUCC Number",
            "PUC Number",
            "PUCC No",
            "PUC No"
        ),
        get_ci(
            other,
            "PUCC Number",
            "PUC Number",
            "PUCC No",
            "PUC No"
        )
    )

    pucc_upto = first_value(
        get_ci(
            data,
            "puccUpto",
            "pucc_upto",
            "puccValidity",
            "pucc_validity",
            "pucUpto",
            "puc_upto",
            "pucValidity",
            "puc_validity"
        ),
        get_ci(
            dates,
            "PUCC Upto",
            "PUC Upto",
            "PUCC Validity",
            "PUC Validity"
        ),
        get_ci(
            other,
            "PUCC Upto",
            "PUC Upto"
        )
    )

    pucc_expiry_in = first_value(
        get_ci(
            data,
            "puccExpiryIn",
            "pucc_expiry_in",
            "pucExpiryIn",
            "puc_expiry_in"
        ),
        get_ci(
            dates,
            "PUCC Expiry In",
            "PUC Expiry In"
        )
    )

    # =========================================================
    # TAX DETAILS
    # =========================================================

    tax_upto = first_value(
        get_ci(
            data,
            "vehicleTaxUpto",
            "vehicle_tax_upto",
            "taxUpto",
            "tax_upto"
        ),
        get_ci(
            dates,
            "Tax Upto"
        )
    )

    # =========================================================
    # ADDRESS DETAILS
    # =========================================================

    present_address = first_value(
        get_ci(
            data,
            "presentAddress",
            "present_address",
            "currentAddress",
            "current_address"
        ),
        get_ci(
            ownership,
            "Present Address",
            "Current Address"
        )
    )

    permanent_address = first_value(
        get_ci(
            data,
            "permanentAddress",
            "permanent_address"
        ),
        get_ci(
            ownership,
            "Permanent Address"
        )
    )

    # =========================================================
    # CAPACITY AND DIMENSION DETAILS
    # =========================================================

    cubic_capacity = first_value(
        get_ci(
            data,
            "vehicleCubicCapacity",
            "vehicle_cubic_capacity",
            "cubicCapacity",
            "cubic_capacity"
        ),
        get_ci(
            other,
            "Cubic Capacity"
        ),
        get_ci(
            best_mmv,
            "cubic_capacity",
            "cubicCapacity"
        )
    )

    gross_vehicle_weight = first_value(
        get_ci(
            data,
            "grossVehicleWeight",
            "gross_vehicle_weight"
        ),
        get_ci(
            other,
            "Gross Vehicle Weight"
        )
    )

    unladen_weight = first_value(
        get_ci(
            data,
            "unladenWeight",
            "unladen_weight"
        ),
        get_ci(
            other,
            "Unladen Weight"
        )
    )

    cylinder_count = first_value(
        get_ci(
            data,
            "vehicleCylindersNo",
            "vehicle_cylinders_no",
            "cylindersNo",
            "cylinders_no"
        ),
        get_ci(
            other,
            "Number Of Cylinders",
            "Cylinder Count"
        )
    )

    seating_capacity = first_value(
        get_ci(
            data,
            "vehicleSeatCapacity",
            "vehicle_seat_capacity",
            "seatingCapacity",
            "seating_capacity"
        ),
        get_ci(
            other,
            "Seating Capacity"
        ),
        get_ci(
            best_mmv,
            "seating_capacity",
            "seatingCapacity"
        )
    )

    sleeper_capacity = first_value(
        get_ci(
            data,
            "vehicleSleeperCapacity",
            "vehicle_sleeper_capacity",
            "sleeperCapacity",
            "sleeper_capacity"
        ),
        get_ci(
            other,
            "Sleeper Capacity"
        )
    )

    standing_capacity = first_value(
        get_ci(
            data,
            "vehicleStandingCapacity",
            "vehicle_standing_capacity",
            "standingCapacity",
            "standing_capacity"
        ),
        get_ci(
            other,
            "Standing Capacity"
        )
    )

    wheelbase = first_value(
        get_ci(
            data,
            "wheelbase",
            "wheelBase",
            "wheel_base"
        ),
        get_ci(
            other,
            "Wheelbase",
            "Wheel Base"
        )
    )

    standard_capacity = first_value(
        get_ci(
            data,
            "rcStandardCap",
            "rc_standard_cap",
            "standardCapacity",
            "standard_capacity"
        ),
        get_ci(
            other,
            "Standard Capacity"
        )
    )

    # =========================================================
    # LEGAL / PERMIT DETAILS
    # =========================================================

    permit_type = first_value(
        get_ci(
            data,
            "permitType",
            "permit_type"
        ),
        get_ci(
            other,
            "Permit Type"
        )
    )

    noc_details = first_value(
        get_ci(
            data,
            "nocDetails",
            "noc_details"
        ),
        get_ci(
            other,
            "NOC Details"
        )
    )

    is_commercial = first_value(
        get_ci(
            data,
            "isCommercial",
            "is_commercial"
        )
    )

    electric_vehicle = first_value(
        get_ci(
            data,
            "electricVehicle",
            "electric_vehicle",
            "isElectricVehicle",
            "is_electric_vehicle"
        )
    )

    # =========================================================
    # BASIC RTO CARD DETAILS
    # =========================================================

    city_name = first_value(
        get_ci(
            data,
            "cityName",
            "city_name"
        ),
        get_ci(
            basic,
            "City Name"
        )
    )

    rto_phone = first_value(
        get_ci(
            data,
            "rtoPhone",
            "rto_phone"
        ),
        get_ci(
            basic,
            "Phone"
        )
    )

    rto_website = first_value(
        get_ci(
            data,
            "rtoWebsite",
            "rto_website"
        ),
        get_ci(
            basic,
            "Website"
        )
    )

    rto_address = first_value(
        get_ci(
            data,
            "rtoAddress",
            "rto_address"
        ),
        get_ci(
            basic,
            "Address"
        )
    )

    # =========================================================
    # BEST MMV MODEL MATCH
    # =========================================================

    mmv_match_score = first_value(
        get_ci(
            best_mmv,
            "score"
        )
    )

    mmv_make_id = first_value(
        get_ci(
            best_mmv,
            "make_id",
            "makeId"
        )
    )

    mmv_model_id = first_value(
        get_ci(
            best_mmv,
            "model_id",
            "modelId"
        )
    )

    mmv_variant_id = first_value(
        get_ci(
            best_mmv,
            "variant_id",
            "variantId"
        )
    )

    ex_showroom_price = first_value(
        get_ci(
            best_mmv,
            "ex_show_room_price",
            "exShowRoomPrice"
        )
    )

    # =========================================================
    # API METADATA
    # =========================================================

    db_result = first_value(
        get_ci(
            data,
            "dbResult",
            "db_result"
        )
    )

    partial_data = first_value(
        get_ci(
            data,
            "partialData",
            "partial_data"
        )
    )

    # =========================================================
    # BUILD FINAL RESULT
    # =========================================================

    result = {}

    # Registration
    add_field(result, "RegistrationNumber", registration_number)
    add_field(result, "RegistrationDate", registration_date)
    add_field(result, "RegistrationAuthority", registered_rto)
    add_field(result, "RTOCode", rto_code)
    add_field(result, "RCExpiryDate", rc_expiry_date)
    add_field(result, "VehicleAge", vehicle_age)
    add_field(
        result,
        "ManufacturingMonthYear",
        manufacturing_month_year
    )

    # Owner
    add_field(result, "OwnerName", owner_name)
    add_field(result, "OwnerFatherName", owner_father_name)
    add_field(result, "OwnerNumber", owner_number)
    add_field(result, "OwnerCount", owner_count)
    add_field(result, "OwnerSerialNumber", owner_serial_number)

    # Finance
    add_field(result, "FinancierName", financier_name)
    add_field(result, "Financed", financed)

    # Vehicle
    add_field(result, "ManufacturerName", manufacturer_name)
    add_field(result, "ModelName", model_name)
    add_field(result, "VariantName", variant_name)
    add_field(result, "VehicleClass", vehicle_class)
    add_field(result, "VehicleCategory", vehicle_category)
    add_field(result, "BodyType", body_type)
    add_field(result, "VehicleColour", vehicle_colour)
    add_field(result, "FuelType", fuel_type)
    add_field(result, "FuelNorms", fuel_norms)
    add_field(result, "ChassisNumber", chassis_number)
    add_field(result, "EngineNumber", engine_number)

    # Status
    add_field(result, "VehicleStatus", vehicle_status)
    add_field(result, "StatusAsOn", status_as_on)
    add_field(result, "BlacklistStatus", blacklist_status)
    add_field(result, "BlacklistDetails", blacklist_details)
    add_field(result, "NonUseStatus", non_use_status)

    # Insurance
    add_field(result, "InsuranceCompany", insurance_company)
    add_field(result, "InsuranceNumber", insurance_number)
    add_field(result, "InsuranceUpto", insurance_upto)
    add_field(result, "InsuranceExpiryIn", insurance_expiry_in)
    add_field(
        result,
        "InsuranceExpiredDays",
        insurance_expired_days
    )

    # PUC / PUCC
    add_field(result, "PUCCNumber", pucc_number)
    add_field(result, "PUCCUpto", pucc_upto)
    add_field(result, "PUCCExpiryIn", pucc_expiry_in)

    # Tax
    add_field(result, "TaxUpto", tax_upto)

    # Address
    add_field(result, "PresentAddress", present_address)
    add_field(result, "PermanentAddress", permanent_address)

    # Capacity and dimensions
    add_field(result, "CubicCapacity", cubic_capacity)
    add_field(result, "GrossVehicleWeight", gross_vehicle_weight)
    add_field(result, "UnladenWeight", unladen_weight)
    add_field(result, "CylinderCount", cylinder_count)
    add_field(result, "SeatingCapacity", seating_capacity)
    add_field(result, "SleeperCapacity", sleeper_capacity)
    add_field(result, "StandingCapacity", standing_capacity)
    add_field(result, "Wheelbase", wheelbase)
    add_field(result, "StandardCapacity", standard_capacity)

    # Legal
    add_field(result, "PermitType", permit_type)
    add_field(result, "NOCDetails", noc_details)
    add_field(result, "IsCommercial", is_commercial)
    add_field(result, "ElectricVehicle", electric_vehicle)

    # RTO contact
    add_field(result, "CityName", city_name)
    add_field(result, "RTOPhone", rto_phone)
    add_field(result, "RTOWebsite", rto_website)
    add_field(result, "RTOAddress", rto_address)

    # Best model match
    add_field(result, "MMVMatchScore", mmv_match_score)
    add_field(result, "MMVMakeID", mmv_make_id)
    add_field(result, "MMVModelID", mmv_model_id)
    add_field(result, "MMVVariantID", mmv_variant_id)
    add_field(result, "ExShowroomPrice", ex_showroom_price)

    # API metadata
    add_field(result, "DatabaseResult", db_result)
    add_field(result, "PartialData", partial_data)

    return result if result else None

__all__ = ["vehicle_extract_data"]
