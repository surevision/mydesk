using Godot;
using System;
using System.Collections.Generic;

public partial class TitleUI : Node3D
{
    private const string targetScene = "res://scenes/main_big.tscn";

    public override void _Ready()
    {
        base._Ready();
        BattleManager.getInstance().titleUI = this;
        this.initLanQrCodes();  // 展示controller端地址
    }

    public void onDuel()
    {
        GD.Print("start duel");
        Node fadeFancy = GetNode("/root/FancyFade");
        PackedScene board = GD.Load<PackedScene>(targetScene);
        if (board == null)
        {
            GD.PushError($"加载棋盘场景失败: {targetScene}");
            return;
        }
        fadeFancy.Call("circle_in", board.Instantiate());
        BattleManager.getInstance().titleUI = null;
    }

    /// <summary>
    /// 获取局域网ip
    /// </summary>
    /// <returns></returns>
    public List<string> GetLanIPv4Addresses()
    {
        var lanIps = new List<string>();
        string[] allIps = IP.GetLocalAddresses();

        foreach (string ip in allIps)
        {
            // 只处理 IPv4 (包含 '.')
            if (!ip.Contains('.')) continue;
            // 排除回环地址
            if (ip.StartsWith("127.")) continue;

            string[] parts = ip.Split('.');
            if (parts.Length != 4) continue;

            if (int.TryParse(parts[0], out int p0) && int.TryParse(parts[1], out int p1))
            {
                // 检查是否属于私有 IP 段
                bool isPrivate = false;
                if (p0 == 10) isPrivate = true; // 10.0.0.0 - 10.255.255.255
                else if (p0 == 172 && p1 >= 16 && p1 <= 31) isPrivate = true; // 172.16.0.0 - 172.31.255.255
                else if (p0 == 192 && p1 == 168) isPrivate = true; // 192.168.0.0 - 192.168.255.255

                if (isPrivate)
                {
                    lanIps.Add(ip);
                }
            }
        }
        return lanIps;
    }

    public void initLanQrCodes()
    {
        CanvasItem p1qrTemplate = this.GetNode<CanvasItem>("ui_big/player1/QrContriner/qrCodeTemplate");
        CanvasItem p2qrTemplate = this.GetNode<CanvasItem>("ui_big/player2/QrContriner/qrCodeTemplate");

        List<string> ips = this.GetLanIPv4Addresses();
        foreach (string _ip in ips)
        {
            string ip = string.Format("{0}:4582", _ip);
            CanvasItem p1qrNode = (CanvasItem)p1qrTemplate.Duplicate();
            CanvasItem p2qrNode = (CanvasItem)p2qrTemplate.Duplicate();
            p1qrNode.Set("data", ip);
            p2qrNode.Set("data", ip);
            p1qrNode.GetNode<Label>("ip").Text = _ip;
            p2qrNode.GetNode<Label>("ip").Text = _ip;
            p1qrTemplate.GetParent().AddChild(p1qrNode);
            p2qrTemplate.GetParent().AddChild(p2qrNode);
            p1qrNode.Visible = true;
            p2qrNode.Visible = true;
        }
    }
}
