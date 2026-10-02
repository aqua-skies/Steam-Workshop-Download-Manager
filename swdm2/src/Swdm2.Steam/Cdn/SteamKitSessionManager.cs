using SteamKit2;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// SteamKit2 会话管理默认实现（D4.1):
/// - SteamClient+CallbackManager 连接 CM（SteamKit 内置服务器列表）→ SteamUser.LogOn;
/// - Steam Guard（邮件码/2FA):EResult.AccountLogonDenied 等 → <see cref="ISteamGuardPrompter"/> 收码 → 带 GuardCode 重试（上限 2 次=防刷码）;
/// - EResult → SteamError 映射（401 语义=InvalidPassword/InvalidLoginAuthCode/AccountLogonDenied→AuthRequired);
/// - 测试 seam:<see cref="LogOnFunc"/> 注入假登录结果（生产=SteamKit 真链，同 qa-20 D3.3 进程 seam 模式）;
/// - ⚠️[参数待重标定] CM 连接超时 30s(C7/D2.6 方法学：1.x 无同栈经验值）。
/// </summary>
public sealed class SteamKitSessionManager : ISteamSessionManager
{
    /// <summary>⚠️[参数待重标定] CM 连接+登录总超时（秒）。</summary>
    public const int DefaultTimeoutSeconds = 30;

    /// <summary>⚠️[参数待重标定] Steam Guard 收码重试上限（防刷码；含邮箱码错误+2FA 码错误）。</summary>
    public const int MaxGuardRetries = 2;

    private readonly ISteamGuardPrompter? _prompter;
    private readonly int _timeoutSeconds;

    /// <summary>
    /// 测试 seam：假登录结果（生产=SteamKit 真链）。
    /// 签式（login, ct) → (EResult, SteamId)。null=用真链。
    /// </summary>
    internal Func<SteamSessionLogin, CancellationToken, Task<(EResult Result, ulong SteamId)>>? LogOnFunc { get; set; }

    public SteamSession? Current { get; private set; }

    public SteamKitSessionManager(ISteamGuardPrompter? prompter = null, int? timeoutSeconds = null)
    {
        _prompter = prompter;
        _timeoutSeconds = timeoutSeconds ?? DefaultTimeoutSeconds;
    }

    /// <summary>
    /// 测试/诊断注入 seam（生产=SteamKit 真链，null 不覆盖）。
    /// App 环境容忍门触发（SWDM2_TEST_2FA=1)注入桩=假 CM 拒认证→走 2FA 弹窗链路（#23 场景）。
    /// </summary>
    /// <param name="prompter">收码回调（App 弹窗 A11)。</param>
    /// <param name="logOnOverride">登录结果桩（login,ct)→(EResult,SteamId);null=SteamKit 真链。</param>
    /// <param name="timeoutSeconds">超时秒。</param>
    public SteamKitSessionManager(
        ISteamGuardPrompter? prompter,
        Func<SteamSessionLogin, CancellationToken, Task<(EResult Result, ulong SteamId)>>? logOnOverride,
        int? timeoutSeconds = null)
        : this(prompter, timeoutSeconds)
    {
        LogOnFunc = logOnOverride;
    }

    public async Task<Result<SteamSession, SteamError>> LoginAsync(SteamSessionLogin login, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(login);
        var attempt = login;
        var guardTries = 0;

        while (true)
        {
            ct.ThrowIfCancellationRequested();
            var outcome = await (LogOnFunc ?? RealLogOnAsync)(attempt, ct).ConfigureAwait(false);

            if (outcome.Result == EResult.OK)
            {
                Current = new SteamSession(
                    Account: attempt.IsAnonymous ? "anonymous" : attempt.Username!,
                    IsAnonymous: attempt.IsAnonymous,
                    SteamId: outcome.SteamId,
                    LoggedInAtUtc: DateTimeOffset.UtcNow);
                return Result<SteamSession, SteamError>.Ok(Current);
            }

            // Steam Guard：邮箱码被拒/未提供 → 回调收码重试
            if (NeedsGuardCode(outcome.Result) && _prompter is not null && guardTries < MaxGuardRetries)
            {
                guardTries++;
                var code = await _prompter.PromptGuardCodeAsync(attempt.Username ?? "anonymous", ct).ConfigureAwait(false);
                if (string.IsNullOrEmpty(code))
                    return Result<SteamSession, SteamError>.Fail(SteamError.AuthRequired); // 用户取消收码=拒认证
                attempt = attempt with { GuardCode = code };
                continue;
            }

            return Result<SteamSession, SteamError>.Fail(MapLogOnResult(outcome.Result));
        }
    }

