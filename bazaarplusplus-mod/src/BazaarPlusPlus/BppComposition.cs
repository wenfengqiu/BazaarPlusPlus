#nullable enable
using BazaarPlusPlus.Core.Config;
using BazaarPlusPlus.Core.Events;
using BazaarPlusPlus.Core.Paths;
using BazaarPlusPlus.Core.Runtime;
using BazaarPlusPlus.Game.BilingualItemNames;
using BazaarPlusPlus.Game.CollectionPanel;
using BazaarPlusPlus.Game.CombatReplay;
using BazaarPlusPlus.Game.CombatReplay.Video;
using BazaarPlusPlus.Game.CombatStatusBar;
using BazaarPlusPlus.Game.EventPreview;
using BazaarPlusPlus.Game.HistoryPanel;
using BazaarPlusPlus.Game.ItemEnchantPreview;
using BazaarPlusPlus.Game.LegendaryPosition;
using BazaarPlusPlus.Game.NameOverride;
using BazaarPlusPlus.Game.OverlayPanels;
using BazaarPlusPlus.Game.PvpBattles.Persistence;
using BazaarPlusPlus.Game.QuestPreview;
using BazaarPlusPlus.Game.RunLifecycle;
using BazaarPlusPlus.Game.RunLogging;
using BazaarPlusPlus.Game.Screenshots;
using BazaarPlusPlus.Game.Screenshots.Upload;
using BazaarPlusPlus.Game.Settings;
using BazaarPlusPlus.Game.Supporters;
using BazaarPlusPlus.Game.Tooltips;
using BazaarPlusPlus.Game.VoiceSubtitles;
using BazaarPlusPlus.GameInterop;
using BazaarPlusPlus.GameInterop.CardPreview;
using BazaarPlusPlus.GameInterop.Encounter;
using BazaarPlusPlus.GameInterop.RunSnapshot;
using BazaarPlusPlus.GameInterop.StaticCards;
using BazaarPlusPlus.ModApi.Clients;
using BazaarPlusPlus.Patches;
using BazaarPlusPlus.Patches.Tooltips;
using BepInEx.Configuration;
using BepInEx.Logging;

namespace BazaarPlusPlus;

internal sealed class BppComposition : IDisposable
{
    private readonly InMemoryBppEventBus _eventBus = new();
    private readonly BppConfig _config = new();
    private readonly BepInExPathProvider _paths = new();
    private readonly RunContextStore _runContext = new();
    private readonly GameStateProbe _gameStateProbe = new();
    private readonly EncounterStateProbe _encounterStateProbe = new();
    private readonly RunSnapshotProbe _runSnapshotProbe = new();
    private readonly BppStaticCardMapProvider _staticCardMapProvider = new();
    private readonly BppRuntimeServices _services;
    private readonly BppFeatureRegistry _featureRegistry = new();
    private readonly BppMountableRegistry _mountables = new();
    private readonly SettingsDockEntryRegistry _settingsDockRegistry = new();
    private readonly RunLifecycleModule _runLifecycle;
    private readonly CombatReplayModule _combatReplayModule;
    private readonly CombatStatusBarModule _combatStatusBarModule;
    private readonly RunLoggingModule _runLoggingModule;
    private readonly EncounterPreviewModule _encounterPreviewModule;
    private readonly INativeCardPreviewHost _nativeCardPreviewHost;
    private readonly EndOfRunCaptureWorkflow _endOfRunCaptureWorkflow;
    private readonly BppPatchFeatures _patchFeatures;
    // MINIMAL BUILD: voice subtitles and build-recommendation catalog removed (both fetch remotely).
    private ModOnlineClient? _onlineClientRef;
    private BazaarDbLinkClient? _accountLinkClientRef;
    private PvpBattleCatalog? _pvpBattleCatalog;

    public IBppServices Services => _services;
    public RunLifecycleModule RunLifecycle => _runLifecycle;

    public IPvpBattleCatalog PvpBattleCatalog =>
        _pvpBattleCatalog ??= new PvpBattleCatalog(
            _paths.RunLogDatabasePath
                ?? throw new InvalidOperationException("Run log database path is not initialized.")
        );

    public BppMountableRegistry Mountables => _mountables;
    public SettingsDockEntryRegistry SettingsDockRegistry => _settingsDockRegistry;
    public BppPatchFeatures PatchFeatures => _patchFeatures;
    public ModOnlineClient? OnlineClient => _onlineClientRef;
    public BazaarDbLinkClient? AccountLinkClient => _accountLinkClientRef;

