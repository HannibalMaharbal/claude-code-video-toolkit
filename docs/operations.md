# Operations, SLOs, and recovery

Initial targets are at least 95% successful jobs without manual intervention and
99% successful resume behavior in the defined transient-provider tests. Track job
success/failure, total and per-stage latency, queue depth, CPU/GPU utilization,
provider rate limits, retry counts, and available disk space. Dashboards cover
latency, traffic, errors, and saturation; alerts must identify an operator action.

Each job is addressed by its stable job ID. Recovery starts by preserving the job
directory and status file, checking that final artifacts pass media validation,
and rerunning the same request. A completed job must reuse its final artifact; a
partial job resumes from valid persisted assets. Provider credentials and input
media must never be copied into incident notes or logs.

Quarterly recovery exercises use local fixtures only: interrupt after one stage,
restart with the same job ID, verify atomic status recovery and validate the final
artifact. Cloud/GPU execution remains an explicit, separately approved action.
