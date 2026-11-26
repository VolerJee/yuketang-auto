"""Minimal RFC 6455 WebSocket client (client side only, stdlib only)."""

import base64
import os
import socket
import ssl
import struct
from urllib.parse import urlparse


class WSError(Exception):
    pass


class WebSocket:
    def __init__(self, url, timeout=15.0):
        u = urlparse(url)
        host = u.hostname
        port = u.port or (443 if u.scheme == 'wss' else 80)
        path = u.path or '/'
        if u.query:
            path += '?' + u.query

        self.sock = socket.create_connection((host, port), timeout=timeout)
        if u.scheme == 'wss':
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(self.sock, server_hostname=host)

        key = base64.b64encode(os.urandom(16)).decode('ascii')
        request = (
            'GET %s HTTP/1.1\r\n'
            'Host: %s:%d\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            'Sec-WebSocket-Key: %s\r\n'
            'Sec-WebSocket-Version: 13\r\n'
            '\r\n'
        ) % (path, host, port, key)
        self.sock.sendall(request.encode('ascii'))

        self._buf = b''
        while b'\r\n\r\n' not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSError('handshake closed by peer')
            self._buf += chunk
        head, self._buf = self._buf.split(b'\r\n\r\n', 1)
        status = head.split(b'\r\n')[0].decode('latin1')
        if ' 101 ' not in status and not status.endswith(' 101'):
            raise WSError('handshake failed: ' + status)

        self._frag_op = 0
        self._frag_data = b''

    # ---------- low level ----------

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, min(n - len(self._buf), 1 << 20)))
            if not chunk:
                raise WSError('connection closed')
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _recv_frame(self):
        b1, b2 = self._read(2)
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack('!H', self._read(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', self._read(8))[0]
        mask = self._read(4) if masked else None
        data = self._read(length) if length else b''
        if mask:
            data = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        return fin, opcode, data

    def _send_frame(self, opcode, payload):
        header = bytearray()
        header.append(0x80 | opcode)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack('!H', length)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', length)
        mask = os.urandom(4)
        header += mask
        body = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + body)

    # ---------- public ----------

    def send_text(self, text):
        self._send_frame(0x1, text.encode('utf-8'))

    def _send_control(self, opcode, payload=b''):
        self._send_frame(opcode, payload)

    def recv_text(self):
        while True:
            fin, opcode, data = self._recv_frame()
            if opcode == 0x8:
                raise WSError('closed by peer')
            if opcode == 0x9:
                self._send_control(0xA, data)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                self._frag_op = opcode
                self._frag_data = data
            elif opcode == 0x0:
                self._frag_data += data
            else:
                continue
            if fin:
                payload = self._frag_data
                self._frag_data = b''
                if self._frag_op == 0x2:
                    return payload
                return payload.decode('utf-8', 'replace')

    def close(self):
        try:
            self._send_control(0x8, b'')
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
