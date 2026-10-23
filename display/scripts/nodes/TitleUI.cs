using Godot;
using System;

public partial class TitleUI : Node3D
{
    private const string targetScene = "res://scenes/main_big.tscn";

    public override void _Ready()
    {
        base._Ready();
        BattleManager.getInstance().titleUI = this;
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
        fadeFancy.Call("blurry_noise", board.Instantiate());
        BattleManager.getInstance().titleUI = null;
    }

}
