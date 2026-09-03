#!/usr/bin/env python3
"""Export item art from The Bazaar's local asset bundles to PNG, by item name.

The collection browser never downloads art: every card's ArtKey resolves through
Addressables to one of the ~928 .bundle files shipped under StreamingAssets/aa. This
script reads those bundles directly, with the game closed, and writes the artwork out.

    python scripts/export-card-art.py "Abducted Cow" "Ice Cream Truck" -o art/
    python scripts/export-card-art.py --from-file names.txt -o art/
    python scripts/export-card-art.py --all -o art/          # every item with art
    python scripts/export-card-art.py --hero vanessa -o art/
    python scripts/export-card-art.py --list                 # print exportable names

Names match case- and punctuation-insensitively, against the same display names the
collection browser shows. Unmatched names are reported with suggestions and set a
non-zero exit code.

How it works
------------
Each card ships a <Name>_CardData ScriptableObject holding its identity and a reference
to the card Material; that Material's _MainTex is the artwork -- almost always a square
1024x1024 texture with no frame or border, because the shader composites the frame, tier
gems and enchantment effects at runtime from shared textures in other bundles. A dozen
assets ship at another size (512x512, 532x1024, one 2048x2048); the export writes
whatever the slot holds. Pass --texture to pull a different slot (e.g. _EnchantmentMask).

The index of asset locators is cached beside this script and keyed to the installed
build: it records aa/catalog.hash, which Addressables rewrites on every build, and
rescans by itself once the game is patched. --rebuild-index forces that early.

Names are resolved through GameData.db when it is available, because the asset's own
name field is a dev placeholder for newer content -- the Season 15 instruments ship as
'AMP' and 'BladedBass' rather than 'Amp' and 'Bass'. The database supplies the real
display name and joins to the asset by template id. Without the database the script
still works, but falls back to those raw asset names.

Coverage
--------
Against the 2026-09-02 build: 1197 of the game's 1408 items export. Of the remainder, 25
have no ArtKey at all (they render blank in game too) and 186 are the shared-art group --
every "<X>'s Package", the chibis, and a few instruments point at generic art that is not
shipped as a per-card asset. Those are reported individually rather than silently skipped.

--list prints 1251 names, more than 1197, because it also exposes art assets with no live
catalog entry: cut cards and dev-named variants that are still in the bundles. A full
--all run therefore writes 1249 files (~1.7 GB) and reports two it cannot: Octopus, whose
_MainTex lives in a dependency bundle, and VanessasShip, whose material is not in the
bundle its CardData sits in.

Requires UnityPy (pip install UnityPy); Pillow comes with it.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import warnings
from pathlib import Path

try:
    import UnityPy
    from UnityPy.exceptions import UnityVersionFallbackWarning
except ImportError:
    print("error: UnityPy is required -- pip install UnityPy", file=sys.stderr)
    raise SystemExit(2)

# The bundles carry no version string, so the fallback we set from globalgamemanagers is
# the correct value rather than a guess. Silence the per-file warning about it.
warnings.filterwarnings("ignore", category=UnityVersionFallbackWarning)

INDEX_PATH = Path(__file__).resolve().parent / ".card-art-index.json"
INDEX_VERSION = 3

GAME_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\The Bazaar"),
    Path(r"D:\Steam\steamapps\common\The Bazaar"),
    Path.home() / "Library/Application Support/Steam/steamapps/common/The Bazaar",
]

DB_CANDIDATES = [
    Path.home() / "AppData/LocalLow/Tempo Storm/The Bazaar/prod/cache/GameData.db",
    Path.home() / "Library/Application Support/com.tempostorm.thebazaar/prod/cache/GameData.db",
    Path.home() / "Library/Application Support/Tempo Storm/The Bazaar/prod/cache/GameData.db",
]


def normalize(name: str) -> str:
    """Fold case and punctuation so "Tok's Clocks" matches "ToksClocks"."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def find_game(explicit: Path | None) -> Path:
    # An explicit --game is an instruction, not a hint: silently falling back to
    # another install would export art from a build the caller never named.
    if explicit is not None:
        if not (explicit / "TheBazaar_Data/StreamingAssets/aa").is_dir():
            raise SystemExit(f"error: {explicit} is not a The Bazaar install")
        return explicit
    for candidate in GAME_CANDIDATES:
        if (candidate / "TheBazaar_Data/StreamingAssets/aa").is_dir():
            return candidate
    raise SystemExit(
        "error: could not locate The Bazaar; pass --game <dir>\n"
        "       expected <dir>/TheBazaar_Data/StreamingAssets/aa to exist"
    )


