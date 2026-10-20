using Godot;
using System;
using System.IO;

public partial class MainUI : Node3D
{
    private Tween p1lpTween;
    private Tween p2lpTween;
    private Label p1lpLabel;
    private Label p2lpLabel;

    Battlefield currField = new Battlefield();
    public override void _Ready()
    {
        base._Ready();
        BattleManager.getInstance().mainUI = this;
    }

    /// <summary>
    /// 让 Label 从 startValue 平滑变化到 endValue
    /// </summary>
    public void AnimateLabel(int player, float endValue, float duration = 1.0f)
    {
        // 如果上一个动画还在跑，先杀掉，避免两个 Tween 抢同一个属性
        Tween tween = player == 1 ? p1lpTween : p2lpTween;
        tween?.Kill();
        p1lpLabel = this.GetNode<Label>("ui/player1/lp/val");
        p2lpLabel = this.GetNode<Label>("ui/player2/lp/val");
        Label label = player == 1 ? p1lpLabel : p2lpLabel;
        float startValue = float.Parse(label.Text);
        tween = CreateTween();
        if (player == 1)
        {
            tween.TweenMethod(
                Callable.From<float>(SetLp1LabelValue), // 每帧被调用的方法
                startValue,                           // 起始值（传参）
                endValue,                             // 结束值（传参）
                duration                              // 持续时间
            );
        }
        if (player == 2)
        {
            tween.TweenMethod(
                Callable.From<float>(SetLp2LabelValue), // 每帧被调用的方法
                startValue,                           // 起始值（传参）
                endValue,                             // 结束值（传参）
                duration                              // 持续时间
            );
        }
    }

    private void SetLp1LabelValue(float value)
    {
        p1lpLabel.Set("text", ((int)value).ToString());
    }
    private void SetLp2LabelValue(float value)
    {
        p2lpLabel.Set("text", ((int)value).ToString());
    }

