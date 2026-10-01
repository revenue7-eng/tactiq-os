#!/usr/bin/env python3
"""Reference F and D (format tactiq-model-exec/1) from a .tflite file alone.

Standard library only: the TFLite flatbuffer is read directly, no TensorFlow.
The result must equal what the runtime extends into PCR 14 after loading the
same file on the CPU path (no delegates). The normative definition of the
format, byte for byte, is tactiq-os docs/design/model-runtime-measurement.md,
section 6; if this script and that section disagree, the section wins.

Usage: mk-model-reference.py <model.tflite> [--dump serialization.bin]
"""
import argparse
import hashlib
import struct
import sys

FORMAT = b"tactiq-model-exec/1\x00"
CUSTOM = 32


class Table:
    """Minimal flatbuffer table reader (little-endian, offsets per spec)."""

    def __init__(self, buf, pos):
        self.buf, self.pos = buf, pos
        vt = pos - struct.unpack_from("<i", buf, pos)[0]
        self.vt_len = struct.unpack_from("<H", buf, vt)[0]
        self.vt = vt

    def _off(self, field):
        o = 4 + 2 * field
        if o >= self.vt_len:
            return 0
        return struct.unpack_from("<H", self.buf, self.vt + o)[0]

    def scalar(self, field, fmt, default=0):
        o = self._off(field)
        return struct.unpack_from(fmt, self.buf, self.pos + o)[0] if o else default

    def _indirect(self, field):
        o = self._off(field)
        if not o:
            return None
        p = self.pos + o
        return p + struct.unpack_from("<I", self.buf, p)[0]

    def table(self, field):
        p = self._indirect(field)
        return Table(self.buf, p) if p is not None else None

    def vector(self, field):
        """(start, length) of a vector field, or None."""
        p = self._indirect(field)
        if p is None:
            return None
        return p + 4, struct.unpack_from("<I", self.buf, p)[0]

    def tables(self, field):
        v = self.vector(field)
        if v is None:
            return []
        start, n = v
        out = []
        for i in range(n):
            q = start + 4 * i
            out.append(Table(self.buf, q + struct.unpack_from("<I", self.buf, q)[0]))
        return out

    def scalars(self, field, fmt):
        v = self.vector(field)
        if v is None:
            return []
        start, n = v
        size = struct.calcsize(fmt)
        return [struct.unpack_from(fmt, self.buf, start + size * i)[0] for i in range(n)]

    def bytes_(self, field):
        v = self.vector(field)
        if v is None:
            return b""
        start, n = v
        return bytes(self.buf[start:start + n])


def measure(buf):
    if len(buf) < 8 or buf[4:8] != b"TFL3":
        raise ValueError("not a TFLite flatbuffer (file identifier TFL3 missing)")
    f_raw = hashlib.sha256(buf).digest()
    model = Table(buf, struct.unpack_from("<I", buf, 0)[0])
    # Model: 1 operator_codes, 2 subgraphs, 4 buffers
    opcodes = model.tables(1)
    subgraphs = model.tables(2)
    buffers = model.tables(4)
    if not subgraphs:
        raise ValueError("model has no subgraphs")
    sg = subgraphs[0]
    tensors = sg.tables(0)       # SubGraph: 0 tensors
    operators = sg.tables(3)     # SubGraph: 3 operators

    def buffer_data(tensor):
        bi = tensor.scalar(2, "<I")          # Tensor: 2 buffer
        if bi == 0:
            return None
        if bi >= len(buffers):
            raise ValueError(f"tensor refers to buffer {bi}, model has {len(buffers)}")
        b = buffers[bi]
        data = b.bytes_(0)                   # Buffer: 0 data
        if data:
            return data
        off = b.scalar(1, "<Q")              # Buffer: 1 offset (large models)
        size = b.scalar(2, "<Q")             # Buffer: 2 size
        if off > 1 and size:
            return bytes(buf[off:off + size])
        return None

    # The runtime and this script must agree on what a constant is. The
    # runtime calls a tensor constant when its allocation is read-only, which
    # TFLite gives to exactly the tensors that carry buffer data. TFLite
    # (checked in 2.21.0, InterpreterBuilder::ParseTensors) refuses to load a
    # model where a tensor has buffer data and is_variable or external_buffer
    # set, so such a model never reaches the runtime measurement. Refuse it
    # here too, instead of producing a D the device can never produce.
    for si, sub in enumerate(subgraphs):
        for ti, ten in enumerate(sub.tables(0)):
            bi = ten.scalar(2, "<I")
            if bi == 0:
                continue
            if bi >= len(buffers):
                raise ValueError(f"subgraph {si} tensor {ti} refers to buffer {bi}, "
                                 f"model has {len(buffers)}")
            b = buffers[bi]
            has_data = bool(b.bytes_(0)) or (b.scalar(1, "<Q") > 1 and b.scalar(2, "<Q"))
            if has_data and (ten.scalar(5, "<?", False) or ten.scalar(10, "<I")):
                raise ValueError(f"subgraph {si} tensor {ti}: buffer data with is_variable "
                                 "or external_buffer; TFLite refuses to load this model")

    s = bytearray(FORMAT)
    s += f_raw
    s += struct.pack("<I", len(operators))
    consts, seen = [], set()
    for op in operators:
        oc = opcodes[op.scalar(0, "<I")]                     # Operator: 0 opcode_index
        code = max(oc.scalar(0, "<b"), oc.scalar(3, "<i"))   # deprecated vs builtin_code
        version = oc.scalar(2, "<i", 1)                      # OperatorCode: 2 version
        name = oc.bytes_(1) if code == CUSTOM else b""       # OperatorCode: 1 custom_code
        s += struct.pack("<iiI", code, version, len(name)) + name
        for t in op.scalars(1, "<i"):                        # Operator: 1 inputs
            if t < 0 or t in seen:
                continue
            if buffer_data(tensors[t]) is not None:
                seen.add(t)
                consts.append(t)
    s += struct.pack("<I", len(consts))
    for t in consts:
        ten = tensors[t]
        data = buffer_data(ten)
        shape = ten.scalars(0, "<i")                         # Tensor: 0 shape
        s += struct.pack("<IiI", t, ten.scalar(1, "<b"), len(shape))  # 1 type
        s += b"".join(struct.pack("<i", d) for d in shape)
        s += struct.pack("<Q", len(data)) + hashlib.sha256(data).digest()
    return f_raw.hex(), hashlib.sha256(bytes(s)).hexdigest(), len(operators), len(consts), bytes(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--dump")
    a = ap.parse_args()
    buf = open(a.model, "rb").read()
    try:
        f, d, n_ops, n_const, ser = measure(buf)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except (struct.error, IndexError) as e:
        print(f"refused: malformed flatbuffer ({e})", file=sys.stderr)
        return 1
    if a.dump:
        open(a.dump, "wb").write(ser)
    print("format  tactiq-model-exec/1")
    print(f"F       {f}")
    print(f"D       {d}")
    print(f"nodes   {n_ops}")
    print(f"consts  {n_const}")


if __name__ == "__main__":
    sys.exit(main())
