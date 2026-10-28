using Godot;
using System;
using System.Text;

public partial class BattleManager : Node
{
    private static BattleManager instance = null;

    public string currentFieldStr = "";

    public MainUI mainUI = null;
    public TitleUI titleUI = null;

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
        currentFieldStr = battlefield;
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
        mainUI.setLp(player, lp, 1);
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

    public void showSummonAnim(string animName)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        mainUI.showSummonAnim(animName);
    }

    public void showAttack(int from_player, string from_cell_type, int from_cell_index,
        int to_player, string to_cell_type, int to_cell_index, bool is_direct)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        this.mainUI.showAttack(from_player, ZoneTypeExtensions.FromKey(from_cell_type), from_cell_index,
            to_player, ZoneTypeExtensions.FromKey(to_cell_type), to_cell_index, is_direct);
    }

    public void backToTitle()
    {
        
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        mainUI.backToTitle();
    }

    public void startDuel()
    {
        
        if (titleUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        titleUI.onDuel();
    }

    public void light(bool on)
    {
        if (mainUI == null)
        {
            GD.Print("UI未就绪");
            return;
        }
        mainUI.light(on);
    }
}