    /// <summary>
    /// 展示场地情况
    /// </summary>
    /// <param name="field"></param>
    public void showField(Battlefield field)
    {
        BattlefieldChange battlefieldChange = BattlefieldChange.compareField(currField, field);
        currField = field.Clone();
        // 先处理移除的卡
        // EX
        for (int i = 0; i <= 1; i += 1)
        {
            if (battlefieldChange.player1CardsRemove.Ex[i] != null)
            {
                this.removeCard(1, ZoneType.Ex, i);
            }
            if (battlefieldChange.player2CardsRemove.Ex[i] != null)
            {
                this.removeCard(2, ZoneType.Ex, i);
            }
        }
        // front
        for (int i = 0; i <= 4; i += 1)
        {
            if (battlefieldChange.player1CardsRemove.Front[i] != null)
            {
                this.removeCard(1, ZoneType.Front, i);
            }
            if (battlefieldChange.player2CardsRemove.Front[i] != null)
            {
                this.removeCard(2, ZoneType.Front, i);
            }
        }
        // back
        for (int i = 0; i <= 4; i += 1)
        {
            if (battlefieldChange.player1CardsRemove.Back[i] != null)
            {
                this.removeCard(1, ZoneType.Back, i);
            }
            if (battlefieldChange.player2CardsRemove.Back[i] != null)
            {
                this.removeCard(2, ZoneType.Back, i);
            }
        }
        // field
        if (battlefieldChange.player1CardsRemove.Field != null)
        {
            this.removeCard(1, ZoneType.Field, 0);
        }
        if (battlefieldChange.player2CardsRemove.Field != null)
        {
            this.removeCard(2, ZoneType.Field, 0);
        }
        // exdeck
        if (battlefieldChange.player1CardsRemove.ExDeck != null)
        {
            this.removeCard(1, ZoneType.ExDeck, 0);
        }
        if (battlefieldChange.player2CardsRemove.ExDeck != null)
        {
            this.removeCard(2, ZoneType.ExDeck, 0);
        }
        // grave
        if (battlefieldChange.player1CardsRemove.Grave != null)
        {
            this.removeCard(1, ZoneType.Grave, 0);
        }
        if (battlefieldChange.player2CardsRemove.Grave != null)
        {
            this.removeCard(2, ZoneType.Grave, 0);
        }
        // deck
        if (battlefieldChange.player1CardsRemove.Deck != null)
        {
            this.removeCard(1, ZoneType.Deck, 0);
        }
        if (battlefieldChange.player2CardsRemove.Deck != null)
        {
            this.removeCard(2, ZoneType.Deck, 0);
        }
        // 再处理新加入的卡
        // EX
        for (int i = 0; i <= 1; i += 1)
        {
            if (battlefieldChange.player1CardsNew.Ex[i] != null)
            {
                this.setCard(1, ZoneType.Ex, i, battlefieldChange.player1CardsNew.Ex[i]);
            }
            if (battlefieldChange.player2CardsNew.Ex[i] != null)
            {
                this.setCard(2, ZoneType.Ex, i, battlefieldChange.player2CardsNew.Ex[i]);
            }
        }
        // front
        for (int i = 0; i <= 4; i += 1)
        {
            if (battlefieldChange.player1CardsNew.Front[i] != null)
            {
                this.setCard(1, ZoneType.Front, i, battlefieldChange.player1CardsNew.Front[i]);
            }
            if (battlefieldChange.player2CardsNew.Front[i] != null)
            {
                this.setCard(2, ZoneType.Front, i, battlefieldChange.player2CardsNew.Front[i]);
            }
        }
        // back
        for (int i = 0; i <= 4; i += 1)
        {
            if (battlefieldChange.player1CardsNew.Back[i] != null)
            {
                this.setCard(1, ZoneType.Back, i, battlefieldChange.player1CardsNew.Back[i]);
            }
            if (battlefieldChange.player2CardsNew.Back[i] != null)
            {
                this.setCard(2, ZoneType.Back, i, battlefieldChange.player2CardsNew.Back[i]);
            }
        }
        // field
        if (battlefieldChange.player1CardsNew.Field != null)
        {
            this.setCard(1, ZoneType.Field, 0, battlefieldChange.player1CardsNew.Field);
        }
        if (battlefieldChange.player2CardsNew.Field != null)
        {
            this.setCard(2, ZoneType.Field, 0, battlefieldChange.player2CardsNew.Field);
        }
        // exdeck
        if (battlefieldChange.player1CardsNew.ExDeck != null)
        {
            this.setCard(1, ZoneType.ExDeck, 0, battlefieldChange.player1CardsNew.ExDeck);
        }
        if (battlefieldChange.player2CardsNew.ExDeck != null)
        {
            this.setCard(2, ZoneType.ExDeck, 0, battlefieldChange.player2CardsNew.ExDeck);
        }
        // grave
        if (battlefieldChange.player1CardsNew.Grave != null)
        {
            this.setCard(1, ZoneType.Grave, 0, battlefieldChange.player1CardsNew.Grave);
        }
        if (battlefieldChange.player2CardsNew.Grave != null)
        {
            this.setCard(2, ZoneType.Grave, 0, battlefieldChange.player2CardsNew.Grave);
        }
        // deck
        if (battlefieldChange.player1CardsNew.Deck != null)
        {
            this.setCard(1, ZoneType.Deck, 0, battlefieldChange.player1CardsNew.Deck);
        }
        if (battlefieldChange.player2CardsNew.Deck != null)
        {
            this.setCard(2, ZoneType.Deck, 0, battlefieldChange.player2CardsNew.Deck);
        }
        // 更新lp
        int p1lp = field.GetPlayer(1).Lp;
        int p2lp = field.GetPlayer(2).Lp;
        if (int.Parse(this.GetNode<Label>("ui/player1/lp/val").Text) != p1lp)
        {
            this.AnimateLabel(1, p1lp);
        }
        if (int.Parse(this.GetNode<Label>("ui/player2/lp/val").Text) != p2lp)
        {
            this.AnimateLabel(2, p2lp);
        }
    }

