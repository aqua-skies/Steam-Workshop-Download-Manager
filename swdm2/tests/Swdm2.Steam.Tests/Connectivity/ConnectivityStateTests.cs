using Swdm2.Core.Options;
using Swdm2.Steam.Connectivity;
using Xunit;

namespace Swdm2.Steam.Tests.Connectivity;

/// <summary>
/// D2.2 IConnectivityState 状态机验收：三态语义（Unknown 初值 + 变更触发事件 + 同值不触发）。
/// </summary>
public sealed class ConnectivityStateTests
{
    [Fact]
    public void Initial_State_All_Endpoints_Unknown()
    {
        var state = new ConnectivityState();
        Assert.Equal(4, state.Current.Count); // 含 Cdn（预留，D3 期探测）
        Assert.All(state.Current.Values, s => Assert.Equal(Reachability.Unknown, s.Reach));
        Assert.All(state.Current.Values, s => Assert.Equal(-1, s.LatencyMs));
    }

    [Fact]
    public void First_Apply_Raises_Changed_Event()
    {
        var state = new ConnectivityState();
        var events = new List<IReadOnlyDictionary<EndpointKind, EndpointStatus>>();
        state.Changed += (_, snapshot) => events.Add(snapshot);

        var snapshot = new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 42),
            [EndpointKind.Store] = new(EndpointKind.Store, Reachability.Direct, 30),
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.ViaProxy, 88),
        };
        state.Apply(snapshot);

        Assert.Single(events);
        Assert.Equal(Reachability.Direct, state.Current[EndpointKind.Api].Reach);
        Assert.Equal(42, state.Current[EndpointKind.Api].LatencyMs);
        Assert.Equal(Reachability.ViaProxy, state.Current[EndpointKind.Community].Reach);
    }

    /// <summary>验收判据：变更触发事件——状态转移（Direct→Blocked）必须触发，同值重复不触发。</summary>
    [Fact]
    public void State_Transition_Raises_Event_Repeat_Same_Does_Not()
    {
        var state = new ConnectivityState();
        var events = new List<IReadOnlyDictionary<EndpointKind, EndpointStatus>>();
        state.Changed += (_, snapshot) => events.Add(snapshot);

        var first = new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 42),
        };
        state.Apply(first);
        Assert.Single(events);

        // 同值再应用（含不同 Latency 也视为变化——Latency 是状态一部分）
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 43),
        });
        Assert.Equal(2, events.Count);

        // 完全同值再应用 → 不触发
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 43),
        });
        Assert.Equal(2, events.Count);

        // 状态转移 Direct → Blocked → Unreachable：各触发一次（三态语义）
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Blocked, -1),
        });
        Assert.Equal(3, events.Count);
        Assert.Equal(Reachability.Blocked, state.Current[EndpointKind.Api].Reach);

        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Unreachable, -1),
        });
        Assert.Equal(4, events.Count);
        Assert.Equal(Reachability.Unreachable, state.Current[EndpointKind.Api].Reach);
    }

    [Fact]
    public void Current_Is_Snapshot_Immutable_To_Later_Applies()
    {
        var state = new ConnectivityState();
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 1),
        });
        var snapshotCopy = state.Current;

        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Unreachable, -1),
        });

        Assert.Equal(Reachability.Direct, snapshotCopy[EndpointKind.Api].Reach);
        Assert.Equal(Reachability.Unreachable, state.Current[EndpointKind.Api].Reach);
    }
}
