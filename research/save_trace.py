"""有期限的保存路径观察器：仅记录，不暂停、不重定向、不调用游戏函数。"""
import frida


AGENT = r'''
let hooks = [], events = [], dropped = 0, closed = false, sequence = 0;
let limit = 4096, token = '', timer = null;
let stream = false;
const handles = new Map();
const activeItems = new Map(), idleWorkers = new Set();
let trackingErrors = 0;
const counts = {};
function matchesPath(path) {
    return path && path.replace(/\\/g, '/').toLowerCase().includes(token);
}
function record(row) {
    row.sequence = ++sequence;
    row.time_ms = Date.now();
    row.thread = Process.getCurrentThreadId();
    if (events.length < limit) {
        events.push(row);
        if (stream) send({kind: 'save_event', event: row});
    } else dropped++;
}
function itemAt(address) {
    const length = address.readU64().toNumber();
    if (length < 1 || length > 4096) throw Error('Invalid path length: ' + length);
    return {path: address.add(8).readPointer().readUtf8String(length),
            buffer: address.add(16).readPointer().toString(),
            flag: address.add(24).readU64().toString()};
}
function stop() {
    if (closed) return;
    closed = true;
    if (timer !== null) clearTimeout(timer);
    for (const hook of hooks) hook.detach();
    hooks = [];
    Interceptor.flush();
}
function observeFiles() {
    for (const suffix of ['A', 'W']) {
        for (const spec of [
            {name: 'ReplaceFile', tag: 'file_replace', paths: ['path', 'replacement', 'backup'], flags: 3},
            {name: 'MoveFileEx', tag: 'file_move', paths: ['path', 'destination'], flags: 2},
            {name: 'MoveFile', tag: 'file_move', paths: ['path', 'destination']},
            {name: 'DeleteFile', tag: 'file_delete', paths: ['path']}
        ]) {
            hooks.push(Interceptor.attach(Module.getGlobalExportByName(spec.name + suffix), {
                onEnter(args) {
                    this.row = null;
                    try {
                        const paths = {};
                        for (let i = 0; i < spec.paths.length; i++)
                            paths[spec.paths[i]] = args[i].isNull() ? null : suffix === 'W' ?
                                args[i].readUtf16String() : args[i].readUtf8String();
                        if (Object.values(paths).some(matchesPath)) {
                            this.row = Object.assign({tag: spec.tag, api: spec.name + suffix}, paths);
                            if (spec.flags !== undefined) this.row.flags = args[spec.flags].toUInt32();
                        }
                    } catch (_) {}
                },
                onLeave(result) {
                    if (!this.row) return;
                    this.row.success = result.toInt32() !== 0;
                    this.row.last_error = this.row.success ? null : this.lastError;
                    record(this.row);
                }
            }));
        }
        hooks.push(Interceptor.attach(Module.getGlobalExportByName('CreateFile' + suffix), {
            onEnter(args) {
                try {
                    const path = suffix === 'W' ? args[0].readUtf16String() : args[0].readUtf8String();
                    this.path = matchesPath(path) ? path : null;
                    this.access = args[1].toUInt32();
                    this.disposition = args[4].toUInt32();
                } catch (_) { this.path = null; }
            },
            onLeave(result) {
                if (!this.path) return;
                const success = !result.equals(ptr(-1));
                if (success) handles.set(result.toString(), this.path);
                record({tag: 'file_open', path: this.path, handle: result.toString(),
                        access: this.access, disposition: this.disposition, success});
            }
        }));
    }
    hooks.push(Interceptor.attach(Module.getGlobalExportByName('WriteFile'), {
        onEnter(args) {
            this.handle = args[0].toString();
            this.path = handles.get(this.handle);
            this.requested = args[2].toUInt32();
            this.written = args[3];
            this.overlapped = !args[4].isNull();
        },
        onLeave(result) {
            if (!this.path) return;
            let written = null;
            const success = result.toInt32() !== 0;
            if (success && !this.overlapped && !this.written.isNull()) written = this.written.readU32();
            record({tag: 'file_write', path: this.path, handle: this.handle, requested: this.requested,
                    written, success, overlapped: this.overlapped});
        }
    }));
    hooks.push(Interceptor.attach(Module.getGlobalExportByName('CloseHandle'), {
        onEnter(args) { this.handle = args[0].toString(); this.path = handles.get(this.handle); },
        onLeave(result) {
            if (!this.path) return;
            const success = result.toInt32() !== 0;
            record({tag: 'file_close', path: this.path, handle: this.handle, success});
            if (success) handles.delete(this.handle);
        }
    }));
    hooks.push(Interceptor.attach(Module.getGlobalExportByName('FlushFileBuffers'), {
        onEnter(args) { this.handle = args[0].toString(); this.path = handles.get(this.handle); },
        onLeave(result) {
            if (!this.path) return;
            const success = result.toInt32() !== 0;
            record({tag: 'file_flush', path: this.path, handle: this.handle,
                    success, last_error: success ? null : this.lastError});
        }
    }));
}
rpc.exports = {
    install(config) {
        limit = config.max_events;
        token = config.path_token.replace(/\\/g, '/').toLowerCase();
        stream = config.stream_events;
        for (const point of config.points) {
            const actual = Array.from(new Uint8Array(ptr(point.address).readByteArray(
                point.expected_code.length / 2)), b => b.toString(16).padStart(2, '0')).join('');
            if (actual !== point.expected_code) throw Error('Code fingerprint mismatch: ' + point.tag);
        }
        try {
            for (const point of config.points) {
                hooks.push(Interceptor.attach(ptr(point.address), function () {
                    counts[point.tag] = (counts[point.tag] || 0) + 1;
                    if (point.counter_only) return;
                    try {
                        const worker = Process.getCurrentThreadId();
                        if (point.complete_item) {
                            const item = activeItems.get(worker);
                            if (item) {
                                record({tag: 'item_finished', point: point.tag, path: item.path,
                                        buffer: item.buffer, flag: item.flag, started_sequence: item.sequence});
                                activeItems.delete(worker);
                            } else if (!idleWorkers.has(worker)) {
                                record({tag: 'worker_idle', point: point.tag});
                            }
                            idleWorkers.add(worker);
                            return;
                        }
                        if (point.state_register !== undefined) {
                            const manager = this.context[point.state_register];
                            const dirty = manager.add(0x7e7a).readU8();
                            if (!point.dirty_only || dirty !== 0)
                                record({tag: point.tag, manager: manager.toString(), dirty,
                                        blocked: manager.add(0x6700).readU8()});
                            return;
                        }
                        const address = point.stack_offset === undefined ? this.context[point.register] :
                            this.context.rsp.add(point.stack_offset);
                        const item = Object.assign({tag: point.tag}, itemAt(address));
                        if (point.track_item && activeItems.has(worker))
                            throw Error('Unfinished item replaced at worker boundary');
                        record(item);
                        if (point.track_item) activeItems.set(worker, item);
                    } catch (error) {
                        if (point.track_item || point.complete_item) trackingErrors++;
                        record({tag: point.tag, error: String(error)});
                    }
                }));
            }
            if (config.file_io) observeFiles();
            Interceptor.flush();
            timer = setTimeout(stop, config.lifetime_ms);
        } catch (error) { stop(); throw error; }
    },
    snapshot() { return {events, counts, dropped, closed, open_handles: Array.from(handles.entries()),
                        in_flight: Array.from(activeItems.values()), idle_workers: Array.from(idleWorkers),
                        tracking_errors: trackingErrors}; },
    stop
};
'''


class SaveTrace:
    def __init__(self, pid, points, path_token, *, max_events=4096, lifetime_ms=180000,
                 file_io=False, on_event=None):
        if not path_token or not 1 <= max_events <= 100000 or not 1 <= lifetime_ms <= 600000:
            raise ValueError('Expected a path token, bounded event count and lifetime')
        self.session = frida.attach(pid)
        try:
            self.script = self.session.create_script(AGENT)
            if on_event is not None:
                def receive(message, data):
                    if message.get('type') == 'send' and message['payload'].get('kind') == 'save_event':
                        on_event(message['payload']['event'])
                self.script.on('message', receive)
            self.script.load()
            self.script.exports_sync.install(dict(points=points, path_token=path_token,
                max_events=max_events, lifetime_ms=lifetime_ms, file_io=file_io,
                stream_events=on_event is not None))
        except BaseException:
            self.session.detach()
            self.session = None
            raise

    def snapshot(self):
        return self.script.exports_sync.snapshot()

    def close(self):
        if self.session is not None:
            try:
                if not self.session.is_detached:
                    try:
                        self.script.exports_sync.stop()
                    except frida.InvalidOperationError:
                        if not self.session.is_detached:
                            raise
            finally:
                self.session.detach()
                self.session = None

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
