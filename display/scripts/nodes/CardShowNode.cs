using Godot;
using System;

public partial class CardShowNode : Node3D
{
    [Export]
    public bool reverse = false;
    private int direction = 1;
    private double speed = 0.2;
    private double moveDistance = 0.1;

    private double baseV = 0.0;
    private double newV = 0.0;

    public bool stop = false;   // 守备状态不动

    public override void _Ready()
    {
        base._Ready();
        baseV = this.Position.X;
        if (reverse)
        {
            direction = -1;
        }
    }


    public override void _Process(double delta)
    {
        base._Process(delta);
        newV += direction * speed * delta;
        if (Mathf.Abs(newV) > moveDistance)
        {
            newV = moveDistance * direction;
            direction *= -1;
        }
        if (!stop)
        {
            this.Position = new Vector3((float)(baseV + newV), this.Position.Y, this.Position.Z);   
        }
        else
        {
            this.Position = new Vector3((float)baseV, this.Position.Y, this.Position.Z);
        }
    }

}
