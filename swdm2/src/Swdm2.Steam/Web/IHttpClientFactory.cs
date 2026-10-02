using Swdm2.Core.Options;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Web;

/// <summary>
/// Steam HTTP 客户端工厂契约（D2.1）。
/// 结果语义：配置错误（如 Custom 代理 URL 缺失/非法）返回 <see cref="SteamError.InvalidConfiguration"/>，
/// 成功返回带**指纹头四件套默认值**的 HttpClient（处理器由 ProxyMode 三态注入 SocketsHttpHandler）。
/// </summary>
public interface IHttpClientFactory
{
    /// <summary>
    /// 创建客户端：DefaultRequestHeaders 装配指纹头四件套（见 <see cref="SteamHttpHeaders"/>），
    ///处理器按当前 SteamOptions 的 ProxyMode/MaxConnectionsPerServer 构建。
    /// </summary>
    Result<HttpClient, SteamError> CreateClient();
}
