using Godot;
using System;
using Godot.Collections;
using AudioService;

public class AudioManager
{
    
    // 单例模式
    private static AudioManager instance = null;

    public static float defaultBGMVolumeRate = 1.0f;
    public static float defaultBGSVolumeRate = 1.0f;
    public static float defaultSEVolumeRate = 1.0f;

    private AudioStreamPlayer syncSEPlayer = null;

    private AudioManager(){}

    public static AudioManager getInstance()
    {
        if (instance == null)
        {
            instance = new AudioManager();
            // 初始化BGM
            AudioHost.Instance.RegisterStreamedBus("BGM");
            // 初始化BGS
            AudioHost.Instance.RegisterStreamedBus("BGS");
            // 初始化SE
            AudioHost.Instance.RegisterPooledBus("SE", capacity: 8);
        }

        return instance;
    }

    private AudioStream getStream(string id, string type)
    {
        string[] file_exts = {"wav", "mp3", "ogg"};
        string resourcePath = $"res://static/audios/{type}/{id}.wav";
        bool foundFlag = false;
        
        foreach (string ext in file_exts)
        {
            resourcePath = $"res://static/audios/{type}/{id}.{ext}";
            if (ResourceLoader.Exists(resourcePath))
            {
                foundFlag = true;
                break;
            }
        }
        if (!foundFlag)
        {
            GD.Print("Audio file not found: " + resourcePath);
            return null;
        }
        AudioStream audioStream = ResourceLoader.Load<AudioStream>(resourcePath);
        return audioStream;
    }

    public void playBGM(string id, float volume = 1.0f)
    {

        // AudioHost.Instance.SetBusVolume("BGM", volume * defaultBGMVolumeRate);
        AudioHost.Instance.PlayStream("BGM", getStream(id, "bgm"));
    }
    public void playExBGM(string id, float volume = 1.0f)
    {

        // AudioHost.Instance.SetBusVolume("BGM", volume * defaultBGMVolumeRate);
        AudioHost.Instance.PlayStream("BGM_EX", getStream(id, "bgm"));
    }
    public void playBGS(string id, float volume = 1.0f)
    {
        // AudioHost.Instance.SetBusVolume("BGS", volume * defaultBGSVolumeRate);
        AudioHost.Instance.PlayStream("BGS", getStream(id, "bgs"));
    }

    /// <summary>静音 / 取消静音全部音频（Master 总线）。</summary>
    public void setMute(bool mute)
    {
        int idx = AudioServer.GetBusIndex("Master");
        if (idx != -1)
        {
            AudioServer.SetBusMute(idx, mute);
        }
    }

    public void playSE(string id, float volume = 1.0f)
    {
        // AudioHost.Instance.SetBusVolume("SE", volume * defaultSEVolumeRate);
        var uiBus = AudioHost.Instance.GetPooledBus("SE");
        uiBus?.Play(getStream(id, "se"), new AudioOptions(VolumeDb: 0f, PitchScale: 1f, PitchVariance: 0f));
    }
    
    /// <summary>
    /// 播放一个音效，当前音效播完之前不会播放新的
    /// </summary>
    /// <param name="id"></param>
    /// <param name="volume"></param>
    public void playSESync(string id, float volume = 1.0f)
    {
        // AudioHost.Instance.SetBusVolume("SE", volume * defaultSEVolumeRate);
        if (this.syncSEPlayer != null && GodotObject.IsInstanceValid(this.syncSEPlayer) && this.syncSEPlayer.Playing)
        {
            return;
        }
        var uiBus = AudioHost.Instance.GetPooledBus("SE");
        this.syncSEPlayer = uiBus?.Play(getStream(id, "se"), new AudioOptions(VolumeDb: 0f, PitchScale: 1f, PitchVariance: 0f));
    }


}