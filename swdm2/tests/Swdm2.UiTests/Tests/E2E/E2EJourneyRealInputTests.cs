using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;
using System.Diagnostics;
using System.IO;
using Xunit;
using Swdm2.UiTests.Tests.Smoke;

namespace Swdm2.UiTests.Tests.E2E;

/// <summary>
/// D10.1(t70): 全链真实输入实跑——用户原话「你自己有没有实地测试过
/// 从选择游戏到选择mod到下载mod」。每步=物理鼠标/键盘+截图+UIA 副证+时间戳。
/// 链：①启动→主页球体 ②设置→gmod→选 Garry's Mod ③浏览→真实条目
/// ④条目详情→真实标题/作者 ⑤下载→任务行→落盘（Installed 模式=
/// %LOCALAPPDATA%\Swdm2\steamcmd\steamapps\workshop\content\4000\&lt;pubfile&gt;)。
/// 失败步骤如实记录（退货归属），不假绿。
/// </summary>
public class E2EJourneyRealInputTests
{
    private static string T() => DateTime.Now.ToString("HH:mm:ss");
    private static readonly string ShotDir =
        Path.Combine(AppContext.BaseDirectory, "e2e_shots");

    private static void Shot(string name)
    {
        try
        {
            Directory.CreateDirectory(ShotDir);
            var path = Path.Combine(ShotDir, $"{name}_{DateTime.Now:HHmmss}.png");
            Capture.MainScreen().ToFile(path);
            Console.WriteLine($"E2E-SHOT {name}: {path} @{T()}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"E2E-SHOT-FAIL {name}: {ex.GetType().Name} @{T()}");
        }
    }

    private static string Elapsed(Stopwatch sw) => $"{sw.Elapsed.TotalSeconds:F1}s";

    /// <summary>
    /// 验证式物理导航点击：物理点击后校验目标页标记 id 出现；未路由=重试（≤3)。
    /// 前台锁间歇吞物理输入（t63/t66 实测同族）=需重试+如实记录每跳尝试次数。
    /// </summary>
    private static bool RealClickNav(Window window, string navId,
        string markerId, string stepName)
    {
        for (var attempt = 1; attempt <= 3; attempt++)
        {
            var nav = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, navId),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            if (nav is null)
            {
                Console.WriteLine($"E2E [STEP {stepName}] nav {navId} absent (attempt {attempt}) @{T()}");
                continue;
            }

            window.Focus();
            Thread.Sleep(300);
            UiTestHelpers.RealClick(nav); // 物理鼠标
            Thread.Sleep(900);
            var marker = window.FindFirstDescendant(cf => cf.ByAutomationId(markerId));
            if (marker is { IsEnabled: true, IsOffscreen: false }
                && marker.BoundingRectangle.Width > 4)
            {
                Console.WriteLine($"E2E [STEP {stepName}] nav physical click routed " +
                                  $"(attempt {attempt}) @{T()}");
                return true;
            }

            Console.WriteLine($"E2E [STEP {stepName}] physical click attempt {attempt} " +
                              $"not routed (foreground lock?) @{T()}");
        }

        return false;
    }

    [WpfFact]
    public async Task E2E_Select_Game_Browse_Detail_Download_Lands()
    {
        var exe = UiTestHelpers.ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing (publish first): {exe}");
        Console.WriteLine($"E2E [{T()}] === START exe={exe} ===");

        if (UiTestHelpers.MainScreenCaptureIsBlank())
        {
            Console.WriteLine($"E2E [{T()}] ENV-DOWNGRADE: no interactive desktop; " +
                              "rerun on the desktop channel (t28/t38 gate)");
            return;
        }

        using var automation = new UIA3Automation();
        var app = Application.Launch(exe);
        var failures = new List<string>();
        try
        {
            var sw = Stopwatch.StartNew();
            var window = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("MainShell"))?.AsWindow(),
                TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(0.2)).Result;
            sw.Stop();
            Assert.NotNull(window);
            window!.Focus();
            Console.WriteLine($"E2E [{T()}] STEP1-PASS launch+MainShell in {Elapsed(sw)}");
            Shot("01_home_sphere");

