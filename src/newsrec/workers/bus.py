import asyncio


class JobBus:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, job_id):
        signal = asyncio.Event()
        self.subscribers.setdefault(job_id, set()).add(signal)
        return signal

    def unsubscribe(self, job_id, signal):
        group = self.subscribers.get(job_id, set())
        group.discard(signal)
        if not group:
            self.subscribers.pop(job_id, None)

    def publish(self, job_id):
        for signal in self.subscribers.get(job_id, ()):
            signal.set()