    /// <summary>需要 Steam Guard 码的 EResult 集合（邮箱码+2FA)。</summary>
    internal static bool NeedsGuardCode(EResult result)
        => result == EResult.AccountLogonDenied
           || result == EResult.InvalidLoginAuthCode
           || result == EResult.TwoFactorCodeMismatch
           || result == EResult.AccountLoginDeniedNeedTwoFactor;

    /// <summary>EResult → SteamError 映射（401=拒凭证→AuthRequired;HTTP 401 同语义）。</summary>
    internal static SteamError MapLogOnResult(EResult result)
        => result switch
        {
            EResult.InvalidPassword => SteamError.AuthRequired,            // 401 语义
            EResult.InvalidLoginAuthCode => SteamError.AuthRequired,       // 2FA 码错
            EResult.AccountLogonDenied => SteamError.AuthRequired,         // 需邮箱 Steam Guard
            EResult.AccountLoginDeniedNeedTwoFactor => SteamError.AuthRequired,
            EResult.AccountDisabled => SteamError.AuthRequired,
            EResult.RateLimitExceeded => SteamError.RateLimited,
            EResult.ServiceUnavailable => SteamError.Network,
            EResult.Timeout => SteamError.Timeout,
            EResult.Banned => SteamError.Blocked,
            _ => SteamError.Network
        };

    /// <summary>生产真链：SteamClient 连 CM + SteamUser.LogOn（阻塞至 LoggedOn/超时）。</summary>
    private async Task<(EResult Result, ulong SteamId)> RealLogOnAsync(SteamSessionLogin login, CancellationToken ct)
    {
        var client = new SteamClient();
        var manager = new CallbackManager(client);
        var user = client.GetHandler<SteamUser>()!;

        var connected = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var loggedOn = new TaskCompletionSource<(EResult, ulong)>(TaskCreationOptions.RunContinuationsAsynchronously);

        manager.Subscribe<SteamClient.ConnectedCallback>(_ => connected.TrySetResult(true));
        manager.Subscribe<SteamUser.LoggedOnCallback>(cb =>
            loggedOn.TrySetResult((cb.Result, cb.ClientSteamID is null ? 0UL : (ulong)cb.ClientSteamID)));

        client.Connect();
        using var registration = ct.Register(() =>
        {
            client.Disconnect();
            connected.TrySetCanceled(ct);
            loggedOn.TrySetCanceled(ct);
        });

        // 回调泵（后台线程，Disconnect 后自然退出）
        var pump = Task.Run(() =>
        {
            while (!loggedOn.Task.IsCompleted)
            {
                manager.RunWaitCallbacks(TimeSpan.FromMilliseconds(200));
            }
        }, ct);

        try
        {
            await connected.Task.WaitAsync(TimeSpan.FromSeconds(_timeoutSeconds), ct).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            client.Disconnect();
            return (EResult.Timeout, 0);
        }

        var details = new SteamUser.LogOnDetails
        {
            // SteamKit 3.x:匿名也需 username+password（"anonymous"/"anonymous"——SteamKit 文档惯例）
            Username = login.IsAnonymous ? "anonymous" : login.Username,
            Password = login.IsAnonymous ? "anonymous" : login.Password,
            AuthCode = login.IsAnonymous ? null : login.GuardCode,    // 邮箱 Steam Guard 码
            TwoFactorCode = login.IsAnonymous ? null : login.GuardCode, // 2FA（同字段复用：首次试错后由 prompter 补）
        };

        user.LogOn(details);

        try
        {
            var (result, steamId) = await loggedOn.Task.WaitAsync(TimeSpan.FromSeconds(_timeoutSeconds), ct).ConfigureAwait(false);
            if (result == EResult.OK)
            {
                // D4.2:会话保持连接（CDN manifest 解析与下载的 SteamApps/SteamContent/UnifiedMessages 调用载体）
                LiveClient = client;
                LiveManager = manager;
            }
            else
            {
                client.Disconnect();
            }
            return (result, steamId);
        }
        catch (TimeoutException)
        {
            client.Disconnect();
            return (EResult.Timeout, 0);
        }
    }

    /// <summary>已连接的 Live 客户端（D4.2+ CDN 原语消费；未登录=null)。</summary>
    internal SteamClient? LiveClient { get; private set; }

    /// <summary>Live 回调管理器（同上；SteamKitCdnClient.CallbackPump 驱动）。</summary>
    internal CallbackManager? LiveManager { get; private set; }

    /// <summary>登出/断线（释放会话；AppHost.StopAsync 消费）。</summary>
    public void Disconnect()
    {
        LiveClient?.Disconnect();
        LiveClient = null;
        LiveManager = null;
    }
}
