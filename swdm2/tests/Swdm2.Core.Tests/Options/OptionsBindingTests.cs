using System.ComponentModel.DataAnnotations;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.DependencyInjection;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;

namespace Swdm2.Core.Tests.Options;

/// <summary>
/// D1.3 验收：强类型绑定（JSON → Options）+ IOptionsMonitor 热更新回调触发。
/// App 实际入口在 Swdm2.App/Configuration/SwdmConfiguration（同绑定语义）。
/// </summary>
public sealed class OptionsBindingTests
{
    [Fact]
    public void Strong_Typed_Binding_From_Json()
    {
        var json = """
        {
          "Steam": {
            "Proxy": "Custom",
            "CustomProxyUrl": "http://127.0.0.1:7897",
            "ThrottleMs": [ 3000, 1500 ],
            "MaxConcurrentMetadataQueries": 4,
            "BackoffInitialMs": 2000,
            "BackoffMaxMs": 30000,
            "CircuitThreshold": 3,
            "CircuitCooldownMs": 45000
          },
          "Download": {
            "MaxConcurrentDownloads": 2,
            "MaxChunkParallelism": 16,
            "MaxSpeedBytesPerSecond": 1048576,
            "ChunkTimeoutMs": 3000,
            "OverlapBytes": 64,
            "UseSparsePlaceholder": false,
            "MaxConnectionsPerServer": 4,
            "ProgressThrottleMs": 80
          },
          "Path": {
            "ForceMode": "Portable",
            "CustomRoot": "C:\\swdm"
          }
        }
        """;
        using var temp = TempFile(json);
        var monitor = BuildMonitor(temp.Path);

        var steam = monitor.GetService<IOptionsMonitor<SteamOptions>>()!.CurrentValue;
        Assert.Equal(ProxyMode.Custom, steam.Proxy);
        Assert.Equal("http://127.0.0.1:7897", steam.CustomProxyUrl);
        Assert.Equal(new double[] { 3000, 1500 }, steam.ThrottleMs);
        Assert.Equal(4, steam.MaxConcurrentMetadataQueries);
        Assert.Equal(2000, steam.BackoffInitialMs);
        Assert.Equal(30000, steam.BackoffMaxMs);
        Assert.Equal(3, steam.CircuitThreshold);
        Assert.Equal(45000, steam.CircuitCooldownMs);

        var download = monitor.GetService<IOptionsMonitor<DownloadOptions>>()!.CurrentValue;
        Assert.Equal(2, download.MaxConcurrentDownloads);
        Assert.Equal(16, download.MaxChunkParallelism);
        Assert.Equal(1048576L, download.MaxSpeedBytesPerSecond);
        Assert.Equal(3000, download.ChunkTimeoutMs);
        Assert.Equal(64, download.OverlapBytes);
        Assert.False(download.UseSparsePlaceholder);
        Assert.Equal(4, download.MaxConnectionsPerServer);
        Assert.Equal(80, download.ProgressThrottleMs);

        var path = monitor.GetService<IOptionsMonitor<PathOptions>>()!.CurrentValue;
        Assert.Equal(PathMode.Portable, path.ForceMode);
        Assert.Equal("C:\\swdm", path.CustomRoot);
    }

    /// <summary>验收判据：文件变更 → IOptionsMonitor&lt;T&gt;.OnChange 回调触发，CurrentValue 已翻新。</summary>
    [Fact]
    public void Hot_Reload_OnChange_Fires()
    {
        var original = """{ "Steam": { "BackoffInitialMs": 5000 } }""";
        var updated = """{ "Steam": { "BackoffInitialMs": 7000, "CircuitThreshold": 9 } }""";
        using var temp = TempFile(original);
        var monitor = BuildMonitor(temp.Path);

        var steamMonitor = monitor.GetService<IOptionsMonitor<SteamOptions>>()!;
        Assert.Equal(5000, steamMonitor.CurrentValue.BackoffInitialMs);

        SteamOptions? reloaded = null;
        using var subscription = steamMonitor.OnChange(o => reloaded = o);

        File.WriteAllText(temp.Path, updated);
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (reloaded is null && DateTime.UtcNow < deadline)
            Thread.Sleep(200);

        Assert.NotNull(reloaded);
        Assert.Equal(7000, reloaded!.BackoffInitialMs);
        Assert.Equal(9, reloaded.CircuitThreshold);
        Assert.Equal(7000, steamMonitor.CurrentValue.BackoffInitialMs); // CurrentValue 已翻新
    }

