using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Core.Tests.Results;

/// <summary>
/// 结果模型单测：Ok/Fail 语义、双分支匹配、映射/绑定、相等性。
/// Contract：Result&lt;T,TErr&gt; where TErr : struct, Enum。
/// </summary>
public sealed class ResultTests
{
    [Fact]
    public void Ok_Carries_Value_And_No_Error()
    {
        var result = Result<WorkshopItem, SteamError>.Ok(MakeItem());
        Assert.True(result.IsOk);
        Assert.NotNull(result.Value);
        Assert.Null(result.Error);
    }

    [Fact]
    public void Fail_Carries_Error_And_Default_Value()
    {
        var result = Result<WorkshopItem, SteamError>.Fail(SteamError.RateLimited);
        Assert.False(result.IsOk);
        Assert.Equal(SteamError.RateLimited, result.Error);
        Assert.Null(result.Value); // 引用类型：null
    }

    [Fact]
    public void Fail_With_Value_Type_Has_Default_Value()
    {
        var result = Result<int, DownloadError>.Fail(DownloadError.DiskSpace);
        Assert.False(result.IsOk);
        Assert.Equal(DownloadError.DiskSpace, result.Error);
        Assert.Equal(0, result.Value); // 结构体 default：先判 IsOk 才读 Value
    }

    [Fact]
    public void Deconstruct_Forces_Both_Branches()
    {
        var (isOk, value, error) = Result<string, SteamError>.Ok("ok");
        Assert.True(isOk);
        Assert.Equal("ok", value);
        Assert.Null(error);

        (isOk, value, error) = Result<string, SteamError>.Fail(SteamError.Network);
        Assert.False(isOk);
        Assert.Equal(SteamError.Network, error);
    }

    [Fact]
    public void Match_Executes_Correct_Branch()
    {
        var ok = Result<int, SteamError>.Ok(42);
        Assert.Equal("42", ok.Match(v => v.ToString(), e => "ERR:" + e));

        var err = Result<int, SteamError>.Fail(SteamError.Timeout);
        Assert.Equal("ERR:Timeout", err.Match(v => v.ToString(), e => "ERR:" + e));

        // 执行式重载只命中一个分支
        var hit = string.Empty;
        err.Match(v => hit = "ok", e => hit = "err");
        Assert.Equal("err", hit);
    }

    [Fact]
    public void Map_Transforms_Value_And_Propagates_Error()
    {
        var ok = Result<PublishedFileId, SteamError>.Ok(new PublishedFileId(7));
        var mapped = ok.Map(id => id.Value);
        Assert.True(mapped.IsOk);
        Assert.Equal(7UL, mapped.Value);

        var err = Result<PublishedFileId, SteamError>.Fail(SteamError.Blocked);
        var mappedErr = err.Map(id => id.Value);
        Assert.False(mappedErr.IsOk);
        Assert.Equal(SteamError.Blocked, mappedErr.Error);
    }

    [Fact]
    public void Bind_Composes_And_Short_Circuits()
    {
        var ok = Result<PublishedFileId, SteamError>.Ok(new PublishedFileId(7));
        var composed = ok.Bind(id => Result<string, SteamError>.Ok(id.ToString()));
        Assert.True(composed.IsOk);
        Assert.Equal("7", composed.Value);

        var err = Result<PublishedFileId, SteamError>.Fail(SteamError.RateLimited);
        var composedErr = err.Bind(id => Result<string, SteamError>.Ok(id.ToString()));
        Assert.False(composedErr.IsOk);
        Assert.Equal(SteamError.RateLimited, composedErr.Error);
    }

    [Fact]
    public void MapError_Translates_Codes()
    {
        var err = Result<string, SteamError>.Fail(SteamError.AuthRequired);
        var translated = err.MapError(e => e == SteamError.AuthRequired ? DownloadError.None /*示例：跨域翻译*/ : DownloadError.ProviderFailed);
        Assert.False(translated.IsOk);
        Assert.Equal(DownloadError.None, translated.Error);
    }

    [Fact]
    public void Equality_Is_Field_Based()
    {
        Assert.Equal(Result<int, SteamError>.Ok(1), Result<int, SteamError>.Ok(1));
        Assert.True(Result<int, SteamError>.Ok(1) == Result<int, SteamError>.Ok(1));
        Assert.True(Result<int, SteamError>.Ok(1) != Result<int, SteamError>.Fail(SteamError.None));
        Assert.True(Result<int, SteamError>.Fail(SteamError.Network) != Result<int, SteamError>.Fail(SteamError.Timeout));
        Assert.Equal(Result<int, SteamError>.Fail(SteamError.Network), Result<int, SteamError>.Fail(SteamError.Network));
    }

    [Fact]
    public void GetValueOrThrow_Fails_Loudly_On_Error()
    {
        var err = Result<WorkshopItem, SteamError>.Fail(SteamError.RateLimited);
        var ex = Assert.Throws<InvalidOperationException>(() => err.GetValueOrThrow());
        Assert.Contains("RateLimited", ex.Message);
    }

    [Fact]
    public void Error_Enums_Have_Contract_Members()
    {
        // SteamError 契约成员（S2.4 熔断独立码等）
        Assert.True(Enum.IsDefined(SteamError.RateLimited));
        Assert.True(Enum.IsDefined(SteamError.CircuitOpen));
        Assert.True(Enum.IsDefined(SteamError.AuthRequired));
        Assert.True(Enum.IsDefined(SteamError.Blocked));
        Array.ForEach((SteamError[])Enum.GetValues(typeof(SteamError)),
            e => Assert.True(Enum.IsDefined(e)));

        // DownloadError 契约成员
        Assert.True(Enum.IsDefined(DownloadError.InvalidChecksum));
        Assert.True(Enum.IsDefined(DownloadError.RangeNotSupported));
        Assert.True(Enum.IsDefined(DownloadError.ProviderFailed));
    }

    private static WorkshopItem MakeItem() =>
        new(new PublishedFileId(100), new AppId(440), "标题");
}
