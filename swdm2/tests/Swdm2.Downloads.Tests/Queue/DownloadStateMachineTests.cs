using System.Collections.Concurrent;
using System.Threading.Channels;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;
using Xunit;

namespace Swdm2.Downloads.Tests.Queue;

/// <summary>
/// D3.1 状态机与队列验收（真实输入：真实 Channel/线程并发，非 mock 线程模型）：
/// - 非法转移抛异常（可测）
/// - 入队自动进队列（Pending→Queued)
/// - 并发槽配置控制（Max=2 时观察并发=2;Max=1 时=1）
/// - FIFO 出队序
/// - 排队期取消跳过 / 失败重试回 Queued
/// </summary>
[Trait("Category", "Downloads")]
public sealed class DownloadStateMachineTests
{
    private static DownloadTask NewTask(long id = 1)
    {
        var item = new WorkshopItem(
            id: new PublishedFileId((ulong)id),
            appId: new AppId(4000),
            title: "测试物品 " + id);
        return new DownloadTask(new DownloadTaskId(Guid.NewGuid()), item, new AppId(4000),
            @"C:\swdm\steamapps\workshop\content\4000");
    }

    // ---------- 状态机转移表 ----------

    [Fact]
    public void Legal_Transitions_Full_Sequence()
    {
        var entry = new DownloadTaskEntry(NewTask());
        Assert.Equal(DownloadState.Pending, entry.State);
        Assert.Equal(DownloadState.Queued, entry.TransitionTo(DownloadState.Queued));
        Assert.Equal(DownloadState.Preparing, entry.TransitionTo(DownloadState.Preparing)); // t3 §3.2: Queued→Preparing→Downloading
        Assert.Equal(DownloadState.Downloading, entry.TransitionTo(DownloadState.Downloading));
        Assert.Equal(DownloadState.Completed, entry.TransitionTo(DownloadState.Completed));
        Assert.True(DownloadStateMachine.IsTerminal(entry.State));
    }

    [Fact]
    public void Pause_Resume_Sequence()
    {
        var entry = new DownloadTaskEntry(NewTask());
        entry.TransitionTo(DownloadState.Queued);
        entry.TransitionTo(DownloadState.Preparing);
        entry.TransitionTo(DownloadState.Downloading);
        Assert.Equal(DownloadState.Paused, entry.TransitionTo(DownloadState.Paused));
        Assert.Equal(DownloadState.Downloading, entry.TransitionTo(DownloadState.Downloading));
        Assert.Equal(DownloadState.Completed, entry.TransitionTo(DownloadState.Completed));
    }

    [Fact]
    public void Failed_Can_Retry_Back_To_Queued()
    {
        var entry = new DownloadTaskEntry(NewTask());
        entry.TransitionTo(DownloadState.Queued);
        entry.TransitionTo(DownloadState.Preparing);
        entry.TransitionTo(DownloadState.Downloading);
        entry.TransitionTo(DownloadState.Failed);
        Assert.Equal(DownloadState.Queued, entry.TransitionTo(DownloadState.Queued)); // 重试
    }

    /// <summary>验收判据：非法转移抛 InvalidOperationException（含 from/to 信息可测）。</summary>
    [Theory]
    [InlineData(DownloadState.Pending, DownloadState.Downloading)] // 跳级
    [InlineData(DownloadState.Pending, DownloadState.Completed)]
    [InlineData(DownloadState.Queued, DownloadState.Downloading)] // 必须经 Preparing
    [InlineData(DownloadState.Queued, DownloadState.Paused)] // 未开始不能暂停
    [InlineData(DownloadState.Queued, DownloadState.Completed)]
    [InlineData(DownloadState.Preparing, DownloadState.Paused)] // 准备期不可暂停
    [InlineData(DownloadState.Preparing, DownloadState.Completed)]
    [InlineData(DownloadState.Downloading, DownloadState.Queued)] // 回退
    [InlineData(DownloadState.Paused, DownloadState.Completed)] // 暂停态必须先恢复
    [InlineData(DownloadState.Completed, DownloadState.Downloading)] // 终态
    [InlineData(DownloadState.Completed, DownloadState.Failed)]
    [InlineData(DownloadState.Cancelled, DownloadState.Downloading)]
    [InlineData(DownloadState.Failed, DownloadState.Completed)]
    public void Illegal_Transitions_Throw(DownloadState from, DownloadState to)
    {
        var ex = Assert.Throws<InvalidOperationException>(() =>
            DownloadStateMachine.EnsureCanTransition(from, to));
        Assert.Contains(from.ToString(), ex.Message);
        Assert.Contains(to.ToString(), ex.Message);
    }

    [Theory]
    [InlineData(DownloadState.Completed)]
    [InlineData(DownloadState.Cancelled)]
    public void Terminal_States_Have_No_Out_Edges(DownloadState terminal)
    {
        Assert.True(DownloadStateMachine.IsTerminal(terminal));
        Assert.False(DownloadStateMachine.Transitions.ContainsKey(terminal));
        Assert.All(Enum.GetValues<DownloadState>(), other =>
            Assert.False(DownloadStateMachine.CanTransition(terminal, other)));
    }

