// SP-3 driver mode: sandbox testhost crashes (SetParentProcessExitCallback Win32Exception(5)),
// so we reflect over the same [Fact]/[Theory] methods in Swdm2.Core.Tests and run them in-process.
using System.Reflection;
using Xunit;

var asm = typeof(Swdm2.Core.Tests.Domain.StrongIdsTests).Assembly;
int pass = 0, fail = 0, skip = 0;
var failures = new List<string>();
var watch = System.Diagnostics.Stopwatch.StartNew();

foreach (var type in asm.GetTypes().OrderBy(t => t.FullName))
{
    foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                              .OrderBy(m => m.Name))
    {
        var fact = method.GetCustomAttribute<FactAttribute>();
        var theory = method.GetCustomAttribute<TheoryAttribute>();
        if (fact is null && theory is null) continue;

        // (Skip handling omitted: no [Skip] used in Core.Tests today.)

        var inlineDatas = method.GetCustomAttributes<InlineDataAttribute>().ToArray();
        if (theory is not null && inlineDatas.Length == 0)
        {
            Console.WriteLine($"[THEORY-DATA?] {type.FullName}.{method.Name} (MemberData/ClassData, driver skipped)");
            skip++;
            continue;
        }

        var caseArgs = new List<object?[]>();
        if (theory is not null)
        {
            foreach (var a in inlineDatas)
            {
                foreach (var d in a.GetData(method))
                {
                    Console.WriteLine($"[DBG] {type.Name}.{method.Name} row len={d?.Length ?? -1} null={(d is null)}");
                    caseArgs.Add(d);
                }
            }
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
                if (task is not null) task.GetAwaiter().GetResult();
                pass++;
            }
            catch (TargetParameterCountException tpc)
            {
                fail++;
                var pc = method.GetParameters().Length;
                failures.Add($"{name}: TargetParameterCount: params={pc} got={p.Length} data=[{string.Join(",", p.Select(o => o?.ToString()??"null"))}]");
            }
            catch (TargetInvocationException tie) when (tie.InnerException is not null)
            {
                fail++;
                failures.Add($"{name}: {tie.InnerException.GetType().Name}: {tie.InnerException.Message}");
            }
            catch (Exception ex)
            {
                fail++;
                failures.Add($"{name}: {ex.GetType().Name}: {ex.Message}");
            }
        }
    }
}

watch.Stop();
Console.WriteLine($"CoreTestsDriver: pass={pass} fail={fail} skip={skip} in {watch.ElapsedMilliseconds}ms");
foreach (var f in failures) Console.WriteLine($"FAIL {f}");
return fail == 0 ? 0 : 1;
