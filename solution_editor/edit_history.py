"""有界编辑历史；只保存脚本文档，不操作游戏现场。"""
import json


class EditHistory:
    def __init__(self, *, max_entries=50, max_bytes=32*1024*1024):
        self.max_entries,self.max_bytes=max_entries,max_bytes
        self.clear()

    def clear(self):
        self._undo=[];self._redo=[]

    @property
    def can_undo(self):return bool(self._undo)

    @property
    def can_redo(self):return bool(self._redo)

    @property
    def bytes_used(self):return sum(len(a)+len(b) for a,b in self._undo+self._redo)

    def push(self,before,after):
        pack=lambda row:json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        entry=pack(before),pack(after)
        if entry[0]==entry[1]:return
        self._redo.clear();self._undo.append(entry)
        while self._undo and (len(self._undo)>self.max_entries or self.bytes_used>self.max_bytes):
            self._undo.pop(0)

    def undo(self):
        if not self._undo:raise ValueError('没有可撤销的编辑。')
        entry=self._undo.pop();self._redo.append(entry)
        return json.loads(entry[0])

    def redo(self):
        if not self._redo:raise ValueError('没有可重做的编辑。')
        entry=self._redo.pop();self._undo.append(entry)
        return json.loads(entry[1])
