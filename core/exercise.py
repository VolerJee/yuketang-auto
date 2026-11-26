"""Answer one homework, question by question.

Loop shape: read the current question meta -> maybe skip if already graded ->
ask the model (text when the page is readable, screenshot when it is not) ->
select the options -> submit -> read the grade mark -> watch the risk score.
"""

import os
import random
import re
import time

import dom
import model
from human import CHECKBOX, RADIO, Pointer

TRUE_WORDS = ('对', 'T', 'A', 'Y', 'TRUE')
FALSE_WORDS = ('错', 'F', 'B', 'N', 'FALSE')

KIND_JUDGE = '判断题'
KIND_SINGLE = '单选题'
KIND_MULTI = '多选题'


class Exercise:
    def __init__(self, cdp, cfg, paths, log, restorer=None,
                 max_q=40, min_delay=10, max_delay=25, abort_score=40):
        self.cdp = cdp
        self.cfg = cfg
        self.paths = paths
        self.log = log
        self.restorer = restorer
        self.max_q = max_q
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.abort_score = abort_score
        self.pointer = Pointer(cdp, log)
        self.stats_path = paths.datafile('hw_stats.json')
        self.shots = paths.shots
        self.cid = ''
        self.ok = 0
        self.bad = 0
        self.hw_total = 0
        self.hw_done = 0

    # ---------- bookkeeping ----------

    def _restore(self):
        if self.restorer:
            self.restorer.restore()

    def _clear_shots(self):
        try:
            for name in os.listdir(self.shots):
                if name.lower().endswith('.png'):
                    os.remove(os.path.join(self.shots, name))
        except Exception:
            pass

    def _load_stats(self):
        old = None
        try:
            import json
            with open(self.stats_path, 'r', encoding='utf-8-sig') as f:
                old = json.load(f)
        except Exception:
            old = None
        if not old:
            return
        if str(old.get('cid') or '') == str(self.cid):
            self.ok = int(old.get('ok') or 0)
            self.bad = int(old.get('bad') or 0)
            self.hw_total = int(old.get('hwTotal') or 0)
            self.hw_done = int(old.get('hwDone') or 0)

    def _save_stats(self):
        from util import write_json
        try:
            write_json(self.stats_path, {
                'cid': self.cid,
                'ok': self.ok,
                'bad': self.bad,
                'hwTotal': self.hw_total,
                'hwDone': self.hw_done,
                'updated': time.strftime('%H:%M:%S'),
            })
        except Exception:
            pass

    # ---------- actions ----------

    def _wait_label(self, label, timeout_ms):
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            self._restore()
            rect = dom.label_rect(self.cdp, label)
            if rect:
                return rect
            time.sleep(0.3)
        return None

    def _submit(self):
        self._restore()
        before = str(self.cdp.evaluate(dom.ACTIVE_INDEX))

        for attempt in (1, 2):
            btn = self._wait_label('下一题', 3000)
            if btn:
                self.log('      [submit] 下一题=%d,%d' % (btn['x'], btn['y']))
                self.pointer.click(btn)
            confirm = self._wait_label('帮我提交', 5000)
            if confirm:
                self.log('      [submit] 帮我提交=%d,%d' % (confirm['x'], confirm['y']))
                self.pointer.click(confirm)
                break
            self.log('      [submit] 对话框第 %d 次没出现，重试' % attempt)
            time.sleep(0.8)

        time.sleep(2)
        after = before
        for _ in range(16):
            time.sleep(0.5)
            after = str(self.cdp.evaluate(dom.ACTIVE_INDEX))
            if after != before:
                break
        if after != before:
            return True

        sub = self._wait_label('提交', 2500)
        if sub:
            self.pointer.click(sub)
            time.sleep(1.2)
        ok = self._wait_label('确定', 3000)
        if ok:
            self.pointer.click(ok)
            time.sleep(2)

        return str(self.cdp.evaluate(dom.ACTIVE_INDEX)) != before

    def _pick(self, kind, answer, n_radio, n_box):
        if kind == KIND_JUDGE:
            if answer in TRUE_WORDS:
                idx = 0
            elif answer in FALSE_WORDS:
                idx = 1
            else:
                return False
            if 0 <= idx < n_radio:
                return self.pointer.select(self.cdp, RADIO, idx)
            return False

        if kind == KIND_SINGLE:
            if re.match(r'^[A-H]$', answer or ''):
                idx = ord(answer[0]) - 65
                if idx < n_radio:
                    return self.pointer.select(self.cdp, RADIO, idx)
            return False

        letters = sorted(set(ord(ch) - 65 for ch in (answer or '') if 'A' <= ch <= 'H'))
        if not letters or max(letters) >= n_box:
            return False
        all_ok = True
        for idx in letters:
            if not self.pointer.select(self.cdp, CHECKBOX, idx):
                all_ok = False
            time.sleep(random.uniform(0.2, 0.5))
        return all_ok

    def _ask(self, qno):
        rect = None
        raw = self.cdp.evaluate(dom.IFRAME_RECT)
        if raw:
            import json
            try:
                rect = json.loads(raw)
            except Exception:
                rect = None

        q = dom.question_text(self.cdp)
        if q and float(q.get('ratio') or 0) >= 0.15:
            self.log('      文本可读（常见字 %d%%），用文本提问' % int(float(q['ratio']) * 100))
            answer = model.ask(self.cfg, question=q['text'], log=self.log)
            if answer:
                return answer
        else:
            if q is not None:
                self.log('      文本不可读（常见字 %d%%），改用截图' % int(float(q.get('ratio') or 0) * 100))

        shot = None
        for attempt in (1, 2, 3):
            if str(self.cdp.evaluate('String(document.hidden)')) == 'true':
                self._restore()
                time.sleep(2)
            clip = None
            if rect:
                clip = {
                    'x': rect['x'], 'y': rect['y'],
                    'width': min(rect['w'], 1100), 'height': min(rect['h'], 520),
                    'scale': 1,
                }
            shot = self.cdp.screenshot(clip)
            if shot:
                break
            self.log('      截图失败（第 %d 次），恢复窗口后重试' % attempt)
            self._restore()
            time.sleep(random.uniform(1.2, 2.2))

        if not shot:
            self.log('[!] 截图失败，跳过该题')
            return ''

        png = os.path.join(self.shots, 'q%02d.png' % qno)
        with open(png, 'wb') as f:
            f.write(shot)
        return model.ask(self.cfg, png_path=png, log=self.log)

    # ---------- main loop ----------

    def run(self):
        self._clear_shots()

        try:
            href = str(self.cdp.evaluate('location.href'))
            m = re.search(r'/lms-graph/(\d+)/exercise/', href)
            if m:
                self.cid = m.group(1)
        except Exception:
            pass
        self._load_stats()

        start_risk = dom.risk(self.cdp)
        if start_risk:
            self.log('起始风险分 %s  规则: %s' % (start_risk.get('total'), ','.join(start_risk.get('rules') or [])))

        self.log('=== 开始答题 ===')
        correct = wrong = skipped = no_mark = 0
        last_qno = -1
        same_count = 0
        processed = 0

        for _ in range(200):
            meta = dom.meta(self.cdp)
            if not meta:
                self.log('[!] 读不到作业页，结束')
                break

            qno = int(meta['idx']) + 1
            prog = str(self.cdp.evaluate(dom.PROGRESS) or '')
            m = re.match(r'^(\d+)/(\d+)$', prog)
            if m and int(m.group(1)) >= int(m.group(2)):
                self.log('      本作业已完成 %s，结束' % prog)
                break

            if qno == last_qno:
                same_count += 1
            else:
                same_count = 0
                last_qno = qno
            if same_count >= 2:
                self.log('[%d] 连续三次停在同一题，结束' % qno)
                break
            if qno < 1:
                self.log('[!] 取不到题号，结束')
                break

            self._restore()

            mark_now = dom.mark_state(self.cdp, qno - 1)
            if mark_now not in ('none', '?', None):
                self.log('[%d] 已判分，跳过' % qno)
                self.pointer.click_label(self.cdp, '下一题')
                time.sleep(0.9)
                dlg = self._wait_label('先不用了', 1500)
                if dlg:
                    self.pointer.click(dlg)
                    time.sleep(0.8)
                processed += 1
                if processed >= self.max_q:
                    break
                time.sleep(2)
                continue

            self.pointer.drift(random.randint(1, 2))

            kind = meta.get('kind') or '?'
            n_radio = int(meta.get('n') or 0)
            n_box = int(meta.get('nb') or 0)

            if kind not in (KIND_JUDGE, KIND_SINGLE, KIND_MULTI):
                self.log('[%d] 跳过 %s' % (qno, kind))
                skipped += 1
            else:
                time.sleep(random.uniform(1.8, 4.5))
                answer = self._ask(qno)
                picked = self._pick(kind, answer, n_radio, n_box)
                if picked:
                    time.sleep(0.5)
                    self.log('[%d] %s 答=%s' % (qno, kind, answer))
                else:
                    self.log('[%d] %s 模型答=%r 未能作答（选项 %d/%d）' % (qno, kind, answer, n_radio, n_box))
                    time.sleep(0.6)
                    self.pointer.click_label(self.cdp, '下一题')
                    time.sleep(0.9)
                    dlg = self._wait_label('先不用了', 1500)
                    if dlg:
                        self.pointer.click(dlg)
                        time.sleep(0.8)
                    skipped += 1
                    continue

            time.sleep(random.uniform(0.7, 1.6))
            if not self._submit():
                self.log('      提交未生效，继续下一题')
            time.sleep(2)

            mark = dom.mark_state(self.cdp, qno - 1)
            if mark is None or ('success' not in mark and 'danger' not in mark):
                self.log('      这题没有判分结果，补交一次')
                sub2 = self._wait_label('提交', 2000)
                if sub2:
                    self.pointer.click(sub2)
                    time.sleep(0.9)
                ok2 = self._wait_label('确定', 2500)
                if ok2:
                    self.pointer.click(ok2)
                    time.sleep(3)
                else:
                    ok2 = self._wait_label('帮我提交', 2000)
                    if ok2:
                        self.pointer.click(ok2)
                        time.sleep(3)
                mark = dom.mark_state(self.cdp, qno - 1) or ''
                self.log('      补交后结果：%s' % mark)

            if mark and 'success' in mark:
                correct += 1
                self.ok += 1
                self._save_stats()
                self.log('      判定：正确')
            elif mark and 'danger' in mark:
                wrong += 1
                self.bad += 1
                self._save_stats()
                self.log('      判定：错误')
            else:
                no_mark += 1
                self.log('      判定：无标记')

            if str(self.cdp.evaluate(dom.DONE_FLAG)) == 'done':
                self.log('      本作业已全部作答，立刻跳到下一个模块')
                break

            risk = dom.risk(self.cdp)
            if risk:
                groups = risk.get('groups') or {}
                detail = ' '.join('%s=%s' % (k, v) for k, v in groups.items())
                self.log('      风险 %s  %s  规则[%s]  验证=%s' % (
                    risk.get('total'), detail, ','.join(risk.get('rules') or []), risk.get('challenge')))
                if risk.get('challenge'):
                    self.log('      平台要求验证，停止')
                    break
                try:
                    if float(risk.get('total') or 0) >= self.abort_score:
                        self.log('风险分达到 %s，停止' % risk.get('total'))
                        break
                except Exception:
                    pass

            now_idx = -1
            try:
                now_idx = int(str(self.cdp.evaluate(dom.ACTIVE_INDEX)))
            except Exception:
                now_idx = -1
            if now_idx == qno - 1:
                rail = dom.rect(self.cdp, '.subject-item', qno)
                if rail:
                    self.pointer.click(rail)
                    time.sleep(random.uniform(0.8, 1.5))

            processed += 1
            if processed >= self.max_q:
                break
            time.sleep(random.randint(self.min_delay, self.max_delay))

        self.log('')
        total = correct + wrong
        if total > 0:
            self.log('=== 判定 %d 题：正确 %d，错误 %d，正确率 %.1f%%；跳过 %d，无标记 %d ===' % (
                total, correct, wrong, correct * 100.0 / total, skipped, no_mark))
        else:
            self.log('=== 无判定（跳过 %d，无标记 %d）===' % (skipped, no_mark))

        self._clear_shots()
        self.log('（截图已清理）')
        return {'ok': correct, 'bad': wrong, 'skipped': skipped, 'no_mark': no_mark}
