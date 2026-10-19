using System;

/// <summary>格子/区域类型。key 与 controller 端一致：front/back/ex/field/exdeck/grave/deck。</summary>
public enum ZoneType
{
    ExDeck,
    Deck,
    Grave,
    Field,
    Front,
    Back,
    Ex,
}

/// <summary>ZoneType 与协议字符串、格子数量之间的换算。</summary>
public static class ZoneTypeExtensions
{
    public static string ToKey(this ZoneType zone) => zone switch
    {
        ZoneType.ExDeck => "exdeck",
        ZoneType.Deck => "deck",
        ZoneType.Grave => "grave",
        ZoneType.Field => "field",
        ZoneType.Front => "front",
        ZoneType.Back => "back",
        ZoneType.Ex => "ex",
        _ => throw new ArgumentOutOfRangeException(nameof(zone)),
    };

    public static ZoneType FromKey(string key) => key switch
    {
        "exdeck" => ZoneType.ExDeck,
        "deck" => ZoneType.Deck,
        "grave" => ZoneType.Grave,
        "field" => ZoneType.Field,
        "front" => ZoneType.Front,
        "back" => ZoneType.Back,
        "ex" => ZoneType.Ex,
        _ => throw new ArgumentException($"未知的格子类型: {key}", nameof(key)),
    };

    /// <summary>是否为「数组区域」（front/back/ex）。</summary>
    public static bool IsArray(this ZoneType zone) =>
        zone is ZoneType.Front or ZoneType.Back or ZoneType.Ex;

    /// <summary>区域格子数量：front/back=5，ex=2，其余=1。</summary>
    public static int Size(this ZoneType zone) => zone switch
    {
        ZoneType.Front or ZoneType.Back => 5,
        ZoneType.Ex => 2,
        _ => 1,
    };
}
