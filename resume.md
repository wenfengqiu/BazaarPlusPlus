# resume.md

Working notes for a private fork of BazaarPlusPlus. Last updated 2026-09-02 (the
2026-09-02 game update: a build break, the grey-card regression, a catalog sync, the
Tempo keywords, an art index fix). **Start at [Open items](#open-items).**

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
plus this document, with eight files **uncommitted** from the 2026-09-02 game update
(seven code, plus this one — §7). Everything builds clean at 0 errors / 0 warnings
against the patched game assemblies, and the no-network goal is verified (see below).

> ✅ **The live install is current** as of 2026-09-02 19:57 — every change listed below
> is deployed and its DLL hash matches the build output. The plugins folder turned out to
> be writable without elevation this time, so the plain `dotnet build` deployed it. Art
> rendering is confirmed working in game; the keyword chips are not yet eyeballed.

Uncommitted:

```
 M bazaarplusplus-mod/scripts/export-card-art.py                     index fingerprint
 M .../BazaarPlusPlus/Data/CollectionSources/collection-sources.json catalog sync
 M .../GameInterop/CardPreview/NativeCardPreviewAssetLoader.cs       grey-card fix
 M .../Game/CollectionPanel/Data/CollectionKeywordWhitelist.cs       Tempo + tag audit
 M .../GameInterop/TagTypography/ReferenceTagBaseResolver.cs         TechReference base
 M .../Game/Lobby/RandomHeroSkinPool/RandomHeroSkinPoolNativeController.cs
 M .../Patches/Lobby/RandomHeroSkinPoolPatches.cs                    build break fix
 M resume.md
```

Committing is the user's job here. One split that matches the branch's existing style,
one commit per file group — no hunk staging needed:

```
fix(mod): follow the CosmeticItem.EquipableItem removal
    RandomHeroSkinPoolNativeController.cs, RandomHeroSkinPoolPatches.cs
fix(collection): restore card art after the 2026-09-02 patch
    NativeCardPreviewAssetLoader.cs
fix(collection): sync the catalog with the 2026-09-02 game update
    collection-sources.json  (Kev's Armory, Prospero, and the Mama Bear gap)
feat(collection): add the Tempo keywords and the missing tag references
    CollectionKeywordWhitelist.cs, ReferenceTagBaseResolver.cs
fix(tools): rebuild the card art index when the game is patched
    export-card-art.py
docs: record the 2026-09-02 game update
    resume.md
```

Committed:

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

14 files, +1301 / −68 committed; 19 files, +1649 / −94 with the working tree.

## Environment

| | |
|---|---|
| Game | `C:\Program Files (x86)\Steam\steamapps\common\The Bazaar` (Steam app 1617400) |
| Live card DB | `%USERPROFILE%\AppData\LocalLow\Tempo Storm\The Bazaar\prod\cache\GameData.db` |
| .NET SDK | 10.0.302 at `C:\Program Files\dotnet` (**not on PATH**; `global.json` pins 10.0.100 `latestFeature`, so SDK 8 fails — the README's ".NET 8+" is wrong) |
| Mod version | 4.6.0 from `Directory.Build.props`; the 4.2.0 in `tauri.conf.json` is the *installer* version |
| BepInEx | 5.4.23.5, installed, stock |
| Unity | 6000.3.11f1 (read from `TheBazaar_Data/globalgamemanagers`; the bundles carry no version string, so UnityPy must be told) |
| Card art | 928 Addressables bundles / 5.6 GB under `TheBazaar_Data/StreamingAssets/aa`, fully local (931 / 5.47 GB before the 2026-09-02 patch) |
| Python | `UnityPy` 1.25.3 installed, for `scripts/export-card-art.py` only |

Rebuild into the game folder (writes to `Program Files`, so it may need an **elevated**
shell — on 2026-09-02 the plugins folder was writable without one):

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

The hero is `EHero.Hero8` in the enum with no display name anywhere in the data *as of
2026-08-09* — the 2026-09-02 update put the name in the data and it matches (§7). Named
**"The Dragons"** from the collectible naming convention — `Album_TheDragons`,
`CardBack_TheDragons`, `Carpet_TheDragons`, `Skin_DRA_*`, and a card called *Honorary
Dragons*. The 2026-09-02 data confirms that reading verbatim (§7), so the guess stood;
the single constant `CollectionPanelText.Hero8DisplayName` is still where to change it if
the game ever renames the hero.

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
  zero spawnable items, so they correctly stay out. Re-checked after the 2026-09-02 update
  and still true; the tags that update *did* add are keywords, not types (§7).

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

Net: the catalog was right about everything except Luxe. A clean run then reported **9
rule drifts + 5 description diffs**, all listed above. `--write` re-verified idempotent.
The 2026-09-02 update made Prospero's drift real and it was fixed, so the live baseline is
now **8 + 5** — see §7.

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
| Bundle load paths | 928/928 via `{Addressables.RuntimePath}` (local) |
| Providers | `AssetBundleProvider` / `BundledAssetProvider` |

`m_DisableCatalogUpdateOnStart` is `false`, but with no remote catalog URL configured
there is nothing to check. 928 bundles / 5.6 GB ship under `StreamingAssets/aa`. The whole
table was re-run against the 2026-09-02 catalog and still reads zero (§7).

**`scripts/export-card-art.py`** exports item art to PNG by name. Needs
`pip install UnityPy`; run with the game closed.

```
python scripts/export-card-art.py "Abducted Cow" "Amp" -o art/
python scripts/export-card-art.py --from-file names.txt -o art/
python scripts/export-card-art.py --all -o art/        # 1249 files, ~1.7 GB
python scripts/export-card-art.py --hero thedragons -o art/
python scripts/export-card-art.py --list
```

It exports the material's `_MainTex`: usually a square 1024×1024 image, no frame or
border.
`--texture` selects another slot. First run indexes the 12 `card_*` bundles and caches
locators to `scripts/.card-art-index.json` (gitignored); later runs take ~2.5s.

The index **rebuilds itself after a game patch** (2026-09-02). It records the install path
and the contents of `aa/catalog.hash`, which Addressables rewrites on every build, and
rescans — ~6s — when either has moved. `--rebuild-index` still forces it. Before that the
cache silently outlived the build it described, which is exactly wrong the day a patch
lands. `--game` and `--db` are now hard requirements rather than hints: a path that is not
an install, or a database that does not exist, is an error instead of a quiet fall back to
whatever else was on the machine.

Two things that shaped it, both worth remembering:

- **The asset's own name is a dev placeholder for newer content.** The Season 15
  instruments ship as `AMP` and `BladedBass`, not `Amp` and `Bass`, so matching on asset
  names alone silently loses them. Resolution goes through `GameData.db` instead, joining
  by template id — the SO's `cardGUID` field **is** the DB template id — then falling back
  to internal name, then display name. So the names you type are the ones the browser
  shows. Works without the DB, just less well.
- **Coverage is 1197 / 1408 items on the 2026-09-02 build, and the gap is real, not a
  bug.** 25 items have no `ArtKey` at all (blank in game too); 186 are the shared-art
  group — every `<X>'s Package`, the chibis, a few instruments — pointing at generic art
  that is not shipped as a per-card asset. Confirmed by sweeping all bundles (31s):
  `CardData` objects exist **only** in the 12 `card_*` bundles. The script names each
  casualty and exits non-zero rather than skipping quietly. Closing the gap would need a
  `catalog.bin` parser to follow `ArtKey → bundle` directly — not attempted.

A full `--all` run was measured on 2026-09-02: **1249 files, ~1.7 GB, ~35 min**, exit 1
with exactly two named failures — `Octopus` (its `_MainTex` lives in a dependency bundle)
and `VanessasShip` (its material is not in the bundle its `CardData` sits in). Both fall
in the shared-art category the coverage note describes; nothing silently vanished. Not
every export is 1024×1024 either: 12 assets ship at another size, up to one 2048×2048.

### 7. The 2026-09-02 game update

The game shipped a full rebuild on 2026-09-02 (every managed assembly, the Addressables
catalog, `GameData.db`). What it actually moved, and what it forced here:

| | before | after |
|---|---|---|
| Unity | 6000.3.11f1 | 6000.3.11f1 (unchanged) |
| Addressables bundles | 931 / 5.47 GB | 928 / 5.6 GB, catalog `catalog_2026.09.02.11.09.16` |
| Cards in `GameData.db` | 1396 items | 3327 total: **1408 items** (+12), 557 skills, 553 encounter events |
| Seasons | through Season 15 | through Season 18 |
| Heroes | 8 + Common | **8 + Common — no new hero** (`EHero` still ends at `Hero8`) |

**Still fully offline.** Re-ran the checks from §6 against the new catalog: 0 URLs in
`settings.json` or `catalog.bin` (ASCII and UTF-16), no `RemoteLoadPath` / `ServerData`,
and 928/928 bundle load paths resolve through `{Addressables.RuntimePath}`.

**One build break, in the one place the API moved.** `CosmeticItem.EquipableItem` is
gone. Its backing field `_equipableItem` survives, and the project sets
`PublicizeAll`, so the four call sites now read the field. That was the *entire* compile
surface of the update — 0 errors / 0 warnings otherwise.

**Patch targets audited, not assumed.** A removed method named only by string in a
`[HarmonyPatch]` attribute fails at patch time, not compile time, so the whole surface
was checked mechanically: dump every type, method, field and property from the five game
assemblies via `System.Reflection.Metadata`, then resolve all 64 `[HarmonyPatch]`
targets and every `AccessTools.Method/Field/Property/TypeByName` string in the mod
against it. **All resolve.** But that checks names, not signatures — and the signature is
where this update actually bit (below). A second pass therefore dumped full parameter
lists (names and types) for every method in those assemblies, via `Assembly.LoadFrom` with
an `AssemblyResolve` handler pointed at `Managed/`, and checked:

- every Harmony prefix/postfix parameter name against its target's real parameter names
  (Harmony binds them by name) — **clean**;
- every `AccessTools.Method(…, new[] { typeof(…) })` overload lookup — **clean**. The
  `NetMessageProcessor.Receive` warning HarmonyX logs at startup is by design: that seam
  probes for a PTR-only overload and falls back to `ReceiveOrQueue(INetMessage)`, which is
  what this build has;
- every reflected `MethodInfo.Invoke` in the card-preview path against the current arity —
  **one break, the grey cards** (below).

What remains unverifiable statically is behaviour: a method that still exists, still takes
the same arguments, and does something different. Only a launch settles that.

The same trick validates the catalog: every hero, tag, hidden tag, size and tier string
in `collection-sources.json` still names a live enum member (`ECardSize`, not `ESize`).

**Catalog sync — three real changes.** The drift report went from the known-inert
baseline to 15 warnings + 1 proposed entry. Three were genuine:

- **Kev's Armory split in two.** A Vanessa-only encounter card
  (`6f5c1ce2…`, "Kev's Armory (Vanessa)") now carries the rule the shared card
  (`a4fa13f8…`, everyone but Mak and Vanessa) already had, identical in every constraint.
  Added as a second `sourceTemplateIds` entry rather than a second catalog entry — the
  Aila precedent, since the merchant's identity is one merchant.
- **Prospero is no longer an all-hero merchant.** Its spawn context lost
  `TSpawnBehaviorIgnoreHero`, so it sells *your* hero's economic items now; the game's own
  description dropped "from any hero" to match. This is the first drift that changed the
  browsed pool since the catalog was written, and the only one the update caused. Rule is
  now `SelectedHero` with the game's exact tag list (`BuyPrice`/`SellPrice`, which matched
  zero cards, dropped with it). Left in the `all-hero` group: groups only drive display
  order, and `The Tester` already sits there as a `SelectedHero` entry.
- **The Dragons' mentor trainer was missing entirely.** `Mama Bear (Level Up)`
  (`386dd351…`, "Teaches skills unique to The Dragons") is the eighth of a set the catalog
  had seven of — same `ConstraintIsOnlyHero` shape as Old Zane, Cymon, Mr. Tuskari, Kelsa,
  Zosima, Uncle Odi and Nonna. It was never *proposed* because trainers ship with an empty
  `Tags` array (trap 1) and the script only proposes tagged sources; it went unnoticed
  because nothing cross-checks the mentor set against the hero list. Inserted at trainer
  order 7, matching `CollectionPanel.HeroOrder`, so the later trainers shift down one.

After those three, the report is back to the §5 residue minus Prospero: **8 rule drifts +
5 description diffs**, every one of them already shown to change nothing. That is the new
baseline; anything beyond it is new.

**Every card rendered as a grey rectangle, and the log said why.** The first launch after
the update filled the collection browser with blank cards. `LogOutput.log` carried
`collection_panel.card.bind_degraded … reason_code=native_preview_unavailable` with a
`TargetParameterCountException` out of `NativeCardPreviewAssetLoader`: the update gave
`AssetLoader.InstantiateAssetAsyncByReference` a second, *optional* parameter
(`AssetScope? scope = null`). C# callers never notice an added optional parameter — the
compiler fills it in — but `MethodInfo.Invoke` does not apply defaults, so the one-element
argument array threw on every single card. The name-level audit could not see this; the
build could not either.

The fix binds the trailing arguments once from `GetParameters()` instead of hard-coding
the array, so the next added optional parameter costs nothing; a parameter with no default
leaves the handle unbound and the preview degrades as it already knows how to. Note the
other three call sites into this API (`CardPreviewBase.SetUp/Show/Resize`) are still
correct at 4/1/0 arguments — checked, not assumed.

**Tempo, and the tag audit it prompted.** The update added mechanics that arrive as
**`EHiddenTag` keywords, not `ECardTag` types** — so they surface in the panel's *Tags*
facet (`CollectionKeywordWhitelist`), not the type-chip row (`PlayerFacingCardTags`).
Every `ECardTag` in the data was already listed; four keywords with live cards were not.

The test for "player-facing" is not a judgement call: the game ships a keyword tooltip
table (`tooltips` in `GameData.db`, 136 keys) and the chip's label, icon and colour are
resolved from it by name through `TooltipTypography.GetConfiguration`. A hidden tag with
no entry there has no label to render. Applying that rule — *the game defines a tooltip
for it and at least one card carries it* — to all 100 `EHiddenTag` members:

| added | items | skills | note |
|---|---|---|---|
| `Tempo` | 20 | 16 | the Season 18 mechanic |
| `TempoReference` | 35 | 5 | the "related" twin |
| `HeatedReference` | 35 | 4 | base `Heated` on no card yet |
| `ChilledReference` | 22 | 3 | base `Chilled` on no card yet |
| `TechReference` | 13 | 0 | type-backed, like `PotionReference` |
| `Experience` | 2 | 0 | small but real |

`Heated` and `Chilled` were added as bases too, for symmetry: availability filtering hides
a chip with no cards, so they cost nothing and appear by themselves the day an item ships.
`ReferenceTagBaseResolver` already mapped Tempo/Heated/Chilled to their bases — only
`TechReference` needed a mapping (to `ECardTag.Tech`, the `PotionReference` precedent).

Excluded, and why: `Package` (121 items), `SpawnMusicNote`, `Level`, `Ticket`,
`AbsorbDestroy`, `AbsorbSlow`, `AbsorbFreeze`, `JoyReference` — no tooltip entry, so they
are system markers with no player-facing name. Three whitelisted keywords now match zero
cards (`CooldownReference`, `Multicast`, `QuestReference`); availability filtering already
hides them, so they stay.

Not touched: `CollectionHiddenTagGroups`. Its groups exist only for
`collection-sources.json` rules, and no catalog merchant constrains on Tempo — the four
`Tempo Up (Level Up)` encounters that do are level-up rewards, the same family as
`Arms Locker (Level Up)`, which the catalog excludes by design.

**The art exporter needed a rebuilt index, which exposed a bug.** The bundle set moved,
so the cached locators were stale — and nothing detected that; the script would happily
export from them. It now fingerprints the build and rebuilds itself (§6). Post-patch
coverage: 1197 / 1408 items, full `--all` run verified.

**"The Dragons" is confirmed by the game itself.** §2 named the hero from the
collectible naming convention and left a single constant to change if it was wrong. The
new data settles it — `Teaches skills unique to The Dragons`, `(if you are The Dragons)`,
`The Dragons (Hero Merchant)`. `CollectionPanelText.Hero8DisplayName` stands.

**The skin-pool warning is ours, and it did not go away.** `hero_skin` now carries one
Hero8 entry ("Explosive Debut Dragons", `Skin_DRA_02a`) — so the *data* gap named in the
old open item is closed — but `lobby.collectible_pool.degraded` still fires. The pool is
built from the skins actually **available to the account**, not from the catalog, and the
thrower is this mod's own `RandomHeroSkinPoolStateFactory.Create`, not the game's. Calling
it an upstream bug was wrong. It is caught and logged, the random-skin feature no-ops, and
nothing in the collection browser depends on it — so it stays an open item, now correctly
attributed.

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
10. **A game patch can delete a public property and keep its backing field.**
   `CosmeticItem.EquipableItem` went in the 2026-09-02 update; `_equipableItem` stayed, and
   `PublicizeAll` makes it readable, so following the field is the smaller and more
   faithful fix. Check for the field before reconstructing anything — see §7.
11. **Only typed references break at compile time.** A `[HarmonyPatch(typeof(X), "M")]`
   whose `M` is gone throws when patches are applied, and a prefix whose parameter name no
   longer matches throws too. Build success after a game update means very little on its
   own; audit the string-named targets (§7) and then launch.
12. **A new mechanic can arrive as a keyword, not a type.** `Tempo` is an `EHiddenTag`,
   so adding it to `PlayerFacingCardTags` would have done nothing — it belongs in
   `CollectionKeywordWhitelist`. To tell whether any hidden tag is player-facing, look it
   up in the game's own tooltip table (`tooltips` in `GameData.db`): that table is what
   gives a chip its label, icon and colour, so no entry means no chip — see §7.
13. **An added *optional* parameter is invisible to the compiler and fatal to reflection.**
   C# fills defaults in at the call site; `MethodInfo.Invoke` does not, and throws
   `TargetParameterCountException`. This is what turned every collection card grey on
   2026-09-02. Build the argument array from `GetParameters()` rather than hard-coding its
   length — see §7.
14. **`LogOutput.log` names the failure precisely; read it before theorising.** The grey
   cards took one grep: the event, the reason code, the exception type and the exact mod
   method were all on one line. The mod's degradation logging is good — use it.

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

### Next session (2026-09-03)

- [x] **Grey cards fixed and confirmed in game** (2026-09-02). Cause and fix in §7.
- [ ] **Confirm the new keyword chips.** They are built and deployed but not yet seen:
      **Tempo** in the Tags row, and **Tempo / Heated / Chilled / Tech Reference** plus
      **Experience** in the *Related* subsection (§7). `Heated` and `Chilled` should
      *not* appear — no card carries the base tag yet, and availability filtering hides
      a chip with no cards.
- [ ] **Confirm the catalog edits in the merchant list:** Mama Bear under trainers, and
      Prospero's description now reading "Sells Economic items". Spot-check Uitar Center
      while there (standing item below).
- [ ] Expected `LogOutput.log` noise after all of this, all benign: the
      `NetMessageProcessor.Receive` probe, one `native_game_fonts.degraded` immediately
      followed by `recovered`, `dock_layout.degraded`, and the skin-pool warning below.
      Anything else is new.

### Standing

- [x] **27 reported rule drifts** — read through on 2026-08-09. See §5; 10 were script
      bugs, 1 was a real catalog gap, the remaining 16 provably change nothing.
- [x] **Deploy the Luxe fix** — done 2026-09-02; the live install is current (§*Current
      state*).
- [x] **Test `scripts/export-card-art.py`** — done 2026-09-02, and it found two bugs, both
      fixed (§6). Verified: missing `UnityPy` exits 2 with the pip hint; `--game` / `--db`
      overrides work and now reject bad paths instead of falling back; the full `--all`
      run completes (numbers in §6).
- [ ] **`RandomHeroSkinPool` throws for The Dragons.** Still fires after the update, and
      it is **ours**, not upstream (§7 corrects the earlier note): the pool is built from
      the skins available to the account, and `RandomHeroSkinPoolStateFactory.Create`
      throws on an empty set. Caught and logged, feature no-ops, browser unaffected — guard
      it if the warning is annoying.
- [ ] Confirm Uitar Center's inferred rule (`tagsAny: ["Instrument"]`) matches what it
      actually offers in game.
- [ ] Optional: rebase onto upstream when the public repo catches up to 5.x.
- [ ] Optional: a `catalog.bin` parser would close the shared-art items in the exporter by
      following `ArtKey → bundle` directly. Only worth it if the shared/generic art
      actually matters — see §6.
- [ ] Optional: the drift script cannot propose a brand-new *trainer* (they ship untagged,
      trap 1), which is how Mama Bear stayed missing. A cheap guard: assert the mentor set
      — one `ConstraintIsOnlyHero` trainer per hero — covers every hero in `HeroOrder`.

## Things deliberately not done

- Not using the Tauri installer at all — no auto-update, no OBS overlay. BepInEx and the
  mod are installed by hand.
- Not deleting unused feature code, only its registrations. Smaller diff, easier rebase.
- Not regenerating `collection-sources.json` from scratch. Entry grouping, ordering and
  merchant *identity* (the "Aila" entry consolidates 8 encounter cards) are editorial.
- `Backroom Dealings` excluded from the catalog: its `SpawnContext` is null, so it offers
  nothing browsable. The catalog already omits it for the other heroes that list it.
- Hidden tags with no entry in the game's tooltip table stay out of the keyword row —
  `Package` (121 items), `SpawnMusicNote`, `Level`, `Ticket`, `Absorb*`, `JoyReference`.
  They are system markers with no player-facing name, icon or colour (§7).
- No `Tempo` entry in `CollectionHiddenTagGroups`: those groups exist only for
  `collection-sources.json` rules, and no catalogued merchant constrains on Tempo. The
  four `Tempo Up (Level Up)` encounters that do are level-up rewards, the family the
  catalog excludes by design.
