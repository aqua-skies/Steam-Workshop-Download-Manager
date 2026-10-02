// SP-3 driver mode (Steam 域同款): xUnit testhost 崩溃 (SetParentProcessExitCallback Win32Exception(5)) 的替代路径。
// 内化 D1.5r 假绿教训: 特性匹配用基类/名称双判据 (TheoryAttribute 是 FactAttribute 派生但 Name 不同
// → 不能只按 Type.Name 匹配，否则 [Theory] 方法整体被静默跳过)，Theory 用 InlineData.GetData 行展开，
// task-faulted 异步的 Wait 抛 AggregateException (非 TargetInvocationException) 需显式展开。
using System.Reflection;
using Xunit;

var asm = typeof(Swdm2.Steam.Tests.Web.HttpClientFactoryTests).Assembly;
int pass = 0, fail = 0, skip = 0;
var failures = new List<string>();
var watch = System.Diagnostics.Stopwatch.StartNew();

foreach (var type in asm.GetTypes().OrderBy(t => t.FullName))
{
    foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                              .OrderBy(m => m.Name))
    {
        // 双判据: 严格 FactAttribute 实例(非派生) OR TheoryAttribute 派生链任何 [Fact]-ish 特性
        var hasTestAttr = method.CustomAttributes.Any(a =>
            typeof(FactAttribute).IsAssignableFrom(a.AttributeType));
        if (!hasTestAttr) continue;

        var inlineDatas = method.GetCustomAttributes<InlineDataAttribute>().ToArray();
        var isTheory = method.GetCustomAttribute<TheoryAttribute>() is not null;
        if (isTheory && inlineDatas.Length == 0)
        {
            Console.WriteLine($"[THEORY-DATA?] {type.FullName}.{method.Name} (MemberData/ClassData, driver skipped)");
            skip++;
            continue;
        }

        var caseArgs = new List<object?[]>();
        if (isTheory)
        {
            foreach (var a in inlineDatas)
                foreach (var d in a.GetData(method))
                    caseArgs.Add(d);
        }
        else
        {
            caseArgs.Add(Array.Empty<object?>());
        }

        foreach (var args2 in caseArgs)
        {
            var p = (object[]?)args2 ?? Array.Empty<object?>();
            var instance = Activator.CreateInstance(type);
            var name = $"{type.FullName}.{method.Name}" + (p.Length > 0 ? $"[{string.Join(",", p)}]" : "");
            try
            {
                var task = method.Invoke(instance, p) as Task;
                if (task is not null) task.GetAwaiter().GetResult();  // 直接 GetAwaiter: AggregateException 自然传播
                pass++;
            }
            catch (TargetParameterCountException)
            {
                fail++;
                failures.Add($"{name}: TargetParameterCount: params={method.GetParameters().Length} got={p.Length}");
            }
            catch (Exception ex) when (ex is TargetInvocationException or AggregateException)
            {
                fail++;
                var inner = ex is TargetInvocationException tie && tie.InnerException is not null
                    ? tie.InnerException
                    : ex;
                if (inner is AggregateException ae)
                    inner = ae.Flatten().InnerExceptions[0];
                failures.Add($"{name}: {inner?.GetType().Name}: {(inner?.Message ?? "").Split('\n')[0]}");
            }
            catch (Exception ex)
            {
                fail++;
                failures.Add($"{name}: {ex.GetType().Name}: {ex.Message.Split('\n')[0]}");
            }
        }
    }
}

watch.Stop();
Console.WriteLine($"SteamTestsDriver: pass={pass} fail={fail} skip={skip} in {watch.ElapsedMilliseconds}ms");
foreach (var f in failures) Console.WriteLine($"FAIL {f}");
