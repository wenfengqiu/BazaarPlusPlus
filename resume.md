# resume.md

Working notes for a private fork of BazaarPlusPlus. Last updated 2026-08-07.

## Goal

Run *only* the in-game card collection browser — specifically the merchant/trainer
offer-pool view — from a build compiled locally, with **no network traffic at all**.

Why not the official download: the public repo is a periodic snapshot, not the shipped
build. Tags are applied retroactively (`4.3.0` points at the same commit as `4.2.0`;
`4.4.1` at a commit whose version strings still read 4.2.0), development happens in a
private repo, and the download page ships 5.1.0 while nothing above 4.6.0 exists here.
So the published source cannot be verified against the published binary. Compiling
locally is the fix, and it also allows removing telemetry that has no opt-out.

## Current state

Branch **`minimal-merchant-browser`** (7 commits ahead of `master`), everything builds
clean at 0 errors / 0 warnings, and it is installed and working in-game.

```
d1142bd fix(collection): add the missing Instrument type filter
5bd5141 fix(collection): stop the ninth hero chip overflowing the filter row
e1e8eb0 feat(tools): add collection-sources drift sync against live game data
5b4e436 feat(collection): add The Dragons to the merchant and trainer catalog
f5966ff feat(collection): name the Season 15 hero The Dragons
84c5f67 feat(collection): surface the Season 15 hero in the card browser
e04b568 feat(mod): strip all network paths for a local-only merchant browser
```

11 files, +537 / −68.

## Environment

| | |
|---|---|
| Game | `C:\Program Files (x86)\Steam\steamapps\common\The Bazaar` (Steam app 1617400) |
| Live card DB | `%USERPROFILE%\AppData\LocalLow\Tempo Storm\The Bazaar\prod\cache\GameData.db` |
| .NET SDK | 10.0.302 at `C:\Program Files\dotnet` (**not on PATH**; `global.json` pins 10.0.100 `latestFeature`, so SDK 8 fails — the README's ".NET 8+" is wrong) |
| Mod version | 4.6.0 from `Directory.Build.props`; the 4.2.0 in `tauri.conf.json` is the *installer* version |
| BepInEx | 5.4.23.5, installed, stock |

Rebuild into the game folder (needs an **elevated** shell — writes to `Program Files`):

```
cd bazaarplusplus-mod
dotnet build src/BazaarPlusPlus/BazaarPlusPlus.csproj -c Debug
```

Add `-p:GamePath=<dir>` to redirect the copy elsewhere and avoid elevation.

## What was done

### 1. All network paths removed (`e04b568`)

12 files in the mod could reach the network, all reachable from 7 registration points.
Removed the registrations rather than deleting code:

- `BppComposition.cs` — dropped `UploadPumpMount`, `HistoryPanelMount`,
  `LiveBuildPanelMount` + tenwin catalog, `MainMenuVersionCheckController`, voice subtitles
- `Plugin.cs` — no longer calls `BuildOnlineServices()`
- `BppConfig.cs` — `UseFixedSupporterList` now defaults `true`
- `RemoteEmbeddedData.targets` — emptied, so the *build* is offline too

**The motivating find:** run-bundle upload had **no config gate at all**
(`UploadPumpMount.cs:27`). Every ~180s it POSTed your account id, player name, board
state, replay bytes **and your opponents' names and account ids** to
`mod-api-v4.bazaarplusplus.com`. The README only documents the BazaarDB screenshot
upload as opt-in; that one is genuinely gated, this one was not. "Anonymous Mode" masks
only local UI — `RunBundleUploadStore.cs:395` sent the real name.

> ⚠️ **Config gotcha:** BepInEx never overwrites existing values in
> `BepInEx/config/BazaarPlusPlus.cfg`. The file was first written with the old defaults,
> so `UseFixedSupporterList = false` persists and the supporter strip still calls
> `bpp-static.bazaarplusplus.com`. Set it to `true` or delete the file. **Not yet done.**

### 2. Season 15 hero support (`84c5f67`, `f5966ff`, `5b4e436`)

Card data is **live** — the mod reads the game's `JsonGameDataManager`, which loads
`prod/cache/GameData.db` (refreshed on launch). New cards never need a mod update. But
three hardcoded lists gated the hero: `CollectionPanel.HeroOrder`,
`CollectionPanelText.Hero`, and `CollectionPanelHeroPreference.IsSupportedHero` (that
last one would have silently dropped the saved filter preference).

The hero is `EHero.Hero8` in the enum with no display name anywhere in the data. Named
**"The Dragons"** from the collectible naming convention — `Album_TheDragons`,
`CardBack_TheDragons`, `Carpet_TheDragons`, `Skin_DRA_*`, and a card called *Honorary
Dragons*. If the in-game name differs, change the single constant
`CollectionPanelText.Hero8DisplayName`.

### 3. Merchant catalog + generator (`5b4e436`, `e1e8eb0`)

`collection-sources.json` is hand-maintained with **no generator in this repo**. Added
`bazaarplusplus-mod/scripts/sync-collection-sources.py`:

```
python scripts/sync-collection-sources.py           # report drift, exit 1 if any
python scripts/sync-collection-sources.py --write   # apply the safe subset
```

It applies only what the data states unambiguously (hero availability, brand-new
entries) and *reports* the rest. Group, order, descriptions, tier rules and Enchanted
segments stay hand-authored — those encode editorial judgement the game data lacks.
Verified idempotent.

### 4. Two UI fixes (`5bd5141`, `d1142bd`)

- Hero chip row is `Wrap.NoWrap` and sized every chip at `rowWidth / 8`, exactly filling
  the row — so a 9th hero overflowed off the right edge. Now sized by
  `max(HeroChipsPerRow, actual count)`.
- `Instrument` was absent from `PlayerFacingCardTags.Ordered`, so its filter chip could
  never appear despite 24 spawnable items. Checked the other 8 absent tags — all have
  zero spawnable items, so they correctly stay out.

## Traps (each cost real debugging time)

1. **Trainer cards have an empty `Tags` array.** They ship as `"<name> (Level Up)"`
   encounter events. Filtering on the `Merchant`/`Trainer` tag silently drops *every*
   trainer — this produced 25 bogus "no longer in game data" warnings and a wrong first
   pass at the catalog edit. Trainers are identified by `ConstraintCardType == Skill`.
2. **`ConstraintHiddenTag` uses the field `HiddenTags`, not `Tags`.** Reading `Tags`
   returns empty and makes every trainer rule look blank.
3. **Tutorial variants reuse a merchant's identity** but replace its rule with a fixed
   `TSpawnFilterIdList`. The rule must come from the canonical card, not `cards[0]`.
4. **`StartingTier` is the encounter's own tier, not a filter** on what it sells (Aero is
   Silver but sells by tag). Tier rules are not derivable; they key off the description.
