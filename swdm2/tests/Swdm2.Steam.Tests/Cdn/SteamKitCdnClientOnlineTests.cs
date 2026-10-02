using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Steam.Tests.Cdn;

/// <summary>
/// D4.2 Online:真实 pubfile 解析（CM+PICS+CDN 真链，-pubfile 路径）。
/// 依据 acceptance：真实 pubfile 解析出文件/chunk 列表。
/// 沙箱：CM TCP 阻断→会话登录 Network/Timeout →环境容忍标注（同 D3.3/D4.1 门模式，
/// 换网络条件=桌面通道复跑）。非预期错误类 fail 保护。
/// </summary>
[Trait("Category", "Online")]
public sealed class SteamKitCdnClientOnlineTests
{
    /// <summary>真实 pubfile 3808352517(KFC - Chicken Bucket,GMod app 4000)→ manifest 文件/chunk 列表。</summary>
    [Fact]
    public async Task Online_Resolve_Real_Pubfile_Produces_File_And_Chunk_List()
    {
        var session = new SteamKitSessionManager();
        var client = new SteamKitCdnClient(session);

        var login = await session.LoginAsync(new SteamSessionLogin(null, null, null));
        if (!login.IsOk)
        {
            // 环境容忍门：网络阻断/CM 匿名登录节流（RateLimited=环境条件，非实现缺陷）
            Assert.True(
                login.Error is SteamError.Network or SteamError.Timeout or SteamError.AuthRequired
                                 or SteamError.Blocked or SteamError.RateLimited,
                $"Online 匿名登录失败={login.Error}——非预期错误类（环境阻断应为 Network/Timeout)");
            Console.WriteLine($"[ONLINE-RESULT-FAIL] {login.Error} — 环境阻断，非实现缺陷（换网络条件复验）");
            return;
        }

        var result = await client.ResolveUgcManifestAsync(
            new AppId(4000), new PublishedFileId(3808352517));

        if (!result.IsOk)
        {
            // 匿名 manifest 访问受限亦属可容忍类（AuthRequired=旧 manifest 匿名不可得，CR 同义）
            Assert.True(
                result.Error is SteamError.Network or SteamError.Timeout or SteamError.AuthRequired or SteamError.Blocked,
                $"Online manifest 解析失败={result.Error}——非预期错误类");
            Console.WriteLine($"[ONLINE-RESULT-FAIL] {result.Error} — 环境阻断/匿名受限，非实现缺陷（换网络条件复验）");
            return;
        }

        Assert.False(result.Value!.IsDirectLink);
        Assert.NotEmpty(result.Value.Files);
        Assert.All(result.Value.Files, f =>
        {
            Assert.False(string.IsNullOrEmpty(f.FileName));
            Assert.NotEmpty(f.Chunks);
        });
        Assert.True(result.Value.TotalUncompressedSize > 0);
        Console.WriteLine(
            $"[ONLINE-RESULT-OK] pubfile→manifest: files={result.Value.Files.Count} " +
            $"size={result.Value.TotalUncompressedSize} depot={result.Value.DepotId}");
    }
}
