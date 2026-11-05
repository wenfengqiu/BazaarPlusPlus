#nullable enable
using BazaarPlusPlus.Infrastructure;
using TheBazaar.Assets.Scripts.ScriptableObjectsScripts;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace BazaarPlusPlus.Game.CollectionPanel.Grid;

// L2 of the design's four-layer cache stack (§7). Item art (CardAssetDataSO) is loaded by
// CardPreviewItem.LoadArt directly through Addressables.LoadAssetAsync<>, bypassing the
// game's shared AssetLoader cache; each call increments the Addressables ref count and the
// game never releases. Without L2, scrolling through 1146 Items would leak 1146 ref counts.
//
// We hold the AsyncOperationHandle ourselves so we can call Addressables.Release exactly
// once per artKey when the panel closes. An LRU bound caps resident SOs at a fixed number
// regardless of catalog size; the LRU only evicts entries with refcount 0 so handles still
// in use by active or pooled cards stay resident.
//
// Since the 2026-11-04 game update the SO no longer embeds its Material: `cardMaterial`
// became `cardMaterialReference`, an AssetReferenceT<Material> that is its own Addressables
// asset. Each entry therefore holds two handles — the SO and the Material it points at —
// loaded and released together, so the rest of the panel still sees one unit per artKey.
internal sealed class CollectionCardArtCache
{
    private const int DefaultCapacity = 256;

    private readonly int _capacity;
    private readonly Dictionary<string, CacheEntry> _entries = new(StringComparer.Ordinal);
    private readonly LinkedList<string> _lru = new();
    private readonly Dictionary<string, LinkedListNode<string>> _nodeMap = new(
        StringComparer.Ordinal
    );
    private readonly HashSet<string> _failedKeys = new(StringComparer.Ordinal);
    private readonly CollectionCardArtLogState _logState = new();

    public CollectionCardArtCache(int capacity = DefaultCapacity)
    {
        _capacity = Math.Max(8, capacity);
    }

    // Returns null on load failure; the caller proceeds without a material assignment, which
    // matches the game's own behaviour for invalid art keys (blank face, frame still drawn).
    public Task<CollectionCardArt?> Get(string artKey) => GetCore(artKey, acquireRef: false);

    public Task<CollectionCardArt?> Acquire(string artKey) => GetCore(artKey, acquireRef: true);

    internal void ReportDegraded(
        CollectionPanelLogReasonCode reasonCode,
        string? artKey,
        Exception exception
    ) =>
        _logState.ReportDegraded(
            reasonCode,
            CollectionCardArtStatus.ArtUnavailable,
            artKey,
            exception
        );

    private async Task<CollectionCardArt?> GetCore(string artKey, bool acquireRef)
    {
        if (string.IsNullOrEmpty(artKey))
            return null;

        if (_failedKeys.Contains(artKey))
            return null;

        if (_entries.TryGetValue(artKey, out var existing))
        {
            Touch(artKey);
            if (acquireRef)
                existing.RefCount++;
            return existing.Art;
        }

        var assetHandle = await LoadOrFail<CardAssetDataSO>(artKey, artKey);
        if (assetHandle == null)
            return null;

        // The game guards the same way (CardPreviewItem.UpdateCardImageMaterial): no valid
        // reference means no art, which renders as a blank face with the frame still drawn.
        var reference = assetHandle.Value.Result.cardMaterialReference;
        if (reference == null || !reference.RuntimeKeyIsValid())
        {
            _logState.ReportDegraded(
                CollectionPanelLogReasonCode.AddressablesLoadFailed,
                CollectionCardArtStatus.ArtUnavailable,
                artKey,
                null
            );
            ReleaseQuietly(assetHandle.Value);
            _failedKeys.Add(artKey);
            return null;
        }

        // Load by RuntimeKey rather than reference.LoadAssetAsync(): an AssetReference keeps a
        // single internal handle and throws on a second load, and the game's own AssetLoader
        // may already hold that one for this SO.
        var materialHandle = await LoadOrFail<Material>(reference.RuntimeKey, artKey);
        if (materialHandle == null)
        {
            ReleaseQuietly(assetHandle.Value);
            return null;
        }

        // A second concurrent Get could have populated the entry while we awaited.
        if (_entries.TryGetValue(artKey, out var raced))
        {
            ReleaseQuietly(materialHandle.Value);
            ReleaseQuietly(assetHandle.Value);
            Touch(artKey);
            if (acquireRef)
                raced.RefCount++;
            return raced.Art;
        }

        var art = new CollectionCardArt(assetHandle.Value.Result, materialHandle.Value.Result);
        var node = _lru.AddFirst(artKey);
        _nodeMap[artKey] = node;
        _entries[artKey] = new CacheEntry(
            assetHandle.Value,
            materialHandle.Value,
            art,
            acquireRef ? 1 : 0
        );
        Evict();
        return art;
    }

