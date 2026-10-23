using Godot;
using System;

public partial class TitleUI : Node3D
{
    [Export]
    public PackedScene mainBig;

    [Export]
    public PackedScene mainMid;

    [Export]
    public PackedScene mainSmall;

    public override void _Ready()
    {
        base._Ready();
         BattleManager.getInstance().titleUI = this;
    }

    public void onDuel()
    {
        GD.Print("start duel");
        Node fadeFancy = GetNode("/root/FadeFancy");
        fadeFancy.Call("blurry_noise", mainBig.Instantiate());
        BattleManager.getInstance().titleUI = null;
    }

}
