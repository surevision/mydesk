using Godot;
using System;

public partial class ExDeckGlowParticle : CpuParticles2D
{
    [Export]
    public Control targetNode = null;
    [Export]
    public float speed = 150.0f;
    [Export]
    public bool rotate = false; // 是否旋转90度
    [Export]
    public Vector2 imageSize = new Vector2(1024, 1024);
    [Export]
    public Vector2 baseLineSize = new Vector2(890, 540);
    public Vector2 lineSize = new Vector2(890, 540);

    private Control target;
    private float distance = 0.0f;

    public override void _Ready()
    {
        base._Ready();
        target = targetNode;
        if (rotate)
        {
            lineSize = new Vector2(baseLineSize.Y, baseLineSize.X);
        }
        else
        {
            lineSize = new Vector2(baseLineSize.X, baseLineSize.Y);
        }
    }

    public void setRotate(bool rotate)
    {
        this.rotate = rotate;
        if (rotate)
        {
            lineSize = new Vector2(baseLineSize.Y, baseLineSize.X);
        }
        else
        {
            lineSize = new Vector2(baseLineSize.X, baseLineSize.Y);
        }
    }

    public void setTarget(Control control)
    {
        target = control;
        targetNode = control;
    }

    public override void _Process(double delta)
    {
        base._Process(delta);
        if (target == null)
        {
            // GD.Print("not found");
            return;
        }

        Rect2 rect = target.GetGlobalRect();
        if (imageSize.X <= 0.0f || imageSize.Y <= 0.0f)
        {
            return;
        }


        float width = rect.Size.X * lineSize.X / imageSize.X;
        float height = rect.Size.Y * lineSize.Y / imageSize.Y;
        if (width <= 0.0f || height <= 0.0f)
        {
            return;
        }

        float perimeter = 2.0f * (width + height);
        distance = Mathf.PosMod(distance + speed * (float)delta, perimeter);

        Vector2 center = rect.GetCenter();
        float halfW = width * 0.5f;
        float halfH = height * 0.5f;
        Vector2 point;
        if (distance < width)
        {
            point = new Vector2(center.X - halfW + distance, center.Y - halfH);
        }
        else if (distance < width + height)
        {
            point = new Vector2(center.X + halfW, center.Y - halfH + (distance - width));
        }
        else if (distance < 2.0f * width + height)
        {
            point = new Vector2(center.X + halfW - (distance - width - height), center.Y + halfH);
        }
        else
        {
            point = new Vector2(center.X - halfW, center.Y + halfH - (distance - 2.0f * width - height));
        }

        this.GlobalPosition = point;
    }
}
