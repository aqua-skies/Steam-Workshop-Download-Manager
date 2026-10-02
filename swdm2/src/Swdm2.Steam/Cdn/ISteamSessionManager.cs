using Swdm2.Core.Results;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// SteamKit2 会话管理契约（D4.1,spec §3.2):
/// - 匿名会话（Username=null 或 "anonymous"):SteamKit CM 连接+匿名登录（工坊内容下载前置）;
/// - 账号会话：用户名+密码，Steam Guard 邮箱验证码经 <see cref="ISteamGuardPrompter"/> 回调（App 弹窗收码，A11);
/// - 401 语义（拒凭证）→ <see cref="SteamError.AuthRequired"/>;
/// - 失败=Result.Fail 而非抛异常（D2.3/D3.3 同构）。
/// spec 契约细化说明：spec 原签 Task LoginAsync(SteamCmdLogin);本契约返回 Result&lt;SteamSession&gt;
/// 并用 <see cref="SteamSessionLogin"/>（与 SteamCmdLogin 同构+2FA 回调语义），同属审批内 DAG 细化。
/// </summary>
public interface ISteamSessionManager
{
    /// <summary>登录（匿名/账号；Steam Guard 触发时走 prompter 回调重试）。null=取消收码。</summary>
    Task<Result<SteamSession, SteamError>> LoginAsync(SteamSessionLogin login, CancellationToken ct = default);

    /// <summary>当前会话快照（不发请求；未登录=null)。</summary>
    SteamSession? Current { get; }
}

/// <summary>登录请求（不可变；Username 空或 "anonymous"=匿名）。</summary>
public sealed record SteamSessionLogin(string? Username, string? Password, string? GuardCode)
{
    /// <summary>匿名模式判定。</summary>
    public bool IsAnonymous => string.IsNullOrEmpty(Username) || Username == "anonymous";
}

/// <summary>会话快照（不可变）。</summary>
public sealed record SteamSession(string Account, bool IsAnonymous, ulong SteamId, DateTimeOffset LoggedInAtUtc);

/// <summary>
/// Steam Guard 收码交互契约（App 实现，A11 模式：Dispatcher.Invoke 切 UI 线程 ShowDialog
/// + TaskCompletionSource&lt;string?&gt; 唤醒后台 await——SCA SteamAuth §4 教训 #6)。
/// 返回 null=用户取消收码。
/// </summary>
public interface ISteamGuardPrompter
{
    /// <summary>弹出收码窗（模态阻塞主窗口）；返回验证码或 null（取消）。</summary>
    Task<string?> PromptGuardCodeAsync(string account, CancellationToken ct = default);
}
