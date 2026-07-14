"""
Normalizes messy city text ("mumbai", "Bombay", "MUMBAI ") to one canonical
city + state, using the city_lookup collection. Falls back to a cleaned-up
version of the raw text (title-cased, trimmed) if there's no mapping yet —
and records that raw text as an "unmapped" variant so it shows up for you to
map properly later, instead of silently staying inconsistent forever.
"""
from typing import Optional, Tuple, List
from app.database import city_lookup_col


def _clean(raw: str) -> str:
    return " ".join(str(raw or "").strip().split()).lower()


async def normalize_city(raw_location_or_city: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (canonical_city, canonical_state). Both None if input is empty."""
    if not raw_location_or_city:
        return None, None

    cleaned = _clean(raw_location_or_city)
    mapping = await city_lookup_col.find_one({"raw_variants": cleaned})
    if mapping:
        return mapping["canonical_city"], mapping.get("canonical_state")

    # No mapping yet — best-effort fallback: title-case the raw text as the
    # "city" guess (works fine for clean input like "Pune", less well for
    # full addresses like "Kothrud, Pune" — that's what manual mapping fixes).
    fallback_city = cleaned.title()

    # Record it as unmapped so it surfaces on the City Mappings page for you
    # to properly map later (e.g. merge "kothrud, pune" into "Pune").
    await city_lookup_col.update_one(
        {"canonical_city": fallback_city, "is_unmapped_guess": True},
        {"$addToSet": {"raw_variants": cleaned},
         "$setOnInsert": {"canonical_city": fallback_city, "canonical_state": None, "is_unmapped_guess": True}},
        upsert=True,
    )
    return fallback_city, None


async def toggle_high_conversion(canonical_city: str):
    doc = await city_lookup_col.find_one({"canonical_city": canonical_city})
    current = (doc or {}).get("is_high_conversion", False)
    await city_lookup_col.update_one(
        {"canonical_city": canonical_city},
        {"$set": {"is_high_conversion": not current}},
    )


async def is_high_conversion_city(city: Optional[str]) -> bool:
    if not city:
        return False
    doc = await city_lookup_col.find_one({"canonical_city": city})
    return bool((doc or {}).get("is_high_conversion", False))


async def list_mappings() -> List[dict]:
    docs = [d async for d in city_lookup_col.find().sort("canonical_city", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def create_or_update_mapping(canonical_city: str, canonical_state: Optional[str], raw_variants: List[str]):
    cleaned_variants = [_clean(v) for v in raw_variants if v.strip()]
    await city_lookup_col.update_one(
        {"canonical_city": canonical_city},
        {"$set": {"canonical_state": canonical_state, "is_unmapped_guess": False},
         "$addToSet": {"raw_variants": {"$each": cleaned_variants}}},
        upsert=True,
    )


async def delete_mapping(mapping_id: str):
    from bson import ObjectId
    await city_lookup_col.delete_one({"_id": ObjectId(mapping_id)})


async def confirm_mapping(mapping_id: str, canonical_city: str, canonical_state: Optional[str]):
    """
    Turns an auto-generated guess into a confirmed mapping. If the confirmed
    name differs from the guess (e.g. guess was "Kothrud", real city is
    "Pune"), merges its raw_variants into the target city's doc and
    retroactively updates every contact that had the old guess as their city.
    """
    from bson import ObjectId
    old_doc = await city_lookup_col.find_one({"_id": ObjectId(mapping_id)})
    if not old_doc:
        return

    old_guess_city = old_doc.get("canonical_city")
    raw_variants = old_doc.get("raw_variants", [])

    await create_or_update_mapping(canonical_city, canonical_state, raw_variants)

    if old_guess_city and old_guess_city != canonical_city:
        await city_lookup_col.delete_one({"_id": ObjectId(mapping_id)})
        from app.database import contacts_col
        await contacts_col.update_many(
            {"city": old_guess_city},
            {"$set": {"city": canonical_city, "state": canonical_state}},
        )
    else:
        await city_lookup_col.update_one(
            {"_id": ObjectId(mapping_id)},
            {"$set": {"is_unmapped_guess": False, "canonical_state": canonical_state}},
        )
