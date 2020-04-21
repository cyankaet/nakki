"""
Code modified by Puddles
Original version retrieved from: https://github.com/dbader/schedule

The MIT License (MIT)

Copyright (c) 2013 Daniel Bader (http://dbader.org)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
import datetime
import functools
import logging
import time
import threading

logger = logging.getLogger('schedule')


class Scheduler(object):
    def __init__(self):
        self.jobs = []

    def run_pending(self):
        """Run all jobs that are scheduled to run.

        Please note that it is *intended behavior that tick() does not
        run missed jobs*. For example, if you've registered a job that
        should run every minute and you only call tick() in one hour
        increments then your job won't be run 60 times in between but
        only once.
        """
        runnable_jobs = (job for job in self.jobs if job.should_run)
        for job in sorted(runnable_jobs):
            job.run()

    def run_continuously(self, interval=1):
        """Continuously run, while executing pending jobs at each elapsed
        time interval.

        @return cease_continuous_run: threading.Event which can be set to
        cease continuous run.

        Please note that it is *intended behavior that run_continuously()
        does not run missed jobs*. For example, if you've registered a job
        that should run every minute and you set a continuous run interval
        of one hour then your job won't be run 60 times at each interval but
        only once.
        """
        cease_continuous_run = threading.Event()

        class ScheduleThread(threading.Thread):
            @classmethod
            def run(cls):
                while not cease_continuous_run.is_set():
                    self.run_pending()
                    time.sleep(interval)

        continuous_thread = ScheduleThread()
        continuous_thread.start()
        return cease_continuous_run

    def run_all(self, delay_seconds=0):
        """Run all jobs regardless if they are scheduled to run or not.

        A delay of `delay` seconds is added between each job. This helps
        distribute system load generated by the jobs more evenly
        over time."""
        logger.info('Running *all* %i jobs with %is delay inbetween',
                    len(self.jobs), delay_seconds)
        for job in self.jobs:
            job.run()
            time.sleep(delay_seconds)

    def clear(self):
        """Deletes all scheduled jobs."""
        del self.jobs[:]

    def every(self, interval=1):
        """Schedule a new periodic job."""
        job = Job(interval)
        self.jobs.append(job)
        return job

    @property
    def next_run(self):
        """Datetime when the next job should run."""
        return min(self.jobs).next_run

    @property
    def idle_seconds(self):
        """Number of seconds until `next_run`."""
        return (self.next_run - datetime.datetime.now()).total_seconds()


class Job(object):
    """A periodic job as used by `Scheduler`."""
    def __init__(self, interval):
        self.interval = interval  # pause interval * unit between runs
        self.job_func = None  # the job job_func to run
        self.unit = None  # time units, e.g. 'minutes', 'hours', ...
        self.at_time = None  # optional time at which this job runs
        self.last_run = None  # datetime of the last run
        self.next_run = None  # datetime of the next run
        self.period = None  # timedelta between runs, only valid for

    def __lt__(self, other):
        """PeriodicJobs are sortable based on the scheduled time
        they run next."""
        return self.next_run < other.next_run

    def __repr__(self):
        def format_time(t):
            return t.strftime("%Y-%m-%d %H:%M:%S") if t else '[never]'

        timestats = '(last run: %s, next run: %s)' % (
                    format_time(self.last_run), format_time(self.next_run))

        job_func_name = self.job_func.__name__
        args = [repr(x) for x in self.job_func.args]
        kwargs = ['%s=%s' % (k, repr(v))
                  for k, v in self.job_func.keywords.items()]
        call_repr = job_func_name + '(' + ', '.join(args + kwargs) + ')'

        if self.at_time is not None:
            return 'Every %s %s at %s do %s %s' % (
                   self.interval,
                   self.unit[:-1] if self.interval == 1 else self.unit,
                   self.at_time, call_repr, timestats)
        else:
            return 'Every %s %s do %s %s' % (
                   self.interval,
                   self.unit[:-1] if self.interval == 1 else self.unit,
                   call_repr, timestats)

    @property
    def second(self):
        assert self.interval == 1
        return self.seconds

    @property
    def seconds(self):
        self.unit = 'seconds'
        return self

    @property
    def minute(self):
        assert self.interval == 1
        return self.minutes

    @property
    def minutes(self):
        self.unit = 'minutes'
        return self

    @property
    def hour(self):
        assert self.interval == 1
        return self.hours

    @property
    def hours(self):
        self.unit = 'hours'
        return self

    @property
    def day(self):
        assert self.interval == 1
        return self.days

    @property
    def days(self):
        self.unit = 'days'
        return self

    @property
    def week(self):
        assert self.interval == 1
        return self.weeks

    @property
    def weeks(self):
        self.unit = 'weeks'
        return self

    def at(self, time_str):
        """Schedule the job every day at a specific time.

        Calling this is only valid for jobs scheduled to run every
        N day(s).
        """
        assert self.unit == 'days'
        hour, minute = [int(t) for t in time_str.split(':')]
        assert 0 <= hour <= 23
        assert 0 <= minute <= 59
        self.at_time = datetime.time(hour, minute)
        return self

    def do(self, job_func, *args, **kwargs):
        """Specifies the job_func that should be called every time the
        job runs.

        Any additional arguments are passed on to job_func when
        the job runs.
        """
        self.job_func = functools.partial(job_func, *args, **kwargs)
        functools.update_wrapper(self.job_func, job_func)
        self._schedule_next_run()
        return self

    @property
    def should_run(self):
        """True if the job should be run now."""
        return datetime.datetime.now() >= self.next_run

    def run(self):
        """Run the job and immediately reschedule it."""
        logger.info('Running job %s', self)
        self.job_func()
        self.last_run = datetime.datetime.now()
        self._schedule_next_run()

    def _schedule_next_run(self):
        """Compute the instant when this job should run next."""
        # Allow *, ** magic temporarily:
        # pylint: disable=W0142
        assert self.unit in ('seconds', 'minutes', 'hours', 'days', 'weeks')
        self.period = datetime.timedelta(**{self.unit: self.interval})
        self.next_run = datetime.datetime.now() + self.period
        if self.at_time:
            assert self.unit == 'days'
            self.next_run = self.next_run.replace(hour=self.at_time.hour,
                                                  minute=self.at_time.minute,
                                                  second=self.at_time.second,
                                                  microsecond=0)
            # If we are running for the first time, make sure we run
            # at the specified time *today* as well
            if (not self.last_run and
                    self.at_time > datetime.datetime.now().time()):
                self.next_run = self.next_run - datetime.timedelta(days=1)


# The following methods are shortcuts for not having to
# create a Scheduler instance:

default_scheduler = Scheduler()
jobs = default_scheduler.jobs  # todo: should this be a copy, e.g. jobs()?


def every(interval=1):
    """Schedule a new periodic job."""
    return default_scheduler.every(interval)


def run_continuously(interval=1):
    """Continuously run, while executing pending jobs at each elapsed
    time interval.

    @return cease_continuous_run: threading.Event which can be set to
    cease continuous run.

    Please note that it is *intended behavior that run_continuously()
    does not run missed jobs*. For example, if you've registered a job
    that should run every minute and you set a continuous run interval
    of one hour then your job won't be run 60 times at each interval but
    only once.
    """
    return default_scheduler.run_continuously(interval)


def run_pending():
    """Run all jobs that are scheduled to run.

    Please note that it is *intended behavior that run_pending()
    does not run missed jobs*. For example, if you've registered a job
    that should run every minute and you only call run_pending()
    in one hour increments then your job won't be run 60 times in
    between but only once.
    """
    default_scheduler.run_pending()


def run_all(delay_seconds=0):
    """Run all jobs regardless if they are scheduled to run or not.

    A delay of `delay` seconds is added between each job. This can help
    to distribute the system load generated by the jobs more evenly over
    time."""
    default_scheduler.run_all(delay_seconds=delay_seconds)


def clear():
    """Deletes all scheduled jobs."""
    default_scheduler.clear()


def next_run():
    """Datetime when the next job should run."""
    return default_scheduler.next_run


def idle_seconds():
    """Number of seconds until `next_run`."""
    return default_scheduler.idle_seconds