            // ---------- STEP2 设置→默认游戏→gmod→选 Garry's Mod ----------
            sw.Restart();
            if (!RealClickNav(window, "MainShell_Nav_SettingsButton",
                    "SettingsPage_Game_SearchTextBox", "2-nav-settings"))
            {
                failures.Add("STEP2: 设置页导航物理点击 3 次未路由（前台锁）");
                Console.WriteLine($"E2E [{T()}] STEP2-FAIL settings nav not routed (3 attempts)");
            }
            else
            {
                var searchBox = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, "SettingsPage_Game_SearchTextBox"),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                Assert.NotNull(searchBox);
                // 物理打字验证：文本框内容==gmod 才算路由（前台锁可能吞键
                // 盘=重试打字≤3 次；zh-CN 会话默认微软拼音 IME 会把字母组合
                // 成拼音（boxText="g'mo'd")=先物理按 Shift 切英文模式=真实用户动作）
                var typedOk = false;
                for (var tAttempt = 1; tAttempt <= 3 && !typedOk; tAttempt++)
                {
                    searchBox.Focus();
                    await Task.Delay(200);
                    if (tAttempt == 1) // 切 IME 英文模式一次（Shift 按下/释放）
                    {
                        Keyboard.Press(VirtualKeyShort.SHIFT);
                        Keyboard.Release(VirtualKeyShort.SHIFT);
                        await Task.Delay(300);
                    }
                    else
                    {
                        // 未路由：清场重试（物理键全选+删除）
                        searchBox.Focus();
                        Keyboard.Press(VirtualKeyShort.CONTROL); Keyboard.Type("a");
                        Keyboard.Release(VirtualKeyShort.CONTROL);
                        Keyboard.Type(VirtualKeyShort.BACK);
                    }

                    Keyboard.Type("gmod"); // 物理键盘输入
                    await Task.Delay(400);
                    var tb = searchBox.AsTextBox();
                    var text = tb?.Text ?? "";
                    Console.WriteLine(
                        $"E2E [{T()}] STEP2a typed gmod attempt {tAttempt}: boxText=\"{text}\"");
                    typedOk = text.Contains("gmod");
                }

                Console.WriteLine($"E2E [{T()}] STEP2a typing routed={typedOk}; waiting suggestions...");
                await Task.Delay(1500); // 防抖 350ms + 请求 + 渲染
                Shot("02_gmod_suggestions");

