using Godot;
using System;
using System.Text;

/// <summary>
/// 网络连接节点（全局 Autoload）。
/// 作为 WebSocket 客户端连接到主控端（center），接收手动操作的游戏王投影场地的控制指令。
///
/// 约定消息为 JSON 文本，格式：
///   { "type": "on_lp_change", ...其他参数... }
/// 其中 "type" 即为下面对应接口的名称，处理函数内部实现暂时留空，由具体投影逻辑补充。
/// </summary>
public partial class Connection : Node
{
    // ---------- 可配置项 ----------

    /// <summary>服务器 IP。</summary>
    [Export]
    public string server_ip = "127.0.0.1";

    /// <summary>服务器端口。</summary>
    [Export]
    public int server_port = 8765;

    /// <summary>断线后是否自动重连。</summary>
    [Export]
    public bool auto_reconnect = true;

    /// <summary>自动重连的间隔（秒）。</summary>
    [Export]
    public float reconnect_interval = 3.0f;

    /// <summary>心跳发送间隔（秒）。</summary>
    [Export]
    public float heartbeat_interval = 5.0f;

    /// <summary>心跳超时时间（秒）：超过该时间未收到任何数据则判定连接断开并重连。</summary>
    [Export]
    public float heartbeat_timeout = 15.0f;

    // ---------- 内部状态 ----------

    private WebSocketPeer socket = new WebSocketPeer();
    private WebSocketPeer.State last_state = WebSocketPeer.State.Closed;
    private double reconnect_timer = 0.0;
    private bool manual_close = false;

    // 心跳计时（毫秒，来自 Time.GetTicksMsec）
    private ulong last_recv_time = 0;
    private ulong last_ping_time = 0;

    public override void _Ready()
    {
        base._Ready();
        last_recv_time = Time.GetTicksMsec();
        ConnectToServer();
    }

    public override void _Process(double delta)
    {
        base._Process(delta);

        // 驱动 WebSocket 状态机（必须每帧调用）
        socket.Poll();
        WebSocketPeer.State state = socket.GetReadyState();

        if (state != last_state)
        {
            OnStateChanged(state);
            last_state = state;
        }

        if (state == WebSocketPeer.State.Open)
        {
            // 连接正常：取出所有已到达的数据包并逐条处理
            while (socket.GetAvailablePacketCount() > 0)
            {
                byte[] packet = socket.GetPacket();
                last_recv_time = Time.GetTicksMsec();
                HandleMessage(Encoding.UTF8.GetString(packet));
            }

            // 心跳：定时发送 ping，并在超时未收到任何数据时主动断开重连
            ulong now = Time.GetTicksMsec();
            if (now - last_ping_time >= (ulong)(heartbeat_interval * 1000.0f))
            {
                last_ping_time = now;
                SendPing();
            }
            if (now - last_recv_time >= (ulong)(heartbeat_timeout * 1000.0f))
            {
                GD.PushWarning("心跳超时，断开并重新连接");
                socket.Close();
            }
        }
        else if (auto_reconnect && !manual_close && state == WebSocketPeer.State.Closed)
        {
            // 连接已关闭：按间隔定时重连
            reconnect_timer += delta;
            if (reconnect_timer >= reconnect_interval)
            {
                ConnectToServer();
            }
        }
    }

    public override void _ExitTree()
    {
        base._ExitTree();
        // 退出时主动关闭，避免自动重连
        manual_close = true;
        socket.Close();
    }

    // ---------- 连接管理 ----------

    /// <summary>连接到配置的服务器。</summary>
    public void ConnectToServer()
    {
        reconnect_timer = 0.0;

        string url = $"ws://{server_ip}:{server_port}";
        Error err = socket.ConnectToUrl(url);
        if (err != Error.Ok)
        {
            GD.PushError($"WebSocket 连接 {url} 失败: {err}");
        }
        else
        {
            GD.Print($"WebSocket 正在连接 {url} ...");
        }
    }

