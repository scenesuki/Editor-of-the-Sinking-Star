"""异步快速完成任务：不阻塞界面轮询，停止时撤销尚未执行的请求。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event


class CompletionJob:
    def __init__(self,runtime):
        self.cancelled=Event()
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='complete-tile')
        self.future=self.executor.submit(runtime.command,dict(action='complete_tile',_cancel=self.cancelled))
        self.executor.shutdown(wait=False)

    @property
    def done(self):return self.future.done()

    def poll(self):
        if not self.done:return False
        self.future.result()
        return True

    def cancel(self):self.cancelled.set()
