using Godot;
using System;
using System.Text;

public partial class BattleManager : Node
{
    private static BattleManager instance = null;

    public MainUI mainUI = null;

    public static BattleManager getInstance()
    {
        if (instance == null)
        {
            instance = new BattleManager();
        }
        return instance;
    }

    public void togglePosRects(bool show)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        GD.Print("toggle show pos rect ", show);
        mainUI.togglePosRects(show);
    }

    public void showField(string battlefield)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        if (!Battlefield.TryFromJson(battlefield, out Battlefield field))
        {
            GD.PushWarning($"战场 JSON 解析失败: {battlefield}");
            return;
        }
        mainUI.showField(field);
    }
    public void setLp(int player, int lp)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        GD.Print("set new lp ", player, " ", lp);
        mainUI.setLp(player, lp);
    }

    public void showDice(int player, int val)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        GD.Print("show dice ", player, " ", val);
        mainUI.showDice(player, val);
    }

    public void showCoin(int player, int val)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        GD.Print("show coin ", player, " ", val);
        mainUI.showCoin(player, val);
    }
}