using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>一张卡，对应 protocol.js 中的 card 结构。</summary>
public class CardData
{
    [JsonPropertyName("id")] public int Id { get; set; } = -1;   // ydk passcode；-1 表示占位/未识别
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("atk")] public int Atk { get; set; }
    [JsonPropertyName("def")] public int Def { get; set; }
    [JsonPropertyName("level")] public int Level { get; set; }
    [JsonPropertyName("rank")] public int Rank { get; set; }
    [JsonPropertyName("attribute")] public string Attribute { get; set; } = "";
    [JsonPropertyName("race")] public string Race { get; set; } = "";
    [JsonPropertyName("arrows")] public List<int> Arrows { get; set; } = new();
    [JsonPropertyName("face_up")] public bool FaceUp { get; set; } = true;
    [JsonPropertyName("orientation")] public Orientation Orientation { get; set; } = Orientation.Vertical;
    [JsonPropertyName("markers")] public List<string> Markers { get; set; } = new();
    [JsonPropertyName("counters")] public List<CardCounter> Counters { get; set; } = new();
    [JsonPropertyName("extra")] public Dictionary<string, JsonElement> Extra { get; set; } = new();

    /// <summary>是否为占位/未识别卡（id 小于 0）。</summary>
    [JsonIgnore] public bool IsPlaceholder => Id < 0;

    public static CardData FromJson(string json) => JsonSerializer.Deserialize<CardData>(json, GameJson.Options);
    public string ToJson() => JsonSerializer.Serialize(this, GameJson.Options);
    public CardData Clone() => FromJson(ToJson());
}
