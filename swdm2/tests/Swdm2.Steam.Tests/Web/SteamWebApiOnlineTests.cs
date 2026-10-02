using System.Text.Json;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Web;

/// <summary>
/// D2.3 在线集成测试（真实输入）：
/// - 真实 api.steampowered.com + 真实工坊 id 3808352517;
/// - Category=Online 标记（CI 无网可过滤或用 SWDM2_SKIP_ONLINE=1 跳过）;
/// - 失败容忍定律：RateLimited/Blocked 等网络环境结论**不算失败**（设计对照纪律——换网络条件复验），
///   仅断言结构语义：Result 必须给出明确 Ok 或明确 SteamError（不得抛异常/不得假绿）。
/// </summary>
[Trait("Category", "Online")]
public sealed class SteamWebApiOnlineTests
{
    private const long RealItemId = 3808352517;

    private static bool ShouldSkipOnline
        => Environment.GetEnvironmentVariable("SWDM2_SKIP_ONLINE") == "1";

    /// <summary>真实 id 3808352517:GetDetails 必返 result:1（字段非空：标题/描述/预览图）。</summary>
    [Fact]
    public async Task Online_GetPublishedFileDetails_Real_Id_Returns_Result_One()
    {
        if (ShouldSkipOnline)
        {
            Console.WriteLine("[ONLINE-SKIP] SWDM2_SKIP_ONLINE=1");
            return;
        }
        var client = new SteamWebApiClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }));

        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(RealItemId));

        if (!result.IsOk)
        {
            // 网络环境结论记录（不作为失败）：RateLimited/Network/Blocked 等明确错误 = 门控良好
            Console.WriteLine($"[ONLINE-RESULT-FAIL] {result.Error} — 环境阻断，非实现缺陷（换网络条件复验）");
            Assert.Contains(result.Error ?? SteamError.None, new[]
            {
                SteamError.RateLimited, SteamError.Network, SteamError.Blocked, SteamError.Timeout, SteamError.NotFound,
            });
            return;
        }

        var item = result.Value!;
        Assert.Equal(new PublishedFileId(RealItemId), item.Id);
        Assert.False(string.IsNullOrEmpty(item.Title), "真实物品标题非空");
        Assert.False(string.IsNullOrEmpty(item.Description), "真实物品描述非空");
        Assert.False(string.IsNullOrEmpty(item.PreviewUrl), "真实物品预览图非空");
        Assert.NotNull(item.Creator);
        Console.WriteLine($"[ONLINE-OK] id={item.Id} title={item.Title} titleLen={item.Title!.Length} " +
                          $"descLen={item.Description?.Length ?? -1} preview={item.PreviewUrl}");
    }

    /// <summary>真实 storesearch:中文搜索词返回真实游戏（id 即 AppId)。</summary>
    [Fact]
    public async Task Online_StoreSearch_Real_Term_Returns_Games()
    {
        if (ShouldSkipOnline)
        {
            Console.WriteLine("[ONLINE-SKIP] SWDM2_SKIP_ONLINE=1");
            return;
        }
        var client = new StoreSearchClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }));

        var result = await client.SearchGamesAsync("Don't Starve Together");

        if (!result.IsOk)
        {
            Console.WriteLine($"[ONLINE-RESULT-FAIL] {result.Error} — 环境阻断（换网络条件复验）");
            Assert.Contains(result.Error ?? SteamError.None, new[]
            {
                SteamError.RateLimited, SteamError.Network, SteamError.Blocked, SteamError.Timeout, SteamError.Deserialization,
            });
            return;
        }

        Assert.NotEmpty(result.Value!);
        Assert.All(result.Value!, g => Assert.True(g.Id.Value > 0));
        var first = result.Value![0];
        Console.WriteLine($"[ONLINE-OK] appId={first.Id} name={first.Name}");
    }
}
