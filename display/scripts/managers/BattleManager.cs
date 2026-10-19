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
}