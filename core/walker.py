"""Course discovery, unit extraction, sequential walk and homework driver."""

import json
import random
import time

import dom
from cdp import alive
from util import read_json, set_status, write_json


INDEX_URL = 'https://www.yuketang.cn/v2/web/index'
STUDENT_LOG = ('https://www.yuketang.cn/v2/web/studentLog/%s'
               '?university_id=3415&platform_id=3&classroom_id=%s&content_url=&tab=content')
UNIT_URL = ('https://www.yuketang.cn/ai-workspace/lms-graph/%s/graph/%s'
            '?is_chapter=1&agentFrom=rain_blended&courseType=1')
VIDEO_URL = ('https://www.yuketang.cn/ai-workspace/lms-graph/%s/video/%s'
             '?is_chapter=1&agentFrom=rain_blended&courseType=1')
FORUM_URL = ('https://www.yuketang.cn/ai-workspace/lms-graph/%s/forum/%s'
             '?is_chapter=1&agentFrom=rain_blended&courseType=1')
EXERCISE_URL = ('https://www.yuketang.cn/ai-workspace/lms-graph/%s/exercise/%s'
                '?is_chapter=1%s&agentFrom=rain_blended&courseType=1')

PHRASES = ('老师好',)

TYPE_VIDEO = 0
TYPE_ARTICLE = 3
TYPE_DISCUSSION = 4
TYPE_HOMEWORK = 6


# ---------------------------------------------------------------- discovery

def discover_courses(cdp, log):
    log('=== 读取课程清单 ===')
    cdp.navigate(INDEX_URL, 8000)
    time.sleep(0.8)

    count, raw = dom.courses(cdp)
    if count <= 0:
        log('  列表为空，切换到「我听的课」…')
        cdp.evaluate(dom.CLICK_MY_COURSES)
        for _ in range(8):
            time.sleep(2)
            count, raw = dom.courses(cdp)
            if count > 0:
                break
    if count <= 0:
        log('课程清单为空，终止')
        return []

    try:
        items = json.loads(raw)['data']['list']
    except Exception:
        log('课程清单解析失败')
        return []

    courses = []
    for item in items:
        courses.append({
            'cid': str(item.get('classroom_id')),
            'name': str(item.get('name') or ''),
            'term': str(item.get('term_name') or ''),
        })
    picked = [c for c in courses if c['term'] == '202601' or '2026' in c['name']]
    log('课程总数 %d，其中 2026 的 %d 门：' % (len(courses), len(picked)))
    for c in picked:
        log('  %s  %s' % (c['cid'], c['name']))
    return picked


def _open_course(cdp, log, cid):
    cdp.navigate(STUDENT_LOG % (cid, cid), 8000)
    frame = ''
    for _ in range(10):
        frame = str(cdp.evaluate(dom.IFRAME_SRC) or '')
        if frame:
            break
        time.sleep(2)
    if not frame:
        log('  没有 iframe，跳过')
        return False
    cdp.navigate(frame, 12000)
    return True


def _wait_capture(cdp, log, timeout=10):
    length = 0
    for _ in range(timeout):
        length = int(str(cdp.evaluate('String((window.__capU||[]).length)') or 0))
        if length > 0:
            break
        time.sleep(2)
    if length <= 0:
        log('  抓不到结构数据，跳过')
        return False
    progress = 0
    for _ in range(8):
        progress = len(str(cdp.evaluate('String(window.__csched||"")') or ''))
        if progress > 100:
            break
        time.sleep(2)
    if progress <= 100:
        log('  ! 没拿到学习进度')
    return True


def extract_units(cdp, course, paths, log):
    cid = course['cid']
    if not _open_course(cdp, log, cid):
        return None
    if not _wait_capture(cdp, log):
        return None
    data = dom.units(cdp)
    if not data:
        log('  解析失败，跳过')
        return None
    path = paths.datafile('ykt_units_%s.json' % cid)
    write_json(path, data)
    counts = data.get('counts') or {}
    log('  单元 %d：视频 %s / 图文 %s / 讨论 %s / 作业 %s' % (
        data.get('total'),
        counts.get('0', 0), counts.get('3', 0), counts.get('4', 0), counts.get('6', 0)))
    return data


# ---------------------------------------------------------------- walk

