"""仅保留一次外部游戏按键事件的停机标志，不保存输入文本。"""
import threading


class ExternalInputLatch:
    def __init__(self, watched_keys, own_tag):
        self.watched_keys = frozenset(watched_keys)
        self.own_tag = own_tag
        self._external = threading.Event()

    def feed(self, vk, down, flags, extra_info, foreground):
        if (foreground and down and vk in self.watched_keys
                and not (flags & 0x10 and extra_info == self.own_tag)):
            self._external.set()

    def check(self):
        if self._external.is_set():
            raise RuntimeError('External keyboard event detected; starting state is unknown')
