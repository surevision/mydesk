using System.Text.Json.Serialization;

/// <summary>卡牌指示物：某种指示物的数量（kind 用英文规范键，如 "Magic"）。</summary>
public class CardCounter
{
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("count")] public int Count { get; set; }
}
