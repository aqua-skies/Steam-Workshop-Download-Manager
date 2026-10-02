using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// provider 失败异常（D4.4 链路由判据载体）:
/// 携带 <see cref="SteamError"/> 错误码，<see cref="DownloadProviderRouter"/> 按类型决定回退/直切/失败。
/// </summary>
public sealed class DownloadProviderException : Exception
{
    /// <summary>失败错误码（路由表输入）。</summary>
    public SteamError Error { get; }

    public DownloadProviderException(SteamError error, string message)
        : base(message)
    {
        Error = error;
    }

    public DownloadProviderException(SteamError error, string message, Exception inner)
        : base(message, inner)
    {
        Error = error;
    }
}

/// <summary>provider 暴露最近一次失败原因（router 读以做错误类型路由）。</summary>
public interface IReportLastError
{
    /// <summary>最近一次 ExecuteAsync 失败原因（成功执行后置 null)。</summary>
    Exception? LastError { get; }
}
