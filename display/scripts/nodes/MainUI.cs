using Godot;
using System;
using System.IO;

public partial class MainUI : Node3D
{
    [Export]
    public PackedScene titleBig;

    // LP 动画
    private Tween p1lpTween;
    private Tween p2lpTween;
    private Label p1lpLabel;
    private Label p2lpLabel;

    private int p1Lp;
    private int p2Lp;

    // 攻击动画
    private Tween p1AtkTween;
    private Tween p2AtkTween;
    
    private Sprite3D p1AtkSpriteTemplate;
    private Sprite3D p2AtkSpriteTemplate;

    private Sprite3D p1AtkSpriteMoving;
    private Sprite3D p2AtkSpriteMoving;



    Battlefield currField = new Battlefield();
    public override void _Ready()
    {
        base._Ready();
        BattleManager.getInstance().mainUI = this;
        AudioManager.getInstance().playSESync("yugioh-lp-shows-sfx");
    }

    /// <summary>
    /// 让 Label 从 startValue 平滑变化到 endValue
    /// </summary>
    public void AnimateLabel(int player, float endValue, int playSfxType = -1, float duration = 2.0f)
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
        if (playSfxType == 0)
        {   
            // 初始音效
            // AudioManager.getInstance().playSESync("yugioh-lp-shows-sfx");
        }
        if (playSfxType == 1)
        {   
            // 变化音效
            AudioManager.getInstance().playSESync("point-drop");
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
        PlayerData p1Data = field.GetPlayer(1);
        PlayerData p2Data = field.GetPlayer(2);
        int p1lp = p1Data != null ? p1Data.Lp : this.p1Lp;
        int p2lp = p2Data != null ? p2Data.Lp : this.p2Lp;
        if (this.p1Lp != p1lp)
        {
            this.setLp(1, p1lp, 0);
        }
        if (this.p2Lp != p2lp)
        {
            this.setLp(2, p2lp, 0);
        }
    }

    // 展示一张卡
    public void setCard(int player, ZoneType zoneType, int index, CardData cardData)
    {
        try
        {
            setCardImpl(player, zoneType, index, cardData);
        }
        catch (Exception ex)
        {
            GD.PushError($"setCard P{player} {zoneType}[{index}] failed: {ex.Message}");
            PlayerData pd = currField.GetPlayer(player);
            if (pd != null)
            {
                pd.SetCell(zoneType, index, null);
            }
        }
    }

    private void setCardImpl(int player, ZoneType zoneType, int index, CardData cardData)
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
        GD.Print("rotate ", cardData.Id, " ", cardData.Orientation == Orientation.Horizontal, " ", rotate, " ", cardData.Orientation);
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
            particle.setRotate(rotate);
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
        if (Godot.FileAccess.FileExists(Path.GetDirectoryName(Path.Combine(baseDir, "../", "static", "picture"))))
        {
            baseDir = Path.Combine(baseDir, "../", "static", "picture");
        }
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
                    filePath = Path.Combine(baseDir, "static", "picture", "field", string.Format("{0}.jpg", cardData.Id.ToString()));
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

