using System.Text.Json.Serialization;

/// <summary>骰子 / 硬币结果，对应 battlefield.dice 或 battlefield.coin。</summary>
public class DiceCoin
{
    [JsonPropertyName("player")] public int Player { get; set; }  // 0=公用，1=P1，2=P2
    [JsonPropertyName("value")] public int Value { get; set; }    // dice: 1-6；coin: 1=正面，0=反面
    [JsonPropertyName("ts")] public long Ts { get; set; }         // 时间戳（毫秒）
}
