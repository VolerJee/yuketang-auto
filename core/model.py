"""DeepSeek chat client: text question or screenshot, same JSON-answer contract."""

import base64
import json
import random
import re
import time
import urllib.error
import urllib.request

_ANSWER_RE = re.compile(r'"answer"\s*:\s*"([^"]*)"')

SYSTEM_TEXT = 'You are a quiz solver. Output JSON only, no prose.'
SYSTEM_IMAGE = 'You are a quiz solver. One question per image. Output JSON only, no prose.'

TEXT_PROMPT = (
    '题目：\n%s\n\n'
    '判断题输出 {"answer":"对"} 或 {"answer":"错"}；'
    '单选题输出选项字母，如 {"answer":"B"}；'
    '多选题输出全部正确字母，如 {"answer":"AC"}。'
)

IMAGE_PROMPT = (
    'True/false -> {"answer":"对"} or {"answer":"错"}. '
    'Single choice -> the option letter, e.g. {"answer":"B"}. '
    'Multiple choice -> all correct letters together, e.g. {"answer":"AC"}.'
)


def _post(cfg, body, timeout=45):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        cfg.base_url + '/chat/completions',
        data=data,
        headers={
            'Authorization': 'Bearer ' + cfg.api_key,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def _extract(content):
    m = _ANSWER_RE.search(content or '')
    return m.group(1).strip().upper() if m else ''


def _body_text(cfg, question):
    return {
        'model': cfg.model,
        'messages': [
            {'role': 'system', 'content': SYSTEM_TEXT},
            {'role': 'user', 'content': TEXT_PROMPT % question},
        ],
        'max_tokens': 200,
        'thinking': {'type': 'disabled'},
        'stream': False,
    }


def _body_image(cfg, png_b64):
    return {
        'model': cfg.model,
        'messages': [
            {'role': 'system', 'content': SYSTEM_IMAGE},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': IMAGE_PROMPT},
                {'type': 'image_url', 'image_url': {
                    'url': 'data:image/png;base64,' + png_b64,
                    'detail': cfg.detail,
                }},
            ]},
        ],
        'max_tokens': cfg.max_tokens,
        'thinking': {'type': 'disabled'},
        'stream': False,
    }


def _ask_once(cfg, body, log=None, label='模型'):
    for attempt in (1, 2, 3):
        try:
            resp = _post(cfg, body)
            content = ((resp.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
            answer = _extract(content)
            if answer:
                return answer
            if log:
                short = re.sub(r'\s+', ' ', content)[:60]
                log('      %s 返回不含答案（第 %d 次）：%s' % (label, attempt, short))
        except Exception as exc:
            if log:
                log('      %s 请求失败（第 %d 次）：%s' % (label, attempt, exc))
        time.sleep(random.uniform(0.9, 2.1))
    return ''


def ask_text(cfg, question, log=None):
    return _ask_once(cfg, _body_text(cfg, question), log=log, label='文本请求')


def ask_image(cfg, png_path, log=None):
    with open(png_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return _ask_once(cfg, _body_image(cfg, b64), log=log, label='请求')


def ask(cfg, question=None, png_path=None, log=None):
    """Ask once: text when the question is readable, screenshot otherwise."""
    if question:
        return ask_text(cfg, question, log)
    return ask_image(cfg, png_path, log)
