using Swdm2.Core.Domain;

namespace Swdm2.App.Library;

/// <summary>
/// 本地库扫描契约（D6.1 库管理接入点；t51 D5.12 库页消费侧）。
/// D6.1（阶段 6）实现真实扫描/导入导出；t51 期间默认实现=本地目录轻扫。
/// </summary>
public interface ILibraryScanner
{
    /// <summary>扫描已安装的工坊物品条目（按游戏 AppId 分组的库目录）。</summary>
    Task<IReadOnlyList<ModLibraryEntry>> ScanAsync(CancellationToken ct = default);
}