    // Loads one Addressables asset. On failure it logs, releases the handle, marks artKey
    // failed and returns null, so the caller only unwinds what it already holds.
    private async Task<AsyncOperationHandle<T>?> LoadOrFail<T>(object key, string artKey)
        where T : UnityEngine.Object
    {
        AsyncOperationHandle<T> handle;
        try
        {
            handle = Addressables.LoadAssetAsync<T>(key);
            await handle.Task;
        }
        catch (Exception ex)
        {
            _logState.ReportDegraded(
                CollectionPanelLogReasonCode.AddressablesLoadException,
                CollectionCardArtStatus.ArtUnavailable,
                artKey,
                ex
            );
            _failedKeys.Add(artKey);
            return null;
        }

        if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
        {
            _logState.ReportDegraded(
                CollectionPanelLogReasonCode.AddressablesLoadFailed,
                CollectionCardArtStatus.ArtUnavailable,
                artKey,
                null
            );
            ReleaseQuietly(handle);
            _failedKeys.Add(artKey);
            return null;
        }

        return handle;
    }

    private static void ReleaseQuietly<T>(AsyncOperationHandle<T> handle)
    {
        try
        {
            Addressables.Release(handle);
        }
        catch
        {
            // best-effort
        }
    }

    public void AddRef(string artKey)
    {
        if (string.IsNullOrEmpty(artKey))
            return;
        if (_entries.TryGetValue(artKey, out var entry))
            entry.RefCount++;
    }

    public void Release(string artKey)
    {
        if (string.IsNullOrEmpty(artKey))
            return;
        if (_entries.TryGetValue(artKey, out var entry))
            entry.RefCount = Math.Max(0, entry.RefCount - 1);
    }

    public void DisposeAll()
    {
        foreach (var pair in _entries)
        {
            try
            {
                pair.Value.ReleaseHandles();
            }
            catch (Exception ex)
            {
                BppLog.DebugEvent(
                    CollectionPanelLogEvents.CacheCleanupFailed,
                    ex,
                    () =>
                        [
                            CollectionPanelLogEvents.CacheCleanupFailedCache.Bind(
                                CollectionCacheKind.Art
                            ),
                            CollectionPanelLogEvents.CacheCleanupFailedStage.Bind(
                                CollectionCacheCleanupStage.Release
                            ),
                            CollectionPanelLogEvents.CacheCleanupFailedArtKey.Bind(pair.Key),
                        ]
                );
            }
        }
        _entries.Clear();
        _lru.Clear();
        _nodeMap.Clear();
        _failedKeys.Clear();
    }

    private void Evict()
    {
        while (_lru.Count > _capacity)
        {
            // Walk from tail to head looking for an entry with refcount 0. If every entry is
            // still in use we stop and let the cache temporarily exceed _capacity rather than
            // pull the rug from under a live card.
            var node = _lru.Last;
            string? evictKey = null;
            while (node != null)
            {
                if (_entries.TryGetValue(node.Value, out var entry) && entry.RefCount <= 0)
                {
                    evictKey = node.Value;
                    break;
                }
                node = node.Previous;
            }
            if (evictKey == null)
                break;

            if (_nodeMap.TryGetValue(evictKey, out var evictNode))
            {
                _lru.Remove(evictNode);
                _nodeMap.Remove(evictKey);
            }
            if (_entries.TryGetValue(evictKey, out var evictedEntry))
            {
                _entries.Remove(evictKey);
                try
                {
                    evictedEntry.ReleaseHandles();
                }
                catch (Exception ex)
                {
                    BppLog.DebugEvent(
                        CollectionPanelLogEvents.CacheCleanupFailed,
                        ex,
                        () =>
                            [
                                CollectionPanelLogEvents.CacheCleanupFailedCache.Bind(
                                    CollectionCacheKind.Art
                                ),
                                CollectionPanelLogEvents.CacheCleanupFailedStage.Bind(
                                    CollectionCacheCleanupStage.EvictRelease
                                ),
                                CollectionPanelLogEvents.CacheCleanupFailedArtKey.Bind(evictKey),
                            ]
                    );
                }
            }
        }
    }

    private void Touch(string artKey)
    {
        if (!_nodeMap.TryGetValue(artKey, out var node))
            return;
        _lru.Remove(node);
        _lru.AddFirst(node);
    }

    private sealed class CacheEntry
    {
        public CacheEntry(
            AsyncOperationHandle<CardAssetDataSO> assetHandle,
            AsyncOperationHandle<Material> materialHandle,
            CollectionCardArt art,
            int refCount
        )
        {
            AssetHandle = assetHandle;
            MaterialHandle = materialHandle;
            Art = art;
            RefCount = Math.Max(0, refCount);
        }

        public AsyncOperationHandle<CardAssetDataSO> AssetHandle { get; }
        public AsyncOperationHandle<Material> MaterialHandle { get; }
        public CollectionCardArt Art { get; }
        public int RefCount { get; set; }

        // Material first, in reverse load order. If that release throws, the SO is still
        // released and the exception reaches the caller's cleanup logging.
        public void ReleaseHandles()
        {
            try
            {
                Addressables.Release(MaterialHandle);
            }
            finally
            {
                Addressables.Release(AssetHandle);
            }
        }
    }
}

// One resolved card art: the SO and the source Material its cardMaterialReference names.
// SourceMaterial is the Addressables-owned asset. Never mutate or destroy it; clone it, as
// CollectionCardMaterialCache does.
internal sealed class CollectionCardArt
{
    public CollectionCardArt(CardAssetDataSO asset, Material sourceMaterial)
    {
        Asset = asset;
        SourceMaterial = sourceMaterial;
    }

    public CardAssetDataSO Asset { get; }
    public Material SourceMaterial { get; }
}
