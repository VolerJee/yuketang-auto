"""Local paths, config, logging and small file helpers."""

import json
import os
import time


def now_str():
    return time.strftime('%m-%d %H:%M:%S')


class Paths:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.logs = os.path.join(self.root, 'logs')
        self.data = os.path.join(self.root, 'data')
        self.shots = os.path.join(self.data, 'shots')
        for d in (self.logs, self.data, self.shots):
            os.makedirs(d, exist_ok=True)

    def log(self, name):
        return os.path.join(self.logs, name)

    def datafile(self, name):
        return os.path.join(self.data, name)


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def write_text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


class Log:
    """Append one line to a log file and echo it to stdout."""

    def __init__(self, path):
        self.path = path

    def __call__(self, msg):
        line = '[%s] %s' % (now_str(), msg)
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass
        try:
            print(line, flush=True)
        except Exception:
            pass


def set_status(paths, text):
    try:
        write_text(os.path.join(paths.data, 'status.txt'), text)
    except Exception:
        pass


class Config:
    def __init__(self, root):
        self.path = os.path.join(root, 'config.json')
        self.raw = read_json(self.path, {}) or {}

    @property
    def base_url(self):
        return (self.raw.get('baseUrl') or 'https://api.deepseek.com').rstrip('/')

    @property
    def api_key(self):
        return (self.raw.get('apiKey') or '').strip()

    @property
    def has_key(self):
        k = self.api_key
        return bool(k) and len(k) > 10 and k != 'REPLACE_WITH_YOUR_KEY'

    @property
    def model(self):
        return self.raw.get('model') or 'deepseek-flash'

    @property
    def detail(self):
        return self.raw.get('detail') or 'original'

    @property
    def max_tokens(self):
        try:
            return int(self.raw.get('maxTokens') or 800)
        except Exception:
            return 800

    @property
    def homework_enabled(self):
        hw = self.raw.get('homework') or {}
        return bool(hw.get('enabled', True))
