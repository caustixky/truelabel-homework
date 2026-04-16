import math

from locust import HttpUser, LoadTestShape, constant_throughput, task


class ApiUser(HttpUser):
    # 1 user ~ 1 rps roughly
    wait_time = constant_throughput(1)

    @task
    def hit_endpoint(self):
        self.client.get("/api/v1/test")


class AdaptiveStepShape(LoadTestShape):
    """
    Step-wise load shape that finds the service's degradation point.

    Each step grows the user count by STEP_INCREASE (+5% per the task)
    and runs a three-phase cycle: SPAWN -> STABILIZE -> MEASURE.

    The phases exist because you can only draw conclusions from a steady
    state. During SPAWN users are still being started, so response times
    reflect Locust's ramp, not the SUT. During STABILIZE users are all
    live but the SUT is still settling (cold caches, connection pools,
    autoscalers). Only in MEASURE is the system in a state worth reading;
    that's also where we reset stats so the p95 is scoped to this step
    alone and not diluted by the previous one.

    After MEASURE we compare the step's p95 to the previous step's.
    If it jumped by P95_REGRESSION_RATIO (+20%) or more, we've crossed
    the degradation point — we stop the test and print the user count
    at which it happened. Otherwise we bump the target and loop.
    """

    START_USERS = 100
    STEP_INCREASE = 0.05
    MAX_USERS = 2000

    STABILIZE_SECONDS = 30
    MEASURE_SECONDS = 30

    P95_REGRESSION_RATIO = 1.20
    SPAWN_RATE = 100

    SPAWN, STABILIZE, MEASURE = "spawn", "stabilize", "measure"

    def __init__(self):
        super().__init__()
        self.target_users = self.START_USERS
        self.state = self.SPAWN
        self.phase_started_at = 0.0
        self.prev_p95 = None

    def tick(self):
        if self.target_users > self.MAX_USERS:
            return None

        now = self.get_run_time()

        if self.state == self.SPAWN:
            if self.get_current_user_count() >= self.target_users:
                self._enter(self.STABILIZE, now)
            return self.target_users, self.SPAWN_RATE

        if self.state == self.STABILIZE:
            if self._wait_for_stabilization(now):
                self.runner.stats.reset_all()
                self._enter(self.MEASURE, now)
            return self.target_users, self.SPAWN_RATE

        if self.state == self.MEASURE:
            if now - self.phase_started_at < self.MEASURE_SECONDS:
                return self.target_users, self.SPAWN_RATE

            stats = self.runner.stats.total

            if stats.num_requests == 0 or stats.num_failures == stats.num_requests:
                return None

            p95 = stats.get_response_time_percentile(0.95) or 0
            effective_rps = stats.num_requests / self.MEASURE_SECONDS

            if self._regressed(p95):
                self._print_report(p95, effective_rps)
                return None

            self.prev_p95 = p95
            self.target_users = math.ceil(self.target_users * (1 + self.STEP_INCREASE))
            self._enter(self.SPAWN, now)
            return self.target_users, self.SPAWN_RATE

        return None

    def _enter(self, state, now):
        self.state = state
        self.phase_started_at = now

    def _wait_for_stabilization(self, now) -> bool:
        """
        Returns True once the SUT is considered stable at the current load.

        Called every tick while in STABILIZE; MEASURE starts on the first
        tick that returns True.

        The simplest possible check is used here — just wait a fixed number
        of seconds. It's enough for the task, but any readiness logic fits:
        poll /health, wait for RPS to flatten, watch queue depth, error
        rate, GC pauses, CPU saturation — anything that proves the system
        has actually settled before we trust the p95 reading.
        """
        return now - self.phase_started_at >= self.STABILIZE_SECONDS

    def _regressed(self, p95):
        if self.prev_p95 is None or self.prev_p95 <= 0:
            return False
        return p95 >= self.prev_p95 * self.P95_REGRESSION_RATIO

    def _print_report(self, p95, rps):
        print(f"Threshold passed at {self.target_users} users (~{rps:.0f} RPS)")
        print(f"p95: {self.prev_p95:.0f}ms -> {p95:.0f}ms")
