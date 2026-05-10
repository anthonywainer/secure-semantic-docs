"""Spark partition-count helpers for CPU-bound workloads."""


def compute_partition_count(
        total_executor_cores: int,
        configured: int,
        is_local_mode: bool
) -> int:
    """Return the number of Spark partitions to use for a CPU-bound stage.

    **Default strategy — one partition per core:**
    For CPU-bound work (model inference, encryption, heavy text processing)
    the sweet spot is one partition per available core.  Unlike IO-bound or
    shuffle-heavy stages — where 2–4× over-partitioning hides straggler tasks
    — CPU-bound stages already saturate one core per partition through internal
    batch parallelism.  Adding extra partitions only introduces scheduling
    overhead and, for workloads that load large in-process state (e.g. ML
    models), causes each worker to duplicate that state unnecessarily.

    **Manual override:**
    Pass ``configured > 0`` to bypass the auto-calculated value.  Useful when
    you know your data is heavily skewed, the cluster has heterogeneous cores,
    or you are tuning for a specific memory/throughput trade-off.

    **Local mode:**
    In local mode the function always returns ``1``, regardless of
    ``total_executor_cores`` or ``configured``.  Local mode runs all workers
    in the same JVM process; each additional partition launches a separate
    Python subprocess.  For workloads that load large in-process state (e.g.
    an ML model) this causes every subprocess to load that state
    simultaneously, quickly exhausting memory.  A single partition is both
    safe and optimal — the workload's internal batching still uses all cores.

    Parameters
    ----------
    total_executor_cores:
        ``spark.sparkContext.defaultParallelism`` — equals
        ``N_executors × cores_per_executor`` in cluster mode or the local
        thread count in local mode.
    configured:
        User-supplied partition count (e.g. from a YAML config field).
        When ``> 0`` it takes precedence over the auto-calculated value.
        Pass ``0`` or a negative number to use the default strategy.
    is_local_mode:
        Whether the SparkSession is running locally (master starts with
        ``"local"``).

    Returns
    -------
    int
        Partition count, always ``>= 1``.
    """
    if is_local_mode:
        return 1
    if configured > 0:
        return configured
    return max(1, total_executor_cores)
