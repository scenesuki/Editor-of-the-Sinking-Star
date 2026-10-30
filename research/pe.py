"""只读解析调查所需的 x64 PE 节区和地址映射，不加载可执行文件。"""

import struct


class PeImage:
    def __init__(self, data):
        self.data = bytes(data)
        try:
            if self.data[:2] != b'MZ':
                raise ValueError('Missing DOS signature')
            pe = struct.unpack_from('<I', self.data, 0x3c)[0]
            if self.data[pe:pe + 4] != b'PE\0\0':
                raise ValueError('Missing PE signature')
            machine, count = struct.unpack_from('<HH', self.data, pe + 4)
            optional_size = struct.unpack_from('<H', self.data, pe + 20)[0]
            optional = pe + 24
            magic = struct.unpack_from('<H', self.data, optional)[0]
            if machine != 0x8664 or magic != 0x20b or optional_size < 0xf0:
                raise ValueError('Expected x64 PE32+')
            self.image_base = struct.unpack_from('<Q', self.data, optional + 24)[0]
            self.header_size = struct.unpack_from('<I', self.data, optional + 60)[0]
            if not 0 < self.header_size <= len(self.data):
                raise ValueError('Invalid header size')
            self.directories = [struct.unpack_from('<II', self.data, optional + 112 + 8 * i)
                                for i in range(16)]
            self.sections = []
            for i in range(count):
                pos = optional + optional_size + i * 40
                name = self.data[pos:pos + 8].rstrip(b'\0').decode('ascii')
                virtual_size, rva, raw_size, offset = struct.unpack_from('<IIII', self.data, pos + 8)
                if offset + raw_size > len(self.data):
                    raise ValueError('Truncated section')
                self.sections.append(dict(name=name, rva=rva, offset=offset,
                                          raw_size=raw_size, virtual_size=virtual_size))
        except (struct.error, UnicodeDecodeError) as error:
            raise ValueError('Malformed PE image') from error

    def rva_to_offset(self, rva):
        if 0 <= rva < self.header_size:
            return rva
        for section in self.sections:
            delta = rva - section['rva']
            if 0 <= delta < section['raw_size']:
                return section['offset'] + delta
        raise ValueError(f'RVA has no file data: {rva:#x}')

    def offset_to_rva(self, offset):
        if 0 <= offset < self.header_size:
            return offset
        for section in self.sections:
            delta = offset - section['offset']
            if 0 <= delta < section['raw_size']:
                return section['rva'] + delta
        raise ValueError(f'Offset has no mapped section: {offset:#x}')

    def runtime_functions(self):
        """读取 x64 异常目录的半开代码范围；缺项不推测叶函数边界。"""
        rva, size = self.directories[3]
        if (rva, size) == (0, 0):
            return []
        if not rva or not size or size % 12:
            raise ValueError('Invalid runtime function table size')
        offset = self.rva_to_offset(rva)
        if self.rva_to_offset(rva + size - 1) != offset + size - 1:
            raise ValueError('Non-contiguous runtime function table')
        result = []
        previous_end = 0
        for pos in range(offset, offset + size, 12):
            begin, end, unwind = struct.unpack_from('<III', self.data, pos)
            if begin >= end or begin < previous_end:
                raise ValueError('Invalid or overlapping runtime function range')
            start = self.rva_to_offset(begin)
            if self.rva_to_offset(end - 1) != start + end - begin - 1:
                raise ValueError('Non-contiguous runtime function code')
            self.rva_to_offset(unwind)
            result.append((begin, end, unwind))
            previous_end = end
        return result