class Walker:
    def __init__(self, cdp, cfg, paths, log, restorer=None, homework_enabled=False):
        self.cdp = cdp
        self.cfg = cfg
        self.paths = paths
        self.log = log
        self.restorer = restorer
        self.homework_enabled = homework_enabled
        self.done_path = paths.datafile('ykt_walk_done.json')
        self.done = set(read_json(self.done_path, []) or [])

    def _save_done(self, unit_id):
        self.done.add(unit_id)
        write_json(self.done_path, sorted(self.done, key=str))

    def _restore(self):
        if self.restorer:
            self.restorer.restore()

    def _alive(self, port):
        return alive(port)

    def run(self, units, classroom, port):
        if not units:
            self.log('课程结构为空')
            return

        counts = {}
        for u in units:
            counts[u.get('type')] = counts.get(u.get('type'), 0) + 1
        self.log('计划: 共 %d 单元  视频=%s 图文=%s 讨论=%s 作业=%s 考试=%s' % (
            len(units), counts.get(0, 0), counts.get(3, 0), counts.get(4, 0),
            counts.get(6, 0), counts.get(5, 0)))

        finished = len([u for u in units if u.get('prog') is not None and float(u['prog']) >= 0.999])
        self.log('平台已标记完成: %d / %d 个单元' % (finished, len(units)))
        self.log('classroom=%s' % classroom)
        if self.homework_enabled:
            self.log('作业自动答题: 已启用')
        else:
            self.log('作业自动答题: 未启用（缺少 API Key）')

        for index, unit in enumerate(units, 1):
            if not self._alive(port):
                self.log('浏览器已关闭，程序退出')
                break
            uid = unit.get('id')
            if uid in self.done:
                continue
            if unit.get('prog') is not None and float(unit['prog']) >= 0.999:
                self._save_done(uid)
                continue

            tag = '[%d/%d]' % (index, len(units))
            kind = int(unit.get('type') or -1)
            try:
                if kind == TYPE_ARTICLE:
                    self._article(tag, unit, classroom)
                elif kind == TYPE_VIDEO:
                    self._video(tag, unit, classroom)
                elif kind == TYPE_DISCUSSION:
                    self._discussion(tag, unit, classroom)
                elif kind == TYPE_HOMEWORK:
                    self._homework(tag, unit, classroom, port)
                else:
                    self.log('%s 跳过 type=%s  %s/%s' % (tag, kind, unit.get('chap'), unit.get('name')))
            except Exception as exc:
                self.log('%s 单元出错: %s' % (tag, exc))

        pct = str(self.cdp.evaluate(
            "var t=(document.body&&document.body.innerText)||''; (t.match(/完成度[^\\n]{0,12}/)||[''])[0]") or '')
        self.log('=== 结束，%s ===' % pct)

    # ---------- per type ----------

    def _article(self, tag, unit, classroom):
        self.cdp.navigate(UNIT_URL % (classroom, unit['id']), 6000)
        set_status(self.paths, '正在打开图文：%s' % unit.get('name'))
        self.log('%s 图文  %s/%s' % (tag, unit.get('chap'), unit.get('name')))
        self._save_done(unit['id'])

    def _video(self, tag, unit, classroom):
        self.cdp.navigate(VIDEO_URL % (classroom, unit['id']), 9000)
        self.cdp.evaluate(dom.CTRL)

        duration = 0
        for _ in range(8):
            time.sleep(2)
            value = self.cdp.evaluate(
                "var v=document.querySelector('video'); v&&isFinite(v.duration)? Math.round(v.duration):0")
            if value:
                duration = int(value)
                break
        if duration <= 0:
            time.sleep(5)
            value = self.cdp.evaluate(
                "var v=document.querySelector('video'); v&&isFinite(v.duration)? Math.round(v.duration):0")
            if value:
                duration = int(value)
        if duration <= 0:
            self.log('%s 视频 no-video  %s/%s' % (tag, unit.get('chap'), unit.get('name')))
            return

        self.log('%s 视频  %ds  %s/%s' % (tag, duration, unit.get('chap'), unit.get('name')))
        set_status(self.paths, '正在看视频：%s　2 倍速　全长 %d 分钟' % (unit.get('name'), (duration + 119) // 120))

        deadline = time.time() + max(180, duration // 2 + 200)
        ok = False
        current = 0
        while time.time() < deadline:
            wait = 6
            if current > 0:
                wait = min(15, max(2, (duration - current) // 2))
            time.sleep(wait)
            raw = self.cdp.evaluate(
                "var v=document.querySelector('video'); v? JSON.stringify({c:Math.round(v.currentTime),"
                "d:Math.round(v.duration||0),e:v.ended}) : ''")
            if not raw:
                break
            state = json.loads(raw)
            current = int(state.get('c') or 0)
            left = max(0, (duration - current) // 2)
            set_status(self.paths, '正在看视频：%s　2 倍速　还剩 %d 分 %02d 秒' % (
                unit.get('name'), left // 60, left % 60))
            if state.get('e') or current >= int(state.get('d') or 0) - 1:
                ok = True
                break
            self.cdp.evaluate(dom.CTRL)

        if ok:
            self._save_done(unit['id'])
        else:
            self.log('%s 视频 timeout' % tag)

    def _discussion(self, tag, unit, classroom):
        self.cdp.navigate(FORUM_URL % (classroom, unit['id']), 10000)
        text = random.choice(PHRASES)
        set_status(self.paths, '正在发讨论：%s' % unit.get('name'))

        fill = ("(function(){var t=document.querySelectorAll('textarea')[0];if(!t)return 'no box';"
                "var st=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
                "st.call(t,'%s');t.dispatchEvent(new Event('input',{bubbles:true}));return 'filled';})()") % text
        r1 = self.cdp.evaluate(fill)

        r2 = ''
        for _ in range(30):
            r2 = self.cdp.evaluate(
                "var b=document.querySelector('.prompt-send-btn'); if(!b){'no btn'} "
                "else if(b.classList.contains('disabled')){'disabled'} else {'ready'}")
            if r2 != 'disabled':
                break
            time.sleep(0.1)

        if r2 == 'ready':
            r2 = self.cdp.evaluate(
                "var b=document.querySelector('.prompt-send-btn'); if(!b){'no btn'} "
                "else { b.click(); 'clicked' }")

        seen = 'missing'
        for _ in range(12):
            time.sleep(0.5)
            seen = self.cdp.evaluate(
                "var b=(document.body&&document.body.innerText)||''; b.indexOf('%s')>=0?'ok':'missing'" % text)
            if seen == 'ok':
                break

        if r2 == 'clicked' and seen == 'ok':
            self.log('%s 讨论  %s/%s -> 「%s」' % (tag, unit.get('chap'), unit.get('name'), text))
            self._save_done(unit['id'])
        else:
            self.log('%s 讨论 失败 fill=%s click=%s seen=%s' % (tag, r1, r2, seen))

    def _homework(self, tag, unit, classroom, port):
        if not (self.homework_enabled and self.cfg.has_key):
            self.log('%s 作业 需你自己做  %s/%s' % (tag, unit.get('chap'), unit.get('name')))
            return
        self.log('%s 作业  %s/%s' % (tag, unit.get('chap'), unit.get('name')))
        node_q = '&node_id=%s' % unit['node_id'] if int(unit.get('node_id') or 0) > 0 else ''
        self.cdp.navigate(EXERCISE_URL % (classroom, unit['id'], node_q), 12000)
        ready = False
        for attempt in range(10):
            if attempt:
                time.sleep(2)
            if str(self.cdp.evaluate("String(document.querySelectorAll('iframe').length)")) != '0':
                ready = True
                break
        if not ready:
            self.log('%s 作业页没加载出来' % tag)
            return

        from exercise import Exercise
        exercise = Exercise(self.cdp, self.cfg, self.paths, self.log, self.restorer, max_q=60)
        exercise.run()
        self._save_done(unit['id'])


# ---------------------------------------------------------------- homework

def homework_units(cdp, course, paths, log):
    if not _open_course(cdp, log, course['cid']):
        return None
    if not _wait_capture(cdp, log):
        return None
    return dom.homework_units(cdp)


def run_homework(cdp, cfg, paths, log, restorer, courses, max_q=60, only_cid=''):
    total_done = 0
    total_skip = 0
    for course in courses:
        if only_cid and course['cid'] != only_cid:
            continue
        log('')
        log('=== %s (%s) ===' % (course['name'], course['cid']))
        set_status(paths, '正在处理课程：%s' % course['name'])
        units = homework_units(cdp, course, paths, log)
        if units is None:
            log('  没有作业单元')
            continue
        todo = [u for u in units if u.get('prog') is None or float(u['prog']) < 0.999]
        log('  作业 %d 个，未完成 %d 个' % (len(units), len(todo)))
        total_skip += len(units) - len(todo)

        for unit in todo:
            log('  -> %s/%s' % (unit.get('chap'), unit.get('name')))
            set_status(paths, '正在答作业：%s' % unit.get('name'))
            node_q = '&node_id=%s' % unit['node'] if int(unit.get('node') or 0) > 0 else ''
            url = EXERCISE_URL % (course['cid'], unit['id'], node_q)
            cdp.navigate(url, 12000)

            ready = False
            for attempt in range(10):
                if attempt:
                    time.sleep(2)
                if str(cdp.evaluate(
                        "String(location.href.indexOf('/exercise/')>=0 "
                        "&& document.querySelectorAll('iframe').length>0)")) == 'true':
                    ready = True
                    break
            if not ready:
                log('     作业页没加载出来')
                continue

            from exercise import Exercise
            Exercise(cdp, cfg, paths, log, restorer, max_q=max_q).run()

            left = -1
            try:
                left = int(str(cdp.evaluate(dom.LEFT_QUESTIONS)))
            except Exception:
                left = -1
            if left > 0:
                log('     复查：还有 %d 题没有完成，重新作答' % left)
                Exercise(cdp, cfg, paths, log, restorer, max_q=max_q).run()
                try:
                    left = int(str(cdp.evaluate(dom.LEFT_QUESTIONS)))
                except Exception:
                    left = -1
            if left == 0:
                log('     复查通过：全部题目已完成')
            elif left > 0:
                log('     复查：仍有 %d 题未完成（留给你手动补）' % left)
            total_done += 1

    log('')
    log('=== 结束：本次处理作业 %d 份，跳过已完成 %d 份 ===' % (total_done, total_skip))
    summary = _exercise_summary(paths)
    if summary:
        log('  正确 %d / 错误 %d / 合计 %d' % summary)


def _exercise_summary(paths):
    ok = bad = 0
    try:
        with open(paths.log('exercise.log'), 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if '判定：正确' in line:
                    ok += 1
                elif '判定：错误' in line:
                    bad += 1
    except Exception:
        return None
    return ok, bad, ok + bad