def find_db(explicit: Path | None) -> Path | None:
    if explicit is not None:
        if not explicit.is_file():
            raise SystemExit(f"error: no database at {explicit}")
        return explicit
    return next((c for c in DB_CANDIDATES if c.is_file()), None)


def build_fingerprint(game: Path) -> str:
    """Identify the installed build, so a game patch invalidates the cached index.

    catalog.hash is rewritten by every Addressables build -- exactly when bundles
    appear, vanish or move their assets; the 2026-09-02 patch took the set from 931
    bundles to 928. Without this the cache outlives the build it describes and the
    script exports from locators that no longer hold.
    """
    fingerprint = game / "TheBazaar_Data/StreamingAssets/aa/catalog.hash"
    return fingerprint.read_text(encoding="utf-8").strip() if fingerprint.is_file() else ""


def unity_version(game: Path) -> str:
    """Read the build's Unity version; the bundles carry none, so UnityPy needs it."""
    blob = (game / "TheBazaar_Data/globalgamemanagers").read_bytes()[:200]
    match = re.search(rb"\d+\.\d+\.\d+[abfp]\d+", blob)
    if not match:
        raise SystemExit("error: could not read the Unity version from globalgamemanagers")
    return match.group().decode()


def build_index(game: Path) -> dict:
    """Locate every card art asset. Stores locators only, never pixels."""
    aa = game / "TheBazaar_Data/StreamingAssets/aa"
    bundles = sorted(aa.rglob("card_*_assets_all.bundle"))
    if not bundles:
        raise SystemExit(f"error: no card bundles found under {aa}")

    assets = []
    for i, bundle in enumerate(bundles, 1):
        print(f"  [{i}/{len(bundles)}] {bundle.name}", flush=True)
        env = UnityPy.load(str(bundle))
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if "<Name>k__BackingField" not in tree:
                continue
            material = (tree.get("cardMaterial") or {}).get("m_PathID")
            if not material:
                continue  # cut/unreleased cards ship without art
            assets.append({
                "display": tree.get("<Name>k__BackingField") or "",
                "internal": tree.get("<InternalName>k__BackingField") or "",
                "cardGuid": (tree.get("cardGUID") or "").lower(),
                "bundle": bundle.name,
                "materialPathId": material,
                # card_vanessa_assets_all -> vanessa
                "group": bundle.name.split("_")[1],
            })
    return {
        "indexVersion": INDEX_VERSION,
        "game": str(game),
        "catalogHash": build_fingerprint(game),
        "assets": assets,
    }


def load_index(game: Path, rebuild: bool) -> list[dict]:
    stale = None
    if INDEX_PATH.is_file() and not rebuild:
        try:
            cached = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            if cached.get("indexVersion") == INDEX_VERSION and cached.get("assets"):
                if cached.get("game") != str(game):
                    stale = f"it was built from {cached['game']}"
                elif cached.get("catalogHash") != build_fingerprint(game):
                    stale = "the game has been patched since it was built"
                else:
                    return cached["assets"]
        except (ValueError, OSError):
            pass
    if stale:
        print(f"card art index is stale ({stale}); rebuilding...")
    else:
        print("building card art index (first run reads ~1.2 GB of bundles)...")
    index = build_index(game)
    INDEX_PATH.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"indexed {len(index['assets'])} art assets -> {INDEX_PATH.name}\n")
    return index["assets"]


