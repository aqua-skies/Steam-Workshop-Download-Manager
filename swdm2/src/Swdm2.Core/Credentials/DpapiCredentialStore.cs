using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Swdm2.Core.Paths;

namespace Swdm2.Core.Credentials;

/// <summary>
/// DPAPI(CurrentUser) 凭据存储。**仅 Windows**（DPAPI 为 Windows 平台 API；Core 整体平台无关，
/// 本实现显式标 <see cref="SupportedOSPlatformAttribute"/>——非 Windows 调用方在平台守卫层就该被拦）。
/// 存储模型：<see cref="IPathService.CredentialsFile"/> = &lt;Root&gt;/credentials.bin——
/// JSON 字典（账号 → Base64(DPAPI 密文)），原子写入（临时文件 + File.Move），单写者锁。
/// C2：明文不落盘（仅密文+Base64）、明文不进异常（CryptographicException 包装为 CredentialStoreException）。
/// 密码字节使用后即清（CryptographicOperations.ZeroMemory）。
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class DpapiCredentialStore : ICredentialStore, IDisposable
{
    private readonly string _filePath;
    private readonly SemaphoreSlim _writeLock = new(1, 1);

    /// <param name="filePath">凭据文件绝对路径（由 IPathService.CredentialsFile 提供）。</param>
    public DpapiCredentialStore(string filePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        _filePath = filePath;
    }

    /// <summary>便捷工厂：从 IPathService 取凭据文件路径。</summary>
    public static DpapiCredentialStore FromPathService(IPathService paths)
        => new(paths.CredentialsFile);

    public async Task<ReadOnlyMemory<char>?> GetPasswordAsync(string account, CancellationToken ct = default)
    {
        var key = NormalizeAccount(account);
        var entries = await ReadEntriesAsync(ct).ConfigureAwait(false);
        if (!entries.TryGetValue(key, out var cipherBase64))
            return null; // 不存在分支：返回 null，不抛异常

        try
        {
            var cipher = Convert.FromBase64String(cipherBase64);
            var plain = ProtectedData.Unprotect(cipher, optionalEntropy: null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain).AsMemory();
        }
        catch (CryptographicException ex)
        {
            // C2：包装为不含明文的异常（密码原文绝不出现在消息/InnerException 中）
            throw new CredentialStoreException("凭据解密失败（文件损坏或由其他用户/机器生成）。", ex);
        }
    }

    public async Task SetPasswordAsync(string account, ReadOnlyMemory<char> password, CancellationToken ct = default)
    {
        if (password.IsEmpty)
            throw new ArgumentException("密码不能为空；如需清除请调用 DeleteAsync。", nameof(password));

        var key = NormalizeAccount(account);
        var plainBytes = Encoding.UTF8.GetBytes(password.ToArray());
        try
        {
            var cipher = ProtectedData.Protect(plainBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
            var cipherBase64 = Convert.ToBase64String(cipher);

            await _writeLock.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                var entries = await ReadEntriesAsync(ct).ConfigureAwait(false);
                entries[key] = cipherBase64;
                await WriteEntriesAtomicAsync(entries, ct).ConfigureAwait(false);
            }
            finally { _writeLock.Release(); }
        }
        finally
        {
            // 明文字节用完即清（减少驻留泄露窗口）
            CryptographicOperations.ZeroMemory(plainBytes);
        }
    }

    public async Task DeleteAsync(string account, CancellationToken ct = default)
    {
        var key = NormalizeAccount(account);
        await _writeLock.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var entries = await ReadEntriesAsync(ct).ConfigureAwait(false);
            entries.Remove(key); // 不存在视为成功（幂等）
            await WriteEntriesAtomicAsync(entries, ct).ConfigureAwait(false);
        }
        finally { _writeLock.Release(); }
    }

    /// <summary>读取全部条目；文件不存在 → 空字典（不抛）。</summary>
    private async Task<Dictionary<string, string>> ReadEntriesAsync(CancellationToken ct)
    {
        if (!File.Exists(_filePath))
            return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        await using var stream = new FileStream(_filePath, FileMode.Open, FileAccess.Read, FileShare.Read,
                                                bufferSize: 4096, FileOptions.Asynchronous);
        var dict = await JsonSerializer.DeserializeAsync<Dictionary<string, string>>(stream, cancellationToken: ct)
                       .ConfigureAwait(false)
                   ?? new Dictionary<string, string>();
        // 反序列化后的字典比较器不保证大小写不敏感；统一重建
        return new Dictionary<string, string>(dict, StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>原子写入：临时文件 + Move（崩溃不产生半截凭据文件）。</summary>
    private async Task WriteEntriesAtomicAsync(Dictionary<string, string> entries, CancellationToken ct)
    {
        var dir = Path.GetDirectoryName(_filePath);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);

        var temp = _filePath + ".tmp";
        await using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None,
                                                 bufferSize: 4096, FileOptions.Asynchronous))
        {
            await JsonSerializer.SerializeAsync(stream, entries, cancellationToken: ct).ConfigureAwait(false);
            await stream.FlushAsync(ct).ConfigureAwait(false);
        }
        File.Move(temp, _filePath, overwrite: true);
    }

    /// <summary>释放单写者锁资源。</summary>
    public void Dispose() => _writeLock.Dispose();

    private static string NormalizeAccount(string account)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(account);
        return account.Trim();
    }
}

/// <summary>凭据存储异常（C2：消息不含账号/密码明文）。</summary>
public sealed class CredentialStoreException : Exception
{
    public CredentialStoreException(string message) : base(message) { }
    public CredentialStoreException(string message, Exception inner) : base(message, inner) { }
}
