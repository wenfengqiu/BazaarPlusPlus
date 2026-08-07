#nullable enable
using BazaarGameShared.Domain.Core.Types;

namespace BazaarPlusPlus.Game.CardTags;

// Canonical ordering for card tags that are meaningful to players. Feature-specific
// consumers may filter this list further (for example aggregate item effects only
// count item types, so Merchant is excluded there).
internal static class PlayerFacingCardTags
{
    public static readonly IReadOnlyList<ECardTag> Ordered = new[]
    {
        ECardTag.Weapon,
        ECardTag.Friend,
        ECardTag.Aquatic,
        ECardTag.Tool,
        ECardTag.Drone,
        ECardTag.Vehicle,
        ECardTag.Food,
        ECardTag.Trap,
        ECardTag.Toy,
        ECardTag.Potion,
        ECardTag.Reagent,
        ECardTag.Relic,
        ECardTag.Dragon,
        // 24 spawnable items carry Instrument (Bass, Bagpipes, Death Metal Drum Kit), most of
        // them the Season 15 hero's, but the tag was never listed here so the filter chip for
        // it could never appear. Of the other ECardTag members absent from this list, none has
        // a single spawnable item -- they are internal markers such as Sigil, Key and Combat.
        ECardTag.Instrument,
        ECardTag.Core,
        ECardTag.Tech,
        ECardTag.Dinosaur,
        ECardTag.Ray,
        ECardTag.Apparel,
        ECardTag.Merchant,
        ECardTag.Property,
        ECardTag.Loot,
    };
}