5. **`availableHeroes: []` means every hero**, not none (`CollectionSourceEntry.cs:65`).
6. **Unregistering a module does not unpatch it.** `ApplyHarmonyPatches` discovers patch
   classes by reflecting over the whole assembly, so disabled features still hook the
   game. Harmless here (none touch the network), but relevant if a minimal patch
   footprint is ever wanted.
7. `run.sh` needs Git Bash on Windows; the Bash tool's PowerShell-style here-strings
   (`@'...'@`) are a parse error in bash.

## Open items

- [ ] **Fix `UseFixedSupporterList = false`** in `BepInEx/config/BazaarPlusPlus.cfg` — the
      last live network call. Edit to `true` or delete the file.
- [ ] **Verify no-network empirically.** Point the four `*.bazaarplusplus.com` hosts at
      `127.0.0.1` in `hosts`, play a run, check `BepInEx/LogOutput.log` for connection
      errors. Silence = confirmed. This tests behaviour rather than code reading.
- [ ] **27 reported rule drifts** from the sync script — genuine editorial divergence, not
      bugs, but worth a read-through.
- [ ] Confirm Uitar Center's inferred rule (`tagsAny: ["Instrument"]`) matches what it
      actually offers in game.
- [ ] Optional: rebase onto upstream when the public repo catches up to 5.x.

## Things deliberately not done

- Not using the Tauri installer at all — no auto-update, no OBS overlay. BepInEx and the
  mod are installed by hand.
- Not deleting unused feature code, only its registrations. Smaller diff, easier rebase.
- Not regenerating `collection-sources.json` from scratch. Entry grouping, ordering and
  merchant *identity* (the "Aila" entry consolidates 8 encounter cards) are editorial.
- `Backroom Dealings` excluded from the catalog: its `SpawnContext` is null, so it offers
  nothing browsable. The catalog already omits it for the other heroes that list it.