    /// <summary>状态变化时的回调。</summary>
    private void OnStateChanged(WebSocketPeer.State state)
    {
        switch (state)
        {
            case WebSocketPeer.State.Open:
                GD.Print("WebSocket 已连接");
                // 连接建立后重置心跳计时，立即进入正常心跳节奏
                ulong now = Time.GetTicksMsec();
                last_recv_time = now;
                last_ping_time = now;
                break;
            case WebSocketPeer.State.Closed:
                GD.Print("WebSocket 连接已关闭");
                break;
        }
    }

    // ---------- 消息解析与分发 ----------

    /// <summary>解析一条 JSON 消息并按 type 分发到对应的处理函数。</summary>
    private void HandleMessage(string message)
    {
        Variant parsed = Json.ParseString(message);
        if (parsed.VariantType != Variant.Type.Dictionary)
        {
            GD.PushWarning($"收到的消息不是 JSON 对象: {message}");
            return;
        }

        Godot.Collections.Dictionary data = parsed.AsGodotDictionary();
        string type = GetString(data, "type");

        switch (type)
        {
            case "on_lp_change":
                on_lp_change(GetInt(data, "player"), GetInt(data, "lp"));
                break;

            case "on_battlefield_change":
                on_battlefield_change(GetString(data, "battlefield"));
                break;

            case "on_summon_anim":
                on_summon_anim(GetString(data, "summon_type"));
                break;

            case "on_destroy_anim":
                on_destroy_anim(
                    GetInt(data, "player"),
                    GetString(data, "cell_type"),
                    GetInt(data, "cell_index"));
                break;

            case "on_attack_anim":
                on_attack_anim(
                    GetInt(data, "from_player"),
                    GetString(data, "from_cell_type"),
                    GetInt(data, "from_cell_index"),
                    GetInt(data, "to_player"),
                    GetString(data, "to_cell_type"),
                    GetInt(data, "to_cell_index"),
                    GetBool(data, "is_direct"));
                break;

            case "on_phase_anim":
                on_phase_anim(GetString(data, "phase_index"));
                break;

            case "on_marker_guide":
                on_marker_guide(GetBool(data, "show"));
                break;

            case "on_play_bgm":
                on_play_bgm(GetString(data, "bgm_filename"));
                break;

            case "on_play_se":
                on_play_se(GetString(data, "se_filename"));
                break;

            case "on_card_relate_effect":
                on_card_relate_effect(
                    GetInt(data, "from_player"),
                    GetString(data, "from_cell_type"),
                    GetInt(data, "from_cell_index"),
                    GetInt(data, "to_player"),
                    GetString(data, "to_cell_type"),
                    GetInt(data, "to_cell_index"));
                break;

            case "on_dice":
                on_dice(GetInt(data, "player"), GetInt(data, "value"));
                break;

            case "on_coin":
                on_coin(GetInt(data, "player"), GetInt(data, "value"));
                break;

            case "ping":
                // 服务器心跳探测，回复 pong
                SendPong();
                break;

            case "pong":
                // 服务器心跳应答，到达时间已刷新 last_recv_time，无需处理
                break;

            default:
                GD.PushWarning($"未知的消息类型: {type}");
                break;
        }
    }

    // ---------- 发送与心跳辅助 ----------

    /// <summary>发送一条 JSON 文本消息（仅在连接打开时有效）。</summary>
    public void SendJson(Godot.Collections.Dictionary data)
    {
        if (socket.GetReadyState() != WebSocketPeer.State.Open)
        {
            return;
        }
        socket.SendText(Json.Stringify(data));
    }

    /// <summary>发送心跳 ping。</summary>
    private void SendPing()
    {
        SendJson(new Godot.Collections.Dictionary { { "type", "ping" } });
    }

    /// <summary>回复心跳 pong。</summary>
    private void SendPong()
    {
        SendJson(new Godot.Collections.Dictionary { { "type", "pong" } });
    }

    // ---------- JSON 取值辅助 ----------

    private static string GetString(Godot.Collections.Dictionary data, string key, string fallback = "")
    {
        return data.ContainsKey(key) ? data[key].AsString() : fallback;
    }

