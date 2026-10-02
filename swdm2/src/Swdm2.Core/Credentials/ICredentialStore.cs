namespace Swdm2.Core.Credentials;

/// <summary>
/// 凭据存储契约（§3.1.1）。C2 硬纪律：
/// 1. DPAPI(CurrentUser) 加密落盘——明文**不落盘**、不进配置文件；
/// 2. 明文**不进异常消息**（所有失败包装为 CredentialStoreException，不含账号/密码片段）；
/// 3. 明文**不进日志**（与 D1.5 脱敏 sink 联合断言；调用方亦禁止直接记录返回的 ReadOnlyMemory&lt;char&gt;）。
/// Steam 账号大小写不敏感（邮箱语义），键比较用 OrdinalIgnoreCase。
/// </summary>
public interface ICredentialStore
{
    /// <summary>读取密码；账号不存在返回 null（不抛异常）。</summary>
    Task<ReadOnlyMemory<char>?> GetPasswordAsync(string account, CancellationToken ct = default);

    /// <summary>保存（覆盖）密码。空密码抛 ArgumentException（请改用 DeleteAsync）。</summary>
    Task SetPasswordAsync(string account, ReadOnlyMemory<char> password, CancellationToken ct = default);

    /// <summary>删除凭据；不存在视为成功（幂等）。</summary>
    Task DeleteAsync(string account, CancellationToken ct = default);
}
