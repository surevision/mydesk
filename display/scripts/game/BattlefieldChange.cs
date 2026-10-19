using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// 战场的变化
/// </summary>
public class BattlefieldChange
{
    // 新出现的卡
    public PlayerData player1CardsNew = null;
    // 被移除的卡
    public PlayerData player1CardsRemove = null;
    // 新出现的卡
    public PlayerData player2CardsNew = null;
    // 被移除的卡
    public PlayerData player2CardsRemove = null;

    /// <summary>
    /// 比较两个战场来获取卡片变化
    /// </summary>
    /// <param name="fieldOld"></param>
    /// <param name="fieldNew"></param>
    /// <returns></returns>
    public static BattlefieldChange compareField(Battlefield fieldOld, Battlefield fieldNew)
    {
        BattlefieldChange changeData = new BattlefieldChange();
        PlayerData p1Old = fieldOld.Players["1"];
        PlayerData p2Old = fieldOld.Players["2"];
        PlayerData p1New = fieldNew.Players["1"];
        PlayerData p2New = fieldNew.Players["2"];

        changeData.player1CardsNew = new PlayerData();
        changeData.player2CardsNew = new PlayerData();
        changeData.player1CardsRemove = new PlayerData();
        changeData.player2CardsRemove = new PlayerData();

        // EX 区
        for (int i = 0; i <= 1; i += 1)
        {
            // EX区出现
            if (p1Old.Ex[i] == null && p1New.Ex[i] != null)
            {
                changeData.player1CardsNew.Ex[i] = p1New.Ex[i];
            }
            if (p2Old.Ex[i] == null && p2New.Ex[i] != null)
            {
                changeData.player2CardsNew.Ex[i] = p2New.Ex[i];
            }

            // EX区消失
            if (p1Old.Ex[i] != null && p1New.Ex[i] == null)
            {
                changeData.player1CardsRemove.Ex[i] = p1Old.Ex[i];
            }
            if (p2Old.Ex[i] != null && p2New.Ex[i] == null)
            {
                changeData.player2CardsRemove.Ex[i] = p2Old.Ex[i];
            }

            // EX 区改变
            if (p1Old.Ex[i] != null && p1New.Ex[i] != null && 
                (p1Old.Ex[i].Id != p1New.Ex[i].Id || p1Old.Ex[i].FaceUp != p1New.Ex[i].FaceUp || p1Old.Ex[i].Orientation != p1New.Ex[i].Orientation))
            {
                changeData.player1CardsNew.Ex[i] = p1New.Ex[i];
                changeData.player1CardsRemove.Ex[i] = p1Old.Ex[i];
            }
            if (p2Old.Ex[i] != null && p2New.Ex[i] != null &&
                (p2Old.Ex[i].Id != p2New.Ex[i].Id || p2Old.Ex[i].FaceUp != p2New.Ex[i].FaceUp || p2Old.Ex[i].Orientation != p2New.Ex[i].Orientation))
            {
                changeData.player2CardsNew.Ex[i] = p2New.Ex[i];
                changeData.player2CardsRemove.Ex[i] = p2Old.Ex[i];
            }
        }

        // front怪物区
        for (int i = 0; i <= 4; i += 1)
        {
            // 怪物区出现
            if (p1Old.Front[i] == null && p1New.Front[i] != null)
            {
                changeData.player1CardsNew.Front[i] = p1New.Front[i];
            }
            if (p2Old.Front[i] == null && p2New.Front[i] != null)
            {
                changeData.player2CardsNew.Front[i] = p2New.Front[i];
            }

            // 怪物区消失
            if (p1Old.Front[i] != null && p1New.Front[i] == null)
            {
                changeData.player1CardsRemove.Front[i] = p1Old.Front[i];
            }
            if (p2Old.Front[i] != null && p2New.Front[i] == null)
            {
                changeData.player2CardsRemove.Front[i] = p2Old.Front[i];
            }

            // 怪物区改变
            if (p1Old.Front[i] != null && p1New.Front[i] != null &&
                (p1Old.Front[i].Id != p1New.Front[i].Id || p1Old.Front[i].FaceUp != p1New.Front[i].FaceUp || p1Old.Front[i].Orientation != p1New.Front[i].Orientation))
            {
                changeData.player1CardsNew.Front[i] = p1New.Front[i];
                changeData.player1CardsRemove.Front[i] = p1Old.Front[i];
            }
            if (p2Old.Front[i] != null && p2New.Front[i] != null &&
                (p2Old.Front[i].Id != p2New.Front[i].Id || p2Old.Front[i].FaceUp != p2New.Front[i].FaceUp || p2Old.Front[i].Orientation != p2New.Front[i].Orientation))
            {
                changeData.player2CardsNew.Front[i] = p2New.Front[i];
                changeData.player2CardsRemove.Front[i] = p2Old.Front[i];
            }
        }

        // back魔陷区
        for (int i = 0; i <= 4; i += 1)
        {
            // 魔陷区出现
            if (p1Old.Back[i] == null && p1New.Back[i] != null)
            {
                changeData.player1CardsNew.Back[i] = p1New.Back[i];
            }
            if (p2Old.Back[i] == null && p2New.Back[i] != null)
            {
                changeData.player2CardsNew.Back[i] = p2New.Back[i];
            }

            // 魔陷区消失
            if (p1Old.Back[i] != null && p1New.Back[i] == null)
            {
                changeData.player1CardsRemove.Back[i] = p1Old.Back[i];
            }
            if (p2Old.Back[i] != null && p2New.Back[i] == null)
            {
                changeData.player2CardsRemove.Back[i] = p2Old.Back[i];
            }

            // 魔陷区改变
            if (p1Old.Back[i] != null && p1New.Back[i] != null &&
                (p1Old.Back[i].Id != p1New.Back[i].Id || p1Old.Back[i].FaceUp != p1New.Back[i].FaceUp))
            {
                changeData.player1CardsNew.Back[i] = p1New.Back[i];
                changeData.player1CardsRemove.Back[i] = p1Old.Back[i];
            }
            if (p2Old.Back[i] != null && p2New.Back[i] != null &&
                (p2Old.Back[i].Id != p2New.Back[i].Id || p2Old.Back[i].FaceUp != p2New.Back[i].FaceUp))
            {
                changeData.player2CardsNew.Back[i] = p2New.Back[i];
                changeData.player2CardsRemove.Back[i] = p2Old.Back[i];
            }
        }

        // 场地出现
        if (p1Old.Field == null && p1New.Field != null)
        {
            changeData.player1CardsNew.Field = p1New.Field;
        }
        if (p2Old.Field == null && p2New.Field != null)
        {
            changeData.player2CardsNew.Field = p2New.Field;
        }
        // 场地消失
        if (p1Old.Field != null && p1New.Field == null)
        {
            changeData.player1CardsRemove.Field = p1Old.Field;
        }
        if (p2Old.Field != null && p2New.Field == null)
        {
            changeData.player2CardsRemove.Field = p2Old.Field;
        }
        // 场地改变
        if (p1Old.Field != null && p1New.Field != null &&
            (p1Old.Field.Id != p1New.Field.Id || p1Old.Field.FaceUp != p1New.Field.FaceUp))
        {
            changeData.player1CardsNew.Field = p1New.Field;
            changeData.player1CardsRemove.Field = p1Old.Field;
        }
        if (p2Old.Field != null && p2New.Field != null &&
            (p2Old.Field.Id != p2New.Field.Id || p2Old.Field.FaceUp != p2New.Field.FaceUp))
        {
            changeData.player2CardsNew.Field = p2New.Field;
            changeData.player2CardsRemove.Field = p2Old.Field;
        }

        // 额外卡组出现
        if (p1Old.ExDeck == null && p1New.ExDeck != null)
        {
            changeData.player1CardsNew.ExDeck = p1New.ExDeck;
        }
        if (p2Old.ExDeck == null && p2New.ExDeck != null)
        {
            changeData.player2CardsNew.ExDeck = p2New.ExDeck;
        }
        // 额外卡组消失
        if (p1Old.ExDeck != null && p1New.ExDeck == null)
        {
            changeData.player1CardsRemove.ExDeck = p1Old.ExDeck;
        }
        if (p2Old.ExDeck != null && p2New.ExDeck == null)
        {
            changeData.player2CardsRemove.ExDeck = p2Old.ExDeck;
        }
        // 额外卡组改变
        if (p1Old.ExDeck != null && p1New.ExDeck != null &&
            (p1Old.ExDeck.Id != p1New.ExDeck.Id || p1Old.ExDeck.FaceUp != p1New.ExDeck.FaceUp))
        {
            changeData.player1CardsNew.ExDeck = p1New.ExDeck;
            changeData.player1CardsRemove.ExDeck = p1Old.ExDeck;
        }
        if (p2Old.ExDeck != null && p2New.ExDeck != null &&
            (p2Old.ExDeck.Id != p2New.ExDeck.Id || p2Old.ExDeck.FaceUp != p2New.ExDeck.FaceUp))
        {
            changeData.player2CardsNew.ExDeck = p2New.ExDeck;
            changeData.player2CardsRemove.ExDeck = p2Old.ExDeck;
        }

        // 墓地出现
        if (p1Old.Grave == null && p1New.Grave != null)
        {
            changeData.player1CardsNew.Grave = p1New.Grave;
        }
        if (p2Old.Grave == null && p2New.Grave != null)
        {
            changeData.player2CardsNew.Grave = p2New.Grave;
        }
        // 墓地消失
        if (p1Old.Grave != null && p1New.Grave == null)
        {
            changeData.player1CardsRemove.Grave = p1Old.Grave;
        }
        if (p2Old.Grave != null && p2New.Grave == null)
        {
            changeData.player2CardsRemove.Grave = p2Old.Grave;
        }
        // 墓地改变
        if (p1Old.Grave != null && p1New.Grave != null &&
            (p1Old.Grave.Id != p1New.Grave.Id || p1Old.Grave.FaceUp != p1New.Grave.FaceUp))
        {
            changeData.player1CardsNew.Grave = p1New.Grave;
            changeData.player1CardsRemove.Grave = p1Old.Grave;
        }
        if (p2Old.Grave != null && p2New.Grave != null &&
            (p2Old.Grave.Id != p2New.Grave.Id || p2Old.Grave.FaceUp != p2New.Grave.FaceUp))
        {
            changeData.player2CardsNew.Grave = p2New.Grave;
            changeData.player2CardsRemove.Grave = p2Old.Grave;
        }


        // 卡组出现
        if (p1Old.Deck == null && p1New.Deck != null)
        {
            changeData.player1CardsNew.Deck = p1New.Deck;
        }
        if (p2Old.Deck == null && p2New.Deck != null)
        {
            changeData.player2CardsNew.Deck = p2New.Deck;
        }
        // 卡组消失
        if (p1Old.Deck != null && p1New.Deck == null)
        {
            changeData.player1CardsRemove.Deck = p1Old.Deck;
        }
        if (p2Old.Deck != null && p2New.Deck == null)
        {
            changeData.player2CardsRemove.Deck = p2Old.Deck;
        }
        // 卡组全是背面，没有改变的情况


        return changeData;
    }
}
