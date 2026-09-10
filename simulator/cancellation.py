"""Cooperative cancellation, including an in-flight local-model HTTP request."""
import threading


class SimulationCancelled(Exception):
    pass


class Cancellation:
    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.callbacks = set()

    def check(self):
        if self.event.is_set():
            raise SimulationCancelled('Conversation cancelled')

    def wait(self, seconds):
        if self.event.wait(seconds):
            self.check()

    def register(self, callback):
        with self.lock:
            self.check()
            self.callbacks.add(callback)
        def unregister():
            with self.lock:
                self.callbacks.discard(callback)
        return unregister

    def cancel(self):
        with self.lock:
            self.event.set()
            callbacks = list(self.callbacks)
        for callback in callbacks:
            try:
                callback()
            except OSError:
                pass