    private static int GetInt(Godot.Collections.Dictionary data, string key, int fallback = 0)
    {
        return data.ContainsKey(key) ? data[key].AsInt32() : fallback;
    }

    private static bool GetBool(Godot.Collections.Dictionary data, string key, bool fallback = false)
    {
        return data.ContainsKey(key) ? data[key].AsBool() : fallback;
    }

    // ---------- 各接口处理函数（实现留空，待补充具体投影逻辑）----------

    /// <summary>变更指定 player 的 LP。</summary>
    /// <param name="player">玩家编号。</param>
    /// <param name="lp">新的 LP 值。</param>
    public void on_lp_change(int player, int lp)
    {
    }

    /// <summary>战场情况发生变更。</summary>
    /// <param name="battlefield">战场情况的 JSON 字符串。</param>
    public void on_battlefield_change(string battlefield)
    {
        GD.Print(battlefield);
    }

    /// <summary>播放召唤动画。</summary>
    /// <param name="summon_type">召唤类型。</param>
    public void on_summon_anim(string summon_type)
    {
    }

    /// <summary>播放破坏动画。</summary>
    /// <param name="player">玩家编号。</param>
    /// <param name="cell_type">格子类型："front"、"back"、"ex"。</param>
    /// <param name="cell_index">格子索引。</param>
    public void on_destroy_anim(int player, string cell_type, int cell_index)
    {
    }

    /// <summary>播放攻击动画。</summary>
    /// <param name="from_player">攻击方玩家编号。</param>
    /// <param name="from_cell_type">攻击方格子类型。</param>
    /// <param name="from_cell_index">攻击方格子索引。</param>
    /// <param name="to_player">被攻击方玩家编号。</param>
    /// <param name="to_cell_type">被攻击方格子类型。</param>
    /// <param name="to_cell_index">被攻击方格子索引。</param>
    /// <param name="is_direct">是否为直接攻击。</param>
    public void on_attack_anim(int from_player, string from_cell_type, int from_cell_index,
        int to_player, string to_cell_type, int to_cell_index, bool is_direct)
    {
    }

    /// <summary>播放阶段切换动画。</summary>
    /// <param name="phase_index">阶段："draw"、"standby"、"main1"、"battle"、"main2"、"end"。</param>
    public void on_phase_anim(string phase_index)
    {
    }

    /// <summary>显示/隐藏定位方块（校准用）。</summary>
    /// <param name="show">true=显示，false=隐藏。</param>
    public void on_marker_guide(bool show)
    {
    }

    /// <summary>播放 BGM。</summary>
    /// <param name="bgm_filename">BGM 文件名。</param>
    public void on_play_bgm(string bgm_filename)
    {
    }

    /// <summary>播放音效。</summary>
    /// <param name="se_filename">音效文件名。</param>
    public void on_play_se(string se_filename)
    {
    }

    /// <summary>播放卡片关联动画。</summary>
    /// <param name="from_player">起点玩家编号。</param>
    /// <param name="from_cell_type">起点格子类型。</param>
    /// <param name="from_cell_index">起点格子索引。</param>
    /// <param name="to_player">终点玩家编号。</param>
    /// <param name="to_cell_type">终点格子类型。</param>
    /// <param name="to_cell_index">终点格子索引。</param>
    public void on_card_relate_effect(int from_player, string from_cell_type, int from_cell_index,
        int to_player, string to_cell_type, int to_cell_index)
    {
    }

    /// <summary>掷骰子结果。</summary>
    /// <param name="player">所属玩家：0=公用，1=P1，2=P2。</param>
    /// <param name="value">点数 1-6。</param>
    public void on_dice(int player, int value)
    {
    }

    /// <summary>投硬币结果。</summary>
    /// <param name="player">所属玩家：0=公用，1=P1，2=P2。</param>
    /// <param name="value">1=正面(heads)，0=反面(tails)。</param>
    public void on_coin(int player, int value)
    {
    }
}
