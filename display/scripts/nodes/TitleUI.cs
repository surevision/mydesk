using Godot;
using System;
using System.Collections.Generic;

public partial class TitleUI : Node3D
{
    private const string targetScene = "res://scenes/main_{0}.tscn";

    public string sizeMode = "big"; // small mid big

    public override void _Ready()
    {
        base._Ready();
        BattleManager.getInstance().titleUI = this;
        this.initLanQrCodes();  // 展示controller端地址
        this.switchSizeMode();
    }


    /// <summary>
    /// 切换战场尺寸模式
    /// </summary>
    /// <param name="mode"></param>
    public void switchSizeMode(string mode = null)
    {
        // small mid big
        if (string.IsNullOrEmpty(mode))
        {
            mode = this.sizeMode;
        }
        GetNode<Control>("ui/ui_big").Visible = false;
        GetNode<Control>("ui/ui_mid").Visible = false;
        GetNode<Control>("ui/ui_small").Visible = false;
        GetNode<Control>(string.Format("ui/ui_{0}", mode)).Visible = true;
        this.sizeMode = mode;
    }
    

    public void onDuel()
    {
        GD.Print("start duel");
        Node fadeFancy = GetNode("/root/FancyFade");
        PackedScene board = GD.Load<PackedScene>(string.Format(targetScene, this.sizeMode));
        if (board == null)
        {
            GD.PushError($"加载棋盘场景失败: {string.Format(targetScene, this.sizeMode)}");
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
        CanvasItem p1qrTemplate = this.GetNode<CanvasItem>("ui/QrContriner1/qrCodeTemplate");
        CanvasItem p2qrTemplate = this.GetNode<CanvasItem>("ui/QrContriner2/qrCodeTemplate");

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