def read_items(db_path: Path) -> list[dict]:
    """Every item template, with the display name the collection browser shows."""
    con = sqlite3.connect(str(db_path))
    try:
        items = []
        for card_id, blob in con.execute("select Id, Data from cards"):
            text = blob.decode("utf-8", "replace") if isinstance(blob, bytes) else blob
            try:
                card = json.loads(text)
            except ValueError:
                continue
            if card.get("$type") != "TCardItem":
                continue
            title = (
                ((card.get("Localization") or {}).get("Title") or {}).get("Text") or ""
            ).strip()
            if not title:
                continue
            items.append({
                "id": card_id.lower(),
                "title": title,
                "internal": card.get("InternalName") or "",
                "artKey": card.get("ArtKey") or "",
            })
        return items
    finally:
        con.close()


class Catalog:
    """Maps a user-facing name onto the art asset that draws it."""

    def __init__(self, assets: list[dict], items: list[dict]):
        self.assets = assets
        by_guid = {a["cardGuid"]: a for a in assets if a["cardGuid"]}
        by_internal: dict[str, dict] = {}
        by_display: dict[str, dict] = {}
        for asset in assets:
            by_internal.setdefault(normalize(asset["internal"]), asset)
            by_display.setdefault(normalize(asset["display"]), asset)

        # name -> (asset | None); None records a real item whose art is not shipped.
        self.entries: dict[str, tuple[str, dict | None]] = {}

        for item in items:
            asset = (
                by_guid.get(item["id"])
                or by_internal.get(normalize(item["internal"]))
                or by_display.get(normalize(item["title"]))
            )
            key = normalize(item["title"])
            # Keep a resolved hit over an unresolved duplicate of the same name.
            if key not in self.entries or (asset and self.entries[key][1] is None):
                self.entries[key] = (item["title"], asset)

        # Assets with no matching item (cut content, dev names) stay addressable.
        for asset in assets:
            for name in (asset["display"], asset["internal"]):
                key = normalize(name)
                if key and key not in self.entries:
                    self.entries[key] = (name, asset)

    def get(self, name: str) -> tuple[str, dict | None] | None:
        return self.entries.get(normalize(name))

    def exportable(self) -> list[tuple[str, dict]]:
        seen, out = set(), []
        for label, asset in self.entries.values():
            if asset is None:
                continue
            token = (asset["bundle"], asset["materialPathId"])
            if token in seen:
                continue
            seen.add(token)
            out.append((label, asset))
        return sorted(out, key=lambda pair: pair[0].lower())

    def suggest(self, name: str, limit: int = 5) -> list[str]:
        key = normalize(name)
        if len(key) < 3:
            return []
        hits = {label for k, (label, _) in self.entries.items() if key in k}
        return sorted(hits)[:limit]


