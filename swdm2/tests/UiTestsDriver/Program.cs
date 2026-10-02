// SP-3 driver mode (UiTests edition): 本机 harness 沙箱内 `dotnet test` 的 testhost
// 启动即崩（SetParentProcessExitCallback → Win32Exception(5)，跨进程句柄拒绝），
// 故用 `dotnet run` 以 STA 线程反射执行 Swdm2.UiTests 的同一批 [WpfFact] 方法。
// 特性匹配走纯反射（名称后缀 + 基类全名 "Xunit.FactAttribute" 双判据）——为防御性匹配派生特性
// （UiTests 契约只应有 [WpfFact]，见 t3 v1.3；驱动多匹配不破坏该契约，且为将来 [Theory] 预留展开）：
// ①不编译期引用 xunit 类型——xunit.core 2.9.0 与（StaFact 2.1.7 拉入的）xunit.v3.core
// 对 FactAttribute/InlineDataAttribute 存在 CS0433 二义（D0.2 已知）；
// ②避免"按 Type.Name 精确匹配"漏掉派生特性的 D1.5r 假绿教训复现（IsAssignableFrom 派生链全覆盖）。
// 未设 SynchronizationContext（显式 null）：UIA3 COM 在 STA 线程执行，测试内 sync-over-async
// （Retry.WhileNull(...).Result）后续体落到 ThreadPool，避免 STA 重入死锁。
// 失败钩子（Q10 契约）：catch 分支 Capture.MainScreen().ToFile(TestArtifacts/fail_<类>_<方法>.png)
// + 套件启动前 Kill 残留 Swdm2.App 进程（t3 §2.5 fixture 的驱动级加固，套件扩大后更必要）。
// Watch 项（D5 前扩）：需要 Dispatcher 回 UI 线程的 [WpfFact] 测试在现驱动下会失败（未设 WPF 上下文）；
// 当前测试均为 FlaUI 同步调用不受影响，D5 UI 测试增多后须扩展 STA/WPF 帧泵。
// 产出回归仍在普通交互桌面用 `dotnet test`（架构 SP-3）；沙箱内临时回归用本驱动。
using System.Diagnostics;
using System.Reflection;
using System.Threading;
using FlaUI.Core.Capturing;

var asm = typeof(Swdm2.UiTests.Tests.Smoke.AppLaunchSmokeTests).Assembly;
int pass = 0, fail = 0, skip = 0;
var failures = new List<string>();
var watch = Stopwatch.StartNew();

// Q10 驱动级加固：套件启动前清理残留被测进程（单实例互斥 + 真实输入串行的前置）
foreach (var residual in Process.GetProcessesByName("Swdm2.App"))
{
    try { residual.Kill(); Console.WriteLine($"[CLEAN] 残留 Swdm2.App(pid={residual.Id}) 已 Kill"); }
    catch (Exception ex) { Console.WriteLine($"[CLEAN-SKIP] {ex.GetType().Name}: {ex.Message}"); }
}

