"""Chrome DevTools Protocol session over WebSocket."""

import base64
import json
import time
import urllib.request

from wsclient import WebSocket, WSError


class CDPError(Exception):
    pass


def _get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def alive(port):
    try:
        _get_json('http://127.0.0.1:%d/json/version' % port, timeout=3)
        return True
    except Exception:
        return False


def pick_page(port, url_like='', timeout=5):
    targets = _get_json('http://127.0.0.1:%d/json/list' % port, timeout=timeout)
    pages = [t for t in targets if t.get('type') == 'page']
    if not pages:
        raise CDPError('no page target')
    if url_like:
        for page in pages:
            if url_like in (page.get('url') or ''):
                return page
    return pages[0]


class CDP:
    def __init__(self, port=9340, url_like='', timeout=30.0, ws_url=None):
        self.port = port
        if ws_url:
            page = {'url': ws_url, 'webSocketDebuggerUrl': ws_url}
        else:
            page = pick_page(port, url_like)
        self.page = page
        self.ws = WebSocket(page['webSocketDebuggerUrl'], timeout=timeout)
        self.msg_id = 0
        self.timeout = timeout

    # ---------- core ----------

    def send(self, method, params=None):
        self.msg_id += 1
        mid = self.msg_id
        payload = json.dumps(
            {'id': mid, 'method': method, 'params': params or {}},
            ensure_ascii=False,
        )
        self.ws.send_text(payload)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            raw = self.ws.recv_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get('id') == mid:
                return msg
        raise CDPError('timeout: ' + method)

    def evaluate(self, expression):
        r = self.send('Runtime.evaluate', {
            'expression': expression,
            'returnByValue': True,
            'awaitPromise': True,
            'userGesture': True,
        })
        result = r.get('result') or {}
        if result.get('exceptionDetails'):
            return 'EXC: ' + str((result['exceptionDetails'] or {}).get('text'))
        return (result.get('result') or {}).get('value')

    def navigate(self, url, wait_ms=4000):
        r = self.send('Page.navigate', {'url': url})
        if r.get('error'):
            return 'NAV ERR: ' + json.dumps(r['error'], ensure_ascii=False)
        deadline = time.time() + wait_ms / 1000.0
        time.sleep(0.25)
        while time.time() < deadline:
            try:
                if str(self.evaluate('String(document.readyState)')) == 'complete':
                    break
            except Exception:
                pass
            time.sleep(0.2)
        return 'ok'

    def screenshot(self, clip=None):
        params = {'format': 'png'}
        if clip:
            params['clip'] = clip
        else:
            params['captureBeyondViewport'] = False
        r = self.send('Page.captureScreenshot', params)
        data = (r.get('result') or {}).get('data')
        return base64.b64decode(data) if data else None

    def save_screenshot(self, path, clip=None):
        blob = self.screenshot(clip)
        if not blob:
            return False
        with open(path, 'wb') as f:
            f.write(blob)
        return True

    def enable(self):
        self.send('Page.enable')
        return self

    def add_init_script(self, source):
        self.send('Page.addScriptToEvaluateOnNewDocument', {'source': source})

    # ---------- input ----------

    def mouse_move(self, x, y):
        self.send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': int(x), 'y': int(y)})

    def mouse_press(self, x, y):
        self.send('Input.dispatchMouseEvent', {
            'type': 'mousePressed', 'x': int(x), 'y': int(y),
            'button': 'left', 'clickCount': 1, 'buttons': 1,
        })

    def mouse_release(self, x, y):
        self.send('Input.dispatchMouseEvent', {
            'type': 'mouseReleased', 'x': int(x), 'y': int(y),
            'button': 'left', 'clickCount': 1, 'buttons': 0,
        })

    def key_space(self, down=True):
        params = {
            'type': 'keyDown' if down else 'keyUp',
            'windowsVirtualKeyCode': 32,
            'nativeVirtualKeyCode': 32,
            'key': ' ',
            'code': 'Space',
        }
        if down:
            params['text'] = ' '
        self.send('Input.dispatchKeyEvent', params)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


class Reconnect:
    """Keeps a CDP session object that can be reopened when the socket dies."""

    def __init__(self, port, url_like=''):
        self.port = port
        self.url_like = url_like
        self.session = None

    def get(self):
        if self.session is None:
            self.session = CDP(self.port, self.url_like)
            self.session.enable()
        return self.session

    def reopen(self):
        self.close()
        return self.get()

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def evaluate(self, expr):
        try:
            return self.get().evaluate(expr)
        except (WSError, OSError, CDPError):
            return self.reopen().evaluate(expr)
