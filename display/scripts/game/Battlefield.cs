using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// 完整战场快照，对应 protocol.js 顶部的 battlefield 结构（由 controller 生成、经 center 下发）。
/// </summary>
public class Battlefield
{
    [JsonPropertyName("phase")] public Phase Phase { get; set; } = Phase.Draw;
    [JsonPropertyName("turn_player")] public int TurnPlayer { get; set; } = 1;   // 1/2（0 未知）
    [JsonPropertyName("dice")] public DiceCoin Dice { get; set; }
    [JsonPropertyName("coin")] public DiceCoin Coin { get; set; }
    [JsonPropertyName("players")] public Dictionary<string, PlayerData> Players { get; set; } =
        new Dictionary<string, PlayerData>
        {
            ["1"] = new PlayerData(),
            ["2"] = new PlayerData(),
        };

    public PlayerData P1 => GetPlayer(1);
    public PlayerData P2 => GetPlayer(2);

    /// <summary>按玩家编号（1/2）取场地，不存在返回 null。</summary>
    public PlayerData GetPlayer(int player) =>
        Players != null && Players.TryGetValue(player.ToString(), out var p) ? p : null;

    public static Battlefield FromJson(string json) => JsonSerializer.Deserialize<Battlefield>(json, GameJson.Options);

    public static bool TryFromJson(string json, out Battlefield battlefield)
    {
        try
        {
            battlefield = FromJson(json);
            return battlefield != null;
        }
        catch (JsonException)
        {
            battlefield = null;
            return false;
        }
    }

    public string ToJson() => JsonSerializer.Serialize(this, GameJson.Options);
    public Battlefield Clone() => FromJson(ToJson());

}
