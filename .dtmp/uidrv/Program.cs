using System; using System.Collections.Generic; using System.Linq; using System.Reflection; using System.Threading.Tasks; using Xunit;
var asm = typeof(Swdm2.UiTests.Tests.Smoke.AppLaunchSmokeTests).Assembly;
int pass=0, fail=0;
foreach (var t in asm.GetTypes().OrderBy(x=>x.FullName)) {
  var ms = t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)
            .Where(m => m.GetCustomAttributes(true).Any(a => a.GetType().Name is "FactAttribute" or "WpfFactAttribute"));
  foreach (var m in ms) {
    var inst = Activator.CreateInstance(t);
    try { var r = m.Invoke(inst, null); if (r is Task t2) t2.Wait(); Console.WriteLine("PASS " + t.Name + "." + m.Name); pass++; }
    catch (TargetInvocationException ex) { var inner = ex.InnerException is TargetInvocationException tie ? tie.InnerException : ex.InnerException; while (inner is AggregateException ae) inner = ae.Flatten().InnerExceptions[0]; Console.WriteLine("FAIL " + t.Name + "." + m.Name + ": " + inner?.GetType().Name + ": " + (inner?.Message??"").Split([Environment.NewLine], StringSplitOptions.None)[0]); fail++; }
    catch (AggregateException ex) { var inner = ex.Flatten().InnerExceptions[0]; Console.WriteLine("FAIL " + t.Name + "." + m.Name + ": " + inner?.GetType().Name); fail++; }
  }
}
Console.WriteLine("UiTestsDriver: pass=" + pass + " fail=" + fail);
return fail==0?0:1;
