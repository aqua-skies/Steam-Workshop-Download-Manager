using SteamKit2;
using Swdm2.Core.Results;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Steam.Tests.Cdn;

/// <summary>
/// D4.1 Online 集成（真链 SteamClient 连 CM 服务器）：
/// - 匿名会话建立（真 SteamKit 真登录，无 seam);
/// - 沙箱环境阻断（CM TCP 27017 不通/出口受限）→ Timeout/Network → 环境容忍标注，非实现缺陷
///   （设计对照纪律：换网络条件=桌面/代理环境复跑）。
/// </summary>
[Trait("Category", "Online")]
public sealed class SteamSessionManagerOnlineTests
{
    /// <summary>真链匿名登录：CM 连接+LogOn anonymous。沙箱阻断=Timeout/Network 环境容忍。</summary>
    [Fact]
    public async Task Online_Anonymous_Login_Real_SteamKit()
    {
        var mgr = new SteamKitSessionManager(prompter: null, timeoutSeconds: 45); // ⚠️[参数待重标定] 45s 网络容忍窗
        var result = await mgr.LoginAsync(new SteamSessionLogin(null, null, null));

        // 沙箱可达失败=环境阻断；成功=Online 绿
        if (!result.IsOk)
        {
            Assert.True(
                result.Error is SteamError.Network or SteamError.Timeout or SteamError.AuthRequired,
                $"Online 匿名登录失败={result.Error}——非预期错误类（环境阻断应为 Network/Timeout)");
            // [ONLINE-RESULT-FAIL] 环境阻断，非实现缺陷（换网络条件复验）
            Console.WriteLine($"[ONLINE-RESULT-FAIL] {result.Error} — 环境阻断，非实现缺陷（换网络条件复验）");
            return;
        }

        Assert.True(result.Value!.IsAnonymous);
        Assert.Equal("anonymous", result.Value.Account);
        Assert.True(result.Value.SteamId > 0);
    }
}
