using System.IO;

namespace Swdm2.Spike.FlaUiTests;

/// <summary>
/// spike 控制台驱动：本机 harness 沙箱下 xUnit testhost 的 SetParentProcessExitCallback
/// 被 Win32Exception(5) 拒绝（跨进程句柄禁令），故用 `dotnet run` 直接执行同一批
/// [WpfFact] 方法（反射逐个调用 + 捕获 XunitException），真实输入链路完全相同。
/// 产品期回归仍在普通交互桌面用 `dotnet test` 走 xUnit 运行器（见 architecture 补丁 §SP-3）。
/// </summary>
public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        // UseWPF=true 使 Exe 为 Windows 子系统（无控制台）→ 输出落盘到 spike_result.md
        var logPath = Path.Combine(AppContext.BaseDirectory, "spike_result.md");
        var log = new List<string>();
        void L(string line) { log.Add(line); try { Console.WriteLine(line); } catch { } }

        L("# SWDM 2.0 spike 冒烟结果（WPF-UI 4.3.0 + FlaUI 5.0.0）");
        L($"- 时间：{DateTime.Now:yyyy-MM-dd HH:mm:ss}");
        L($"- 被测进程：进程外 Application.Launch + 真实鼠标/键盘注入（无打桩）");

        var results = new List<(string name, bool ok, string detail)>();
        SpikeSmokeTests? harness = null;
        try
        {
            harness = new SpikeSmokeTests();   // 进程外启动被测 exe + 定位主窗口
            L("- 启动被测进程 + 定位主窗口（AutomationId=MainWindow）：OK");
        }
        catch (Exception ex)
        {
            L($"- [FAIL] 启动/定位主窗口失败: {ex.GetType().Name}: {ex.Message}");
            await File.WriteAllLinesAsync(logPath, log);
            return 2;
        }

        var methods = typeof(SpikeSmokeTests)
            .GetMethods()
            .Where(m => m.GetCustomAttributes(typeof(FactAttribute), true).Length > 0
                        || m.GetCustomAttributes(true).Any(a => a.GetType().Name.EndsWith("FactAttribute")))
            .ToList();

        foreach (var m in methods)
        {
            try
            {
                m.Invoke(harness, null);
                results.Add((m.Name, true, ""));
                L($"- [PASS] {m.Name}");
            }
            catch (Exception ex)
            {
                var inner = ex is System.Reflection.TargetInvocationException tie ? tie.InnerException! : ex;
                var msg = inner is Xunit.Sdk.XunitException xe ? xe.Message : $"{inner.GetType().Name}: {inner.Message}";
                results.Add((m.Name, false, msg));
                L($"- [FAIL] {m.Name} :: {msg.Split('\n')[0]}");
            }
        }

        try { harness.Dispose(); } catch { }

        L("## 汇总");
        var passed = results.Count(r => r.ok);
        foreach (var r in results)
        {
            L($"  {(r.ok ? "PASS" : "FAIL")}  {r.name}");
        }
        L($"共 {results.Count} 项：{passed} 通过 / {results.Count - passed} 失败");
        await File.WriteAllLinesAsync(logPath, log);
        return passed == results.Count ? 0 : 1;
    }
}
