# resume.md

Working notes for a private fork of BazaarPlusPlus. Last updated 2026-11-06 (Propeller
Hat and 11 other cards drew in Tiny mode; §10). The 2026-11-04 game update is in §9.
**Start at [Open items](#open-items).**

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

Branch **`minimal-merchant-browser`**, with everything committed. It builds clean at 0
errors / 0 warnings against the current game assemblies.

> ✅ **The live install is current** as of 2026-11-06: the plugins `BazaarPlusPlus.dll`
> hash matches `bin/Debug`, and the user confirmed the Tiny fix (§10) in game.

Committed:

```
acaeccc fix(collection): clear the baked Tiny keyword on cached card materials
170ce6e update for season 20                       (the 2026-11-04 work, §9)
4e724b0 fix(collection): pin CardPreviewBase.SetUp after the game added an overload
de913aa fix(collection): restore the dock button for the new settings bar layout
d3c991a update for season 18                       (the 2026-09-02 work, §7)
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

## Environment

| | |
|---|---|
| Game | `C:\Program Files (x86)\Steam\steamapps\common\The Bazaar` (Steam app 1617400) |
| Live card DB | `%USERPROFILE%\AppData\LocalLow\Tempo Storm\The Bazaar\prod\cache\GameData.db` |
| .NET SDK | 10.0.302 at `C:\Program Files\dotnet` (**not on PATH**; `global.json` pins 10.0.100 `latestFeature`, so SDK 8 fails — the README's ".NET 8+" is wrong) |
| Mod version | 4.6.0 from `Directory.Build.props`; the 4.2.0 in `tauri.conf.json` is the *installer* version |
| BepInEx | 5.4.23.5, installed, stock |
| Game build | `1.0.13082-prod-windows-x64-dae65d53` (logged at startup as `game_build=`) |
| Unity | 6000.3.27f2 since 2026-11-04 (was 6000.3.11f1; read from `TheBazaar_Data/globalgamemanagers`; the bundles carry no version string, so UnityPy must be told) |
| Card art | 733 Addressables bundles / 6.0 GB under `TheBazaar_Data/StreamingAssets/aa`, fully local (928 / 5.6 GB before the 2026-11-04 patch, 931 / 5.47 GB before 2026-09-02) |
| Python | `UnityPy` 1.25.3 installed, for `scripts/export-card-art.py` only |
| Game assembly inspection | no decompiler installed (`run.sh decompile` needs one). A Mono.Cecil dumper does the job — see §9 |

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
(`CollectionCardArtCache.cs`). The card's Material is cloned and assigned to
`_cardImage.material` — the art is a **material, not a sprite**, because the card shader
composites frame, tier gems and enchantment FX at runtime. **Since 2026-11-04 the SO no
longer embeds the Material** (`cardMaterial` → `cardMaterialReference`, an
`AssetReferenceT<Material>`), so the art cache makes a second Addressables load and holds
both handles per art key (§9).

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
- **Coverage was 1197 / 1408 items on the 2026-09-02 build — and the "shared-art gap"
  turned out to be a join bug, not missing art.** Superseded by §9: the 186 "shared-art"
  items (every `<X>'s Package`, the chibis, a few instruments) share one `CardData`
  between several items, and joining on the SO's single `cardGUID` reaches only one of
  them. Joining on `ArtKey` through a `catalog.bin` parser reaches all of them; coverage
  is now every item with a real `ArtKey` (§9). `CardData` objects do still exist **only**
  in the 12 `card_*` bundles (swept on 2026-09-02).

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

### 8. The 2026-10-08 game update (`de913aa`, `4e724b0`)

Recorded after the fact from the two commits; this document was not updated that day.

- **Grey cards, the second time.** The update added `CardPreviewBase.SetUp(TCardBase,
  bool, CancellationToken)` beside the four-argument overload, so the name-only
  `AccessTools.Method` lookup in `NativeCardPreviewReflection` threw
  `AmbiguousMatchException`. Pinned to the four-argument overload the invoke site already
  passes. (An *added overload* is the mirror image of trap 13's added optional parameter:
  both are invisible to the compiler and fatal to name-based reflection.)
- **Dock button hidden.** The new settings-bar layout left no room above the gear, so the
  planner reported `blocker=viewport`. Ported from upstream: fall back to placing *below*
  the gear, shrink the sibling gap 18 → 8, and give the button its own sorting canvas so
  the hero-ready background stops swallowing its clicks. The resulting
  `dock_layout.degraded` → `recovered` pair in the log is this fallback working.

### 9. The 2026-11-04 game update

A full rebuild again: every managed assembly, Unity 6000.3.11f1 → **6000.3.27f2**, the
Addressables catalog (`catalog_2026.11.04.22.12.11`), and `GameData.db`.

| | before (2026-09-02) | after |
|---|---|---|
| Unity | 6000.3.11f1 | 6000.3.27f2 |
| Addressables bundles | 928 / 5.6 GB | 733 / 6.0 GB (12 `card_*` bundles, unchanged) |
| Items in `GameData.db` | 1408 | 1452 (+44); 582 skills, 561 encounter events |
| Heroes | 8 + Common | 8 + Common — no new hero (`EHero` still ends at `Hero8`) |
| New `EHiddenTag` / `ECardTag` with live cards | — | none the browser needs (below) |

**The user launched once before this session, and the log named the break** (trap 14):
every collection card was grey, `bind_degraded … reason_code=native_preview_runtime_failed`
with `MissingFieldException: CardAssetDataSO.cardMaterial`. The build agreed: three
compile errors, all that one field — the entire compile surface of the update.

**Grey cards, the third time: the Material moved out of the SO.** `CardAssetDataSO` lost
`cardMaterial` (an embedded `Material`) and gained `cardMaterialReference`, an
`AssetReferenceT<Material>`. The Material is now its own Addressables asset. The game's
own path (`CardPreviewItem.UpdateCardImageMaterial`, read from IL) is: load the SO, check
`cardMaterialReference.RuntimeKeyIsValid()`, `LoadAssetAsyncByReference<Material>`,
clone, set `shader = _cardMaterialShader`. The fix follows that:

- `CollectionCardArtCache` loads the Material by the reference's `RuntimeKey` right after
  the SO, and each cache entry now owns **both** handles, released together (Material
  first) on eviction and dispose. Get/Acquire return a `CollectionCardArt` (SO + source
  Material), so the refcount/LRU logic is untouched — one unit per art key, as before.
- Loading by `RuntimeKey` rather than `reference.LoadAssetAsync()` is deliberate: an
  `AssetReference` keeps one internal handle and throws on a second load, and the game's
  `AssetLoader` may already hold it.
- An invalid reference degrades exactly like a missing art key did (blank face, frame
  drawn, logged once) — the same guard the game applies.
- `CollectionCardMaterialCache.GetOrCreate` clones `art.SourceMaterial`; the source is
  Addressables-owned and is never mutated or destroyed.

**Confirmed in game** after the user deployed: no `bind_degraded`, card art renders.

**Merchant portraits showed only their left and right edges** (seen in game after
deploy: Aimbot cut, Jay Jay fine). No log line, because the load succeeds. Cause: **14
portrait sprites carry a 9-slice border of 230 px left and right** (Aimbot, Gaseo,
Stickybeans, Karnok, Private Pitchfork, Pinfeather, Shelter Shelby, The Antiquarian, The
Tester, Kelsa, Mama Bear, Uncle Odi, Uitar Center, The Dragons; read as `m_Border` from
the bundle), and UI Toolkit applies a sprite border to `background-image` as slicing. In
a small chip the edge strips keep full size and the middle collapses. The other 59 have
no border. Dead ends on the way, so they are not retried: animated portraits (none of
the 76 is), mesh type or texture format (identical across broken and working ones), and
mesh coverage (100% for all; an early "fragmented mesh" reading of the screenshot was
wrong). Fix (`CollectionPanelView.Filters.cs`, `SourceChipBackground`): all 73 checkable
portrait sprites are unpacked with `rect` = their full 1024×1024 texture, so the chip
draws `sprite.texture` as a plain quad, with identical framing and no slicing. Anything
not matching that shape keeps the sprite path. **Confirmed in game** by the user on
2026-11-04: the portraits are whole.

How it was found: the user's description ("only the left and right parts shown, the
middle cut") named 9-slicing outright, where a screenshot alone had been misread. Ask for
the symptom in words as well as a picture.

**Patch targets audited — now mechanised.** With no decompiler on the machine, a small
Mono.Cecil console tool (Cecil 0.11.4 is in the NuGet cache) read the *compiled* mod and the
six game assemblies, so `nameof`, `typeof` and constants arrive resolved. It checks every
`[HarmonyPatch]` target exists, is unambiguous or pinned, and that every prefix/postfix
parameter binds by name (including `___field` injections), then scans IL for string-named
`AccessTools.*` / `Type.GetX` lookups. Result: **64/64 patch targets resolve with all
parameters binding; no ambiguous overloads.** The string-lookup misses were all fallback
chains (`TypeByName("X") ?? TypeByName("TheBazaar_X")`), PTR probes (`Config.ServerOption`,
`Receive(…, bool)`) or heuristic mis-pairings — each checked by hand against the type, all
live. It lived in the session scratchpad and is not in the repo; recreating it is ~150 lines.

**Catalog sync — the drift report exploded, and the cause was a new game mechanic.** The
first run reported ~50 merchants as `FixedHero: Vanessa` with every tag repeated nine
times. Not data noise: the update added **cross-hero affinity skills** — *Vanessa's
Fence*, *Pygmalien's Client*, *Dooley's Pal*, *Mak's Confidant*, *Jules' Sous Chef*,
*Stelle's Supplier*, *Karnok's Crush*, *The Dragons' Fan*. Own one and 47 merchants also
stock that hero's items: each merchant got one extra spawn group per hero, carrying
`TSpawnBehaviorIgnoreHero` and gated by a `TPrerequisiteCardCount` on that skill's id
(usually alongside a day ≥ 2 `TPrerequisiteRun`). The script walked every group, took the
first `ConstraintHero` it met, and concatenated the tags.

Fix (`sync-collection-sources.py`): derive the rule from the **base pool** — drop any
group with a prerequisite on owning a specific card (`TCardConditionalId`; *any*
prerequisite, not all, because of the day gate). Run-only gates (day, etc.) still count,
as before. That alone restored the known baseline, so the pre-existing gated groups never
fed it. The browser keeps showing the base pool: what a merchant sells *you*, without a
run-specific skill. Real changes after that:

- **Laurel** — new Jules merchant, "Sells Heated and Chilled related items. Buys your
  Toys at +1 value" (aura 3 is a flat +1 SellPrice on Toys; resolved by hand, per the
  catalog's convention). Rule `SelectedHero` + `HeatedReference`/`ChilledReference`, group
  `tag-type-specialist`, order 20 (end of group).
- **Vermir** (Crit trainer) is now offered to Pygmalien too.
- **27 descriptions reworded by the game** from "Sells X items" to "Sells X related
  items" (trainers: "Teaches X related skills"). Adopted where the *only* change is the
  word "related" — it is the text the player now sees, and it is more accurate for rules
  that include the Reference twins. Kept hand-authored: Barkun, Midsworth, Quixel, Pip
  (the game's are unresolved placeholders) and The Tester (§5).

New baseline: **8 rule drifts + 6 description diffs** — the 8 inert drifts of §5/§7, the
5 known description diffs, and Laurel's resolved placeholder. Anything beyond is new.

**Tags: nothing to add.** Re-ran the trap-12 test (tooltip entry + at least one card).
The only hidden tag that newly passes is `Unsellable`, on exactly one item (*Depleted
Device*, a generated Tech item) — a sale restriction, not a mechanic anyone filters by;
left out. Every `ECardTag` with live items is already in `PlayerFacingCardTags`.
(Note: the `tooltips` table is **one row** whose value is the 136-key dictionary —
`select Id from tooltips` returns the single id `tooltips`. Reading it as one row per key
gives "2 keys" and a false alarm.)

**Still fully offline.** Re-ran the §6 checks against the new catalog: 0 URLs in
`settings.json` or `catalog.bin` (ASCII and UTF-16), no `RemoteLoadPath` / `ServerData`,
and all 733 bundle locations resolve through `{Addressables.RuntimePath}`.

**The art exporter, rebuilt on a `catalog.bin` parser.** It broke the same way (it read
`cardMaterial`'s path id), and the honest fix needed GUID → bundle: same-folder pairing
of `*_CardData.asset` with its `.mat` covered only 1294 of 1338. So the script now parses
the binary Addressables catalog (ContentCatalogData v2: magic `0x0DE38942`; key table of
(key object, location set); strings length-prefixed, or flagged `0x40000000` as leaf-first
linked segments) — 13,334 GUID keys in ~1 s, each to (asset path, bundle). It refuses a
catalog with another magic/version rather than guess. Two hops: `ArtKey` → CardData path,
`cardMaterialReference` → Material bundle + path → path id via the bundle's
`m_Container`. Index version 4; first build ~7 s.

Coverage: **1429 of 1452 items** — every item with a real `ArtKey`. The rest are 20 items
with no `ArtKey` (blank in game too) and the 3 `[… ITEM TEMPLATE]` dev cards. `--list`
shows 1318 distinct art assets, since items sharing a CardData share one image.
A full `--all` run on 2026-11-04 wrote **1316 files, 1.8 GB, in ~10 min** (was ~35),
exit 1 with exactly the two known failures: `Octopus` and `VanessasShip`, whose `_MainTex`
lives in a dependency bundle. Reading bundles works with the game running.

### 10. Twelve cards drew in Tiny mode (2026-11-06)

**Symptom** (user, in the merchant browser): Propeller Hat's art looks like a stretched
copy of its Tiny version.

**Tiny is not a separate image here.** Propeller Hat's bundle holds one 1024×1024 `_D`
texture. Tiny is a shader variant, switched by the `_ISTINY_ON` keyword and tuned per
material (`_TinyScalar`, `_TinyOffsetterX/Y`, `_TinyScaling`, `_TinyEchoScale`, …), so the
art is re-framed by the shader. Whether any other card has redrawn Tiny art was not checked.

**Cause: the mod's material clone skipped a step of the game's.** 12 of 1322 card materials
ship with `_ISTINY_ON` and `_isTiny = 1` baked in, all Medium, none with Tiny anywhere in
their `GameData.db` card: Propeller Hat, Beach Umbrella, Dragonmelon, Worry Wart, Book of
Secrets, Bionic Arm, Disintegration Ray, Sponsored Apparel, Display Case, Ledger, Amp,
Cauterizing Blade. `CardPreviewItem.UpdateCardImageMaterial` (read from IL) clones the
material, sets the shader, then calls `DisableKeyword("_ISTINY_ON")`. The mod replaces that
path (`CollectionItemLoadArtPatch` → `CollectionCardMaterialCache.GetOrCreate`), and its
clone kept the keyword.

**Fix:** `GetOrCreate` makes the same call, using the game's constant
`CardTinyShaderVariables.IsTinyKeyword` (`_ISTINY_ON`), so a rename fails at compile time.
**Confirmed in game** by the user on 2026-11-06.

**The same gap, left as is by the user's decision (2026-11-06):** that method also disables
`_ISPREMIUM_ON` when `isPremium` is false. The browser always passes false
(`NativeCardPreviewRuntime.cs:111`), the mod's `LoadArt` prefix ignores it, and **61
materials ship with the keyword on**, so those cards can draw differently from stock.

**What `_ISPREMIUM_ON` is: the Card Skin effect, not a new feature.** The game's tooltip
(`CardSkins`, version 5.0.0): "Card Skins add premium animation to your in-game cards. Card
Skins are automatically (and always) equipped." `GameData.db` lists 1241 `CardSkin`
collectibles, with season ids from 2 up and `InStore` / `IsFoundInChests` flags.
`ItemVisualsController.Setup` asks `CollectionManager.IsPremiumCardSkinEquipped` and
`SetCardFrameMaterial` sets the keyword from the answer, on or off, so the baked value never
decides it in a run. The 61 therefore look like assets saved with the toggle on, not a
chosen set (inferred: they show no clean pattern in rarity, season or chest flags). The
shader (`The Bazaar/PremiumCard`) is compiled, so the exact visual was not read from it.

**Looked at and ruled out:**

- 7 items whose material `_CRDSIZE_*` disagrees with their database size (Tiny Cutlass,
  Bongos, Meat, Azakan Stew, Exoskeleton, Improvised Bludgeon, Snowmobile). No game assembly
  outside the `System`/`Unity`/`Microsoft` families references that keyword, so the mod
  does not diverge from stock there.
- Shiny Fang's baked `_ENCHANTMENTSTATUS_PRISMATIC`: stock calls `ApplyEnchantment` only
  when an enchantment is passed, so it is left in place either way.

**Tooling:** `decompiled/` is absent on this machine. A ~30-line Mono.Cecil console tool
(regex over member names and string literals, optional IL dump by method) answered this;
it lived in the session scratchpad, like the §9 auditor.

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
15. **Card art breaks on every update, three different ways so far.** 2026-09-02: an
   added optional parameter (trap 13). 2026-10-08: an added overload made a name-only
   lookup ambiguous (§8). 2026-11-04: the embedded Material became an Addressables
   reference (§9). After any update, the first thing to check in game is the collection
   grid, and the first grep is `bind_degraded`.
16. **A merchant's spawn context is not one rule.** Since 2026-11-04 most merchants carry
   per-hero groups that open only when the player owns a cross-hero skill (§9). Any tool
   that walks *every* constraint in the tree picks up the gated groups' heroes and tags.
   Derive from the base pool: drop groups with a `TCardConditionalId` prerequisite.
17. **Game updates arrive while the game is running.** Steam patches, the user launches,
   and the running process holds `BazaarPlusPlus.dll`. Check `tasklist` before assuming
   a build deployed, and compare the plugins DLL timestamp with `bin/Debug`.
18. **UI Toolkit applies a sprite's border as 9-slicing.** A `background-image` set from
   a `Sprite` with a non-zero `border` keeps the edge strips at full size and squeezes
   the middle, while the game's uGUI ignores the border. The symptom is a portrait
   showing only its outer edges. Check `m_Border` in the bundle first. Fix by drawing the
   texture when the sprite spans it — see §9.

19. **A replaced game method takes its side effects with it.** `CollectionItemLoadArtPatch`
   stands in for `CardPreviewItem.LoadArt`, so anything the game adds to that path
   silently stops applying to the browser. When a card looks wrong but loads fine, diff
   the replacement against the method's current IL first — see §10.

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

### Next session (after 2026-11-06)

- [x] Deploy and confirm the Tiny fix (§10) — confirmed by the user 2026-11-06.
- [x] `_ISPREMIUM_ON` (§10) — the user chose to leave it as is on 2026-11-06.

### From 2026-11-04

- [x] Deploy and confirm card art in game — done 2026-11-04 (§9).
- [x] Merchant portraits whole after the 9-slice fix — confirmed in game 2026-11-04 (§9).
      If one is ever cut again, log that sprite's `rect` and `border`: it no longer
      matches the full-texture shape the fix relies on.
- [x] Keyword chips from 2026-09-02 — seen in the user's 2026-11-04 screenshot: Tempo and
      Experience in Tags; Tempo / Heated / Chilled / Tech Related in Related; plain Heated
      and Chilled correctly absent.
- [x] No `collection_panel.cache.cleanup_failed` in the first post-deploy log.
- [ ] **Confirm the catalog edits in the merchant list:** Laurel for Jules, Vermir for
      Pygmalien, and the "related" wording. Not checked yet.
- [ ] Mama Bear under trainers (from 2026-09-02). Not checked yet.
- [ ] Expected `LogOutput.log` noise, all benign: the `NetMessageProcessor.Receive` probe,
      `native_game_fonts.degraded` → `recovered`, `dock_layout.degraded` → `recovered`
      (the §8 fallback), `combat_replay.current_recording_ui.observed` (Info), and the
      skin-pool warning below. Anything else is new.

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
- [x] ~~Optional: a `catalog.bin` parser to close the exporter's shared-art gap~~ — done
      2026-11-04, forced by the Material move; coverage is every item with an `ArtKey` (§9).
- [ ] Optional: keep the Cecil patch-target auditor (§9) in the repo, e.g. under
      `tools/`, so the next update's audit is one command instead of a rewrite.
- [ ] Optional: the browser could show what a merchant *additionally* sells with a
      cross-hero affinity skill (§9). Deliberately not done — it is per-run state.
- [ ] Optional: the drift script cannot propose a brand-new *trainer* (they ship untagged,
      trap 1), which is how Mama Bear stayed missing. A cheap guard: assert the mentor set
      — one `ConstraintIsOnlyHero` trainer per hero — covers every hero in `HeroOrder`.

## Things deliberately not done

- `_ISPREMIUM_ON` is not cleared on cached card materials, though stock previews clear it:
  the 61 materials that ship with it on can draw the Card Skin effect in the browser. The
  user's decision, 2026-11-06 (§10). The fix would be one line beside the Tiny one.
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
- `Unsellable` stays out of the keyword row despite a tooltip entry: one generated item
  carries it, and it is a sale restriction, not a mechanic (§9).
- Merchant pools exclude the cross-hero skill-gated spawn groups (§9): the browser shows
  the base pool every player sees, not one run's extensions.
- No `Tempo` entry in `CollectionHiddenTagGroups`: those groups exist only for
  `collection-sources.json` rules, and no catalogued merchant constrains on Tempo. The
  four `Tempo Up (Level Up)` encounters that do are level-up rewards, the family the
  catalog excludes by design.
