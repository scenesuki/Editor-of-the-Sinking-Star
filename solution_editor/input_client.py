"""独立按键进程的有确认发送接口。"""

import json
import queue
import subprocess
import threading


class InputWorkerClient:
    def __init__(self, command: list[str], *, require_ready=False, require_release=False) -> None:
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                        bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
        self.responses = queue.Queue()
        self._sequence = 0
        self.closed = False
        self.require_release, self.released = require_release, False
        self.fault: str | None = None
        self.own_tag=None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        if require_ready:
            try:
                response = self.responses.get(timeout=3)
                if (not isinstance(response,dict) or response.get('ready') is not True
                    or set(response) not in ({'ready'},{'ready','own_tag'})):
                    raise RuntimeError(response.get('error','Invalid worker startup acknowledgement') if isinstance(response,dict) else 'Invalid worker startup acknowledgement')
                if 'own_tag' in response:
                    tag=response['own_tag']
                    if not isinstance(tag,str) or not tag.isascii() or not tag.isdigit() or not 0<int(tag)<2**63:
                        raise RuntimeError('Invalid worker input tag')
                    self.own_tag=tag
            except Exception as error:
                self.fault = str(error) or 'Input worker startup timed out'
                try:
                    self.close()
                except Exception as cleanup:
                    raise RuntimeError(f'{self.fault}; startup cleanup: {cleanup}') from error
                raise RuntimeError(self.fault) from error

    def _read(self):
        try:
            for line in self.process.stdout:
                row=json.loads(line)
                if self.require_release and row=={'released':True}:self.released=True
                else:self.responses.put(row)
        except Exception as error:
            self.responses.put({'error': str(error)})
        finally:
            self.responses.put({'error': 'Input worker disconnected'})

    def emit(self, key: str, down: bool) -> None:
        if self.closed or self.fault:
            raise RuntimeError(self.fault or 'Input worker is closed')
        self._sequence += 1
        try:
            self.process.stdin.write(json.dumps({'id': self._sequence, 'key': key, 'down': down}) + '\n')
            self.process.stdin.flush()
            response = self.responses.get(timeout=1)
            if response != {'id': self._sequence, 'ok': True}:
                raise RuntimeError(response.get('error', 'Invalid input acknowledgement'))
        except Exception as error:
            self.fault = str(error) or 'Input worker acknowledgement timed out'
            # 关闭写端让子进程触发 EOF 释放；不自动重试不确定的按下。
            try:
                self.process.stdin.close()
            except OSError:
                pass
            raise RuntimeError(self.fault) from error

    def check(self) -> None:
        """在未等待发送确认时调用，等待步骤中也能发现工作进程异常。"""
        if self.closed or self.fault:
            raise RuntimeError(self.fault or 'Input worker is closed')
        problem = None
        try:
            response = self.responses.get_nowait()
        except queue.Empty:
            if self.process.poll() is not None:
                # 等待读取线程将终止信息入队，保留实际错误原因。
                self._reader.join(timeout=.1)
                try:
                    response = self.responses.get_nowait()
                except queue.Empty:
                    response = {'error': 'Input worker disconnected'}
                problem = response.get('error', 'Unexpected input acknowledgement')
        else:
            problem = response.get('error', 'Unexpected input acknowledgement')
        if problem is not None:
            self.fault = problem
            try:
                self.process.stdin.close()
            except OSError:
                pass
            raise RuntimeError(problem)

    def close(self) -> None:
        if self.closed:
            if self.require_release and (not self.released or self.process.returncode != 0):
                raise RuntimeError('Input worker release was not confirmed')
            return
        try:
            self.process.stdin.close()
        except OSError:
            pass
        # 不能用 terminate 代替工作进程自己的释放。超时必须保留并报告失败。
        self.process.wait(timeout=2)
        self._reader.join(timeout=1)
        self.process.stdout.close()
        self.closed = True
        failures = []
        while not self.responses.empty():
            value = self.responses.get_nowait()
            if 'error' in value and value['error'] != 'Input worker disconnected':
                failures.append(value['error'])
        if failures or self.process.returncode != 0:
            self.fault = '; '.join(failures) or f'Input worker exit {self.process.returncode}'
        if self.require_release:
            if not self.released or self.process.returncode != 0:
                raise RuntimeError('Input worker release was not confirmed: '+(self.fault or 'missing receipt'))
            return
        if failures or self.process.returncode != 0:
            raise RuntimeError(self.fault)

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
