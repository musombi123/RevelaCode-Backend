from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# =========================================================
# FILES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

LOCATIONS_FILE = BASE_DIR / "kenya_locations.json"
WARDS_FILE = BASE_DIR / "wards.json"

OUTPUT_FILE = BASE_DIR / "kenya_locations_merged.json"


# =========================================================
# NAME NORMALIZATION
# =========================================================

def normalize(value: Any) -> str:
    """
    Normalize names for reliable comparisons.

    Examples:
        "Lunga Lunga" -> "lungalunga"
        "Lungalunga"  -> "lungalunga"
        "Port reitz"  -> "portreitz"
        "Mt. Elgon"  -> "mtelgon"
        "Lang’ata"    -> "langata"
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    replacements = {
        "&": "and",
        "'": "",
        "’": "",
        "`": "",
        "-": "",
        "/": "",
        ".": "",
        "–": "",
        "—": "",
        "(": "",
        ")": "",
        ",": "",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = re.sub(r"\s+", "", value)

    return value


# =========================================================
# KNOWN NAME ALIASES
# =========================================================

ALIASES = {
    # Kwale
    normalize("Lunga Lunga"): normalize("Lungalunga"),

    # Mombasa
    normalize("Jomvu Kuu"): normalize("Jomvu"),
    normalize("Jomvu kuu"): normalize("Jomvu"),

    # Nairobi
    normalize("Lang’ata"): normalize("Langata"),
    normalize("Lang'ata"): normalize("Langata"),

    # Bungoma
    normalize("Mt. Elgon"): normalize("Mt Elgon"),
    normalize("Mt. Elgon"): normalize("Mt Elgon"),

    # Common spelling variations
    normalize("Tindiret"): normalize("Tinderet"),
    normalize("Mumias East"): normalize("Mumias East"),
}


def canonical_name(value: Any) -> str:
    normalized = normalize(value)

    return ALIASES.get(
        normalized,
        normalized,
    )


# =========================================================
# LOAD JSON
# =========================================================

def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"\nFile not found:\n  {path}\n"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"\nInvalid JSON in:\n  {path}\n"
            f"Line: {exc.lineno}\n"
            f"Column: {exc.colno}\n"
            f"Message: {exc.msg}\n"
        ) from exc


# =========================================================
# BUILD COUNTY INDEX FROM SUB-COUNTIES
# =========================================================

def build_existing_indexes(
    locations: dict,
) -> tuple[
    dict[str, dict],
    dict[str, list[dict]],
]:
    """
    Builds indexes from the existing location dataset.

    Returns:

        subcounty_index:
            normalized sub-county name
                ->
            list of possible county/sub-county records

        county_index:
            normalized county name
                ->
            county object
    """

    subcounty_index: dict[str, list[dict]] = {}

    county_index: dict[str, dict] = {}

    for county in locations.get("counties", []):
        county_name = county.get("name", "").strip()

        if not county_name:
            continue

        county_key = canonical_name(county_name)

        county_index[county_key] = county

        for sub_county in county.get("sub_counties", []):
            sub_name = sub_county.get("name", "").strip()

            if not sub_name:
                continue

            sub_key = canonical_name(sub_name)

            subcounty_index.setdefault(
                sub_key,
                [],
            ).append(
                {
                    "county": county,
                    "sub_county": sub_county,
                }
            )

    return subcounty_index, county_index


# =========================================================
# EXPLICIT CONSTITUENCY -> COUNTY MAP
# =========================================================

def build_constituency_map() -> dict[str, str]:
    """
    Known constituency -> county relationships.

    IMPORTANT:
    This map is intentionally separate from sub-counties because
    constituency and administrative sub-county are not guaranteed
    to be identical concepts.

    The map below covers the constituency names used in the supplied
    wards dataset.

    Format:

        "normalized constituency": "normalized county"
    """

    raw_map = {

        # -----------------------------------------------------
        # MOMBASA
        # -----------------------------------------------------
        "Changamwe": "Mombasa",
        "Jomvu": "Mombasa",
        "Kisauni": "Mombasa",
        "Likoni": "Mombasa",
        "Mvita": "Mombasa",
        "Nyali": "Mombasa",

        # -----------------------------------------------------
        # KWALE
        # -----------------------------------------------------
        "Kinango": "Kwale",
        "Lungalunga": "Kwale",
        "Matuga": "Kwale",
        "Msambweni": "Kwale",

        # -----------------------------------------------------
        # KILIFI
        # -----------------------------------------------------
        "Kilifi North": "Kilifi",
        "Kilifi South": "Kilifi",
        "Kaloleni": "Kilifi",
        "Ganze": "Kilifi",
        "Malindi": "Kilifi",
        "Magarini": "Kilifi",
        "Rabai": "Kilifi",

        # -----------------------------------------------------
        # TANA RIVER
        # -----------------------------------------------------
        "Garsen": "Tana River",
        "Galole": "Tana River",
        "Bura": "Tana River",

        # -----------------------------------------------------
        # LAMU
        # -----------------------------------------------------
        "Lamu East": "Lamu",
        "Lamu West": "Lamu",

        # -----------------------------------------------------
        # TAITA-TAVETA
        # -----------------------------------------------------
        "Voi": "Taita-Taveta",
        "Wundanyi": "Taita-Taveta",
        "Mwatate": "Taita-Taveta",
        "Taveta": "Taita-Taveta",

        # -----------------------------------------------------
        # GARISSA
        # -----------------------------------------------------
        "Dadaab": "Garissa",
        "Fafi": "Garissa",
        "Ijara": "Garissa",
        "Lagdera": "Garissa",
        "Balambala": "Garissa",
        "Garissa Township": "Garissa",

        # -----------------------------------------------------
        # WAJIR
        # -----------------------------------------------------
        "Wajir East": "Wajir",
        "Wajir North": "Wajir",
        "Wajir South": "Wajir",
        "Wajir West": "Wajir",
        "Tarbaj": "Wajir",
        "Eldas": "Wajir",

        # -----------------------------------------------------
        # MANDERA
        # -----------------------------------------------------
        "Mandera West": "Mandera",
        "Mandera East": "Mandera",
        "Mandera North": "Mandera",
        "Mandera South": "Mandera",
        "Banissa": "Mandera",
        "Lafey": "Mandera",

        # -----------------------------------------------------
        # MARSABIT
        # -----------------------------------------------------
        "Moyale": "Marsabit",
        "North Horr": "Marsabit",
        "Laisamis": "Marsabit",
        "Saku": "Marsabit",

        # -----------------------------------------------------
        # ISIOLO
        # -----------------------------------------------------
        "Isiolo North": "Isiolo",
        "Isiolo South": "Isiolo",

        # -----------------------------------------------------
        # MERU
        # -----------------------------------------------------
        "Igembe Central": "Meru",
        "Igembe North": "Meru",
        "Igembe South": "Meru",
        "Tigania East": "Meru",
        "Tigania West": "Meru",
        "North Imenti": "Meru",
        "South Imenti": "Meru",
        "Central Imenti": "Meru",
        "Buuri": "Meru",

        # -----------------------------------------------------
        # THARAKA-NITHI
        # -----------------------------------------------------
        "Chuka/Igambang'ombe": "Tharaka-Nithi",
        "Chuka/Igambang’ombe": "Tharaka-Nithi",
        "Maara": "Tharaka-Nithi",
        "Tharaka": "Tharaka-Nithi",

        # -----------------------------------------------------
        # EMBU
        # -----------------------------------------------------
        "Manyatta": "Embu",
        "Mbeere North": "Embu",
        "Mbeere South": "Embu",
        "Runyenjes": "Embu",

        # -----------------------------------------------------
        # KITUI
        # -----------------------------------------------------
        "Kitui Central": "Kitui",
        "Kitui East": "Kitui",
        "Kitui Rural": "Kitui",
        "Kitui West": "Kitui",
        "Kitui South": "Kitui",
        "Mwingi Central": "Kitui",
        "Mwingi North": "Kitui",
        "Mwingi West": "Kitui",
        "Mwingi East": "Kitui",
        "Kyuso": "Kitui",
        "Mutomo": "Kitui",

        # -----------------------------------------------------
        # MACHAKOS
        # -----------------------------------------------------
        "Masinga": "Machakos",
        "Yatta": "Machakos",
        "Kangundo": "Machakos",
        "Matungulu": "Machakos",
        "Kathiani": "Machakos",
        "Machakos Town": "Machakos",
        "Mavoko": "Machakos",
        "Mwala": "Machakos",
        "Kalama": "Machakos",

        # -----------------------------------------------------
        # MAKUENI
        # -----------------------------------------------------
        "Makueni": "Makueni",
        "Kibwezi East": "Makueni",
        "Kibwezi West": "Makueni",
        "Kilome": "Makueni",
        "Kaiti": "Makueni",
        "Mbooni": "Makueni",

        # -----------------------------------------------------
        # NYANDARUA
        # -----------------------------------------------------
        "Kinangop": "Nyandarua",
        "Kipipiri": "Nyandarua",
        "Ndaragwa": "Nyandarua",
        "Ol Kalou": "Nyandarua",
        "Ol Jorok": "Nyandarua",

        # -----------------------------------------------------
        # NYERI
        # -----------------------------------------------------
        "Tetu": "Nyeri",
        "Kieni": "Nyeri",
        "Mathira": "Nyeri",
        "Nyeri Town": "Nyeri",
        "Mukurweini": "Nyeri",
        "Othaya": "Nyeri",

        # -----------------------------------------------------
        # KIRINYAGA
        # -----------------------------------------------------
        "Mwea": "Kirinyaga",
        "Kirinyaga Central": "Kirinyaga",
        "Ndia": "Kirinyaga",
        "Gichugu": "Kirinyaga",

        # -----------------------------------------------------
        # MURANG'A
        # -----------------------------------------------------
        "Kangema": "Murang'a",
        "Mathioya": "Murang'a",
        "Kiharu": "Murang'a",
        "Kigumo": "Murang'a",
        "Maragua": "Murang'a",
        "Maragwa": "Murang'a",
        "Gatanga": "Murang'a",
        "Kandara": "Murang'a",
        # -----------------------------------------------------
        # KIAMBU
        # -----------------------------------------------------
        "Gatundu North": "Kiambu",
        "Gatundu South": "Kiambu",
        "Githunguri": "Kiambu",
        "Juja": "Kiambu",
        "Kabete": "Kiambu",
        "Kiambaa": "Kiambu",
        "Kiambu": "Kiambu",
        "Kikuyu": "Kiambu",
        "Lari": "Kiambu",
        "Limuru": "Kiambu",
        "Ruiru": "Kiambu",
        "Thika Town": "Kiambu",

        # -----------------------------------------------------
        # TURKANA
        # -----------------------------------------------------
        "Turkana Central": "Turkana",
        "Turkana East": "Turkana",
        "Turkana North": "Turkana",
        "Turkana South": "Turkana",
        "Turkana West": "Turkana",
        "Loima": "Turkana",

        # -----------------------------------------------------
        # WEST POKOT
        # -----------------------------------------------------
        "Kacheliba": "West Pokot",
        "Kapenguria": "West Pokot",
        "Pokot South": "West Pokot",
        "Sigor": "West Pokot",

        # -----------------------------------------------------
        # SAMBURU
        # -----------------------------------------------------
        "Samburu East": "Samburu",
        "Samburu North": "Samburu",
        "Samburu West": "Samburu",

        # -----------------------------------------------------
        # TRANS NZOIA
        # -----------------------------------------------------
        "Kwanza": "Trans Nzoia",
        "Endebess": "Trans Nzoia",
        "Kiminini": "Trans Nzoia",
        "Saboti": "Trans Nzoia",
        "Cherangany": "Trans Nzoia",

        # -----------------------------------------------------
        # UASIN GISHU
        # -----------------------------------------------------
        "Ainabkoi": "Uasin Gishu",
        "Kapseret": "Uasin Gishu",
        "Kesses": "Uasin Gishu",
        "Moiben": "Uasin Gishu",
        "Soy": "Uasin Gishu",
        "Turbo": "Uasin Gishu",

        # -----------------------------------------------------
        # ELGEYO-MARAKWET
        # -----------------------------------------------------
        "Keiyo North": "Elgeyo-Marakwet",
        "Keiyo South": "Elgeyo-Marakwet",
        "Marakwet East": "Elgeyo-Marakwet",
        "Marakwet West": "Elgeyo-Marakwet",

        # -----------------------------------------------------
        # NANDI
        # -----------------------------------------------------
        "Mosop": "Nandi",
        "Emgwen": "Nandi",
        "Chesumei": "Nandi",
        "Aldai": "Nandi",
        "Nandi Hills": "Nandi",
        "Tinderet": "Nandi",

        # -----------------------------------------------------
        # BARINGO
        # -----------------------------------------------------
        "Baringo Central": "Baringo",
        "Baringo North": "Baringo",
        "Baringo South": "Baringo",
        "Mogotio": "Baringo",
        "Eldama Ravine": "Baringo",
        "Tiaty": "Baringo",

        # -----------------------------------------------------
        # LAIKIPIA
        # -----------------------------------------------------
        "Laikipia East": "Laikipia",
        "Laikipia North": "Laikipia",
        "Laikipia West": "Laikipia",

        # -----------------------------------------------------
        # NAKURU
        # -----------------------------------------------------
        "Bahati": "Nakuru",
        "Molo": "Nakuru",
        "Njoro": "Nakuru",
        "Naivasha": "Nakuru",
        "Gilgil": "Nakuru",
        "Subukia": "Nakuru",
        "Rongai": "Nakuru",
        "Kuresoi North": "Nakuru",
        "Kuresoi South": "Nakuru",
        "Nakuru Town East": "Nakuru",
        "Nakuru Town West": "Nakuru",

        # -----------------------------------------------------
        # NAROK
        # -----------------------------------------------------
        "Narok North": "Narok",
        "Narok East": "Narok",
        "Narok South": "Narok",
        "Narok West": "Narok",
        "Kilgoris": "Narok",

        # -----------------------------------------------------
        # KAJIADO
        # -----------------------------------------------------
        "Kajiado Central": "Kajiado",
        "Kajiado East": "Kajiado",
        "Kajiado North": "Kajiado",
        "Kajiado South": "Kajiado",
        "Kajiado West": "Kajiado",

        # -----------------------------------------------------
        # KERICHO
        # -----------------------------------------------------
        "Ainamoi": "Kericho",
        "Belgut": "Kericho",
        "Bureti": "Kericho",
        "Kipkelion East": "Kericho",
        "Kipkelion West": "Kericho",
        "Sigowet/Soin": "Kericho",

        # -----------------------------------------------------
        # BOMET
        # -----------------------------------------------------
        "Bomet Central": "Bomet",
        "Bomet East": "Bomet",
        "Chepalungu": "Bomet",
        "Konoin": "Bomet",
        "Sotik": "Bomet",
        "Emurua Dikirr": "Narok",

        # -----------------------------------------------------
        # KAKAMEGA
        # -----------------------------------------------------
        "Butere": "Kakamega",
        "Khwisero": "Kakamega",
        "Likuyani": "Kakamega",
        "Lugari": "Kakamega",
        "Lurambi": "Kakamega",
        "Malava": "Kakamega",
        "Matungu": "Kakamega",
        "Mumias East": "Kakamega",
        "Mumias West": "Kakamega",
        "Navakholo": "Kakamega",

        # -----------------------------------------------------
        # VIHIGA
        # -----------------------------------------------------
        "Emuhaya": "Vihiga",
        "Vihiga": "Vihiga",
        "Sabatia": "Vihiga",
        "Luanda": "Vihiga",
        "Hamisi": "Vihiga",
        "Ikolomani": "Vihiga",
        "Shinyalu": "Kakamega",

        # -----------------------------------------------------
        # BUNGOMA
        # -----------------------------------------------------
        "Bumula": "Bungoma",
        "Kabuchai": "Bungoma",
        "Kanduyi": "Bungoma",
        "Kimilili": "Bungoma",
        "Mt Elgon": "Bungoma",
        "Sirisia": "Bungoma",
        "Tongaren": "Bungoma",
        "Webuye East": "Bungoma",
        "Webuye West": "Bungoma",

        # -----------------------------------------------------
        # BUSIA
        # -----------------------------------------------------
        "Budalangi": "Busia",
        "Butula": "Busia",
        "Funyula": "Busia",
        "Matayos": "Busia",
        "Nambale": "Busia",
        "Teso North": "Busia",
        "Teso South": "Busia",

        # -----------------------------------------------------
        # SIAYA
        # -----------------------------------------------------
        "Alego Usonga": "Siaya",
        "Bondo": "Siaya",
        "Gem": "Siaya",
        "Rarieda": "Siaya",
        "Ugenya": "Siaya",
        "Ugunja": "Siaya",

        # -----------------------------------------------------
        # KISUMU
        # -----------------------------------------------------
        "Kisumu Central": "Kisumu",
        "Kisumu East": "Kisumu",
        "Kisumu West": "Kisumu",
        "Seme": "Kisumu",
        "Muhoroni": "Kisumu",
        "Nyando": "Kisumu",
        "Nyakach": "Kisumu",

        # -----------------------------------------------------
        # HOMA BAY
        # -----------------------------------------------------
        "Homa Bay Town": "Homa Bay",
        "Kabondo Kasipul": "Homa Bay",
        "Karachuonyo": "Homa Bay",
        "Kasipul": "Homa Bay",
        "Mbita": "Homa Bay",
        "Ndhiwa": "Homa Bay",
        "Rangwe": "Homa Bay",
        "Suba": "Homa Bay",

        # -----------------------------------------------------
        # MIGORI
        # -----------------------------------------------------
        "Awendo": "Migori",
        "Kuria East": "Migori",
        "Kuria West": "Migori",
        "Nyatike": "Migori",
        "Rongo": "Migori",
        "Suna East": "Migori",
        "Suna West": "Migori",
        "Uriri": "Migori",

        # -----------------------------------------------------
        # KISII
        # -----------------------------------------------------
        "Bobasi": "Kisii",
        "Bonchari": "Kisii",
        "Bomachoge Borabu": "Kisii",
        "Bomachoge Chache": "Kisii",
        "Kitutu Chache North": "Kisii",
        "Kitutu Chache South": "Kisii",
        "Nyaribari Chache": "Kisii",
        "Nyaribari Masaba": "Kisii",
        "South Mugirango": "Kisii",
        "West Mugirango": "Nyamira",
        "North Mugirango": "Nyamira",
        "Kitutu Masaba": "Nyamira",
        "Borabu": "Nyamira",

        # -----------------------------------------------------
        # NAIROBI
        # -----------------------------------------------------
        "Dagoretti North": "Nairobi City",
        "Dagoretti South": "Nairobi City",
        "Embakasi Central": "Nairobi City",
        "Embakasi East": "Nairobi City",
        "Embakasi North": "Nairobi City",
        "Embakasi South": "Nairobi City",
        "Embakasi West": "Nairobi City",
        "Kamukunji": "Nairobi City",
        "Kasarani": "Nairobi City",
        "Kibra": "Nairobi City",
        "Langata": "Nairobi City",
        "Makadara": "Nairobi City",
        "Mathare": "Nairobi City",
        "Roysambu": "Nairobi City",
        "Ruaraka": "Nairobi City",
        "Starehe": "Nairobi City",
        "Westlands": "Nairobi City",
    }

    return {
        canonical_name(constituency): canonical_name(county)
        for constituency, county in raw_map.items()
    }


# =========================================================
# MERGE WARDS
# =========================================================

def merge_locations(
    locations: dict,
    wards: list[dict],
) -> dict:

    county_index = {
        canonical_name(county.get("name")): county
        for county in locations.get("counties", [])
    }

    constituency_to_county = build_constituency_map()

    # -----------------------------------------------------
    # Initialize constituency arrays
    # -----------------------------------------------------

    for county in locations.get("counties", []):

        county.setdefault("constituencies", [])

        # Preserve original sub-counties exactly
        for sub_county in county.get("sub_counties", []):
            sub_county.setdefault("wards", [])

    # -----------------------------------------------------
    # Constituency lookup
    # -----------------------------------------------------

    constituency_objects: dict[str, dict] = {}

    unmatched_constituencies = []

    duplicate_ward_codes = []

    seen_codes: set[str] = set()

    merged_wards = 0

    # -----------------------------------------------------
    # Process every ward
    # -----------------------------------------------------

    for ward in wards:

        raw_code = ward.get("code")
        ward_name = str(
            ward.get("name", "")
        ).strip()

        constituency_name = str(
            ward.get("constituency", "")
        ).strip()

        # ---------------------------------------------
        # Validate required fields
        # ---------------------------------------------

        if not raw_code or not ward_name or not constituency_name:

            unmatched_constituencies.append(
                {
                    "reason": "missing_required_field",
                    "ward": ward,
                }
            )

            continue

        ward_code = str(raw_code).strip().zfill(4)

        constituency_key = canonical_name(
            constituency_name
        )

        # ---------------------------------------------
        # Duplicate ward code check
        # ---------------------------------------------

        if ward_code in seen_codes:

            duplicate_ward_codes.append(
                ward_code
            )

        else:

            seen_codes.add(ward_code)

        # ---------------------------------------------
        # Find county
        # ---------------------------------------------

        county_key = constituency_to_county.get(
            constituency_key
        )

        if not county_key:

            unmatched_constituencies.append(
                {
                    "reason": "constituency_not_mapped",
                    "ward_code": ward_code,
                    "ward_name": ward_name,
                    "constituency": constituency_name,
                }
            )

            continue

        county = county_index.get(
            county_key
        )

        if county is None:

            unmatched_constituencies.append(
                {
                    "reason": "mapped_county_not_found",
                    "ward_code": ward_code,
                    "ward_name": ward_name,
                    "constituency": constituency_name,
                    "county": county_key,
                }
            )

            continue

        # ---------------------------------------------
        # Find / create constituency
        # ---------------------------------------------

        constituency = constituency_objects.get(
            constituency_key
        )

        if constituency is None:

            constituency = next(
                (
                    item
                    for item in county["constituencies"]
                    if canonical_name(item.get("name"))
                    == constituency_key
                ),
                None,
            )

            if constituency is None:

                constituency = {
                    "id": (
                        f'{county["id"]}'
                        f'-CON-{len(county["constituencies"]) + 1:03d}'
                    ),
                    "name": constituency_name,
                    "wards": [],
                }

                county["constituencies"].append(
                    constituency
                )

            constituency_objects[
                constituency_key
            ] = constituency

        # ---------------------------------------------
        # Prevent exact duplicate ward insertion
        # ---------------------------------------------

        existing_ward = next(
            (
                item
                for item in constituency["wards"]
                if item.get("code") == ward_code
            ),
            None,
        )

        if existing_ward:

            continue

        # ---------------------------------------------
        # Add ward
        # ---------------------------------------------

        ward_record = {
            "id": (
                f'{constituency["id"]}'
                f'-W-{ward_code}'
            ),
            "code": ward_code,
            "name": ward_name,
        }

        constituency["wards"].append(
            ward_record
        )

        merged_wards += 1

    # =====================================================
    # SORT DATA
    # =====================================================

    for county in locations.get("counties", []):

        county["constituencies"].sort(
            key=lambda item: canonical_name(
                item.get("name", "")
            )
        )

        for constituency in county["constituencies"]:

            constituency["wards"].sort(
                key=lambda item: int(
                    item["code"]
                )
            )

    # =====================================================
    # STATISTICS
    # =====================================================

    county_count = len(
        locations.get("counties", [])
    )

    subcounty_count = sum(
        len(county.get("sub_counties", []))
        for county in locations.get("counties", [])
    )

    constituency_count = sum(
        len(county.get("constituencies", []))
        for county in locations.get("counties", [])
    )

    ward_count = sum(
        len(constituency.get("wards", []))
        for county in locations.get("counties", [])
        for constituency in county.get(
            "constituencies",
            [],
        )
    )

    # =====================================================
    # METADATA
    # =====================================================

    locations["version"] = "2.0.0"

    locations["administrative_levels"] = [
        "country",
        "county",
        "sub_county",
        "constituency",
        "ward",
    ]

    locations["statistics"] = {
        "counties": county_count,
        "sub_counties": subcounty_count,
        "constituencies": constituency_count,
        "wards_source_records": len(wards),
        "wards_merged": merged_wards,
        "wards_in_output": ward_count,
        "unmatched_records": len(
            unmatched_constituencies
        ),
        "duplicate_ward_codes": len(
            set(duplicate_ward_codes)
        ),
    }

    locations["sources"] = {
        "county_sub_county": (
            "kenya_locations.json"
        ),
        "wards": "wards.json",
        "merge_script": (
            "merge_locations.py"
        ),
    }

    locations["validation"] = {
        "valid": (
            len(unmatched_constituencies) == 0
            and len(set(duplicate_ward_codes)) == 0
        ),
        "unmatched_records": (
            unmatched_constituencies
        ),
        "duplicate_ward_codes": sorted(
            set(duplicate_ward_codes)
        ),
    }

    return locations


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    print("=" * 72)
    print("REVELACODE KENYA LOCATION MERGER")
    print("=" * 72)

    print("\nInput files:")

    print(
        f"  Locations : {LOCATIONS_FILE}"
    )

    print(
        f"  Wards     : {WARDS_FILE}"
    )

    print("\nLoading files...")

    locations = load_json(
        LOCATIONS_FILE
    )

    wards = load_json(
        WARDS_FILE
    )

    # -----------------------------------------------------
    # Validate top-level structures
    # -----------------------------------------------------

    if not isinstance(locations, dict):

        raise ValueError(
            "kenya_locations.json must contain a JSON object."
        )

    if not isinstance(wards, list):

        raise ValueError(
            "wards.json must contain a JSON array."
        )

    # -----------------------------------------------------
    # Input statistics
    # -----------------------------------------------------

    county_count = len(
        locations.get("counties", [])
    )

    print(
        f"\nExisting counties : {county_count}"
    )

    print(
        f"Ward source rows  : {len(wards)}"
    )

    # -----------------------------------------------------
    # Merge
    # -----------------------------------------------------

    merged = merge_locations(
        locations,
        wards,
    )

    # -----------------------------------------------------
    # Write output
    # -----------------------------------------------------

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            merged,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    # -----------------------------------------------------
    # Results
    # -----------------------------------------------------

    stats = merged["statistics"]

    validation = merged["validation"]

    print("\n" + "=" * 72)
    print("MERGE RESULT")
    print("=" * 72)

    print(
        f"\nCounties             : "
        f"{stats['counties']}"
    )

    print(
        f"Sub-counties         : "
        f"{stats['sub_counties']}"
    )

    print(
        f"Constituencies       : "
        f"{stats['constituencies']}"
    )

    print(
        f"Ward source rows     : "
        f"{stats['wards_source_records']}"
    )

    print(
        f"Wards merged         : "
        f"{stats['wards_merged']}"
    )

    print(
        f"Wards in output      : "
        f"{stats['wards_in_output']}"
    )

    print(
        f"Unmatched records     : "
        f"{stats['unmatched_records']}"
    )

    print(
        f"Duplicate ward codes : "
        f"{stats['duplicate_ward_codes']}"
    )

    print(
        "\nValidation            : "
        f"{'PASSED' if validation['valid'] else 'FAILED'}"
    )

    print(
        f"Output file           : "
        f"{OUTPUT_FILE}"
    )

    # -----------------------------------------------------
    # Show problems
    # -----------------------------------------------------

    if not validation["valid"]:

        print(
            "\n" + "-" * 72
        )

        print(
            "VALIDATION PROBLEMS"
        )

        print(
            "-" * 72
        )

        unmatched = (
            validation["unmatched_records"]
        )

        if unmatched:

            print(
                f"\nUnmatched records: "
                f"{len(unmatched)}"
            )

            for item in unmatched[:100]:

                print(
                    f"\n  Reason       : "
                    f"{item.get('reason')}"
                )

                print(
                    f"  Ward code    : "
                    f"{item.get('ward_code', '-')}"
                )

                print(
                    f"  Ward name    : "
                    f"{item.get('ward_name', '-')}"
                )

                print(
                    f"  Constituency : "
                    f"{item.get('constituency', '-')}"
                )

                if item.get("county"):

                    print(
                        f"  County       : "
                        f"{item.get('county')}"
                    )

        duplicates = (
            validation["duplicate_ward_codes"]
        )

        if duplicates:

            print(
                "\nDuplicate ward codes:"
            )

            for code in duplicates:

                print(
                    f"  - {code}"
                )

    else:

        print(
            "\nAll mapped records passed validation."
        )

    print(
        "\n" + "=" * 72
    )


if __name__ == "__main__":
    main()