    [Fact]
    public void Missing_Sections_Keep_Documented_Defaults()
    {
        using var temp = TempFile("""{ "Steam": { }, "Download": { }, "Path": { } }""");
        var monitor = BuildMonitor(temp.Path);

        var steam = monitor.GetService<IOptionsMonitor<SteamOptions>>()!.CurrentValue;
        Assert.Equal(ProxyMode.SystemProxy, steam.Proxy);
        Assert.Null(steam.CustomProxyUrl);
        // 空节=未配置（类默认空数组；起点值在 appsettings.json，避免 ConfigurationBinder 追加坑）
        Assert.Empty(steam.ThrottleMs);
        Assert.Equal(5000, steam.BackoffInitialMs);       // ⚠️[参数待重标定] 起点
        Assert.Equal(90000, steam.BackoffMaxMs);

        var download = monitor.GetService<IOptionsMonitor<DownloadOptions>>()!.CurrentValue;
        Assert.Equal(1, download.MaxConcurrentDownloads); // 1.x=1，待 B3 重标定
        Assert.Equal(8, download.MaxChunkParallelism);
        Assert.True(download.UseSparsePlaceholder);

        var path = monitor.GetService<IOptionsMonitor<PathOptions>>()!.CurrentValue;
        Assert.Null(path.ForceMode);                      // null=自动检测（D1.2 语义）
        Assert.Null(path.CustomRoot);
    }

    /// <summary>C7 落地方式：超界配置被 DataAnnotations 拒绝（启动期可暴露坏配置而非静默生效）。</summary>
    [Fact]
    public void Out_Of_Range_Values_Fail_Validation()
    {
        var bad = new DownloadOptions { MaxChunkParallelism = 0, ChunkTimeoutMs = 5, ProgressThrottleMs = 5000 };
        var context = new ValidationContext(bad);
        var results = new List<ValidationResult>();
        Assert.False(Validator.TryValidateObject(bad, context, results, validateAllProperties: true));
        Assert.Contains(results, r => r.MemberNames.Contains(nameof(DownloadOptions.MaxChunkParallelism)));
        Assert.Contains(results, r => r.MemberNames.Contains(nameof(DownloadOptions.ChunkTimeoutMs)));
        Assert.Contains(results, r => r.MemberNames.Contains(nameof(DownloadOptions.ProgressThrottleMs)));

        var good = new DownloadOptions();
        Assert.True(Validator.TryValidateObject(good, new ValidationContext(good), new List<ValidationResult>(), true));
    }

    private static IServiceProvider BuildMonitor(string jsonPath)
    {
        var config = new ConfigurationBuilder()
            .AddJsonFile(jsonPath, optional: false, reloadOnChange: true)
            .Build();
        var services = new ServiceCollection();
        services.AddOptions();
        services.Configure<SteamOptions>(config.GetSection("Steam"));
        services.Configure<DownloadOptions>(config.GetSection("Download"));
        services.Configure<PathOptions>(config.GetSection("Path"));
        return services.BuildServiceProvider();
    }

    private static TempFileScope TempFile(string content)
    {
        var path = Path.Combine(Path.GetTempPath(), "swdm2_d13_" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".json");
        File.WriteAllText(path, content);
        return new TempFileScope(path);
    }

    private sealed class TempFileScope : IDisposable
    {
        public string Path { get; }
        public TempFileScope(string path) => Path = path;
        public void Dispose()
        {
            try { File.Delete(Path); } catch { }
        }
    }
}