def resolve_texture(env, material_path_id: int, slot: str):
    """Follow CardData -> Material -> the named texture slot."""
    objects = {o.path_id: o for o in env.objects}
    material = objects.get(material_path_id)
    if material is None:
        return None, "material not found in bundle"

    for key, value in material.read_typetree()["m_SavedProperties"]["m_TexEnvs"]:
        if key != slot:
            continue
        reference = value.get("m_Texture") or {}
        if not reference.get("m_PathID"):
            return None, f"{slot} is empty"
        # m_FileID != 0 means a dependency bundle (the shared frame/FX atlases).
        if reference.get("m_FileID"):
            return None, f"{slot} is a shared texture in another bundle"
        texture = objects.get(reference["m_PathID"])
        if texture is None:
            return None, f"{slot} target missing"
        return texture, None
    return None, f"no {slot} slot on this material"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".")
    return cleaned or "unnamed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("names", nargs="*", help="item names to export")
    parser.add_argument("-o", "--out", type=Path, default=Path("card-art"),
                        help="output folder (default: ./card-art)")
    parser.add_argument("--from-file", type=Path,
                        help="read names from a file, one per line (# comments allowed)")
    parser.add_argument("--all", action="store_true", help="export every item that has art")
    parser.add_argument("--hero", help="export one bundle group (vanessa, neutral, thedragons...)")
    parser.add_argument("--list", action="store_true", help="print exportable names and exit")
    parser.add_argument("--texture", default="_MainTex",
                        help="material texture slot to export (default: _MainTex)")
    parser.add_argument("--game", type=Path, help="path to The Bazaar install")
    parser.add_argument("--db", type=Path, help="path to GameData.db")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="force a bundle rescan (a game patch triggers one anyway)")
    args = parser.parse_args()

    game = find_game(args.game)
    UnityPy.config.FALLBACK_UNITY_VERSION = unity_version(game)
    assets = load_index(game, args.rebuild_index)

    db_path = find_db(args.db)
    if db_path is None:
        print("warning: GameData.db not found; falling back to raw asset names "
              "(newer cards carry dev placeholders)", file=sys.stderr)
    catalog = Catalog(assets, read_items(db_path) if db_path else [])

    if args.list:
        for label, asset in catalog.exportable():
            print(f"{label}\t{asset['group']}")
        print(f"\n{len(catalog.exportable())} exportable", file=sys.stderr)
        return 0

    wanted = list(args.names)
    if args.from_file:
        for line in args.from_file.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                wanted.append(line)

    unmatched = False
    if args.all:
        selected = catalog.exportable()
    elif args.hero:
        group = normalize(args.hero)
        selected = [(l, a) for l, a in catalog.exportable() if a["group"] == group]
        if not selected:
            groups = sorted({a["group"] for a in assets})
            print(f"error: no group {args.hero!r}; known: {', '.join(groups)}", file=sys.stderr)
            return 2
    elif wanted:
        selected = []
        for name in wanted:
            found = catalog.get(name)
            if found is None:
                unmatched = True
                hint = catalog.suggest(name)
                extra = f" -- did you mean: {', '.join(hint)}" if hint else ""
                print(f"! unknown item: {name}{extra}", file=sys.stderr)
            elif found[1] is None:
                unmatched = True
                print(f"! {found[0]}: no art asset shipped (shared or placeholder art)",
                      file=sys.stderr)
            else:
                selected.append(found)
        if not selected:
            return 1
    else:
        parser.error("give one or more names, or --from-file / --all / --hero / --list")

    args.out.mkdir(parents=True, exist_ok=True)

    by_bundle: dict[str, list[tuple[str, dict]]] = {}
    for label, asset in selected:
        by_bundle.setdefault(asset["bundle"], []).append((label, asset))

    aa = game / "TheBazaar_Data/StreamingAssets/aa"
    written = failed = 0
    for bundle_name, group in sorted(by_bundle.items()):
        path = next(aa.rglob(bundle_name), None)
        if path is None:
            print(f"! missing bundle {bundle_name}; rerun with --rebuild-index", file=sys.stderr)
            failed += len(group)
            continue
        env = UnityPy.load(str(path))
        for label, asset in group:
            texture, problem = resolve_texture(env, asset["materialPathId"], args.texture)
            if texture is None:
                print(f"! {label}: {problem}", file=sys.stderr)
                failed += 1
                continue
            data = texture.read()
            target = args.out / f"{safe_filename(label)}.png"
            data.image.save(target)
            print(f"  {label} -> {target.name} ({data.m_Width}x{data.m_Height})")
            written += 1

    print(f"\nwrote {written} image(s) to {args.out.resolve()}"
          + (f", {failed} failed" if failed else ""))
    return 1 if failed or unmatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