    // ---------- 队列 ----------

    [Fact]
    public async Task Enqueue_Auto_Transitions_To_Queued()
    {
        await using var queue = new DownloadQueue();
        var task = NewTask();
        var entry = await queue.EnqueueAsync(task);
        Assert.Equal(DownloadState.Queued, entry.State); // 入队自动进队列
        Assert.Same(entry, queue.GetEntry(task.Id));
        Assert.Equal(1, queue.PendingCount);
    }

    [Fact]
    public async Task Dequeue_Is_Fifo_Order()
    {
        await using var queue = new DownloadQueue();
        var e1 = await queue.EnqueueAsync(NewTask(1));
        var e2 = await queue.EnqueueAsync(NewTask(2));
        var e3 = await queue.EnqueueAsync(NewTask(3));

        Assert.True(queue.TryDequeue(out var d1));
        Assert.True(queue.TryDequeue(out var d2));
        Assert.True(queue.TryDequeue(out var d3));
        Assert.Same(e1, d1);
        Assert.Same(e2, d2);
        Assert.Same(e3, d3);
        Assert.False(queue.TryDequeue(out _)); // 空
    }

    [Fact]
    public async Task Enqueue_NonPending_State_Throws()
    {
        await using var queue = new DownloadQueue();
        var entry = await queue.EnqueueAsync(NewTask());
        entry.TransitionTo(DownloadState.Cancelled); // 模拟外部取消
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            queue.EnqueueAsync(entry.Task).AsTask());
    }

    // ---------- 调度器并发槽 ----------

    /// <summary>验收判据：MaxConcurrent=2 时并发执行数峰值=2（第三个等槽）。</summary>
    [Fact]
    public async Task Scheduler_Concurrency_Capped_At_MaxConcurrent()
    {
        await using var queue = new DownloadQueue();
        var started = new CountdownEvent(2);
        var release = new TaskCompletionSource();
        var peak = 0; // 执行器内 Interlocked 维护的并发峰值

        async Task<bool> BlockingExecutor(DownloadTaskEntry _, CancellationToken ct)
        {
            var current = Interlocked.Increment(ref peak);
            started.Signal();
            await release.Task.WaitAsync(ct);
            Interlocked.Decrement(ref peak);
            return true;
        }

        await using var scheduler = new DownloadScheduler(queue, BlockingExecutor, maxConcurrent: 2);
        await queue.EnqueueAsync(NewTask(1));
        await queue.EnqueueAsync(NewTask(2));
        await queue.EnqueueAsync(NewTask(3)); // 第三个必等槽

        Assert.True(started.WaitHandle.WaitOne(TimeSpan.FromSeconds(5)));
        await Task.Delay(200); // 让第三个尝试（若超槽会等待）
        Assert.Equal(2, Volatile.Read(ref peak)); // 恰好 2 并发
        Assert.Equal(2, scheduler.ActiveCount);
        Assert.Equal(2, scheduler.MaxConcurrent);

        release.SetResult(); // 放行 → 第三进入
        await Task.Delay(300);
        Assert.Equal(0, scheduler.ActiveCount);
    }

    /// <summary>验收判据：并发槽配置控制——Max=1 时严格串行。</summary>
    [Fact]
    public async Task Scheduler_MaxOne_Runs_Strictly_Sequential()
    {
        await using var queue = new DownloadQueue();
        var order = new ConcurrentQueue<ulong>();
        var gate = new TaskCompletionSource();

        async Task<bool> Executor(DownloadTaskEntry e, CancellationToken ct)
        {
            order.Enqueue(e.Task.Item.Id.Value);
            await gate.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            return true;
        }

        await using var scheduler = new DownloadScheduler(queue, Executor, maxConcurrent: 1);
        await queue.EnqueueAsync(NewTask(1));
        await queue.EnqueueAsync(NewTask(2));

        await Task.Delay(200);
        Assert.Equal(1, scheduler.ActiveCount); // 只有一个在跑
        Assert.Single(order);

        gate.SetResult();
        await Task.Delay(300);
        Assert.Equal(0, scheduler.ActiveCount);
    }

    [Fact]
    public async Task Scheduler_Runs_Task_To_Completed_Or_Failed()
    {
        await using var queue = new DownloadQueue();
        var results = new ConcurrentDictionary<DownloadTaskId, DownloadState>();
        await using var scheduler = new DownloadScheduler(queue, (entry, ct) =>
        {
            // id 偶数成功、奇数失败
            return Task.FromResult(entry.Task.Item.Id.Value % 2 == 0);
        });

        var ok = await queue.EnqueueAsync(NewTask(2));
        var bad = await queue.EnqueueAsync(NewTask(3));

        await Task.Delay(500);
        Assert.Equal(DownloadState.Completed, ok.State);
        Assert.Equal(DownloadState.Failed, bad.State);
    }

    [Fact]
    public async Task Scheduler_Skips_Cancelled_Queued_Entry()
    {
        await using var queue = new DownloadQueue();
        var executed = 0;
        await using var scheduler = new DownloadScheduler(queue, (entry, ct) =>
        {
            Interlocked.Increment(ref executed);
            return Task.FromResult(true);
        });

        var cancelled = await queue.EnqueueAsync(NewTask(1));
        cancelled.TransitionTo(DownloadState.Cancelled); // 排队期取消

        await Task.Delay(300);
        Assert.Equal(0, executed); // 未执行
        Assert.Equal(DownloadState.Cancelled, cancelled.State);
    }

    [Fact]
    public async Task Scheduler_Executor_Exception_Maps_Failed()
    {
        await using var queue = new DownloadQueue();
        await using var scheduler = new DownloadScheduler(queue, (entry, ct) =>
            Task.FromException<bool>(new InvalidOperationException("boom")));

        var entry = await queue.EnqueueAsync(NewTask(1));
        await Task.Delay(300);
        Assert.Equal(DownloadState.Failed, entry.State); // 异常不逃出调度器循环
    }

    [Fact]
    public async Task CancelQueued_Stops_Before_Execution()
    {
        await using var queue = new DownloadQueue();
        var gate = new TaskCompletionSource();
        await using var scheduler = new DownloadScheduler(queue, async (e, ct) =>
        {
            await gate.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            return true;
        }, maxConcurrent: 1); // 串行：第一个 hold 槽

        var running = await queue.EnqueueAsync(NewTask(1));
        var pending = await queue.EnqueueAsync(NewTask(2));
        await Task.Delay(200); // 第一个占槽
        Assert.True(scheduler.CancelQueued(pending.Task.Id));
        Assert.Equal(DownloadState.Cancelled, pending.State);

        gate.SetResult();
        await Task.Delay(300);
        Assert.Equal(DownloadState.Completed, running.State);
        Assert.Equal(DownloadState.Cancelled, pending.State); // 未被执行覆盖
    }

    [Fact]
    public async Task Scheduler_Construct_Invalid_Slot_Throws()
    {
        await using var queue = new DownloadQueue();
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new DownloadScheduler(queue, (e, ct) => Task.FromResult(true), maxConcurrent: 0));
    }

    /// <summary>验收判据：Paused→ResumeAsync→Downloading→Completed(t26 UI 按钮点亮前提）。</summary>
    [Fact]
    public async Task Resume_Paused_Task_Reruns_To_Completed()
    {
        await using var queue = new DownloadQueue();
        var calls = 0;
        async Task<bool> Executor(DownloadTaskEntry e, CancellationToken ct)
        {
            var n = Interlocked.Increment(ref calls);
            if (n == 1)
            {
                e.TransitionTo(DownloadState.Paused); // provider 暂停语义（执行内外部暂停）
                return false; // 暂停≠失败：scheduler 因 state==Paused 保留（不覆盖 Failed)
            }
            await Task.CompletedTask; // CS1998: 保持 async 签名给 scheduler 执行器契约
            return true; // 恢复后完成
        }

        await using var scheduler = new DownloadScheduler(queue, Executor, maxConcurrent: 1);
        var entry = await queue.EnqueueAsync(NewTask(7));

        Assert.True(SpinWaitFor(() => calls >= 1, TimeSpan.FromSeconds(5)));
        Assert.True(SpinWaitFor(() => entry.State == DownloadState.Paused, TimeSpan.FromSeconds(2))); // 暂停保留

        Assert.True(await scheduler.ResumeAsync(entry.Task.Id));
        Assert.True(SpinWaitFor(() => entry.State == DownloadState.Completed, TimeSpan.FromSeconds(5)));
        Assert.Equal(2, calls); // 恢复=重新执行一次
    }

    /// <summary>Resume 非暂停态（如排队中的 Queued）拒绝。</summary>
    [Fact]
    public async Task Resume_Rejects_Non_Paused_State()
    {
        await using var queue = new DownloadQueue();
        var gate = new TaskCompletionSource();
        await using var scheduler = new DownloadScheduler(queue, async (e, ct) =>
        {
            await gate.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            return true;
        }, maxConcurrent: 1);

        var running = await queue.EnqueueAsync(NewTask(1));
        var queuedOne = await queue.EnqueueAsync(NewTask(2)); // 排队等槽
        await Task.Delay(200);
        Assert.Equal(DownloadState.Downloading, running.State); // 占槽
        Assert.False(await scheduler.ResumeAsync(queuedOne.Task.Id)); // Queued 不可 resume（xUnit1030：测试方法不用 ConfigureAwait(false)）
        Assert.Equal(DownloadState.Queued, queuedOne.State);

        gate.SetResult();
        await Task.Delay(300);
        Assert.Equal(DownloadState.Completed, queuedOne.State);
    }

    private static bool SpinWaitFor(Func<bool> predicate, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (predicate()) return true;
            Thread.Sleep(15);
        }
        return predicate();
    }
}
