using System.Windows;
using System.Windows.Threading;
using Swdm2.App.Views;
using Swdm2.Steam.Cdn;

namespace Swdm2.App.Session;

/// <summary>
/// Steam Guard 收码器（D4.1 A11 模式，SCA SteamAuth §4 教训 #6):
/// 后台登录任务 await <see cref="PromptGuardCodeAsync"/> →
/// <see cref="Dispatcher.Invoke"/> 切 UI 线程 <see cref="SteamGuardDialog"/>.ShowDialog()
/// 模态阻塞主窗口 → <see cref="TaskCompletionSource{String}"/> 唤醒后台 await。
/// 取消（null)→登录侧 AuthRequired 不重试。
/// </summary>
public sealed class WpfSteamGuardPrompter : ISteamGuardPrompter
{
    public async Task<string?> PromptGuardCodeAsync(string account, CancellationToken ct = default)
    {
        var tcs = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);

        // UI 线程弹出模态窗（Application 有 Dispatcher；无则回退 null=收码不可用）
        if (Application.Current?.Dispatcher is null)
        {
            return null;
        }

        await Application.Current.Dispatcher.InvokeAsync(() =>
        {
            try
            {
                var dialog = new SteamGuardDialog(account)
                {
                    Owner = Application.Current.MainWindow
                };
                dialog.Closed += (_, _) => tcs.TrySetResult(dialog.DialogResult == true ? dialog.Code : null);
                _ = dialog.ShowDialog();
            }
            catch (Exception ex)
            {
                tcs.TrySetException(ex);
            }
        }, DispatcherPriority.Normal).Task.ConfigureAwait(true);

        return await tcs.Task.ConfigureAwait(false);
    }
}
