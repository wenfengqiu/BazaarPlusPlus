# resume.md

Working notes for a private fork of BazaarPlusPlus. Last updated 2026-08-09 (drift
read-through + card art exporter). **Start at [Open items](#open-items).**

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

Branch **`minimal-merchant-browser`**, ahead of `master` by the ten code commits below
plus this document. Everything builds clean at 0 errors / 0 warnings, and the no-network
goal is verified (see below).

> ⚠️ **The live install is one commit behind.** `6cb62be` (Luxe) changed the embedded
> `collection-sources.json`, but it was only built to a scratch dir with `-p:GamePath`.
> Run the elevated build below to deploy it.

```
87f4bb9 feat(tools): add a card art exporter
6cb62be fix(collection): restrict Luxe to enchantable items
b631cfe fix(tools): correct three false-drift sources in the sync script
d1142bd fix(collection): add the missing Instrument type filter
5bd5141 fix(collection): stop the ninth hero chip overflowing the filter row
e1e8eb0 feat(tools): add collection-sources drift sync against live game data
5b4e436 feat(collection): add The Dragons to the merchant and trainer catalog
f5966ff feat(collection): name the Season 15 hero The Dragons
84c5f67 feat(collection): surface the Season 15 hero in the card browser
e04b568 feat(mod): strip all network paths for a local-only merchant browser
```

13 files, +966 / −68.

## Environment

| | |
|---|---|
| Game | `C:\Program Files (x86)\Steam\steamapps\common\The Bazaar` (Steam app 1617400) |
| Live card DB | `%USERPROFILE%\AppData\LocalLow\Tempo Storm\The Bazaar\prod\cache\GameData.db` |
| .NET SDK | 10.0.302 at `C:\Program Files\dotnet` (**not on PATH**; `global.json` pins 10.0.100 `latestFeature`, so SDK 8 fails — the README's ".NET 8+" is wrong) |
| Mod version | 4.6.0 from `Directory.Build.props`; the 4.2.0 in `tauri.conf.json` is the *installer* version |
| BepInEx | 5.4.23.5, installed, stock |
| Unity | 6000.3.11f1 (read from `TheBazaar_Data/globalgamemanagers`; the bundles carry no version string, so UnityPy must be told) |
| Card art | 931 Addressables bundles / 5.47 GB under `TheBazaar_Data/StreamingAssets/aa`, fully local |
| Python | `UnityPy` 1.25.3 installed, for `scripts/export-card-art.py` only |

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
> so a changed default in `BppConfig.cs` does *not* reach an existing install. Fixed by
> hand on 2026-08-07 (`UseFixedSupporterList = true`); re-check after any config reset.

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

### 5. Drift read-through (2026-08-09)

All 27 reported rule drifts resolved. The test applied was not "does the JSON differ" but
"does the *browsed pool* differ" — expand both sides to the canonical form the resolver
actually consumes (`CollectionSourceCatalog.cs:326` merges `hiddenTagGroupsAny` into
`hiddenTagsAny`), then count affected cards in the live DB.

**Two script bugs, 10 false drifts:**

- `ConstraintTier.Tiers` is the *set* of tiers a merchant offers at (Goldie:
  Bronze/Silver/Gold). The script took `tiers[0]`, so every tier specialist reported as
  Bronze. Fixed to the highest-ranked tier — the sets run contiguously up from Bronze, so
  `AtMost max` is exact. Cleared Goldie, Silvia, Orlin.
- `ConstraintIsOnlyHero` was mapped to `NeutralOnly`. It is nothing of the kind: it carries
  its own `Heroes` list and means "cards belonging to this hero *exclusively*" — the mentor
  trainers. That is `FixedHero`, which for a trainer resolves through
  `MatchesExclusiveHero` (`CollectionSourceOfferPoolResolver.cs:189`), exactly matching.
  Cleared Cymon, Kelsa, Mr. Tuskari, Nonna, Old Zane, Uncle Odi, Zosima.

All ten now re-derive identical to the catalog.

**Comparison was also too literal.** Rules were compared as raw dicts, so
`hiddenTagGroupsAny: ["Freeze"]` vs `hiddenTagsAny: ["Freeze", "FreezeReference"]` counted
as drift even though the catalog loader merges them into one set, and Zara was reported for
list *ordering* alone. Comparison now runs through `canonical_rule()`, which expands the
groups and sorts every list. Cleared Bjorn, C4, Fortis, Malafang, Professor Riggle, Slohmor
Lumbra, Vermir, Zara.

**One real catalog gap:** Luxe's spawn context carries `ConstraintEnchantmentEligible` over
all 12 enchantment types, which the catalog did not express. Added `enchantableOnly: true`.
`IsEnchantable` is `enchantments.Count > 0` (`CollectionCardVm.From.cs:57`), and 31 of 1396
items have no enchantments — so this was 31 items shown that Luxe never offers.

**The 9 that still report are provably inert**, not merely "editorial":

- 5 differ by a tag that matches **zero** cards: `HealthRegen` (Herma, Regenald),
  `CooldownReference` (Tok's Clocks), `BuyPrice`/`SellPrice` (Prospero). Kev's Armory is
  missing the game's `Toughness`, which hits only 3 `TCardEncounterStep` rows — and a
  merchant segment matches `ECardType.Item` only (`...Resolver.cs:40`), so no browsable
  card is affected either way.
- 4 state a tier the data does not carry at all (Adira, Argenta, Curio, Luxe). These key off
  the description, per trap 4. Not derivable; leave hand-authored.

Separately, the 5 description diffs are the game's unresolved placeholders (`{aura.3}`,
  `{ability.0}`) against the catalog's resolved numbers — the catalog reads better. `The
  Tester` is deliberate: "Sells your Hero's Tech items" is *more* accurate than the game's
  "Sells Tech items", since its rule is `SelectedHero`.

Net: the catalog was right about everything except Luxe. A clean run now reports **9 rule
drifts + 5 description diffs**, all listed above — anything beyond that is new and worth
looking at. `--write` re-verified idempotent.

### 6. Card art: how it loads, and an exporter (`87f4bb9`)

**Where the images come from.** Nothing is downloaded. Each card template carries an
`ArtKey` (a Unity asset GUID, e.g. `ef57f889…`), copied into the VM at
`CollectionCardVm.From.cs:56`. The panel reuses the game's own `CardPreviewItem` prefab;
`CollectionItemLoadArtPatch` prefixes its `LoadArt` for cards tagged
`CollectionPanelOwnedMarker` and calls `Addressables.LoadAssetAsync<CardAssetDataSO>`
(`CollectionCardArtCache.cs:73`). The SO's `cardMaterial` is cloned and assigned to
`_cardImage.material` — the art is a **material, not a sprite**, because the card shader
composites frame, tier gems and enchantment FX at runtime.

The mod patches this because the stock `LoadArt` calls Addressables on *every* invocation
and never releases (1146 leaked ref counts over a full scroll), and allocates a fresh
Material per card (no uGUI batching). Hence the L2 art LRU and L3 material cache.

**Verified fully offline** — relevant to the no-network goal:

| Check | Result |
|---|---|
| URLs in `settings.json` / `catalog.bin` | 0 |
| `RemoteLoadPath` / `ServerData` | 0 |
| Bundle load paths | 931/931 via `{Addressables.RuntimePath}` (local) |
| Providers | `AssetBundleProvider` / `BundledAssetProvider` |

`m_DisableCatalogUpdateOnStart` is `false`, but with no remote catalog URL configured
there is nothing to check. 931 bundles / 5.47 GB ship under `StreamingAssets/aa`.

**`scripts/export-card-art.py`** exports item art to PNG by name. Needs
`pip install UnityPy`; run with the game closed.

```
python scripts/export-card-art.py "Abducted Cow" "Amp" -o art/
python scripts/export-card-art.py --from-file names.txt -o art/
python scripts/export-card-art.py --all -o art/        # ~1240 files, ~2 GB
python scripts/export-card-art.py --hero thedragons -o art/
python scripts/export-card-art.py --list
```

It exports the material's `_MainTex`: a square 1024×1024 image, no frame or border.
`--texture` selects another slot. First run indexes the 12 `card_*` bundles and caches
locators to `scripts/.card-art-index.json` (gitignored); later runs take ~2.5s. Use
`--rebuild-index` after a game patch. Measured: `--hero thedragons` wrote 110 files in
55s, zero failures.

Two things that shaped it, both worth remembering:

- **The asset's own name is a dev placeholder for newer content.** The Season 15
  instruments ship as `AMP` and `BladedBass`, not `Amp` and `Bass`, so matching on asset
  names alone silently loses them. Resolution goes through `GameData.db` instead, joining
  by template id — the SO's `cardGUID` field **is** the DB template id — then falling back
  to internal name, then display name. So the names you type are the ones the browser
  shows. Works without the DB, just less well.
- **Coverage is 1180 / 1396 items, and the gap is real, not a bug.** 29 items have no
  `ArtKey` at all (blank in game too); 187 are the shared-art group — every
  `<X>'s Package`, the chibis, a few instruments — pointing at generic art that is not
  shipped as a per-card asset. Confirmed by sweeping all 931 bundles (31s): `CardData`
  objects exist **only** in the 12 `card_*` bundles. The script names each casualty and
  exits non-zero rather than skipping quietly. Closing the gap would need a `catalog.bin`
  parser to follow `ArtKey → bundle` directly — not attempted.

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
   Silver but sells by tag). Note this is *not* the same field as `ConstraintTier`, which
   **is** a real filter and is read — see §5. Where neither exists, tier rules key off the
   description and are not derivable.
5. **`availableHeroes: []` means every hero**, not none (`CollectionSourceEntry.cs:65`).
6. **Unregistering a module does not unpatch it.** `ApplyHarmonyPatches` discovers patch
   classes by reflecting over the whole assembly, so disabled features still hook the
   game. Harmless here (none touch the network), but relevant if a minimal patch
   footprint is ever wanted.
7. `run.sh` needs Git Bash on Windows; the Bash tool's PowerShell-style here-strings
   (`@'...'@`) are a parse error in bash.
8. **A card's art asset name is not its display name.** Newer content ships dev
   placeholders (`AMP`, `BladedBass`); the real name lives in `GameData.db`. Join on the
   SO's `cardGUID`, which is the DB template id — see §6.
9. **This fork has no `tests/` directory**, despite `CLAUDE.md` documenting one. Nothing
   to run; verification is build + the scripts + in-game.

## Verification: no-network confirmed (2026-08-07)

Ran a completed run on The Dragons with all six first-party hosts pointed at `127.0.0.1`
and a freshly deleted `LogOutput.log`. **Result: nothing was ever sent, and nothing tried.**

The proof is in `BazaarPlusPlusV4/bazaarplusplus.db`, not the log:

```
runs:            status=completed, completed=1, hero=Hero8
run_sync_state:  dirty=1
                 uploaded_seq / uploaded_status  = NULL
                 last_attempt_at_utc             = NULL   <- never attempted
                 retry_count = 0, last_error     = NULL
battles:         replay_last_uploaded_at_utc = NULL, last_synced_at_utc = NULL
bazaardb_snapshot_uploads: 0 rows
```

The run was recorded locally and queued (`dirty=1`), but no attempt was made. This is the
distinguishing signal: had the pump been alive and merely *blocked*, `RunBundleUploadService`
would have called `MarkRunUploadFailed(runId, attemptedAtUtc, error)`, populating
`last_attempt_at_utc`, `retry_count` and `last_error`. All three are untouched, so the code
path never executed. That is positive evidence, not absence of evidence. The log agreed:
40 lines, no connection errors, no upload events, no HTTP.

**Dead end, do not repeat:** checking `Get-DnsClientCache` for these domains proves nothing
once the hosts entries exist. Windows preloads hosts-file entries into the resolver cache on
`ipconfig /flushdns`, so all six show up with `127.0.0.1` whether or not anything looked them
up. Use the database bookkeeping instead.

Restore the hosts file afterwards from `%USERPROFILE%\Documents\hosts.bak-bpp`.

## Open items

### Next session (2026-08-10)

- [ ] **Deploy the Luxe fix.** The live install predates `6cb62be`; the branch build only
      went to a scratch dir. Needs the elevated `dotnet build` from *Environment* above.
- [ ] **Test `scripts/export-card-art.py`** — user is trying it out. Untested so far:
      running it on a machine without `UnityPy` (should exit 2 with the pip hint), the
      `--game` / `--db` overrides, and a full `--all` run (~1240 files, ~2 GB).
      Everything else in §6 was exercised and passed.

### Standing

- [x] **27 reported rule drifts** — read through on 2026-08-09. See §5; 10 were script
      bugs, 1 was a real catalog gap, the remaining 16 provably change nothing.
- [ ] **`RandomHeroSkinPool` throws for The Dragons.** Surfaced during the verification run:
      `lobby.collectible_pool.degraded` / `ArgumentException: "Random hero skin pool requires
      at least one skin."` The `hero_skin` collectibles table has zero entries for Hero8 — its
      skin assets exist in Addressables but are not registered yet — and
      `RandomHeroSkinPoolStateFactory.Create` assumes every hero has at least one. Caught and
      logged, so the random-skin feature just no-ops. Upstream bug, not ours; guard it if the
      warning is annoying.
- [ ] Confirm Uitar Center's inferred rule (`tagsAny: ["Instrument"]`) matches what it
      actually offers in game.
- [ ] Optional: rebase onto upstream when the public repo catches up to 5.x.
- [ ] Optional: a `catalog.bin` parser would close the last 187 items in the art exporter
      by following `ArtKey → bundle` directly. Only worth it if the shared/generic art
      actually matters — see §6.

## Things deliberately not done

- Not using the Tauri installer at all — no auto-update, no OBS overlay. BepInEx and the
  mod are installed by hand.
- Not deleting unused feature code, only its registrations. Smaller diff, easier rebase.
- Not regenerating `collection-sources.json` from scratch. Entry grouping, ordering and
  merchant *identity* (the "Aila" entry consolidates 8 encounter cards) are editorial.
- `Backroom Dealings` excluded from the catalog: its `SpawnContext` is null, so it offers
  nothing browsable. The catalog already omits it for the other heroes that list it.
