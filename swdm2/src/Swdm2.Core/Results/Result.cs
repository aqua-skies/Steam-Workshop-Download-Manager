namespace Swdm2.Core.Results;

/// <summary>
/// 结果模型：Ok(T) / Err(TErr) 二选一，可空引用安全。
/// 层间错误传递一律走本类型（不抛业务异常），调用方强制 Match 处理两个分支（测试纪律：无静默丢弃错误）。
/// </summary>
/// <typeparam name="T">成功值类型。</typeparam>
/// <typeparam name="TErr">错误枚举（如 <see cref="SteamError"/>/<see cref="DownloadError"/>）。</typeparam>
public readonly struct Result<T, TErr> where TErr : struct, Enum
{
    /// <summary>是否成功（成功时 <see cref="Value"/> 保证非 default 语义由调用方约束；失败时必读 <see cref="Error"/>）。</summary>
    public bool IsOk { get; }

    /// <summary>成功值（失败时为 default；先判 <see cref="IsOk"/>）。</summary>
    public T? Value { get; }

    /// <summary>错误码（成功时为 null；先判 <see cref="IsOk"/>）。</summary>
    public TErr? Error { get; }

    private Result(bool isOk, T? value, TErr? error)
    {
        IsOk = isOk;
        Value = value;
        Error = error;
    }

    /// <summary>构造成功结果。</summary>
    public static Result<T, TErr> Ok(T value) => new(isOk: true, value, default);

    /// <summary>构造失败结果。</summary>
    public static Result<T, TErr> Fail(TErr error) => new(isOk: false, default, error);

    /// <summary>双分支解构：强制处理两个分支。</summary>
    public void Deconstruct(out bool isOk, out T? value, out TErr? error)
    {
        isOk = IsOk;
        value = Value;
        error = Error;
    }

    /// <summary>映射成功值（错误原样透传）。</summary>
    public Result<TNext, TErr> Map<TNext>(Func<T, TNext> map) where TNext : notnull
        => IsOk ? Result<TNext, TErr>.Ok(map(Value!)) : Result<TNext, TErr>.Fail(Error!.Value);

    /// <summary>映射错误码（成功值原样透传）。</summary>
    public Result<T, TErrNext> MapError<TErrNext>(Func<TErr, TErrNext> map) where TErrNext : struct, Enum
        => IsOk ? Result<T, TErrNext>.Ok(Value!) : Result<T, TErrNext>.Fail(map(Error!.Value));

    /// <summary>绑定（flatMap）：成功时续接，失败时短路。</summary>
    public Result<TNext, TErr> Bind<TNext>(Func<T, Result<TNext, TErr>> next) where TNext : class
        => IsOk ? next(Value!) : Result<TNext, TErr>.Fail(Error!.Value);

    /// <summary>双分支匹配（函数式）。</summary>
    public TResult Match<TResult>(Func<T, TResult> onOk, Func<TErr, TResult> onError)
        => IsOk ? onOk(Value!) : onError(Error!.Value);

    /// <summary>双分支匹配（执行式）。</summary>
    public void Match(Action<T> onOk, Action<TErr> onError)
    {
        if (IsOk) onOk(Value!);
        else onError(Error!.Value);
    }

    /// <summary>成功时取出值；失败抛 <see cref="InvalidOperationException"/>（仅测试/契约断言场景使用，禁止吞错）。</summary>
    public T GetValueOrThrow(string? message = null)
        => IsOk ? Value! : throw new InvalidOperationException(message ?? $"操作失败：{Error}");

    /// <summary>相等性按三字段（IsOk/Value/Error）比较。</summary>
    public override bool Equals(object? obj)
        => obj is Result<T, TErr> other && IsOk == other.IsOk && Equals(Value, other.Value) && Equals(Error, other.Error);

    public override int GetHashCode() => HashCode.Combine(IsOk, Value, Error);

    public static bool operator ==(Result<T, TErr> left, Result<T, TErr> right) => left.Equals(right);
    public static bool operator !=(Result<T, TErr> left, Result<T, TErr> right) => !left.Equals(right);
}
