using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// 战场实体的 JSON 序列化配置，字段命名与 controller 端 protocol.js 保持一致。
/// 枚举按 camelCase 名称读写（如 Phase.Main1 ↔ "main1"、Orientation.Vertical ↔ "vertical"）。
/// </summary>
public static class GameJson
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };
}
