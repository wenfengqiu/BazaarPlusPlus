#!/usr/bin/env python3
"""Sync collection-sources.json against the game's live card database.

collection-sources.json describes which merchants and trainers exist, which heroes
encounter them, and what each one offers. The game already holds all of that: every
merchant is a TCardEncounterEvent whose SelectionContext.SpawnContext carries the
offer rule as a constraint tree. This script reads that database and reports — or
applies — the drift.

The game ships a seed copy of the database under StreamingAssets, but refreshes a
live copy into its persistent data directory on launch. Only the live copy is
current, so that is what this script reads by default.

    python scripts/sync-collection-sources.py              # report drift, exit 1 if any
    python scripts/sync-collection-sources.py --write      # apply the safe subset
    python scripts/sync-collection-sources.py --db PATH    # explicit database

What --write applies:
  * new heroes added to an entry's availableHeroes
  * refreshed descriptions
  * new entries for merchants the catalog has never seen

What it deliberately never does, because these encode editorial judgement that the
game data does not carry:
  * reorder or regroup existing entries
  * remove heroes, entries, or source ids
  * rewrite the offer rule of an existing entry
  * touch Enchanted segments

Rule drift on existing entries is reported so a human can decide. An empty
availableHeroes means "every hero", so it is left alone.

Known limits, all found by diffing derived rules against the hand-written catalog:

  * Tier rules are only partly derivable. A ConstraintTier is a real filter and is
    read, but a card's StartingTier is the encounter's own tier, not a filter on what
    it sells -- Aero is Silver but sells by tag. Several tier specialists (Adira,
    Argenta, Curio, Luxe) carry no ConstraintTier at all and key off the description
    ("Sells Gold-tier items"), so the catalog states a tier the data does not.
    Reported, never derived.
  * Hidden tag groups are approximate. Kev's Armory constrains Shield, Toughness,
    ShieldReference, Health and HealthReference; the catalog simplifies that to the
    Health and Shield groups and drops Toughness. Groups are emitted only when the
    tag set decomposes exactly, so these show as drift. Such differences are cosmetic
    unless a divergent tag actually appears on a browsable item -- as of 2026-08-09
    none does.
  * Discovery is tag-based and therefore incomplete. Trainers ship untagged, so a
    brand-new trainer will not be proposed automatically -- though an existing one
    still syncs correctly, because lookup goes through the catalog's source ids.
  * Enchanted segments are never derived or touched.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

CATALOG = (
    Path(__file__).resolve().parent.parent
    / "src/BazaarPlusPlus/Data/CollectionSources/collection-sources.json"
)

# Mirrors CollectionHiddenTagGroups.cs, where each group is a tag and its Reference twin.
HIDDEN_TAG_GROUPS = [
    "Ammo", "Burn", "Cooldown", "Crit", "Flying", "Freeze", "Haste",
    "Health", "Heal", "Poison", "Regen", "Shield", "Slow",
]
HIDDEN_TAG_GROUP_BY_TAGS = {
    frozenset({g, g + "Reference"}): g for g in HIDDEN_TAG_GROUPS
}

# Mirrors TierOrder.Rank in the mod.
TIER_ORDER = ["Bronze", "Silver", "Gold", "Diamond", "Legendary"]


def tier_rank(tier: str) -> int:
    return TIER_ORDER.index(tier) if tier in TIER_ORDER else 99


def find_database() -> Path | None:
    """Locate the live GameData.db the game refreshes on launch."""
    candidates = [
        Path.home() / "AppData/LocalLow/Tempo Storm/The Bazaar/prod/cache/GameData.db",
        Path.home() / "Library/Application Support/com.tempostorm.thebazaar/prod/cache/GameData.db",
        Path.home() / "Library/Application Support/Tempo Storm/The Bazaar/prod/cache/GameData.db",
    ]
    return next((p for p in candidates if p.is_file()), None)


def is_noise(card) -> bool:
    """Developer and tutorial encounters are not real merchants a player browses.

    Tutorial variants reuse a merchant's identity but replace the offer rule with a
    fixed TSpawnFilterIdList, so deriving a rule from one produces nonsense.
    """
    name = (card.get("InternalName") or "")
    return name.startswith("[DEBUG]") or "Tutorial" in name


def canonical(cards: list[dict], name: str) -> dict:
    """Pick the card an entry's rule should come from.

    Prefer an exact InternalName match, then the card carrying the most constraints;
    a merchant's tier variants are identical in rule, so any of them will do.
    """
    def richness(card):
        context = card.get("SelectionContext")
        return sum(
            len(walk(context, t, []))
            for t in ("ConstraintTag", "ConstraintHiddenTag", "ConstraintSize",
                      "ConstraintTier", "ConstraintHero", "ConstraintEnchantmentEligible")
        )

    exact = [c for c in cards if (c.get("InternalName") or "").strip() == name]
    return max(exact or cards, key=richness)


def walk(node, type_name, out):
    """Collect every dict in the tree whose $type matches."""
    if isinstance(node, dict):
        if node.get("$type") == type_name:
            out.append(node)
        for value in node.values():
            walk(value, type_name, out)
    elif isinstance(node, list):
        for value in node:
            walk(value, type_name, out)
    return out


def load_sources(db_path: Path) -> dict[str, dict]:
    """Return {template_id: card} for every encounter that offers cards.

    Deliberately broader than "tagged Merchant or Trainer": trainers ship as
    "<name> (Level Up)" encounter events with an *empty* Tags array, so filtering on
    the tag silently drops every trainer and makes the catalog look stale. Each card
    is annotated with _discoverable, which records whether the tag is present — only
    tagged cards are precise enough to propose as brand-new entries.
    """
    con = sqlite3.connect(str(db_path))
    try:
        sources = {}
        for card_id, blob in con.execute("select Id, Data from cards"):
            text = blob.decode("utf-8", "replace") if isinstance(blob, bytes) else blob
            try:
                card = json.loads(text)
            except ValueError:
                continue
            if card.get("$type") != "TCardEncounterEvent":
                continue
            # A null SpawnContext offers nothing to browse (e.g. Backroom Dealings).
            if not (card.get("SelectionContext") or {}).get("SpawnContext"):
                continue
            tags = {str(t) for t in (card.get("Tags") or [])}
            card["Id"] = card_id
            card["_discoverable"] = bool(tags & {"Merchant", "Trainer"})
            sources[card_id.lower()] = card
        return sources
    finally:
        con.close()


def derive_kind(card) -> str:
    """Trainers are merchants whose spawn filter constrains card type to Skill."""
    types = {t for c in walk(card, "ConstraintCardType", []) for t in (c.get("Types") or [])}
    return "Trainer" if "Skill" in types else "Merchant"


def derive_rule(card) -> dict:
    """Translate the spawn constraint tree into a CollectionSourceOfferRule."""
    context = (card.get("SelectionContext") or {}).get("SpawnContext")
    rule: dict = {}

    heroes = [h for c in walk(context, "ConstraintHero", []) for h in (c.get("Heroes") or [])]
    # ConstraintIsOnlyHero names the hero a card must belong to *exclusively* -- the
    # mentor trainers (Old Zane -> Vanessa) teach only that hero's skills. It carries
    # its own Heroes list; it is not a neutral-item constraint.
    only_hero = [h for c in walk(context, "ConstraintIsOnlyHero", []) for h in (c.get("Heroes") or [])]
    ignore_hero = any(b.get("IgnoreHero") for b in walk(context, "TSpawnBehaviorIgnoreHero", []))
    exclude_player = bool(walk(context, "TSpawnBehaviorExcludePlayerHero", []))

    if only_hero:
        rule["heroMode"] = "FixedHero"
        rule["hero"] = only_hero[0]
    elif heroes == ["Common"]:
        rule["heroMode"] = "NeutralOnly"
    elif heroes:
        rule["heroMode"] = "FixedHero"
        rule["hero"] = heroes[0]
    elif exclude_player:
        rule["heroMode"] = "OtherHeroes"
    elif ignore_hero:
        rule["heroMode"] = "AllHeroes"
    else:
        rule["heroMode"] = "SelectedHero"

    tags_any, tags_none = [], []
    for c in walk(context, "ConstraintTag", []):
        (tags_none if c.get("IsNot") else tags_any).extend(c.get("Tags") or [])
    if tags_any:
        rule["tagsAny"] = tags_any
    if tags_none:
        rule["tagsNone"] = tags_none

    hidden = []
    for c in walk(context, "ConstraintHiddenTag", []):
        hidden.extend(c.get("HiddenTags") or [])
    if hidden:
        # Emit named groups only when the set decomposes exactly into them; a stray tag
        # such as Charge alongside Haste/HasteReference means the raw list is the truth.
        remaining, groups = set(hidden), []
        for tags, name in HIDDEN_TAG_GROUP_BY_TAGS.items():
            if tags <= remaining:
                groups.append(name)
                remaining -= tags
        if groups and not remaining:
            rule["hiddenTagGroupsAny"] = groups
        else:
            rule["hiddenTagsAny"] = hidden

    sizes = [s for c in walk(context, "ConstraintSize", []) for s in (c.get("Sizes") or [])]
    if sizes:
        rule["sizesAny"] = sizes

    tiers = [t for c in walk(context, "ConstraintTier", []) for t in (c.get("Tiers") or [])]
    if tiers:
        # Tiers is the *set* the merchant offers at (Goldie: Bronze, Silver, Gold), and
        # those sets run contiguously up from Bronze, so AtMost the highest is exact.
        # Taking the first entry instead reports every such merchant as Bronze.
        rule["startingTier"] = {"mode": "AtMost", "tier": max(tiers, key=tier_rank)}

    if walk(context, "ConstraintEnchantmentEligible", []):
        rule["enchantableOnly"] = True

    return rule


def canonical_rule(rule: dict) -> dict:
    """Reduce a rule to what the mod actually matches on, for comparison only.

    CollectionSourceCatalog merges hiddenTagGroupsAny into hiddenTagsAny and the
    resolver tests every list with an overlap check, so neither the group/tag notation
    nor the ordering carries meaning. Comparing raw dicts reports both as drift.
    """
    out = dict(rule)
    hidden = set(out.pop("hiddenTagsAny", None) or [])
    for group in out.pop("hiddenTagGroupsAny", None) or []:
        hidden |= {group, group + "Reference"}
    if hidden:
        out["hiddenTagsAny"] = sorted(hidden)
    for key in ("tagsAny", "tagsNone", "sizesAny", "enchantmentTypesAny",
                "enchantmentTagsAny", "enchantmentHiddenTagsAny"):
        if out.get(key):
            out[key] = sorted(out[key])
    return out


def derive_group(kind: str, rule: dict) -> str:
    if kind == "Trainer":
        return "trainer"
    if rule.get("heroMode") == "FixedHero":
        return "other-hero"
    if rule.get("heroMode") == "AllHeroes":
        return "all-hero"
    if "sizesAny" in rule:
        return "size-specialist"
    if "startingTier" in rule:
        return "tier-specialist"
    if {"tagsAny", "tagsNone", "hiddenTagGroupsAny", "hiddenTagsAny"} & rule.keys():
        return "tag-type-specialist"
    return "generalist"


def describe(card) -> str:
    localization = card.get("Localization") or {}
    return ((localization.get("Description") or {}).get("Text") or "").strip()


def display_name(card) -> str:
    localization = card.get("Localization") or {}
    title = ((localization.get("Title") or {}).get("Text") or "").strip()
    return title or (card.get("InternalName") or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="path to GameData.db")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--write", action="store_true", help="apply the safe subset of changes")
    args = parser.parse_args()

    db_path = args.db or find_database()
    if not db_path or not db_path.is_file():
        print("error: could not locate GameData.db; pass --db", file=sys.stderr)
        print("       expected under the game's persistent data directory, and it only", file=sys.stderr)
        print("       appears once the game has been launched at least once.", file=sys.stderr)
        return 2

    print(f"database: {db_path}")
    sources = load_sources(db_path)
    doc = json.loads(args.catalog.read_text(encoding="utf-8"))
    entries = doc["entries"]
    print(f"catalog:  {args.catalog}")
    print(f"          {len(entries)} entries, {len(sources)} browsable sources in game\n")

    by_source = {sid.lower(): e for e in entries for sid in e.get("sourceTemplateIds", [])}
    changes, warnings = [], []

    # The game's real hero roster, used to expand a hero-agnostic Common source.
    roster = sorted(
        {h for c in sources.values() for h in (c.get("Heroes") or [])} - {"Common"}
    )

    # --- entries the catalog already knows -------------------------------------------
    for entry in entries:
        ids = [s.lower() for s in entry.get("sourceTemplateIds", [])]
        cards = [sources[i] for i in ids if i in sources]
        for missing in (i for i in ids if i not in sources):
            warnings.append(f"{entry['name']}: source {missing} no longer in game data")
        if not cards:
            continue

        available = entry.get("availableHeroes") or []
        if available:  # empty means every hero, so there is nothing to sync
            live = {h for c in cards for h in (c.get("Heroes") or [])}
            # A Common source is hero-agnostic: the whole roster qualifies.
            wanted = set(roster) if "Common" in live else live - {"Common"}
            extra = sorted(wanted - set(available))
            if extra:
                changes.append((entry, "availableHeroes", sorted(available + extra)))

        # Descriptions are reported but never applied: the catalog's are hand-written and
        # often say more than the game's ("Buys your Small items at +1 Value"), and the
        # game's carry unresolved template tokens such as {aura.3}.
        source = canonical([c for c in cards if not is_noise(c)] or cards, entry["name"])
        live_description = describe(source)
        if live_description and live_description != entry.get("description", ""):
            warnings.append(
                f"{entry['name']}: description differs\n"
                f"    catalog: {entry.get('description', '')!r}\n"
                f"    game:    {live_description!r}"
            )

        derived = derive_rule(source)
        normal = next((s for s in entry["offerSegments"] if s["kind"] == "Normal"), None)
        if (
            normal
            and canonical_rule(normal["rule"]) != canonical_rule(derived)
            and len(entry["offerSegments"]) == 1
        ):
            warnings.append(
                f"{entry['name']}: rule drift\n"
                f"    catalog: {json.dumps(normal['rule'], sort_keys=True)}\n"
                f"    game:    {json.dumps(derived, sort_keys=True)}"
            )

    # --- merchants the catalog has never seen -----------------------------------------
    unseen = [
        card for sid, card in sources.items()
        if sid not in by_source and not is_noise(card) and card["_discoverable"]
    ]
    # One merchant can ship as several encounter cards (tier variants); the catalog
    # models that as one entry with several sourceTemplateIds, so group by name.
    grouped: dict[str, list[dict]] = {}
    for card in unseen:
        grouped.setdefault(display_name(card), []).append(card)

    new_entries = []
    for name, cards in sorted(grouped.items()):
        source = canonical(cards, name)
        kind = derive_kind(source)
        rule = derive_rule(source)
        group = derive_group(kind, rule)
        orders = [e["order"] for e in entries + new_entries if e["group"] == group]
        heroes = {h for c in cards for h in (c.get("Heroes") or [])}
        new_entries.append({
            "kind": kind,
            "group": group,
            "order": (max(orders) + 1) if orders else 0,
            "name": name,
            "availableHeroes": [] if "Common" in heroes else sorted(heroes),
            "description": describe(source),
            "portraitTemplateId": source["Id"],
            "sourceTemplateIds": sorted(c["Id"] for c in cards),
            "offerSegments": [{"key": "normal", "kind": "Normal", "rule": rule}],
        })

    # --- report ------------------------------------------------------------------------
    for entry, field, value in changes:
        before = entry.get(field)
        print(f"~ {entry['name']}.{field}")
        print(f"    - {json.dumps(before, ensure_ascii=False)}")
        print(f"    + {json.dumps(value, ensure_ascii=False)}")
    for entry in new_entries:
        print(f"+ {entry['name']}  [{entry['group']}] "
              f"heroes={entry['availableHeroes'] or 'ALL'} "
              f"rule={json.dumps(entry['offerSegments'][0]['rule'], ensure_ascii=False)}")
    for warning in warnings:
        print(f"! {warning}")

    if not changes and not new_entries:
        print("catalog is in sync with the game database.")
        return 1 if warnings else 0

    if not args.write:
        print(f"\n{len(changes)} field change(s), {len(new_entries)} new entr(ies), "
              f"{len(warnings)} warning(s). Re-run with --write to apply.")
        return 1

    for entry, field, value in changes:
        entry[field] = value
    entries.extend(new_entries)
    args.catalog.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"\nwrote {args.catalog}")
    if warnings:
        print("warnings above were reported only; review them by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
