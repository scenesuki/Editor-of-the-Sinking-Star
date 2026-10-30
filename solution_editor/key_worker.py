"""独立输入进程：主进程失联或单次持键超时即释放。"""

import json
import queue
import threading
import time


ALLOWED_KEYS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') | {'Up', 'Down', 'Left', 'Right', 'Space',
    'Tab', 'Enter', 'Backspace', 'Delete'}


class PressRejected(RuntimeError):
    """发送前明确拒绝；没有注入事件，也没有取得该物理键的释放责任。"""


def serve(source, output, emit, *, max_hold_ms=500, check_held=None, check_pending=None):
    """运行在独立进程。emit 的按下分支仍必须核对目标与焦点。

    EOF、非法消息、超时只退出，不重试按下。释放失败会报告并在 finally 再试一次。
    不能保证操作系统拒绝注入或此工作进程自身被杀时仍能释放。
    """
    if type(max_hold_ms) is not int or not 0 < max_hold_ms <= 500:
        raise ValueError('Invalid key hold limit')
    messages = queue.Queue(maxsize=64)
    finished = threading.Event()

    def reader():
        try:
            while not finished.is_set():
                line = source.readline()
                if len(line) > 1024:
                    raise ValueError('Input message too large')
                messages.put(line, timeout=.1)
                if not line:
                    return
        except Exception as error:
            try:
                messages.put(error, timeout=.1)
            except queue.Full:
                finished.set()

    def report(value):
        try:
            output.write(json.dumps(value) + '\n')
            output.flush()
        except (BrokenPipeError, OSError):
            finished.set()

    held = None
    released = True
    deadline = None  # 没有持键时允许任意长度的等待步骤；父进程断开由 EOF 收尾。
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        while not finished.is_set():
            if check_pending is not None:
                check_pending()
            # 不依赖主界面轮询；仅在本进程持键期间检查，允许失焦准备和空闲。
            if held is not None and check_held is not None:
                check_held()
            remaining = deadline - time.monotonic() if deadline is not None else .02
            if remaining <= 0:
                raise TimeoutError('Key worker timeout')
            try:
                line = messages.get(timeout=min(.02, remaining))
            except queue.Empty:
                continue
            if isinstance(line, Exception):
                raise line
            if not line:
                break
            message = json.loads(line)
            if (type(message) is not dict or set(message) != {'id', 'key', 'down'}
                    or type(message['id']) is not int or message['id'] < 1
                    or type(message['key']) is not str or message['key'] not in ALLOWED_KEYS
                    or type(message['down']) is not bool):
                raise ValueError('Invalid input message')
            key, down = message['key'], message['down']
            if down:
                if held is not None:
                    raise ValueError('Overlapping key press')
                held = key  # 发送失败也保留释放责任。
                deadline = time.monotonic() + max_hold_ms / 1000
                try:
                    emit(key, True)
                except PressRejected:
                    held = None
                    raise
            else:
                if held != key:
                    raise ValueError('Release does not match owned key')
                emit(key, False)
                held = None
                deadline = None
            report({'id': message['id'], 'ok': True})
    except Exception as error:
        report({'error': str(error)})
    finally:
        if held is not None:
            try:
                emit(held, False)
            except Exception as error:
                released = False
                report({'error': f'Final release failed: {error}'})
        finished.set()
    return released
