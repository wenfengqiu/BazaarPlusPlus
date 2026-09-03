#nullable enable
using System.Reflection;
using System.Runtime.ExceptionServices;
using BazaarGameShared.Domain.Cards;
using BazaarGameShared.Domain.Core.Types;
using HarmonyLib;
using TheBazaar.AppFramework;
using UnityEngine;
using Object = UnityEngine.Object;

namespace BazaarPlusPlus.GameInterop.CardPreview;

internal readonly record struct NativeCardPreviewInstantiateOutcome(
    Component? Card,
    NativeCardPreviewFailure? Failure
);

internal sealed class NativeCardPreviewAssetLoader
{
    private static readonly MethodInfo? InstantiateAssetMethod = AccessTools.Method(
        typeof(AssetLoader),
        "InstantiateAssetAsyncByReference"
    );

    // Reflection does not apply optional-parameter defaults, and the 2026-09-02 game
    // patch gave this method a second one (AssetScope? scope = null). Bind the trailing
    // arguments once from the signature so a later addition costs nothing; a parameter
    // that carries no default leaves this null and the preview degrades instead of
    // throwing TargetParameterCountException on every card.
    private static readonly object?[]? InstantiateAssetArgs = BindTrailingDefaults(
        InstantiateAssetMethod
    );
    private static readonly FieldInfo? SmallItemAsset = AccessTools.Field(
        typeof(AssetLoader),
        "SmallCardUIAssetRef"
    );
    private static readonly FieldInfo? MediumItemAsset = AccessTools.Field(
        typeof(AssetLoader),
        "MediumCardUIAssetRef"
    );
    private static readonly FieldInfo? LargeItemAsset = AccessTools.Field(
        typeof(AssetLoader),
        "LargeCardUIAssetRef"
    );
    private static readonly FieldInfo? SkillAsset = AccessTools.Field(
        typeof(AssetLoader),
        "SkillUIAssetRef"
    );

    private static object?[]? BindTrailingDefaults(MethodInfo? method)
    {
        var parameters = method?.GetParameters();
        if (parameters == null || parameters.Length == 0)
            return null;

        var arguments = new object?[parameters.Length];
        for (var i = 1; i < parameters.Length; i++)
        {
            if (!parameters[i].HasDefaultValue || parameters[i].DefaultValue is Missing)
                return null;
            arguments[i] = parameters[i].DefaultValue;
        }
        return arguments;
    }

    internal async Task<NativeCardPreviewInstantiateOutcome> InstantiateInactiveCardAsync(
        TCardBase template,
        Transform parent,
        CancellationToken token = default
    )
    {
        if (template == null || parent == null)
            return default;

        if (!Services.TryGet<AssetLoader>(out var assetLoader) || assetLoader == null)
        {
            return Failed(template.Id, NativeCardPreviewFailureReason.AssetLoaderUnavailable);
        }

        var assetField = ResolveAssetField(template);
        if (InstantiateAssetMethod == null || InstantiateAssetArgs == null || assetField == null)
        {
            return Failed(template.Id, NativeCardPreviewFailureReason.ReflectionUnavailable);
        }

        GameObject? root = null;
        try
        {
            token.ThrowIfCancellationRequested();
            var assetReference = assetField.GetValue(assetLoader);
            if (assetReference == null)
                return Failed(template.Id, NativeCardPreviewFailureReason.PreviewTypeUnavailable);

            var arguments = (object?[])InstantiateAssetArgs.Clone();
            arguments[0] = assetReference;
            var raw = InstantiateAssetMethod.Invoke(assetLoader, arguments);
            if (raw is not Task<GameObject> task)
                return Failed(template.Id, NativeCardPreviewFailureReason.ReflectionUnavailable);

            root = await task;
            token.ThrowIfCancellationRequested();
            if (root == null)
            {
                return Failed(
                    template.Id,
                    NativeCardPreviewFailureReason.PreviewComponentUnavailable
                );
            }

            root.SetActive(false);
            root.transform.SetParent(parent, worldPositionStays: false);
            var cardPreviewBaseType = NativeCardPreviewReflection.CardPreviewBaseType;
            if (cardPreviewBaseType == null)
            {
                Object.Destroy(root);
                return Failed(template.Id, NativeCardPreviewFailureReason.PreviewTypeUnavailable);
            }

            var card = root.GetComponent(cardPreviewBaseType);
            if (card == null)
            {
                Object.Destroy(root);
                return Failed(
                    template.Id,
                    NativeCardPreviewFailureReason.PreviewComponentUnavailable
                );
            }

            return new NativeCardPreviewInstantiateOutcome(card, null);
        }
        catch (OperationCanceledException)
        {
            if (root != null)
                Object.Destroy(root);
            throw;
        }
        catch (TargetInvocationException ex) when (ex.InnerException is OperationCanceledException)
        {
            if (root != null)
                Object.Destroy(root);
            ExceptionDispatchInfo.Capture(ex.InnerException!).Throw();
            throw;
        }
        catch (Exception ex)
        {
            if (root != null)
                Object.Destroy(root);
            return new NativeCardPreviewInstantiateOutcome(
                null,
                new NativeCardPreviewFailure(
                    NativeCardPreviewOperation.Instantiate,
                    NativeCardPreviewFailureReason.InstantiateException,
                    template.Id,
                    ex
                )
            );
        }
    }

    private static FieldInfo? ResolveAssetField(TCardBase template) =>
        template.Type switch
        {
            ECardType.Skill => SkillAsset,
            ECardType.Item when template.Size == ECardSize.Small => SmallItemAsset,
            ECardType.Item when template.Size == ECardSize.Medium => MediumItemAsset,
            ECardType.Item when template.Size == ECardSize.Large => LargeItemAsset,
            _ => null,
        };

    private static NativeCardPreviewInstantiateOutcome Failed(
        Guid templateId,
        NativeCardPreviewFailureReason reason
    ) =>
        new(
            null,
            new NativeCardPreviewFailure(NativeCardPreviewOperation.Instantiate, reason, templateId)
        );
}
