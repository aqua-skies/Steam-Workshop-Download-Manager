using System.IO;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Swdm2.Core.Options;

namespace Swdm2.App.Configuration;

/// <summary>
/// D1.3 配置与选项骨架：
/// 1. 从 exe 同级 appsettings.json 加载默认配置（reloadOnChange=true 文件变更即重绑定）；
/// 2. 若 Root 下存在运行时配置（IPathService.ConfigFile，D5.8 设置页写入）则叠加覆盖；
/// 3. 绑定强类型选项（SteamOptions/DownloadOptions/PathOptions），订阅方经 IOptionsMonitor 热更新。
/// C7：所有数值为 ⚠️[参数待重标定] 起点，终值由 D2.6/D4.8 实测锁定。
/// </summary>
public static class SwdmConfiguration
{
    /// <summary>
    /// 加载配置：appsettings.json（exe 同级）+ 可选运行时覆盖（runtimeConfigPath 存在时叠加）。
    /// </summary>
    public static IConfigurationRoot LoadConfiguration(string? runtimeConfigPath = null)
    {
        var builder = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true);

        if (!string.IsNullOrEmpty(runtimeConfigPath) && File.Exists(runtimeConfigPath))
            builder.AddJsonFile(runtimeConfigPath, optional: true, reloadOnChange: true);

        return builder.Build();
    }

    /// <summary>把三个选项节绑定到 DI（订阅方注入 IOptionsMonitor&lt;T&gt; 即获热更新）。</summary>
    public static IServiceCollection ConfigureSwdmOptions(this IServiceCollection services, IConfiguration config)
    {
        services.Configure<SteamOptions>(config.GetSection("Steam"));
        services.Configure<DownloadOptions>(config.GetSection("Download"));
        services.Configure<PathOptions>(config.GetSection("Path"));
        return services;
    }
}
