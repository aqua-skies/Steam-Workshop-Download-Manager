using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;

namespace Swdm2.UiTests.Tests.Smoke;

/// <summary>
/// UI test helpers (D3.7 P0 journey; t26 pattern extracted for reuse):
/// - VisibleElement: on-screen+enabled+real-rect element resolution (clickability precondition);
/// - RealClick: physical mouse input only (GetClickablePoint, fallback rect-center
///   Mouse.MoveTo + Mouse.Click) — no InvokePattern (t3 real-input hard rule);
/// - DumpTree: read-only UIA tree dump for ENV-DOWNGRADE domain audit evidence;
/// - ResolveAppExe: t3 section 2.4 SWDM2_APP_EXE override path resolution.
/// </summary>
internal static class UiTestHelpers
{
    internal static AutomationElement? VisibleElement(Window window, string automationId)
    {
        var e = window.FindFirstDescendant(cf => cf.ByAutomationId(automationId));
        return e is { IsEnabled: true, IsOffscreen: false }
               && e.BoundingRectangle.Width > 4 && e.BoundingRectangle.Height > 2
            ? e : null;
    }

    /// <summary>
    /// Real physical click (spike-verified pattern t4): GetClickablePoint when available;
    /// fallback = bounding-rect center + Mouse.MoveTo + Mouse.Click (physical down/up).
    /// No InvokePattern / no programmatic activation (t3 hard rule: real input only).
    /// </summary>
    internal static void RealClick(AutomationElement element)
    {
        System.Drawing.Point pt;
        try
        {
            pt = element.GetClickablePoint();
        }
        catch (FlaUI.Core.Exceptions.NoClickablePointException)
        {
            var r = element.BoundingRectangle;
            pt = new System.Drawing.Point(r.X + r.Width / 2, r.Y + r.Height / 2);
        }
        Mouse.MoveTo(pt);
        Mouse.Click(MouseButton.Left);
    }

    /// <summary>
    /// Real keyboard activation (t3 real-input hard rule): focus element, then physical
    /// Enter keystroke (Keyboard Press/Release = hardware-level input, spike-verified pattern).
    /// </summary>
    internal static void RealActivateByKey(AutomationElement element)
    {
        element.Focus();
        Keyboard.Press(VirtualKeyShort.RETURN);
        Keyboard.Release(VirtualKeyShort.RETURN);
    }

    // read-only UIA tree dump for domain audit (env-downgrade evidence).
    internal static void DumpTree(Window window, string reason)
    {
        Console.WriteLine($"DIAG tree dump ({reason}):");
        foreach (var e in window.FindAllDescendants())
        {
            try
            {
                if (!string.IsNullOrEmpty(e.AutomationId))
                    Console.WriteLine($"DIAG id={e.AutomationId}");
            }
            catch { /* property unsupported on some providers — skip */ }
        }
    }

    internal static string ResolveAppExe()
    {
        var overridden = Environment.GetEnvironmentVariable("SWDM2_APP_EXE");
        if (!string.IsNullOrEmpty(overridden) && File.Exists(overridden))
            return overridden;
        return Path.GetFullPath(Path.Combine(            AppContext.BaseDirectory, "..", "..", "..", "..", "..",
            "src", "Swdm2.App", "bin", "Debug", "net8.0-windows", "Swdm2.App.exe"));
    }

    /// <summary>
    /// Headless-sandbox detection evidence: when the harness session has no interactive
    /// desktop, Capture.MainScreen produces a fully black image (verified t26/t28 runs).
    /// Used to tag ENV-DOWNGRADE for the physical-input journey layer (desktop channel rerun,
    /// environment tolerance gate pattern same as D3.3/D3.4 Online runs).
    /// </summary>
    internal static bool MainScreenCaptureIsBlank()
    {
        string? tempFile = null;
        try
        {
            var shot = Capture.MainScreen();
            tempFile = Path.Combine(Path.GetTempPath(), $"swdm_envprobe_{Guid.NewGuid():N}.png");
            shot.ToFile(tempFile);
            var bytes = File.ReadAllBytes(tempFile);
            if (bytes.Length < 5000) return true; // solid-color PNG is tiny
            using var bmp = new System.Drawing.Bitmap(tempFile);
            var c = bmp.GetPixel(bmp.Width / 2, bmp.Height / 2);
            var corner = bmp.GetPixel(10, 10);
            return c.R == corner.R && c.G == corner.G && c.B == corner.B
                   && (c.R < 12 && c.G < 12 && c.B < 12); // black
        }
        catch
        {
            return true; // capture unavailable = treat as blank (env constraint)
        }
        finally
        {
            if (tempFile is not null && File.Exists(tempFile))
            {
                try { File.Delete(tempFile); } catch { }
            }
        }
    }
}