// 失败截图落盘目录：<swdm2>/TestArtifacts（与 t3 §2.7 失败证据工件约定同目录族）
var artifactsDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "TestArtifacts"));
Directory.CreateDirectory(artifactsDir);
string Sanitize(string s) => string.Concat(s.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
void CaptureFailure(string testName)
{
    try
    {
        var shot = Capture.MainScreen();
        var path = Path.Combine(artifactsDir, $"fail_{Sanitize(testName)}_{DateTime.Now:yyyyMMdd_HHmmss}.png");
        shot.ToFile(path);
        Console.WriteLine($"[FAIL-SHOT] {path}");
    }
    catch (Exception ex) { Console.WriteLine($"[FAIL-SHOT-SKIP] {ex.GetType().Name}: {ex.Message}"); }
}


Exception? staError = null;
var sta = new Thread(() =>
{
    try
    {
        foreach (var type in asm.GetTypes().OrderBy(t => t.FullName))
        {
            foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                                       .OrderBy(m => m.Name))
            {
                if (!IsTestAttribute(method, out var isTheory))
                    continue;

                var rows = GetInlineDataRows(method);
                if (isTheory && rows.Count == 0)
                {
                    Console.WriteLine($"[THEORY-DATA?] {type.FullName}.{method.Name} (MemberData/ClassData, driver skipped)");
                    skip++;
                    continue;
                }

                if (rows.Count == 0)
                    rows.Add(Array.Empty<object?>());

                foreach (var args2 in rows)
                {
                    var p = (object[]?)args2 ?? Array.Empty<object?>();
                    var instance = Activator.CreateInstance(type);
                    var name = $"{type.FullName}.{method.Name}" + (p.Length > 0 ? $"[{string.Join(",", p)}]" : "");
                    try
                    {
                        SynchronizationContext.SetSynchronizationContext(null);
                        var task = method.Invoke(instance, p) as Task;
                        if (task is not null) task.GetAwaiter().GetResult();
                        pass++;
                        Console.WriteLine($"[PASS] {name}");
                    }
                    catch (TargetParameterCountException)
                    {
                        fail++;
                        CaptureFailure(name);
                        var pc = method.GetParameters().Length;
                        failures.Add($"{name}: TargetParameterCount: params={pc} got={p.Length} data=[{string.Join(",", p.Select(o => o?.ToString() ?? "null"))}]");
                    }
                    catch (TargetInvocationException tie) when (tie.InnerException is not null)
                    {
                        fail++;
                        CaptureFailure(name);
                        failures.Add($"{name}: {tie.InnerException.GetType().Name}: {tie.InnerException.Message}");
                    }
                    catch (Exception ex)
                    {
                        fail++;
                        CaptureFailure(name);
                        failures.Add($"{name}: {ex.GetType().Name}: {ex.Message}");
                    }
                }
            }
        }
    }
    catch (Exception ex)
    {
        staError = ex;
    }
});
sta.SetApartmentState(ApartmentState.STA);
sta.Start();
sta.Join();

watch.Stop();
if (staError is not null)
{
    Console.WriteLine($"UiTestsDriver: DRIVER-LEVEL FAILURE: {staError.GetType().Name}: {staError.Message}");
    return 3;
}
Console.WriteLine($"UiTestsDriver: pass={pass} fail={fail} skip={skip} in {watch.ElapsedMilliseconds}ms");
foreach (var f in failures) Console.WriteLine($"FAIL {f}");
return fail == 0 ? 0 : 1;

// 双判据：特性类型基链含 "Xunit.FactAttribute"（v2/v3 均适用），或名称以 FactAttribute/TheoryAttribute 结尾。
static bool IsTestAttribute(MethodInfo m, out bool isTheory)
{
    isTheory = false;
    foreach (var attr in m.GetCustomAttributes(true))
    {
        var t = attr.GetType();
        if (InheritsFromNamed(t, "Xunit.FactAttribute") || t.Name.EndsWith("FactAttribute") || t.Name.EndsWith("TheoryAttribute"))
        {
            if (t.Name.Contains("Theory")) isTheory = true;
            return true;
        }
    }
    return false;
}

static bool InheritsFromNamed(Type t, string fullName)
{
    for (var b = t; b is not null; b = b.BaseType)
        if (b.FullName == fullName) return true;
    return false;
}

// InlineData 行展开（纯反射 GetData(MethodInfo)，兼容 xunit v2/v3 的 InlineDataAttribute）。
static List<object?[]> GetInlineDataRows(MethodInfo method)
{
    var rows = new List<object?[]>();
    foreach (var attr in method.GetCustomAttributes(true))
    {
        var getData = attr.GetType().GetMethod("GetData", new[] { typeof(MethodInfo) });
        if (getData is null) continue;
        try
        {
            var result = getData.Invoke(attr, new object?[] { method }) as System.Collections.IEnumerable;
            if (result is null) continue;
            foreach (var row in result)
            {
                if (row is object?[] arr) rows.Add(arr);
                else if (row is object[] arr2) rows.Add(arr2.Cast<object?>().ToArray());
            }
        }
        catch
        {
            // InlineData.GetData 反射失败（理论数据异常）：留空，由调用处按"无数据 Theory"跳过并显式计数
        }
    }
    return rows;
}