    // 展示一张卡
    public void setCard(int player, ZoneType zoneType, int index, CardData cardData)
    {
        // 光效
        // 预备复制的节点
        string templatePath = string.Format("ui/ring/temmplate/bling_p{0}", player);
        // 预备的节点命名
        string nodeName = string.Format("bling_p{0}_{1}_{2}", player, zoneType.ToString(), index + 1);

        string findPath = string.Format("ui/ring/items/{0}", nodeName);
        ExDeckGlowParticle particle = (ExDeckGlowParticle)this.GetNodeOrNull(findPath);

        // 只有Ex、场地、怪物区、魔陷区需要光圈
        if (particle == null && (
            zoneType == ZoneType.Ex ||
            zoneType == ZoneType.Field ||
            zoneType == ZoneType.Front ||
            zoneType == ZoneType.Back))
        {
            // 创建一个新节点
            ExDeckGlowParticle node = this.GetNode<ExDeckGlowParticle>(templatePath);
            particle = (ExDeckGlowParticle)node.Duplicate();
        }
        // 设置位置
        string targetPath = "";
        bool rotate = false;
        // 怪兽
        if (zoneType == ZoneType.Ex)
        {
            targetPath = string.Format("ui/player{0}/ex/ex{1}", player, index + 1);
            rotate = cardData.Orientation == Orientation.Horizontal;
        }
        if (zoneType == ZoneType.Front)
        {
            targetPath = string.Format("ui/player{0}/front/front{1}", player, index + 1);
            rotate = cardData.Orientation == Orientation.Horizontal;
        }
        // 魔陷
        if (zoneType == ZoneType.Back)
        {
            targetPath = string.Format("ui/player{0}/back/back{1}", player, index + 1);
        }
        // 场地
        if (zoneType == ZoneType.Field)
        {
            targetPath = string.Format("ui/player{0}/front/field", player);
        }
        if (particle != null)
        {
            // 设置光圈位置
            GD.Print("targetPath ", targetPath, " ", player, " ", index + 1, " ");
            particle.setTarget(this.GetNode<Control>(targetPath));
            particle.rotate = rotate;
            particle.Visible = true;
            particle.Name = nodeName;
            if (particle.GetParent() == null)
            {
                this.GetNode("ui/ring/items").AddChild(particle);
            }
        }

        // 卡图
        // string baseDir = OS.GetExecutablePath().GetBaseDir();
        // string baseDir = "D:/Git/mydesk/display";
        string anchorAbsPath = ProjectSettings.GlobalizePath("res://icon.svg");
        string baseDir = Path.GetDirectoryName(anchorAbsPath);
        int exRotate90 = 90;
        if (cardData.FaceUp)
        {
            // 正面，加载卡图
            if (
                zoneType == ZoneType.Ex ||
                zoneType == ZoneType.Field ||
                zoneType == ZoneType.Front ||
                zoneType == ZoneType.Back)
            {
                string filePath = "";
                string nodePath = "";
                if (zoneType == ZoneType.Field)
                {
                    filePath = Path.Combine(baseDir, "static", "picture", "hd_card", string.Format("{0}.jpg", cardData.Id.ToString()));
                    nodePath = string.Format("showfield/middle/field/player{0}/card", player);
                    // todo 处理双方都有场地卡的情况，一人一半
                }
                if (zoneType == ZoneType.Ex)
                {
                    filePath = Path.Combine(baseDir, "static", "picture", "closeup", string.Format("{0}.png", cardData.Id.ToString()));
                    if (cardData.Id == -1)
                    {
                        filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                    }
                    if (player == 1)
                    {
                        exRotate90 = -90;
                        if (index == 0)
                        {
                            nodePath = "showfield/middle/cards/ex/card2";
                        }
                        if (index == 1)
                        {
                            nodePath = "showfield/middle/cards/ex/card1";
                        }
                    }
                    if (player == 2)
                    {
                        exRotate90 = 90;
                        if (index == 0)
                        {
                            nodePath = "showfield/middle/cards/ex/card1";   
                        }
                        if (index == 1)
                        {
                            nodePath = "showfield/middle/cards/ex/card2";
                        }
                    }
                }
                if (zoneType == ZoneType.Front)
                {
                    filePath = Path.Combine(baseDir, "static", "picture", "closeup", string.Format("{0}.png", cardData.Id.ToString()));
                    nodePath = string.Format("showfield/middle/cards/player{0}/front/card{1}", player, index + 1);
                    if (cardData.Id == -1)
                    {
                        filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                    }
                    GD.Print(nodePath, " ", player, " ", index + 1, " ");
                }
                if (zoneType == ZoneType.Back)
                {
                    filePath = Path.Combine(baseDir, "static", "picture", "hd_card", string.Format("{0}.jpg", cardData.Id.ToString()));
                    nodePath = string.Format("showfield/middle/cards/player{0}/back/card{1}", player, index + 1);
                    if (cardData.Id == -1)
                    {
                        filePath = Path.Combine(baseDir, "static", "common", "back_placeholder.png");
                    }
                }
                if (!string.IsNullOrEmpty(nodePath))
                {
                    if (!File.Exists(filePath))
                    {
                        GD.PrintErr($"文件不存在: {filePath}");
                        // 采用默认图
                        if (zoneType == ZoneType.Ex)
                        {
                            filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                        }
                        if (zoneType == ZoneType.Front)
                        {
                            filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                        }
                        if (zoneType == ZoneType.Back)
                        {
                            filePath = Path.Combine(baseDir, "static", "common", "back_placeholder.png");
                        }
                    }
                    Image image = Image.LoadFromFile(filePath);
                    if (image == null || image.IsEmpty())
                    {
                        GD.PrintErr($"加载失败: {filePath}");
                        return;
                    }

                    image.GenerateMipmaps();
                    var texture = ImageTexture.CreateFromImage(image);

                    var sprite = GetNode<Sprite3D>(nodePath);
                    if (sprite == null)
                    {
                        GD.Print("no sprite ", nodePath);
                    }
                    else
                    {
                        sprite.Texture = texture;   
                    }
                    if (zoneType == ZoneType.Ex)
                    {
                        sprite.GlobalRotation = new Vector3(0, 0, exRotate90);
                    }
                    // 攻击防御图标
                    
                    if (zoneType == ZoneType.Front || zoneType == ZoneType.Ex)
                    {
                        string iconPath = cardData.Orientation == Orientation.Vertical ? "state_attack" : "state_defense";
                        sprite.GetNode<Sprite3D>("state_attack").Visible = false;
                        sprite.GetNode<Sprite3D>("state_defense").Visible = false;
                        sprite.GetNode<Sprite3D>(iconPath).Visible = true;
                        ((CardShowNode)sprite).stop = cardData.Orientation == Orientation.Horizontal;
                    }
                }
            }
        } 
        else
        {
            // 背面，显示占位图
            if (
                zoneType == ZoneType.Ex ||
                zoneType == ZoneType.Front ||
                zoneType == ZoneType.Back)
            {
                string filePath = "";
                string nodePath = "";
                if (zoneType == ZoneType.Ex)
                {
                    filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                    if (player == 1)
                    {
                        exRotate90 = -90;
                        if (index == 0)
                        {
                            nodePath = "showfield/middle/cards/ex/card2";   
                        }
                        if (index == 1)
                        {
                            nodePath = "showfield/middle/cards/ex/card1";
                        }
                    }
                    if (player == 2)
                    {
                        exRotate90 = 90;
                        if (index == 0)
                        {
                            nodePath = "showfield/middle/cards/ex/card1";   
                        }
                        if (index == 1)
                        {
                            nodePath = "showfield/middle/cards/ex/card2";
                        }
                    }
                }
                if (zoneType == ZoneType.Front)
                {
                    filePath = Path.Combine(baseDir, "static", "common", "front_placeholder.png");
                    nodePath = string.Format("showfield/middle/cards/player{0}/front/card{1}", player, index + 1);
                }
                if (zoneType == ZoneType.Back)
                {
                    filePath = Path.Combine(baseDir, "static", "common", "back_placeholder.png");
                }
                if (File.Exists(filePath))
                {
                    Image image = Image.LoadFromFile(filePath);
                    if (image == null || image.IsEmpty())
                    {
                        GD.PrintErr($"加载失败: {filePath}");
                        return;
                    }

                    image.GenerateMipmaps();
                    var texture = ImageTexture.CreateFromImage(image);

                    var sprite = GetNode<Sprite3D>(nodePath);
                    sprite.Texture = texture;
                    if (zoneType == ZoneType.Ex)
                    {
                        sprite.GlobalRotation = new Vector3(0, 0, exRotate90);
                    }
                    if (zoneType == ZoneType.Front || zoneType == ZoneType.Ex)
                    {
                        string iconPath = cardData.Orientation == Orientation.Vertical ? "state_attack" : "state_defense";
                        sprite.GetNode<Sprite3D>("state_attack").Visible = false;
                        sprite.GetNode<Sprite3D>("state_defense").Visible = false;
                        sprite.GetNode<Sprite3D>(iconPath).Visible = true;
                        ((CardShowNode)sprite).stop = cardData.Orientation == Orientation.Horizontal;
                    }
                }
                else
                {
                    GD.PrintErr($"文件不存在: {filePath}");
                }
            }
        }
    }
    public void removeCard(int player, ZoneType zoneType, int index)
    {
        // 移除光效：隐藏该位置对应的 2D 光圈粒子节点
        string nodeName = string.Format("bling_p{0}_{1}_{2}", player, zoneType.ToString(), index + 1);
        string findPath = string.Format("ui/ring/items/{0}", nodeName);
        ExDeckGlowParticle glow = this.GetNodeOrNull<ExDeckGlowParticle>(findPath);
        if (glow != null)
        {
            glow.Visible = false;
        }

        // 计算 Sprite3D 卡图节点路径（与 setCard 一致）
        string nodePath = "";
        if (zoneType == ZoneType.Ex)
        {
            if (player == 1)
            {
                if (index == 0)
                {
                    nodePath = "showfield/middle/cards/ex/card2";
                }
                if (index == 1)
                {
                    nodePath = "showfield/middle/cards/ex/card1";
                }
            }
            if (player == 2)
            {
                if (index == 0)
                {
                    nodePath = "showfield/middle/cards/ex/card1";
                }
                if (index == 1)
                {
                    nodePath = "showfield/middle/cards/ex/card2";
                }
            }
        }
        if (zoneType == ZoneType.Front)
        {
            nodePath = string.Format("showfield/middle/cards/player{0}/front/card{1}", player, index + 1);
        }
        if (zoneType == ZoneType.Back)
        {
            nodePath = string.Format("showfield/middle/cards/player{0}/back/card{1}", player, index + 1);
        }
        // 场地
        if (zoneType == ZoneType.Field)
        {
            nodePath = string.Format("showfield/middle/field/player{0}/card", player);
        }

        if (nodePath == "")
        {
            return;
        }

        // 移除战场图片：清空贴图
        Sprite3D sprite = this.GetNodeOrNull<Sprite3D>(nodePath);
        if (sprite == null)
        {
            return;
        }
        sprite.Texture = null;
        // 隐藏攻击/防御图标
        if (zoneType == ZoneType.Front || zoneType == ZoneType.Ex)
        {
            Sprite3D stateAttack = sprite.GetNodeOrNull<Sprite3D>("state_attack");
            if (stateAttack != null)
            {
                stateAttack.Visible = false;
            }
            Sprite3D stateDefense = sprite.GetNodeOrNull<Sprite3D>("state_defense");
            if (stateDefense != null)
            {
                stateDefense.Visible = false;
            }
        }
    }

    public void setLp(int player, int newLp)
    {
        this.AnimateLabel(player, newLp);
    }

    public void setPhase()
    {
        
    }

    public void showDice()
    {
        
    }

    public void showCoin()
    {
        
    }

    public void showSummonAnim()
    {
        
    }

    public void showAttack()
    {
        
    }

    public void togglePosRects(bool show = true)
    {
        string []pathes = [
            "ui/player1/back/deck/PosRect",
            "ui/player1/back/exdeck/PosRect",
            "ui/player1/front/field/PosRect",
            "ui/player1/front/grave/PosRect",
            "ui/player2/back/exdeck/PosRect",
            "ui/player2/back/deck/PosRect",
            "ui/player2/front/field/PosRect",
            "ui/player2/front/grave/PosRect"
        ];

        foreach (string path in pathes)
        {
            this.GetNode<ColorRect>(path).Visible = show;
        }
    }

}
