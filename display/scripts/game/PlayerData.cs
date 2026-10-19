using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// 一方玩家的场地，对应 protocol.js 的 players["1"]/players["2"]。
/// 单格区域：exdeck/deck/grave/field；数组区域：front(5)/back(5)/ex(2)。
/// </summary>
public class PlayerData
{
    [JsonPropertyName("lp")] public int Lp { get; set; } = 8000;
    [JsonPropertyName("exdeck")] public CardData ExDeck { get; set; }
    [JsonPropertyName("deck")] public CardData Deck { get; set; }
    [JsonPropertyName("grave")] public CardData Grave { get; set; }
    [JsonPropertyName("field")] public CardData Field { get; set; }
    [JsonPropertyName("front")] public List<CardData> Front { get; set; } = NewZone(ZoneType.Front);
    [JsonPropertyName("back")] public List<CardData> Back { get; set; } = NewZone(ZoneType.Back);
    [JsonPropertyName("ex")] public List<CardData> Ex { get; set; } = NewZone(ZoneType.Ex);

    private static List<CardData> NewZone(ZoneType zone)
    {
        var list = new List<CardData>();
        for (int i = 0; i < zone.Size(); i++) list.Add(null);
        return list;
    }

    /// <summary>取单格区域（数组区域返回 null）。</summary>
    public CardData GetSingle(ZoneType zone) => zone switch
    {
        ZoneType.ExDeck => ExDeck,
        ZoneType.Deck => Deck,
        ZoneType.Grave => Grave,
        ZoneType.Field => Field,
        _ => null,
    };

    public void SetSingle(ZoneType zone, CardData card)
    {
        switch (zone)
        {
            case ZoneType.ExDeck: ExDeck = card; break;
            case ZoneType.Deck: Deck = card; break;
            case ZoneType.Grave: Grave = card; break;
            case ZoneType.Field: Field = card; break;
        }
    }

    /// <summary>取数组区域（单格区域返回 null）。</summary>
    public List<CardData> GetArray(ZoneType zone) => zone switch
    {
        ZoneType.Front => Front,
        ZoneType.Back => Back,
        ZoneType.Ex => Ex,
        _ => null,
    };

    /// <summary>按区域与下标取卡（单格区域忽略 index）。</summary>
    public CardData GetCell(ZoneType zone, int index = 0)
    {
        if (zone.IsArray())
        {
            var arr = GetArray(zone);
            return arr != null && index >= 0 && index < arr.Count ? arr[index] : null;
        }
        return GetSingle(zone);
    }

    /// <summary>写入格子（card 传 null 表示清空）。</summary>
    public void SetCell(ZoneType zone, int index, CardData card)
    {
        if (zone.IsArray())
        {
            var arr = GetArray(zone);
            if (arr != null && index >= 0 && index < arr.Count) arr[index] = card;
            return;
        }
        SetSingle(zone, card);
    }

    public static PlayerData FromJson(string json) => JsonSerializer.Deserialize<PlayerData>(json, GameJson.Options);
    public string ToJson() => JsonSerializer.Serialize(this, GameJson.Options);
    public PlayerData Clone() => FromJson(ToJson());
}
