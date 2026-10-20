using System.Threading;
using System.Threading.Tasks;
using Godot;

namespace AudioService.Handlers;

public partial class StreamedBusHandler
{
    private const float MUTE = -80f;
    private const float NORMAL = 0f;

    private static readonly NodePath PropertyVolumeDb = "volume_db";

    private readonly Node owner;

    private readonly AudioStreamPlayer channelA;
    private readonly AudioStreamPlayer channelB;

    private Tween tween;

    private AudioStreamPlayer activeChannel;
    private CancellationTokenSource playCts;

    public StreamedBusHandler(Node owner, StringName busName)
    {
        this.owner = owner;

        channelA = new AudioStreamPlayer { Bus = busName, Name = $"{busName}_ChannelA" };
        channelB = new AudioStreamPlayer { Bus = busName, Name = $"{busName}_ChannelB" };

        owner.AddChild(channelA);
        owner.AddChild(channelB);
    }

    public virtual void PlayStream(AudioStream stream, double fadeDuration = 1f, float fromPosition = 0)
    {
        SetStreamPaused(false);
        CancelCurrent();

        var targetChannel = (activeChannel == channelA) ? channelB : channelA;
        var outgoingChannel = activeChannel;

        targetChannel.Stream = stream;
        targetChannel.Play(fromPosition);

        activeChannel = targetChannel;

        tween = RecreateTween().SetParallel();
        tween.TweenProperty(targetChannel, PropertyVolumeDb, NORMAL, fadeDuration).From(MUTE);

        if (outgoingChannel != null && outgoingChannel.Playing)
        {
            tween.TweenProperty(outgoingChannel, PropertyVolumeDb, MUTE, fadeDuration).From(NORMAL);
            tween.Chain().TweenCallback(Callable.From(outgoingChannel.Stop));
        }
    }

    public virtual async Task<bool> PlayStreamAsync(AudioStream stream, double fadeDuration = 1f)
    {
        PlayStream(stream, fadeDuration);

        var token = playCts.Token;
        var player = activeChannel;

        if (player is null || !player.Playing)
            return false;

        var finishedTask = AwaitFinished(player);
        var cancelTask = Task.Delay(Timeout.Infinite, token);

        var completedTask = await Task.WhenAny(finishedTask, cancelTask);

        return completedTask == finishedTask;
    }

    public virtual void StopStream(double fadeDuration = 1f)
    {
        CancelCurrent();

        if (activeChannel is null)
            return;

        tween = RecreateTween();
        tween.TweenProperty(activeChannel, PropertyVolumeDb, MUTE, fadeDuration).From(NORMAL);
        tween.TweenCallback(Callable.From(activeChannel.Stop));
    }

    public virtual void SetStreamPaused(bool paused)
    {
        if (activeChannel != null)
            activeChannel.StreamPaused = paused;
    }

    private async Task AwaitFinished(AudioStreamPlayer player)
    {
        await owner.ToSignal(player, AudioStreamPlayer.SignalName.Finished);
    }

    private void CancelCurrent()
    {
        playCts?.Cancel();
        playCts?.Dispose();
        playCts = new CancellationTokenSource();
    }

    private Tween RecreateTween()
    {
        if (tween != null && tween.IsValid())
            tween.Kill();
        return owner.CreateTween();
    }
}
