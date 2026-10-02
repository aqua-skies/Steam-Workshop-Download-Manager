using System.Text;
using Swdm2.Core.Credentials;
using Swdm2.Core.Paths;

namespace Swdm2.Core.Tests.Credentials;

/// <summary>
/// D1.4 DPAPI 凭据存储验收。C2 三连：明文不落盘 / 明文不进异常 / 明文不残留（ZeroMemory 对象级断言用文件级替代）。
/// "日志不含明文"的联合断言（脱敏 sink）在 D1.5 落地——本任务覆盖前两条 + 全部 CRUD 分支。
/// </summary>
public sealed class DpapiCredentialStoreTests
{
    private const string Secret = "P@ssw0rd-饥荒-Don't";

    [Fact]
    public async Task Set_Get_RoundTrip_Returns_Plaintext()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            await store.SetPasswordAsync("user@example.com", Secret.AsMemory());
            var got = await store.GetPasswordAsync("user@example.com");
            Assert.NotNull(got);
            Assert.Equal(Secret, got!.Value.ToString());
        }
        finally { Cleanup(tempDir); }
    }

    /// <summary>验收判据：不存在分支——返回 null，不抛异常。</summary>
    [Fact]
    public async Task Get_Missing_Account_Returns_Null()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            Assert.Null(await store.GetPasswordAsync("nobody@example.com"));

            // 文件本身不存在时也不抛
            await store.SetPasswordAsync("a@example.com", "x".AsMemory());
            Assert.NotNull(await store.GetPasswordAsync("a@example.com"));
            Assert.Null(await store.GetPasswordAsync("b@example.com"));
        }
        finally { Cleanup(tempDir); }
    }

    [Fact]
    public async Task Delete_Removes_And_Is_Idempotent()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            await store.SetPasswordAsync("user@example.com", Secret.AsMemory());
            await store.DeleteAsync("user@example.com");
            Assert.Null(await store.GetPasswordAsync("user@example.com"));

            await store.DeleteAsync("user@example.com"); // 幂等：不存在也成功
            Assert.Null(await store.GetPasswordAsync("user@example.com"));
        }
        finally { Cleanup(tempDir); }
    }

    [Fact]
    public async Task Set_Overwrites_Previous_Value()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            await store.SetPasswordAsync("user@example.com", "old".AsMemory());
            await store.SetPasswordAsync("user@example.com", "new".AsMemory());
            Assert.Equal("new", (await store.GetPasswordAsync("user@example.com"))!.Value.ToString());
        }
        finally { Cleanup(tempDir); }
    }

    /// <summary>验收判据：明文不落盘——原始文件字节中检索不到明文（UTF8/任何 ASCII 形态）。</summary>
    [Fact]
    public async Task Plaintext_Never_Reaches_Disk()
    {
        using var store = CreateInTempDir(out var tempDir, out var credFile);
        try
        {
            await store.SetPasswordAsync("user@example.com", Secret.AsMemory());
            var raw = await File.ReadAllBytesAsync(credFile);
            var needle = Encoding.UTF8.GetBytes(Secret);

            // 明文 UTF8 字节序列不出现在文件中
            Assert.False(raw.AsSpan().IndexOf(needle) >= 0, "明文字节出现在凭据文件中（C2 违反）");
            // 密文与明文字节不同（非恒同"加密"）
            Assert.NotEqual(needle, raw);
            // 账号本身（键）允许在文件中（JSON 键），但密码子串不可见
            var text = Encoding.UTF8.GetString(raw);
            Assert.DoesNotContain("P@ssw0rd", text);
        }
        finally { Cleanup(tempDir); }
    }

    /// <summary>验收判据：明文不进异常——文件损坏时异常消息与内部异常均不含明文/账号片段。</summary>
    [Fact]
    public async Task Corrupted_File_Throws_Sanitized_Exception()
    {
        using var store = CreateInTempDir(out var tempDir, out var credFile);
        try
        {
            await store.SetPasswordAsync("user@example.com", Secret.AsMemory());
            // 写入损坏数据（非 Base64 密文）
            await File.WriteAllTextAsync(credFile, """{"user@example.com":"!!!not-base64!!!"}""");

            var ex = await Assert.ThrowsAsync<CredentialStoreException>(
                async () => await store.GetPasswordAsync("user@example.com"));
            Assert.DoesNotContain(Secret, ex.Message);
            Assert.NotNull(ex.InnerException);
            Assert.DoesNotContain(Secret, ex.InnerException!.Message);
            Assert.DoesNotContain(Secret, ex.ToString());
        }
        finally { Cleanup(tempDir); }
    }

    [Fact]
    public async Task Empty_Password_Rejected()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            await Assert.ThrowsAsync<ArgumentException>(
                async () => await store.SetPasswordAsync("user@example.com", ReadOnlyMemory<char>.Empty));
        }
        finally { Cleanup(tempDir); }
    }

    [Fact]
    public async Task Multiple_Accounts_Coexist()
    {
        using var store = CreateInTempDir(out var tempDir);
        try
        {
            await store.SetPasswordAsync("a@example.com", "pa".AsMemory());
            await store.SetPasswordAsync("b@example.com", "pb".AsMemory());
            Assert.Equal("pa", (await store.GetPasswordAsync("a@example.com"))!.Value.ToString());
            Assert.Equal("pb", (await store.GetPasswordAsync("b@example.com"))!.Value.ToString());
        }
        finally { Cleanup(tempDir); }
    }

    /// <summary>路径契约延伸：CredentialsFile 在 Root 下（与 D1.2 路径服务联测）。</summary>
    [Fact]
    public void CredentialsFile_Lives_Under_Root()
    {
        var root = Path.Combine(Path.GetTempPath(), "swdm2_d14_paths_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        try
        {
            var paths = new PathService(PathMode.Portable, rootOverride: root);
            Assert.Equal(Path.Combine(root, "credentials.bin"), paths.CredentialsFile);
        }
        finally { Cleanup(root); }
    }

    private static DpapiCredentialStore CreateInTempDir(out string tempDir)
        => CreateInTempDir(out tempDir, out _);

    private static DpapiCredentialStore CreateInTempDir(out string tempDir, out string credFile)
    {
        tempDir = Path.Combine(Path.GetTempPath(), "swdm2_d14_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        credFile = Path.Combine(tempDir, "credentials.bin");
        Directory.CreateDirectory(tempDir);
        return new DpapiCredentialStore(credFile);
    }

    private static void Cleanup(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true); } catch { }
    }
}
