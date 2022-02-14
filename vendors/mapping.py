from vendors.models import Job, WorkLog

STATUS_TO_EVENT = {
    Job.Statuses.Not_Accepted: WorkLog.Event.Init,
    Job.Statuses.Not_Accepted_Seen: WorkLog.Event.Seen,
    Job.Statuses.Accepted: WorkLog.Event.Accept,
    Job.Statuses.Incomplete: WorkLog.Event.Incomplete,
    Job.Statuses.In_Progress: WorkLog.Event.Start,
    Job.Statuses.Paused: WorkLog.Event.Pause,
    Job.Statuses.Completed: WorkLog.Event.Finish,
    Job.Statuses.Unable_To_Complete: WorkLog.Event.Finish_Unable,
    Job.Statuses.Cancelled: WorkLog.Event.Cancel,
    Job.Statuses.Declined: WorkLog.Event.Decline,
}
