from .common import ci_get, unwrap_data

def aadhar_fam_extract_data(res):
    """
    Flexible Aadhaar / Family / Ration Card extractor.

    Supports:
    - Direct list of family members
    - data -> details -> card_info + members
    - raw_ration_data -> pd -> memberDetailsList
    - familyMembers
    - members
    - Any nested dictionary/list structure

    Missing fields are omitted completely.
    No field gets "Unknown".
    """

    result = {
        "Members": []
    }

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

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

        member_keys = {
            "membername",
            "member_name",
            "name",
            "memberid",
            "member_id",
            "relationship",
            "releationship_name",
            "uid",
            "uid_masked",
            "aadhaar",
            "familyhead"
        }

        keys = {
            str(k).replace("-", "").replace("_", "").lower()
            for k in data.keys()
        }

        return bool(
            keys.intersection(
                {
                    "membername",
                    "memberid",
                    "relationship",
                    "releationshipname",
                    "uid",
                    "uidmasked",
                    "aadhaar",
                    "familyhead"
                }
            )
        )

    # ---------------------------------------------------------
    # MEMBER NORMALIZER
    # ---------------------------------------------------------

    def normalize_member(member):
        if not isinstance(member, dict):
            return None

        output = {}

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

        add_if_exists(
            output,
            "FamilyHead",
            get_ci(
                member,
                "familyHead",
                "family_head"
            )
        )

        add_if_exists(
            output,
            "Gender",
            get_ci(
                member,
                "gender",
                "sex"
            )
        )

        add_if_exists(
            output,
            "EKYCStatus",
            get_ci(
                member,
                "ekyc_status",
                "ekycStatus"
            )
        )

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

    # ---------------------------------------------------------
    # RECURSIVE DATA SCANNER
    # ---------------------------------------------------------

    def scan(node):
        if isinstance(node, list):

            for item in node:

                if isinstance(item, dict):

                    # Direct family member
                    if is_member_dict(item):

                        member = normalize_member(item)

                        if member:
                            result["Members"].append(member)

                    # Continue scanning nested structures
                    scan(item)

                elif isinstance(item, list):
                    scan(item)

            return

        if not isinstance(node, dict):
            return

        # -----------------------------------------------------
        # CARD / RATION INFORMATION
        # -----------------------------------------------------

        add_if_exists(
            result,
            "RCID",
            get_ci(
                node,
                "rcId",
                "rc_id",
                "rationCardNumber",
                "ration_card_id",
                "rationCardId"
            )
        )

        add_if_exists(
            result,
            "FPSID",
            get_ci(
                node,
                "fpsId",
                "fps_id"
            )
        )

        add_if_exists(
            result,
            "State",
            get_ci(
                node,
                "state",
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

        add_if_exists(
            result,
            "RationCardNumber",
            get_ci(
                node,
                "rationCardNumber",
                "ration_card_id"
            )
        )

        # -----------------------------------------------------
        # MEMBERS LISTS
        # -----------------------------------------------------

        for key, value in node.items():

            key_normalized = (
                str(key)
                .strip()
                .lower()
                .replace("_", "")
                .replace("-", "")
            )

            if key_normalized in {
                "members",
                "familymembers",
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

            # Continue recursively
            if isinstance(value, (dict, list)):
                scan(value)

    # ---------------------------------------------------------
    # START SCANNING
    # ---------------------------------------------------------

    scan(res)

    # ---------------------------------------------------------
    # REMOVE DUPLICATE MEMBERS
    # ---------------------------------------------------------

    unique_members = []
    seen = set()

    for member in result["Members"]:

        identity = (
            member.get("MemberID")
            or member.get("Aadhaar")
            or member.get("MemberName")
        )

        if identity and identity not in seen:

            seen.add(identity)
            unique_members.append(member)

    result["Members"] = unique_members

    # ---------------------------------------------------------
    # FINAL CLEANUP
    # ---------------------------------------------------------

    if not result["Members"]:
        result.pop("Members", None)

    if not result:
        return None

    return result

__all__ = ["aadhar_fam_extract_data"]