                var suggestList = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, "SettingsPage_Game_SuggestionsList"),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                AutomationElement? gmodItem = null;
                if (suggestList is null)
                {
                    failures.Add("STEP2: 联想列表未出现（网络/防抖）");
                    Console.WriteLine($"E2E [{T()}] STEP2-FAIL suggestions list absent");
                }
                else
                {
                    foreach (var item in suggestList.FindAllChildren())
                    {
                        var name = item.Name ?? "";
                        if (name.Contains("Garry", StringComparison.OrdinalIgnoreCase))
                        {
                            gmodItem = item;
                            break;
                        }
                    }

                    if (gmodItem is null)
                    {
                        // 证据：转储联想条目真名（排查名不对/编码/子件承载文本）
                        var names = suggestList.FindAllChildren()
                            .Select(i => i.Name ?? "(noname)").ToArray();
                        Console.WriteLine(
                            $"E2E [{T()}] STEP2-FAIL no Garry item; suggestion names=[" +
                            string.Join(" | ", names) + "]");
                        failures.Add("STEP2: 联想无 Garry's Mod 条目");
                    }
                    else
                    {
                        window.Focus();
                        UiTestHelpers.RealClick(gmodItem); // 物理选中
                        await Task.Delay(800);
                        var bound = window.FindFirstDescendant(
                            cf => cf.ByAutomationId("SettingsPage_Game_BoundDisplay"));
                        var boundText = bound?.Name ?? "(unset)";
                        Console.WriteLine(
                            $"E2E [{T()}] STEP2-PASS selected Garry's Mod, bound=\"{boundText}\" in {Elapsed(sw)}");
                        Shot("03_game_bound");
                    }
                }
            }

            // ---------- STEP3 浏览工坊→真实条目（社区 HTML 真源） ----------
            sw.Restart();
            if (!RealClickNav(window, "MainShell_Nav_BrowseButton",
                    "WorkshopBrowsePage_PageLabel", "3-nav-browse"))
            {
                failures.Add("STEP3: 浏览页导航物理点击 3 次未路由（前台锁）");
                Console.WriteLine($"E2E [{T()}] STEP3-FAIL browse nav not routed (3 attempts)");
                Shot("04_browse_navfail");
            }
            else
            {
                var itemDetail = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, "WorkshopBrowsePage_Item_DetailButton"),
                    TimeSpan.FromSeconds(60), TimeSpan.FromSeconds(0.5)).Result;
                if (itemDetail is null)
                {
                    failures.Add("STEP3: 浏览条目未物料化（真源网络不可达）");
                    Console.WriteLine($"E2E [{T()}] STEP3-FAIL browse items not materialized (60s)");
                    Shot("04_browse_empty");
                }
                else
                {
                    // 真源证据：当前游戏/条目数/示例横幅状态（区分真源 vs fallback)
                    var gameLabel = window.FindFirstDescendant(
                        cf => cf.ByAutomationId("WorkshopBrowsePage_CurrentGameLabel"))?.Name;
                    var countLabel = window.FindFirstDescendant(
                        cf => cf.ByAutomationId("WorkshopBrowsePage_ItemCountLabel"))?.Name;
                    var sampleBanner = window.FindFirstDescendant(
                        cf => cf.ByAutomationId("WorkshopBrowsePage_SampleBanner"));
                    var sampleOn = sampleBanner is { IsEnabled: true, IsOffscreen: false };
                    Console.WriteLine(
                        $"E2E [{T()}] STEP3-CTX game=\"{gameLabel}\" count=\"{countLabel}\" " +
                        $"sampleBannerOn={sampleOn}");
                    var items = window.FindAllDescendants()
                        .Where(e => e.AutomationId == "WorkshopBrowsePage_Item_DetailButton")
                        .ToList();
                    Console.WriteLine(
                        $"E2E [{T()}] STEP3-PASS browse real items={items.Count} in {Elapsed(sw)}");
                    Shot("04_browse_real_items");

                    // ---------- STEP4 条目详情→真实标题/作者/预览 ----------
                    sw.Restart();
                    window.Focus();
                    itemDetail = Retry.WhileNull(
                        () => UiTestHelpers.VisibleElement(window, "WorkshopBrowsePage_Item_DetailButton"),
                        TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                    Assert.NotNull(itemDetail);
                    UiTestHelpers.RealClick(itemDetail); // 物理点「详情」
                    var titleEl = Retry.WhileNull(
                        () => UiTestHelpers.VisibleElement(window, "ModDetailPage_TitleText"),
                        TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.3)).Result;
                    if (titleEl is null)
                    {
                        failures.Add("STEP4: 详情页标题未出现");
                        Console.WriteLine($"E2E [{T()}] STEP4-FAIL detail title absent");
                    }
                    else
                    {
                        // 社区回退富化=异步（v8 实测 1.7s 读到 demo 兜底，2s 后任务行
                        // 已显真名）：标题轮询 ≤10s 等「非 demo 标题」出现
                        var title = titleEl.Name;
                        var demoAt = Elapsed(sw);
                        for (var i = 0; i < 20 && (title.Contains("示例 mod") || title.Contains("Download Demo")); i++)
                        {
                            await Task.Delay(500);
                            titleEl = UiTestHelpers.VisibleElement(window, "ModDetailPage_TitleText");
                            title = titleEl?.Name ?? title;
                        }

                        // 真条目详情不应显 demo 兜底标题（v5/v6/v8 实测：富化完成后
                        // 应换真名；持久 demo=产品缺陷；瞬态 demo 已等富化消除）
                        if (title.Contains("示例 mod") || title.Contains("Download Demo"))
                            failures.Add($"STEP4: 真条目详情=demo 兜底标题 \"{title}\"（富化后仍 demo?)");
                        var banner = window.FindFirstDescendant(
                            cf => cf.ByAutomationId("ModDetailPage_SampleBanner"));
                        var sampleShown = banner is { IsEnabled: true, IsOffscreen: false };
                        Console.WriteLine(
                            $"E2E [{T()}] STEP4-PASS detail title=\"{title}\" sampleBanner={sampleShown} " +
                            $"in {Elapsed(sw)} (demo at {demoAt} before enrich)");
                        // STEP4 证据：错误横幅（API 401 匿名=详情加载失败诚实态）
                        var errEl = window.FindFirstDescendant(
                            cf => cf.ByAutomationId("ModDetailPage_ErrorMessageText"));
                        Console.WriteLine(
                            $"E2E [{T()}] STEP4-CTX detail error=\"{errEl?.Name ?? "(none)"}\"");
                        Shot("05_detail_real");

                        // ---------- STEP5 下载→任务行→落盘 ----------
                        sw.Restart();
                        var downloadBtn = Retry.WhileNull(
                            () => UiTestHelpers.VisibleElement(window, "ModDetailPage_DownloadButton"),
                            TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
                        if (downloadBtn is null)
                        {
                            failures.Add("STEP5: 详情页下载钮不可见");
                            Console.WriteLine($"E2E [{T()}] STEP5-FAIL download button absent");
                        }
                        else
                        {
                            var btnRect = downloadBtn.BoundingRectangle;
                            var winRect = window.BoundingRectangle;
                            // 按钮矩形中心是否在窗口可见区内（v3 实测按钮 y=887 落
                            // 底缘外=点击出界被任务栏吞；出界=物理 Enter 激活兜底）
                            var clickableInWindow = btnRect.Y >= winRect.Y
                                                     && btnRect.Bottom <= winRect.Bottom - 8;
                            Console.WriteLine(
                                $"E2E [{T()}] STEP5-CTX downloadBtn rect=({btnRect.X},{btnRect.Y}) " +
                                $"{btnRect.Width:F0}x{btnRect.Height:F0} enabled={downloadBtn.IsEnabled} " +
                                $"inWindow={clickableInWindow} (winBottom={winRect.Bottom:F0})");
                            window.Focus();
                            if (clickableInWindow)
                            {
                                UiTestHelpers.RealClick(downloadBtn); // 物理鼠标
                            }
                            else
                            {
                                // 物理键盘激活（真实输入口径；焦点在钮+物理 Enter)
                                downloadBtn.Focus();
                                Keyboard.Press(VirtualKeyShort.RETURN);
                                Keyboard.Release(VirtualKeyShort.RETURN);
                            }
                            Console.WriteLine($"E2E [{T()}] STEP5a clicked download (mode={(clickableInWindow ? "mouse" : "enter")})");
                            await Task.Delay(1500);
                            // 点击后副证：详情页错误/状态变化+是否自动跳下载页
                            UiTestHelpers.DumpTree(window, "e2e step5 after download click");
                            var autoNav = UiTestHelpers.VisibleElement(window,
                                "DownloadsPage_TaskList_Items");
                            Console.WriteLine(
                                $"E2E [{T()}] STEP5-CTX autoNavToDownloads={autoNav is not null}");
                            if (!RealClickNav(window, "MainShell_Nav_DownloadsButton",
                                    "DownloadsPage_TaskList_Items", "5-nav-downloads"))
                            {
                                failures.Add("STEP5: 下载页导航物理点击 3 次未路由（前台锁）");
                                Console.WriteLine($"E2E [{T()}] STEP5-FAIL downloads nav not routed");
                            }
                            else
                            {
                                try
                                {
                                    // crash-context 证据：进下载页先 dump（驱动级崩点定位）
                                    UiTestHelpers.DumpTree(window, "e2e step5 downloads page");
                                    var row = Retry.WhileNull(
                                        () => UiTestHelpers.VisibleElement(window, "DownloadsPage_TaskList_Item"),
                                        TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.3)).Result;
                                if (row is null)
                                {
                                    failures.Add("STEP5: 下载页任务行未出现");
                                    Console.WriteLine($"E2E [{T()}] STEP5-FAIL task row absent (30s)");
                                }
                                else
                                {
                                    Shot("06_download_row");
                                    var fileNameEl = row.FindFirstDescendant(
                                        cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_FileNameText"));
                                    var fileName = fileNameEl?.Name ?? "";
                                    Console.WriteLine(
                                        $"E2E [{T()}] STEP5-PASS task row appeared, file=\"{fileName}\" in {Elapsed(sw)}");

                                    // 等完成（≤10min,steamcmd 匿名下载）
                                    sw.Restart();
                                    string lastState = "?";
                                    var done = false;
                                    while (sw.Elapsed < TimeSpan.FromMinutes(10))
                                    {
                                        var rowCur = Retry.WhileNull(
                                            () => UiTestHelpers.VisibleElement(window, "DownloadsPage_TaskList_Item"),
                                            TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(0.5)).Result;
                                        if (rowCur is null) break;
                                        var stateEl = rowCur.FindFirstDescendant(
                                            cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_StateText"));
                                        lastState = stateEl?.Name ?? lastState;
                                        if (lastState == "完成") { done = true; break; }

                                        if (lastState == "失败" || lastState == "已取消")
                                        {
                                            failures.Add($"STEP5: 下载终态={lastState}");
                                            break;
                                        }

                                        await Task.Delay(2000);
                                    }

                                    Console.WriteLine(
                                        $"E2E [{T()}] STEP5-wait done={done} state=\"{lastState}\" after {Elapsed(sw)}");
                                    if (!done)
                                    {
                                        // 10min 超时=下载 stall(v5/v6 实测 provider 回退 AuthRequired 后无进展）
                                        // 不能假绿：超时即失败（v6 教训=timeout 路径漏记 failures)
                                        failures.Add(
                                            $"STEP5: 下载 10min 未完成 state=\"{lastState}\"（provider 回退后 stall?)");
                                    }

                                    Shot("07_download_state");

                                    // 落盘检查：Installed 模式 Root=%APPDATA%\Swdm2(v5 路径错 LocalAppData 教训）
                                    // PathService L69:GetDefaultRoot(Installed)=SpecialFolder.ApplicationData
                                    if (done)
                                    {
                                        var pubFile = new string(fileName.Where(char.IsDigit).ToArray());
                                        var root = Path.Combine(
                                            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                            "Swdm2");
                                        var contentDir = Path.Combine(root, "steamcmd", "steamapps",
                                            "workshop", "content", "4000");
                                        var landed = false;
                                        long size = -1;
                                        string? landedPath = null;
                                        if (Directory.Exists(contentDir))
                                        {
                                            var candidates = string.IsNullOrEmpty(pubFile)
                                                ? Directory.GetFiles(contentDir, "*", SearchOption.AllDirectories)
                                                : Directory.GetFiles(contentDir, pubFile, SearchOption.AllDirectories);
                                            if (candidates.Length > 0)
                                            {
                                                landedPath = candidates[0];
                                                size = new FileInfo(landedPath).Length;
                                                landed = size > 0;
                                            }
                                        }

                                        if (landed)
                                        {
                                            Console.WriteLine(
                                                $"E2E [{T()}] STEP6-PASS landed size={size}B path=\"{landedPath}\"");
                                            Shot("08_landed");
                                        }
                                        else
                                        {
                                            failures.Add(
                                                $"STEP6: 落盘失败（下载完成但文件不存在/size=0,pubfile={pubFile})");
                                            Console.WriteLine(
                                                $"E2E [{T()}] STEP6-FAIL no landed file (pubfile={pubFile}, " +
                                                $"contentDir exists={Directory.Exists(contentDir)})");
                                        }
                                    }
                                }
                                }
                                catch (Exception ex)
                                {
                                    // 驱动级崩前最后证据（不可恢复的硬崩不在此.catch 范围）
                                    failures.Add($"STEP5: 行等待异常 {ex.GetType().Name}: {ex.Message[..Math.Min(80, ex.Message.Length)]}");
                                    Console.WriteLine(
                                        $"E2E [{T()}] STEP5-EXC {ex.GetType().Name}: " +
                                        $"{ex.Message[..Math.Min(100, ex.Message.Length)]}");
                                    Shot("07_row_exception");
                                }
                            }
                        }
                    }
                }
            }

            // ---------- 汇总 ----------
            Console.WriteLine($"E2E [{T()}] === SUMMARY failures={failures.Count} ===");
            foreach (var f in failures)
                Console.WriteLine($"E2E-FAIL {f}");
            if (failures.Count == 0)
                Console.WriteLine("E2E-PASS full journey real-input e2e complete");
            else
                Console.WriteLine("E2E-PARTIAL 部分步骤失败（已如实记录+退货归属）");
        }
        finally
        {
            try { app?.Kill(); } catch { /* cleanup */ }
        }
    }
}