                    var sprite = GetNodeOrNull<Sprite3D>(nodePath);
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
                        sprite.GlobalRotationDegrees = new Vector3(0, 0, exRotate90);
                    }
                    // 攻击防御图标
                    
                    if (zoneType == ZoneType.Front || zoneType == ZoneType.Ex)
                    {
                        string iconPath = cardData.Orientation == Orientation.Vertical ? "state_attack" : "state_defense";
                        var stateAttack = sprite.GetNodeOrNull<Sprite3D>("state_attack");
                        if (stateAttack != null) stateAttack.Visible = false;
                        var stateDefense = sprite.GetNodeOrNull<Sprite3D>("state_defense");
                        if (stateDefense != null) stateDefense.Visible = false;
                        var stateIcon = sprite.GetNodeOrNull<Sprite3D>(iconPath);
                        if (stateIcon != null) stateIcon.Visible = true;
                        if (sprite is CardShowNode cardNode) cardNode.stop = cardData.Orientation == Orientation.Horizontal;
                        GD.Print("stop ", cardData.Id, " ", cardData.Orientation == Orientation.Horizontal, " ", ((CardShowNode)sprite).stop, " ", cardData.Orientation);
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
                    nodePath = string.Format("showfield/middle/cards/player{0}/back/card{1}", player, index + 1);
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
                    GD.Print("卡背nodePath ", nodePath);
                    var sprite = GetNodeOrNull<Sprite3D>(nodePath);
                    if (sprite == null)
                    {
                        GD.PushError($"no sprite {nodePath}");
                        return;
                    }
                    sprite.Texture = texture;
                    if (zoneType == ZoneType.Ex)
                    {
                        sprite.GlobalRotationDegrees = new Vector3(0, 0, exRotate90);
                    }
                    if (zoneType == ZoneType.Front || zoneType == ZoneType.Ex)
                    {
                        string iconPath = cardData.Orientation == Orientation.Vertical ? "state_attack" : "state_defense";
                        var stateAttack = sprite.GetNodeOrNull<Sprite3D>("state_attack");
                        if (stateAttack != null) stateAttack.Visible = false;
                        var stateDefense = sprite.GetNodeOrNull<Sprite3D>("state_defense");
                        if (stateDefense != null) stateDefense.Visible = false;
                        var stateIcon = sprite.GetNodeOrNull<Sprite3D>(iconPath);
                        if (stateIcon != null) stateIcon.Visible = true;
                        if (sprite is CardShowNode cardNode) cardNode.stop = cardData.Orientation == Orientation.Horizontal;
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
        try
        {
            removeCardImpl(player, zoneType, index);
        }
        catch (Exception ex)
        {
            GD.PushError($"removeCard P{player} {zoneType}[{index}] failed: {ex.Message}");
        }
    }

    private void removeCardImpl(int player, ZoneType zoneType, int index)
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

    public void setLp(int player, int newLp, int playSfxType = -1)
    {
        this.AnimateLabel(player, newLp, playSfxType);
        if (player == 1)
        {
            this.p1Lp = newLp;
        }
        if (player == 2)
        {
            this.p2Lp = newLp;
        }
    }

    public void setPhase()
    {
        
    }

    public void showDice(int player, int val)
    {
        Node3D roller = GetNode<Node3D>("showfield/middle/dice/DiceCinematicRoller3D");

        // 属性：0=下 1=上 2=左 3=右
        roller.Set("gravity_direction", player == 1 ? 2 : (player == 2 ? 3 : Random.Shared.NextInt64() % 4));

        // 场景里没有生成骰子时：有 dice_definitions 就按定义生成（保留贴图），
        // 否则创建一颗默认 D6；不创建的话 roll_all() 没有骰子可滚。
        if (roller.Call("get_registered_dice").AsGodotArray().Count == 0)
        {
            if (roller.Get("dice_definitions").AsGodotArray().Count > 0)
            {
                roller.Call("spawn_dice_from_definitions");
            }
            else
            {
                Variant die = roller.Call("create_die");
                die.AsGodotObject().Set("edge_length", 1.8f);
            }
        }

        roller.Call("roll_all", val);
        AudioManager.getInstance().playSE("dice-shake-1");
    }

    public void showCoin(int player, int val)
    {
        // 1=正面，0=反面
        var coin = GetNode<Node3D>("showfield/middle/coin/CoinToss3D");
        coin.Set("gravity_direction", player == 1 ? 2 : (player == 2 ? 3 : Random.Shared.NextInt64() % 4));
        coin.Call("toss", val);
        AudioManager.getInstance().playSE("dice-grab-1");

    }

    public void showSummonAnim(string animName)
    {
        AnimatedSprite3D animatedSprite3D = GetNode<AnimatedSprite3D>("showfield/middle/items/summon_anim/anim");
        animatedSprite3D.Animation = animName;
        animatedSprite3D.Play();
        Godot.Collections.Dictionary<string, string> audioMap = new Godot.Collections.Dictionary<string, string>();
        audioMap.Add("advance", "specialsummon");
        audioMap.Add("normal", "specialsummon");
        audioMap.Add("flip", "specialsummon");
        audioMap.Add("special", "specialsummon2");
        audioMap.Add("fusion", "summon2");
        audioMap.Add("synchro", "summon2");
        audioMap.Add("xyz", "summon2");
        audioMap.Add("pendulum", "summon2");
        audioMap.Add("link", "summon2");
        audioMap.Add("ritual", "summon2");
        if (audioMap.ContainsKey(animName))
        {
            AudioManager.getInstance().playSE(audioMap[animName]);
        } 
        else
        {
            AudioManager.getInstance().playSE(audioMap["normal"]);
        }
    }

    public void playAtkSequence(int fromPlayer, ZoneType fromCellType, int fromCellIndex, int toPlayer, ZoneType toCellType, int toCellIndex, bool isDirect,
        Sprite3D movingSprite, Tween tween, Vector3 destination, float fadeDuration = 0.5f, float turnDuration = 0.4f, float moveDuration = 0.3f)
    {
        if (movingSprite == null)
        {
            GD.PushError("movingSprite 未赋值");
            return;
        }

        if (fromPlayer == 1)
        {
            movingSprite.RotationDegrees = new Vector3(movingSprite.RotationDegrees.X, movingSprite.RotationDegrees.Y, -90);
        }
        if (fromPlayer == 2)
        {
            movingSprite.RotationDegrees = new Vector3(movingSprite.RotationDegrees.X, movingSprite.RotationDegrees.Y, 90);
        }
        // 先确保初始透明度为 0
        var mod = movingSprite.Modulate;
        mod.A = 0f;
        movingSprite.Modulate = mod;

        // 记录起始状态
        Vector3 startPos = movingSprite.GlobalPosition;
        float startRotZ = movingSprite.Rotation.Z;

        // 计算目标角度：让 sprite 的朝向指向 destination
        // 这里按“Z 轴旋转 + 精灵默认朝 +X”来算；
        Vector3 dir = startPos - destination;
        float targetRotZ = Mathf.Atan2(dir.Y, dir.X);

        // 处理角度环绕，避免绕远路
        float deltaAngle = Mathf.Wrap(targetRotZ, -Mathf.Pi, Mathf.Pi);
        float finalRotZ = (startRotZ + deltaAngle + Mathf.Pi) % Mathf.Pi;
        if (fromPlayer == 1)
        {
            finalRotZ = (startRotZ + deltaAngle - Mathf.Pi) % Mathf.Pi;   
        }

        if (fromCellType == ZoneType.Ex && toCellType == ZoneType.Ex)
        {
            if (fromPlayer == 1)
            {
                if (toCellIndex == 1)
                {
                    
                    movingSprite.RotationDegrees = new Vector3(movingSprite.RotationDegrees.X, movingSprite.RotationDegrees.Y, 270);
                    startRotZ = movingSprite.Rotation.Z;
                    finalRotZ = Mathf.Pi;   
                }
                else
                {
                    finalRotZ = 0;
                }
            }
            if (fromPlayer == 2)
            {
                if (toCellIndex == 1)
                {
                    finalRotZ = 0;
                }
                else
                {
                    finalRotZ = Mathf.Pi;   
                }
            }
            GD.Print("startRotZ: ", startRotZ, " finalRotZ: ", finalRotZ);
        }
        

        // 1. 透明度 0 → 1
        tween.TweenProperty(movingSprite, "modulate:a", 1.0f, fadeDuration);

        // 2. 沿 Z 轴转向指定角度（x、y 不变）
        tween.TweenMethod(
            Callable.From<float>(t =>
            {
                Vector3 rot = movingSprite.Rotation;
                rot.Z = Mathf.Lerp(startRotZ, finalRotZ, t);
                // 显式保持 X、Y 不变
                rot.X = movingSprite.Rotation.X; // 实际就是原值
                rot.Y = movingSprite.Rotation.Y;
                movingSprite.Rotation = rot;
            }),
            0.0f, 1.0f, turnDuration
        );

        // 3. 顺着该方向斜向移动到指定 globalPosition
        tween.TweenMethod(
            Callable.From<float>(t =>
            {
                movingSprite.GlobalPosition = startPos.Lerp(destination, t);
            }),
            0.0f, 1.0f, moveDuration
        );
        // 播放移动音频
        tween.Parallel().TweenCallback(Callable.From(() => {
            AudioManager.getInstance().playSE("attack");
        }));

        // 4. 等待0.3s
        tween.TweenInterval(0.3f);

        // 可选：动画结束后回调
        tween.TweenCallback(Callable.From(() =>
        {
            GD.Print("动画完成，当前位置: " + movingSprite.GlobalPosition);
            movingSprite.Visible = false;
            movingSprite.Modulate = new Color(1, 1, 1, 0);
            if (fromPlayer == 1)
            {
                movingSprite.RotationDegrees = new Vector3(movingSprite.RotationDegrees.X, movingSprite.RotationDegrees.Y, -90);
            }
            if (fromPlayer == 2)
            {
                movingSprite.RotationDegrees = new Vector3(movingSprite.RotationDegrees.X, movingSprite.RotationDegrees.Y, 90);
            }
        }));
    }

    public void showAttack(int fromPlayer, ZoneType fromCellType, int fromCellIndex, int toPlayer, ZoneType toCellType, int toCellIndex, bool isDirect)
    {
        GD.Print(fromPlayer, " ", fromCellType, " ", fromCellIndex, " ", toPlayer, " ", toCellType, " ", toCellIndex, " ", isDirect, " ");

        fromCellIndex += 1;
        toCellIndex += 1;
        
        string newNodeName = string.Format("{0}_{1}_{2}", fromPlayer, fromCellType, fromCellIndex);
        string atkNodeName = string.Format("showfield/middle/cards/player{0}/front/card{1}", fromPlayer, fromCellIndex);
        string atkNodeNameTo = string.Format("showfield/middle/cards/player{0}/front/card{1}", toPlayer, toCellIndex);

        if (fromCellType == ZoneType.Ex)
        {
            if (fromPlayer == 1)
            {
                atkNodeName = string.Format("showfield/middle/cards/ex/card{0}", fromCellIndex == 1 ? 2 : 1);
            }
            else
            {
                atkNodeName = string.Format("showfield/middle/cards/ex/card{0}", fromCellIndex);
            } 
        }
        if (toCellType == ZoneType.Ex)
        {
            if (toPlayer == 1)
            {
                atkNodeNameTo = string.Format("showfield/middle/cards/ex/card{0}", toCellIndex == 1 ? 2 : 1);
            } 
            else
            {
                atkNodeNameTo = string.Format("showfield/middle/cards/ex/card{0}", toCellIndex);
            }
        }
        Sprite3D node = GetNodeOrNull<Sprite3D>(newNodeName);;

        // 创建节点
        if (node == null)
        {
            GD.Print("创建节点: " + atkNodeName);
            Sprite3D template = null;
            if (fromPlayer == 1)
            {
                template = this.GetNode<Sprite3D>("showfield/middle/player1AtkSwordTemplate");
                this.p1AtkSpriteTemplate = template;
            }
            else
            {
                template = this.GetNode<Sprite3D>("showfield/middle/player2AtkSwordTemplate");
                this.p2AtkSpriteTemplate = template;
            }
            node = (Sprite3D)template.Duplicate();
            node.Name = newNodeName;
            template.GetParent<Node3D>().AddChild(node);
            GD.Print("add child");
            node.Modulate = new Color(1, 1, 1, 0);
        }
        if (fromPlayer == 1)
        {
            this.p1AtkSpriteMoving = node;   
        } 
        else
        {
            this.p2AtkSpriteMoving = node;
        }
        Sprite3D fromSprte = this.GetNode<Sprite3D>(atkNodeName);
        node.Visible = true;
        node.GlobalPosition = new Vector3(fromSprte.GlobalPosition.X, fromSprte.GlobalPosition.Y, node.GlobalPosition.Z);
        Node3D targetNode = null;
        if (!isDirect)
        {
            targetNode = this.GetNode<Sprite3D>(atkNodeNameTo);
        }
        else
        {
            targetNode = this.GetNode<Node3D>(string.Format("showfield/middle/cards/player{0}/directNode", toPlayer));
        }
        GD.Print(atkNodeName, "\n", atkNodeNameTo);
        Vector3 destination = new Vector3(targetNode.GlobalPosition.X, targetNode.GlobalPosition.Y, node.GlobalPosition.Z);
        Tween tween = node.CreateTween();
        this.playAtkSequence(fromPlayer, fromCellType, fromCellIndex, toPlayer, toCellType, toCellIndex, isDirect, node, tween, destination);
    }

    public void backToTitle()
    {
        GD.Print("back to title");
        clearField();
        currField = new Battlefield();
        // 返回标题界面
         Node fadeFancy = GetNode("/root/FancyFade");
         fadeFancy.Call("blurry_noise", titleBig.Instantiate());
         BattleManager.getInstance().mainUI = null;
    }

    public void clearField()
    {
        for (int player = 1; player <= 2; player += 1)
        {
            for (int i = 0; i < 5; i += 1)
            {
                removeCard(player, ZoneType.Front, i);
                removeCard(player, ZoneType.Back, i);
            }
            for (int i = 0; i < 2; i += 1)
            {
                removeCard(player, ZoneType.Ex, i);
            }
            removeCard(player, ZoneType.Field, 0);
        }
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

    public void light(bool on=false)
    {
        Color color = on ? Colors.White : Colors.Black;
        this.GetNode<ColorRect>("ui/player1/backcolor").Color = color;
        this.GetNode<ColorRect>("ui/player2/backcolor").Color = color;
    }

}
