using SteamKit2;
using Swdm2.Core.Results;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Steam.Tests.Cdn;

/// <summary>
/// D4.1 SteamKit2 会话验收：
/// - 匿名会话建立（seam 桩：EResult.OK;真 Online 见 SessionManagerOnlineTests)
/// - 401→AuthRequired（InvalidPassword/InvalidLoginAuthCode)
/// - Steam Guard 回调链路（AccountLogonDenied→prompter→带码重试→OK;用户取消→AuthRequired;重试上限）
/// - EResult→SteamError 映射表
/// 真链登录（SteamClient 连 CM)在沙箱可能被环境阻断——Online 测试走环境容忍门模式（同 D3.3/D3.4)。
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SteamSessionManagerTests
{
    private static SteamSessionLogin Anonymous() => new(null, null, null);

    /// <summary>验收判据：匿名会话建立（Current 快照+IsAnonymous)。</summary>
    [Fact]
    public async Task Anonymous_Login_Establishes_Session()
    {
        var mgr = new SteamKitSessionManager
        {
            LogOnFunc = (_, _) => Task.FromResult((EResult.OK, 76561198000000002UL))
        };

        var result = await mgr.LoginAsync(Anonymous());

        Assert.True(result.IsOk);
        Assert.True(result.Value!.IsAnonymous);
        Assert.Equal("anonymous", result.Value.Account);
        Assert.Equal(76561198000000002UL, result.Value.SteamId);
        Assert.Same(mgr.Current, result.Value);
    }

    /// <summary>验收判据：401 语义（拒凭证）→ AuthRequired。</summary>
    [Theory]
    [InlineData(EResult.InvalidPassword)]
    [InlineData(EResult.InvalidLoginAuthCode)]
    [InlineData(EResult.AccountDisabled)]
    public async Task Credential_Rejection_Maps_AuthRequired(EResult rejected)
    {
        var mgr = new SteamKitSessionManager
        {
            LogOnFunc = (_, _) => Task.FromResult((rejected, 0UL))
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", null));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    /// <summary>验收判据：Steam Guard 回调链路——首次 AccountLogonDenied→prompter 收码→带码重试成功。</summary>
    [Fact]
    public async Task Guard_Required_Prompts_And_Retries_With_Code()
    {
        var prompted = 0;
        var prompter = new StubPrompter(_ => { Interlocked.Increment(ref prompted); return "ABC12"; });

        var first = true;
        var mgr = new SteamKitSessionManager(prompter)
        {
            LogOnFunc = (login, _) =>
            {
                if (first)
                {
                    first = false;
                    return Task.FromResult((EResult.AccountLogonDenied, 0UL));
                }
                Assert.Equal("ABC12", login.GuardCode); // 收码已注入重试
                return Task.FromResult((EResult.OK, 76561198000000003UL));
            }
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", null));

        Assert.True(result.IsOk);
        Assert.Equal(1, prompted);
        Assert.Equal(76561198000000003UL, result.Value!.SteamId);
    }

    /// <summary>验收判据：用户取消收码→AuthRequired（不重试）。</summary>
    [Fact]
    public async Task Guard_Prompt_Cancelled_Fails_AuthRequired()
    {
        var prompter = new StubPrompter(_ => null!);
        var mgr = new SteamKitSessionManager(prompter)
        {
            LogOnFunc = (_, _) => Task.FromResult((EResult.AccountLogonDenied, 0UL))
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", null));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    /// <summary>验收判据：收码重试上限（连续错码不无限弹窗）。</summary>
    [Fact]
    public async Task Guard_Retries_Capped_At_MaxGuardRetries()
    {
        var prompts = 0;
        var prompter = new StubPrompter(_ => { Interlocked.Increment(ref prompts); return "BAD12"; });

        var mgr = new SteamKitSessionManager(prompter)
        {
            LogOnFunc = (_, _) => Task.FromResult((EResult.InvalidLoginAuthCode, 0UL))
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", null));

        Assert.False(result.IsOk);
        Assert.Equal(SteamKitSessionManager.MaxGuardRetries, prompts); // 弹窗次数=重试上限（含首次收码）
        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    /// <summary>2FA 码错误（TwoFactorCodeMismatch）也走收码重试。</summary>
    [Fact]
    public async Task TwoFactor_Mismatch_Also_Prompts()
    {
        var prompter = new StubPrompter(_ => "XYZ99");
        var first = true;
        var mgr = new SteamKitSessionManager(prompter)
        {
            LogOnFunc = (_, _) =>
            {
                if (first)
                {
                    first = false;
                    return Task.FromResult((EResult.TwoFactorCodeMismatch, 0UL));
                }
                return Task.FromResult((EResult.OK, 76561198000000004UL));
            }
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", "OLD1"));
        Assert.True(result.IsOk);
    }

    /// <summary>无 prompter 时需码直接 AuthRequired（非交互场景）。</summary>
    [Fact]
    public async Task Guard_Required_Without_Prompter_Fails_Fast()
    {
        var mgr = new SteamKitSessionManager /* prompter=null */
        {
            LogOnFunc = (_, _) => Task.FromResult((EResult.AccountLogonDenied, 0UL))
        };

        var result = await mgr.LoginAsync(new SteamSessionLogin("user", "pw", null));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    // ---------- EResult 映射表 ----------

    [Theory]
    [InlineData(EResult.InvalidPassword, SteamError.AuthRequired)]
    [InlineData(EResult.InvalidLoginAuthCode, SteamError.AuthRequired)]
    [InlineData(EResult.AccountLogonDenied, SteamError.AuthRequired)]
    [InlineData(EResult.AccountLoginDeniedNeedTwoFactor, SteamError.AuthRequired)]
    [InlineData(EResult.RateLimitExceeded, SteamError.RateLimited)]
    [InlineData(EResult.Timeout, SteamError.Timeout)]
    [InlineData(EResult.ServiceUnavailable, SteamError.Network)]
    [InlineData(EResult.Banned, SteamError.Blocked)]
    public void MapLogOnResult_Table(EResult input, SteamError expected)
        => Assert.Equal(expected, SteamKitSessionManager.MapLogOnResult(input));

    [Theory]
    [InlineData(EResult.AccountLogonDenied, true)]
    [InlineData(EResult.InvalidLoginAuthCode, true)]
    [InlineData(EResult.TwoFactorCodeMismatch, true)]
    [InlineData(EResult.InvalidPassword, false)]
    [InlineData(EResult.OK, false)]
    public void NeedsGuardCode_Table(EResult input, bool expected)
        => Assert.Equal(expected, SteamKitSessionManager.NeedsGuardCode(input));

    private sealed class StubPrompter : ISteamGuardPrompter
    {
        private readonly Func<string, string?> _behavior;
        public StubPrompter(Func<string, string?> behavior) => _behavior = behavior;
        public Task<string?> PromptGuardCodeAsync(string account, CancellationToken ct = default)
            => Task.FromResult(_behavior(account));
    }
}
