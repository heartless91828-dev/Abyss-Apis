from .common import ci_get, unwrap_data


def aadhar_fam_extract_data(res):
    """
    Aadhaar / Family / Ration Card extractor.

    Supports:
    - aadhaar
    - ration_no / rationCardNumber
    - family_members
    - members
    - memberDetailsList
    - familyMembers
    - Nested dictionary/list structures

    Missing fields are omitted.
    No field gets "Unknown".
    """

    result = {
        "Members": []
    }

    # =========================================================
    # HELPERS
    # =========================================================

    def clean(value):
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
                "n/a",
                "na",
                "nil",
                "-"
            }:
                return None

            return value

        return value

    def add_if_exists(target, key, value):
        value = clean(value)

        if value is not None:
            target[key] = value

    def get_ci(data, *keys):
        if not isinstance(data, dict):
            return None

        lower_map = {
            str(k).strip().lower(): v
            for k, v in data.items()
        }

        for key in keys:
            value = lower_map.get(
                str(key).strip().lower()
            )

            value = clean(value)

            if value is not None:
                return value

        return None

    def is_member_dict(data):
        if not isinstance(data, dict):
            return False

        normalized_keys = {
            str(k)
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
            .lower()
            for k in data.keys()
        }

        member_keys = {
            "membername",
            "memberid",
            "relationship",
            "releationshipname",
            "uid",
            "uidmasked",
            "aadhaar",
            "aadhar",
            "familyhead",
            "remark"
        }

        return bool(normalized_keys.intersection(member_keys))

    # =========================================================
    # MEMBER NORMALIZER
    # =========================================================

    def normalize_member(member):
        if not isinstance(member, dict):
            return None

        output = {}

        # Member ID
        add_if_exists(
            output,
            "MemberID",
            get_ci(
                member,
                "memberId",
                "member_id",
                "id"
            )
        )

        # Member Name
        add_if_exists(
            output,
            "MemberName",
            get_ci(
                member,
                "memberName",
                "member_name",
                "name"
            )
        )

        # State
        add_if_exists(
            output,
            "State",
            get_ci(
                member,
                "state",
                "stateName",
                "homeStateName"
            )
        )

        # District
        add_if_exists(
            output,
            "District",
            get_ci(
                member,
                "district",
                "districtName",
                "homeDistName"
            )
        )

        # Ration Card Number
        add_if_exists(
            output,
            "RationNo",
            get_ci(
                member,
                "ration_no",
                "rationNo",
                "rationNumber",
                "rationCardNumber",
                "ration_card_id",
                "rcId",
                "rc_id"
            )
        )

        # Scheme
        add_if_exists(
            output,
            "Scheme",
            get_ci(
                member,
                "scheme",
                "schemeName",
                "card_type",
                "cardType"
            )
        )

        # Relationship
        add_if_exists(
            output,
            "Relationship",
            get_ci(
                member,
                "relationship",
                "relationship_name",
                "releationship_name",
                "relation"
            )
        )

        # Aadhaar
        add_if_exists(
            output,
            "Aadhaar",
            get_ci(
                member,
                "aadhaar",
                "aadhar",
                "uid",
                "uid_masked"
            )
        )

        # Family Head
        add_if_exists(
            output,
            "FamilyHead",
            get_ci(
                member,
                "familyHead",
                "family_head"
            )
        )

        # Gender
        add_if_exists(
            output,
            "Gender",
            get_ci(
                member,
                "gender",
                "sex"
            )
        )

        # eKYC
        add_if_exists(
            output,
            "EKYCStatus",
            get_ci(
                member,
                "ekyc_status",
                "ekycStatus",
                "eKYCStatus",
                "remark"
            )
        )

        # Remark separately if available
        add_if_exists(
            output,
            "Remark",
            get_ci(
                member,
                "remark"
            )
        )

        # Serial Number
        add_if_exists(
            output,
            "SNo",
            get_ci(
                member,
                "s_no",
                "sNo",
                "serial_no",
                "serialNumber"
            )
        )

        # Last Updated
        add_if_exists(
            output,
            "LastUpdated",
            get_ci(
                member,
                "cr_last_updated",
                "last_updated",
                "lastUpdated"
            )
        )

        if output:
            return output

        return None

    # =========================================================
    # RECURSIVE SCANNER
    # =========================================================

    def scan(node):

        # -----------------------------------------------------
        # LIST
        # -----------------------------------------------------

        if isinstance(node, list):

            for item in node:

                if isinstance(item, dict):

                    if is_member_dict(item):
                        member = normalize_member(item)

                        if member:
                            result["Members"].append(member)

                    scan(item)

                elif isinstance(item, list):
                    scan(item)

            return

        # -----------------------------------------------------
        # DICT
        # -----------------------------------------------------

        if not isinstance(node, dict):
            return

        # =====================================================
        # TOP-LEVEL AADHAAR
        # =====================================================

        add_if_exists(
            result,
            "Aadhaar",
            get_ci(
                node,
                "aadhaar",
                "aadhar",
                "uid"
            )
        )

        # =====================================================
        # RATION CARD
        # =====================================================

        add_if_exists(
            result,
            "RCID",
            get_ci(
                node,
                "rcId",
                "rc_id",
                "rationCardNumber",
                "ration_card_id",
                "rationCardId",
                "ration_no",
                "rationNo"
            )
        )

        add_if_exists(
            result,
            "RationCardNumber",
            get_ci(
                node,
                "ration_no",
                "rationNo",
                "rationCardNumber",
                "ration_card_id",
                "rcId",
                "rc_id"
            )
        )

        # =====================================================
        # FPS
        # =====================================================

        add_if_exists(
            result,
            "FPSID",
            get_ci(
                node,
                "fpsId",
                "fps_id"
            )
        )

        # =====================================================
        # LOCATION
        # =====================================================

        add_if_exists(
            result,
            "State",
            get_ci(
                node,
                "state",
                "stateName",
                "homeStateName"
            )
        )

        add_if_exists(
            result,
            "District",
            get_ci(
                node,
                "district",
                "districtName",
                "homeDistName"
            )
        )

        # =====================================================
        # CARD INFORMATION
        # =====================================================

        add_if_exists(
            result,
            "Address",
            get_ci(
                node,
                "address"
            )
        )

        add_if_exists(
            result,
            "CardType",
            get_ci(
                node,
                "card_type",
                "cardType",
                "Card Type",
                "schemeName",
                "scheme"
            )
        )

        add_if_exists(
            result,
            "Scheme",
            get_ci(
                node,
                "scheme",
                "schemeName"
            )
        )

        add_if_exists(
            result,
            "IssueDate",
            get_ci(
                node,
                "issueDate",
                "Issue Date"
            )
        )

        add_if_exists(
            result,
            "HomeFPS",
            get_ci(
                node,
                "homeFPS",
                "Home FPS"
            )
        )

        add_if_exists(
            result,
            "AllowedONORC",
            get_ci(
                node,
                "allowed_onorc",
                "allowedONORC"
            )
        )

        # =====================================================
        # RESPONSE INFORMATION
        # =====================================================

        add_if_exists(
            result,
            "Status",
            get_ci(
                node,
                "status"
            )
        )

        add_if_exists(
            result,
            "Timestamp",
            get_ci(
                node,
                "timestamp",
                "time"
            )
        )

        add_if_exists(
            result,
            "Message",
            get_ci(
                node,
                "message"
            )
        )

        add_if_exists(
            result,
            "Cooldown",
            get_ci(
                node,
                "cooldown"
            )
        )

        add_if_exists(
            result,
            "FamilyCount",
            get_ci(
                node,
                "familyCount",
                "family_count"
            )
        )

        # =====================================================
        # MEMBER LISTS
        # =====================================================

        for key, value in node.items():

            key_normalized = (
                str(key)
                .strip()
                .lower()
                .replace("_", "")
                .replace("-", "")
                .replace(" ", "")
            )

            if key_normalized in {
                "members",
                "familymembers",
                "familymember",
                "memberdetailslist",
                "memberlist"
            }:

                if isinstance(value, list):

                    for member_data in value:

                        if isinstance(member_data, dict):

                            member = normalize_member(
                                member_data
                            )

                            if member:
                                result["Members"].append(
                                    member
                                )

            # Continue recursive scanning
            if isinstance(value, (dict, list)):
                scan(value)

    # =========================================================
    # START
    # =========================================================

    # If common.py unwraps API wrappers, use the unwrapped data.
    try:
        data = unwrap_data(res)
    except Exception:
        data = res

    scan(data)

    # =========================================================
    # REMOVE DUPLICATES
    # =========================================================

    unique_members = []
    seen = set()

    for member in result["Members"]:

        identity = (
            member.get("MemberID")
            or member.get("Aadhaar")
            or (
                member.get("MemberName"),
                member.get("RationNo")
            )
        )

        if identity and identity not in seen:

            seen.add(identity)
            unique_members.append(member)

    result["Members"] = unique_members

    # =========================================================
    # FAMILY COUNT
    # =========================================================

    if result.get("Members"):
        result["FamilyCount"] = len(result["Members"])

    # =========================================================
    # FINAL CLEANUP
    # =========================================================

    if not result["Members"]:
        result.pop("Members", None)

    if not result:
        return None

    return result


__all__ = ["aadhar_fam_extract_data"]