using System.Reflection;
using Swdm2.Core.Domain;

namespace Swdm2.Core.Tests.Domain;

/// <summary>
/// 强类型 id 单测 + C6 不变量验证（UgcId 与 PublishedFileId 编译期不可互换）。
/// </summary>
public sealed class StrongIdsTests
{
    [Fact]
    public void Ctor_Rejects_Zero()
    {
        Assert.Throws<ArgumentException>(() => new PublishedFileId(0));
        Assert.Throws<ArgumentException>(() => new UgcId(0));
        Assert.Throws<ArgumentException>(() => new AppId(0));
        Assert.Throws<ArgumentException>(() => new DownloadTaskId(Guid.Empty));
    }

    [Fact]
    public void Ctor_Accepts_Valid_Value()
    {
        var pf = new PublishedFileId(3808352517);
        Assert.Equal(3808352517UL, pf.Value);

        var ugc = new UgcId(17906);
        Assert.Equal(17906UL, ugc.Value);

        var app = new AppId(440);
        Assert.Equal(440, app.Value);
    }

    [Fact]
    public void TryParse_Accepts_Canonical_And_Rejects_Garbage()
    {
        Assert.True(PublishedFileId.TryParse("3808352517", out var pf));
        Assert.Equal(3808352517UL, pf.Value);

        Assert.False(PublishedFileId.TryParse("0", out _));
        Assert.False(PublishedFileId.TryParse("", out _));
        Assert.False(PublishedFileId.TryParse(null, out _));
        Assert.False(PublishedFileId.TryParse("abc", out _));

        Assert.True(UgcId.TryParse("17906", out var ugc));
        Assert.Equal(17906UL, ugc.Value);
        Assert.False(UgcId.TryParse("0", out _));

        Assert.True(AppId.TryParse("440", out var app));
        Assert.Equal(440, app.Value);
        Assert.False(AppId.TryParse("-1", out _));
        Assert.False(AppId.TryParse("0", out _));

        Assert.True(DownloadTaskId.TryParse(Guid.NewGuid().ToString("D"), out var taskId));
        Assert.False(DownloadTaskId.TryParse(Guid.Empty.ToString("D"), out _));
    }

    [Fact]
    public void Equality_Is_Value_Based()
    {
        Assert.Equal(new PublishedFileId(123), new PublishedFileId(123));
        Assert.True(new UgcId(123).Equals(new UgcId(123)));
        Assert.NotEqual(new AppId(1), new AppId(2));
        Assert.NotEqual<DownloadTaskId>(DownloadTaskId.New(), DownloadTaskId.New());
    }

    [Fact]
    public void With_Clone_Preserves_Or_Rejects()
    {
        var app = new AppId(440);
        Assert.Equal(441, (app with { Value = 441 }).Value);
        Assert.Throws<ArgumentException>(() => app with { Value = 0 });
    }

    [Fact]
    public void ToString_Is_InvariantCulture()
    {
        Assert.Equal("3808352517", new PublishedFileId(3808352517).ToString());
        Assert.Equal("440", new AppId(440).ToString());
    }

    /// <summary>
    /// C6：PublishedFileId 与 UgcId 是不同类型——运行期断言不存在互换通道
    /// （无派生关系、无相互转换运算符），编译期效果见下方注释中的不可编译示例。
    /// </summary>
    [Fact]
    public void C6_Id_Types_Are_Not_Interchangeable()
    {
        // 无继承互换
        Assert.False(typeof(UgcId).IsAssignableFrom(typeof(PublishedFileId)));
        Assert.False(typeof(PublishedFileId).IsAssignableFrom(typeof(UgcId)));
        Assert.False(typeof(AppId).IsAssignableFrom(typeof(PublishedFileId)));

        // 无相互转换运算符（op_Implicit/op_Explicit 在两类型间任何方向声明）
        static bool HasConversionOperator(Type from, Type to)
            => to.GetMethods(BindingFlags.Public | BindingFlags.Static)
                .Where(m => m.Name is "op_Implicit" or "op_Explicit")
                .Any(m => m.GetParameters() is { Length: 1 } p && p[0].ParameterType == from);

        Assert.False(HasConversionOperator(typeof(PublishedFileId), typeof(UgcId)));
        Assert.False(HasConversionOperator(typeof(UgcId), typeof(PublishedFileId)));
        Assert.False(HasConversionOperator(typeof(ulong), typeof(PublishedFileId))); // 仅显式 operator ulong(PublishedFileId)，反向无
    }

    // ——— 编译期不互换的证明（不可编译示例，留作契约文档） ———
    // private static void WontCompile()
    // {
    //     PublishedFileId pf = new UgcId(17906);          // CS0029: 无法隐式转换
    //     UgcId ugc = new PublishedFileId(17906);          // CS0029: 无法隐式转换
    //     void NeedsPublishedFile(PublishedFileId id) { }
    //     NeedsPublishedFile(new UgcId(17906));            // CS1503: 参数类型不匹配
    //     void NeedsUgc(UgcId id) { }
    //     NeedsUgc(new PublishedFileId(17906));            // CS1503: 参数类型不匹配
    // }
}