    public BppComposition(ManualLogSource logger, ConfigFile configFile, IGameBuildInfo gameBuild)
    {
        if (logger == null)
            throw new ArgumentNullException(nameof(logger));
        if (configFile == null)
            throw new ArgumentNullException(nameof(configFile));
        if (gameBuild == null)
            throw new ArgumentNullException(nameof(gameBuild));

        _config.Initialize(configFile);
        _paths.Initialize();
        _runContext.Reset();

        _services = new BppRuntimeServices(
            _eventBus,
            _config,
            _paths,
            _runContext,
            _gameStateProbe,
            _encounterStateProbe,
            _runSnapshotProbe,
            gameBuild,
            logger
        );

        _runLifecycle = new RunLifecycleModule(_eventBus, _gameStateProbe, _runContext);
        _combatReplayModule = new CombatReplayModule(_eventBus);
        _combatStatusBarModule = new CombatStatusBarModule(_eventBus, _runContext);
        _nativeCardPreviewHost = new NativeCardPreviewHost(new NativeTooltipDataFactoryAdapter());
        var encounterPreviewCachePath = System.IO.Path.Combine(
            System.IO.Path.GetDirectoryName(
                _paths.RunLogDatabasePath
                    ?? throw new InvalidOperationException(
                        "Run log database path is not initialized."
                    )
            )!,
            "EncounterPreview",
            "preview-plans.json"
        );
        _encounterPreviewModule = new EncounterPreviewModule(
            _services,
            _staticCardMapProvider,
            encounterPreviewCachePath
        );
        _endOfRunCaptureWorkflow = new EndOfRunCaptureWorkflow(_services);
        _patchFeatures = new BppPatchFeatures(_encounterPreviewModule, _endOfRunCaptureWorkflow);
        _runLoggingModule = new RunLoggingModule(
            _services,
            PvpBattleCatalog,
            () => _combatReplayModule.Runtime?.HasPendingPersistence == true
        );

        _featureRegistry.Register(_runLifecycle);
        _featureRegistry.Register(_combatReplayModule);
        _featureRegistry.Register(_combatStatusBarModule);
        _featureRegistry.Register(_runLoggingModule);

        _settingsDockRegistry.Register(BazaarDbSnapshotUploadSettingsDockEntry.Create());
        _settingsDockRegistry.Register(FixedSupporterListSettingsDockEntry.Create());
        _settingsDockRegistry.Register(ChineseLocaleModeSettingsDockEntry.Create(_eventBus));
        _settingsDockRegistry.Register(CombatStatusBarSettingsDockEntry.Create());
        _settingsDockRegistry.Register(BilingualItemNamesSettingsDockEntry.Create());
        _settingsDockRegistry.Register(new EndOfRunScreenshotSettingsDockEntry());
        _settingsDockRegistry.Register(new HistoryPanelSettingsDockEntry());
        _settingsDockRegistry.Register(ItemEnchantPreviewSettingsDockEntry.Create());
        _settingsDockRegistry.Register(EventPreviewSettingsDockEntry.Create());
        _settingsDockRegistry.Register(
            QuestPreviewSettingsDockEntry.Create(() =>
            {
                QuestRewardPreviewTooltipPatch.ClearPooledPresentation();
                AggregateItemMissingTypesTooltipPatch.ClearPooledPresentation();
            })
        );
        _settingsDockRegistry.Register(LegendaryPositionSettingsDockEntry.Create());
        _settingsDockRegistry.Register(NameOverrideSettingsDockEntry.Create());

        // MINIMAL BUILD: upload pumps removed (run-bundle + BazaarDB screenshot uploads).
        _mountables.Register(
            new ComponentMount<EventPreviewStaticDataObserver>(
                (observer, _) => observer.Initialize(_encounterPreviewModule)
            )
        );
        // The overlay host must mount before every Main Overlay Panel mount below: panels
        // register their lifecycle with it through the accessor.
        var overlayPanelHostMount = new OverlayPanelHostMount();
        _mountables.Register(overlayPanelHostMount);
        _mountables.Register(
            new CollectionPanelMount(
                () => overlayPanelHostMount.Host,
                _staticCardMapProvider,
                _nativeCardPreviewHost
            )
        );
        _mountables.Register(
            new ComponentMount<CombatReplayVideoRecorder>((c, s) => c.Initialize(s))
        );
        _mountables.Register(new ComponentMount<CombatStatusBar>((c, s) => c.Initialize(s)));
        _mountables.Register(
            new ComponentMount<EndOfRunCaptureDriver>(
                (driver, services) => driver.Initialize(_endOfRunCaptureWorkflow, services)
            )
        );
        // MINIMAL BUILD: removed MainMenuVersionCheckController (installer version fetch),
        // HistoryPanelMount (ghost-battle sync), LiveBuildPanelMount (tenwin recommendations
        // fetch) and VoiceLineDisplayDispatcher (voice-lines catalog fetch).
        _mountables.Register(new ComponentMount<VersionLabelScanner>());
        _mountables.Register(
            new ComponentMount<TooltipModifierRefreshController>(
                (c, s) => c.Initialize(s.Config, s.EncounterState, _nativeCardPreviewHost)
            )
        );

        // Publish the public game-interop facades for the out-of-process BazaarAgent host
        // plugin (it declares [BepInDependency(BazaarPlusPlus)] and therefore loads after us).
        // BazaarPlusPlus does not reference the agent module; the host reads the facades through
        // BazaarAgentGameBridge. Published unconditionally — they are passive accessors that
        // nothing reads unless the host plugin is installed. The recorder's runtime accessor is
        // lazy on purpose: CombatReplayRuntime is attached after this constructor runs.
        BazaarAgentGameBridge.Current = new BazaarAgentGameProbe(_encounterStateProbe);
        BazaarAgentGameBridge.CurrentRecorder = BazaarAgentReplayRecorderWiring.Create(
            () => _combatReplayModule.Runtime,
            _services
        );
    }

    public void AttachCombatReplayRuntime(CombatReplayRuntime runtime) =>
        _combatReplayModule.AttachRuntime(runtime);

    public void AttachOnlineClient(ModOnlineClient? client) => _onlineClientRef = client;

    public void AttachAccountLinkClient(BazaarDbLinkClient? client) =>
        _accountLinkClientRef = client;

    public void Start() => _featureRegistry.Start();

    public void Dispose()
    {
        BazaarAgentGameBridge.Current = null;
        BazaarAgentGameBridge.CurrentRecorder = null;
        _featureRegistry.Stop();
        _endOfRunCaptureWorkflow.Dispose();
        _encounterPreviewModule.Dispose();
    }
}
