"""Buff 系统"""
import time


class Buff:
    def __init__(self, btype, end_time, data=None):
        self.type = btype
        self.end_time = end_time
        self.data = data or {}

    @property
    def expired(self):
        return time.time() >= self.end_time
