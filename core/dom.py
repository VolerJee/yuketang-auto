"""All page-side probes and actions.

The JavaScript here is the part that took the longest to get right against the
real site, so it is kept as close to the original as possible. Selectors target
the exercise iframe (``f.contentDocument``); everything else runs on the top
document.
"""

import json

# ---------------------------------------------------------------- injection

HOOK = r"""
(function(){
  window.__cls = window.__cls || [];
  window.__capU = window.__capU || [];
  window.__csched = window.__csched || '';
  var XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u = u; return XO.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(){
    var self = this;
    this.addEventListener('load', function(){
      try {
        var u = self.__u || '';
        if (/\/courses\/list/.test(u)) { window.__cls.push(self.responseText || ''); }
        else if (/course\/schedule/.test(u)) { window.__csched = self.responseText || ''; }
        else if (/course\/chapter/.test(u)) { window.__capU.push(self.responseText || ''); }
      } catch(e) {}
    });
    return XS.apply(this, arguments);
  };
})()
"""

CTRL = r"""
(function(){
  if (window.__yktCtl) return 'already';
  window.__yktCtl = true;
  function patch(v){
    if (!v || v.__yktPatched) return;
    try {
      const d = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'playbackRate');
      Object.defineProperty(v, 'playbackRate', {
        configurable: true,
        get: function(){ return d.get.call(v); },
        set: function(){ d.set.call(v, 2); }
      });
      v.__yktPatched = true;
    } catch(e) {}
  }
  setInterval(function(){
    var ms = document.querySelectorAll('video,audio');
    for (var i = 0; i < ms.length; i++) { try { ms[i].muted = true; ms[i].volume = 0; } catch(e) {} }
    var v = document.querySelector('video');
    if (!v) return;
    patch(v);
    if (v.paused && !v.ended && v.readyState >= 2) { try { v.play(); } catch(e) {} }
    if (v.playbackRate !== 2) { try { v.playbackRate = 2; } catch(e) {} }
  }, 1500);
  return 'ok';
})()
"""

# ---------------------------------------------------------------- course list

PICK_COURSES = r"""
(function(){
  var best = null, bestN = -1;
  (window.__cls || []).forEach(function(s){
    try {
      var d = JSON.parse(s).data;
      var n = (d && d.list) ? d.list.length : 0;
      if (n > bestN) { bestN = n; best = s; }
    } catch(e) {}
  });
  return JSON.stringify({n: bestN, raw: best || ''});
})()
"""

CLICK_MY_COURSES = r"""
(function(){
  var t = [].slice.call(document.querySelectorAll('.el-tabs__item')).filter(function(e){
    return /我听的课/.test(e.textContent || '');
  })[0];
  if (t) { t.click(); return 'clicked'; }
  return 'no tab';
})()
"""

DUMP_UNITS = r"""
(function(){
  var arr = window.__capU || [];
  if (!arr.length) return '';
  var raw = arr[arr.length - 1];
  var d;
  try { d = JSON.parse(typeof raw === 'string' ? raw : raw.b); } catch(e) { return ''; }
  var cc = (d.data || d).course_chapter || [];
  var prog = {};
  try {
    var ls = JSON.parse(window.__csched || '{}').data.leaf_schedules || {};
    Object.keys(ls).forEach(function(k){
      var v = ls[k], p = 0;
      if (typeof v === 'number') { p = v; }
      else if (v && typeof v === 'object') {
        if (typeof v.progress === 'number') { p = v.progress; }
        else if (v.total > 0) { p = (v.done || 0) / v.total; }
        else if (v.status === 1) { p = 1; }
      }
      prog[k] = p;
    });
  } catch(e) {}
  var out = [];
  function push(l, chap, sec){
    var p = (typeof prog[l.id] === 'number') ? prog[l.id] : null;
    out.push({
      id: l.id, node_id: l.node_id, type: l.leaf_type,
      name: (l.name || '').trim().slice(0, 30), chap: chap, sec: sec || '', prog: p
    });
  }
  cc.forEach(function(ch){
    (ch.section_leaf_list || []).forEach(function(l){
      if (l.leaf_list) l.leaf_list.forEach(function(x){ push(x, ch.name, l.name); });
      else push(l, ch.name, '');
    });
  });
  var by = {};
  out.forEach(function(l){ by[l.type] = (by[l.type] || 0) + 1; });
  return JSON.stringify({counts: by, total: out.length, list: out});
})()
"""

DUMP_HOMEWORK = r"""
(function(){
  var arr = window.__capU || [];
  if (!arr.length) return '';
  var best = null, bestN = -1;
  arr.forEach(function(raw){
    try {
      var dd = JSON.parse(typeof raw === 'string' ? raw : raw.b);
      var ccc = (dd.data || dd).course_chapter || [];
      var cnt = 0;
      ccc.forEach(function(ch){
        (ch.section_leaf_list || []).forEach(function(l){ cnt += l.leaf_list ? l.leaf_list.length : 1; });
      });
      if (cnt > bestN) { bestN = cnt; best = ccc; }
    } catch(e) {}
  });
  if (!best) return '';
  var prog = {};
  try {
    var ls = JSON.parse(window.__csched || '{}').data.leaf_schedules || {};
    Object.keys(ls).forEach(function(k){
      var v = ls[k], p = 0;
      if (typeof v === 'number') { p = v; }
      else if (v && typeof v === 'object') {
        if (typeof v.progress === 'number') { p = v.progress; }
        else if (v.total > 0) { p = (v.done || 0) / v.total; }
        else if (v.status === 1) { p = 1; }
      }
      prog[k] = p;
    });
  } catch(e) {}
  var out = [];
  function push(l, chap){
    if (l.leaf_type !== 6) return;
    out.push({
      id: l.id, node: l.node_id || 0, name: (l.name || '').trim().slice(0, 30),
      chap: chap, prog: (typeof prog[l.id] === 'number' ? prog[l.id] : null)
    });
  }
  best.forEach(function(ch){
    (ch.section_leaf_list || []).forEach(function(l){
      if (l.leaf_list) l.leaf_list.forEach(function(x){ push(x, ch.name); });
      else push(l, ch.name);
    });
  });
  return JSON.stringify(out);
})()
"""

# ---------------------------------------------------------------- iframe probes

_RECT_TMPL = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument, fr = f.getBoundingClientRect();
  var els = [].slice.call(d.querySelectorAll('__SEL__')).filter(function(e){
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.left > -500 && r.top > -500;
  });
  var e = els[__IDX__];
  if (!e) return '';
  var r = e.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(fr.left + r.left), y: Math.round(fr.top + r.top),
    w: Math.round(r.width), h: Math.round(r.height), n: els.length
  });
})()
"""

_LABEL_TMPL = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument, fr = f.getBoundingClientRect();
  var els = [].slice.call(d.querySelectorAll('button,.el-button,.rain-btn')).filter(function(e){
    var t = (e.textContent || '').replace(/\s+/g, '');
    if (t !== '__LABEL__') return false;
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.left > -500;
  });
  var e = els[0];
  if (!e) return '';
  var r = e.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(fr.left + r.left), y: Math.round(fr.top + r.top),
    w: Math.round(r.width), h: Math.round(r.height)
  });
})()
"""

_CHECKED_TMPL = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument;
  var els = [].slice.call(d.querySelectorAll('__SEL__')).filter(function(e){
    var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  });
  var e = els[__IDX__];
  return e ? String(e.classList.contains('is-checked')) : 'none';
})()
"""

_FOCUS_TMPL = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument;
  var els = [].slice.call(d.querySelectorAll('__SEL__')).filter(function(e){
    var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  });
  var e = els[__IDX__];
  if (!e) return '';
  var inp = e.querySelector('input') || e;
  try { inp.focus(); } catch(x) {}
  return 'ok';
})()
"""

RISK = r"""
(function(){
  for (var i = 0; i < localStorage.length; i++) {
    var k = localStorage.key(i);
    if (/automation-risk-probe/.test(k)) {
      try {
        var o = JSON.parse(localStorage.getItem(k));
        var g = {};
        (o.sessionGroupScores || []).forEach(function(x){ if (x.appliedScore) g[x.group] = x.appliedScore; });
        return JSON.stringify({
          total: o.sessionScore || 0, groups: g, rules: (o.segmentHitRuleIds || []),
          challenge: !!o.challengeRequired, challenges: o.challengeCount || 0
        });
      } catch(e) {}
    }
  }
  return '';
})()
"""

ACTIVE_INDEX = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '-1';
  var it = [].slice.call(f.contentDocument.querySelectorAll('.subject-item'));
  for (var k = 0; k < it.length; k++) {
    if (it[k].classList.contains('active')) return String(k);
  }
  return '-1';
})()
"""

_MARK_TMPL = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '?';
  var it = f.contentDocument.querySelectorAll('.subject-item')[__IDX__];
  if (!it) return '?';
  var s = it.querySelector('.icon-status');
  return s ? s.className : 'none';
})()
"""

DONE_FLAG = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return 'more';
  var d = f.contentDocument;
  var it = [].slice.call(d.querySelectorAll('.subject-item'));
  if (it.length) {
    var m = it.filter(function(e){ return e.querySelector('.icon-status'); }).length;
    if (m >= it.length) return 'done';
  }
  var mm = (d.body.innerText || '').replace(/\s+/g, ' ').match(/(\d+)\/(\d+) 题/);
  if (mm && +mm[1] >= +mm[2]) return 'done';
  return 'more';
})()
"""

QUESTION_TEXT = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument;
  var t = (d.body.innerText || '').replace(/\s+/g, ' ');
  var m = t.match(/\d+\.(判断题|单选题|多选题|填空题|简答题)/);
  if (!m) return '';
  var s = m.index;
  var e = t.indexOf('上一题');
  var body = t.slice(s, (e > s ? e : s + 500)).trim();
  var common = '的是了在和与不有为这那个我们可以学习工程伦理问题方法是否正确';
  var cn = (body.match(/[\u4e00-\u9fa5]/g) || []).length;
  var hit = 0;
  for (var i = 0; i < body.length; i++) { if (common.indexOf(body[i]) >= 0) hit++; }
  return JSON.stringify({text: body, ratio: cn ? +(hit / cn).toFixed(3) : 0});
})()
"""

META = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument;
  var t = (d.body.innerText || '').replace(/\s+/g, ' ');
  var qm = t.match(/\d+\.(判断题|单选题|多选题|填空题|简答题)/);
  var rs = [].slice.call(d.querySelectorAll('.el-radio.homeworkElRadio')).filter(function(e){
    var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.left > -500;
  });
  var bs = [].slice.call(d.querySelectorAll('.el-checkbox')).filter(function(e){
    var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.left > -500;
  });
  var it = [].slice.call(d.querySelectorAll('.subject-item'));
  var active = -1;
  for (var k = 0; k < it.length; k++) { if (it[k].classList.contains('active')) { active = k; break; } }
  return JSON.stringify({idx: active, kind: qm ? qm[1] : '?', n: rs.length, nb: bs.length});
})()
"""

PROGRESS = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '';
  var d = f.contentDocument;
  var m = (d.body.innerText || '').replace(/\s+/g, ' ').match(/(\d+)\/(\d+) 题/);
  return m ? (m[1] + '/' + m[2]) : '';
})()
"""

IFRAME_RECT = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f) return '';
  var r = f.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(r.left), y: Math.round(r.top),
    w: Math.round(r.width), h: Math.round(r.height)
  });
})()
"""

LEFT_QUESTIONS = r"""
(function(){
  var f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return '0';
  var d = f.contentDocument;
  var it = [].slice.call(d.querySelectorAll('.subject-item'));
  return String(it.filter(function(e){ return !e.querySelector('.icon-status'); }).length);
})()
"""

DISPLAY_NAME = r"""
(function(){
  try {
    var u = JSON.parse(localStorage.getItem('Report.Daily.User') || '{}');
    return u.name || u.nickname || '';
  } catch(e) { return ''; }
})()
"""

IFRAME_SRC = r"""
(function(){ var f = document.querySelector('iframe'); return f ? f.src : ''; })()
"""


# ---------------------------------------------------------------- helpers

def rect(cdp, selector, index=0):
    src = _RECT_TMPL.replace('__SEL__', selector).replace('__IDX__', str(index))
    raw = cdp.evaluate(src)
    return json.loads(raw) if raw else None


def label_rect(cdp, label):
    src = _LABEL_TMPL.replace('__LABEL__', label)
    raw = cdp.evaluate(src)
    return json.loads(raw) if raw else None


def is_checked(cdp, selector, index):
    src = _CHECKED_TMPL.replace('__SEL__', selector).replace('__IDX__', str(index))
    return cdp.evaluate(src)


def focus_option(cdp, selector, index):
    src = _FOCUS_TMPL.replace('__SEL__', selector).replace('__IDX__', str(index))
    return cdp.evaluate(src)


def mark_state(cdp, index):
    return cdp.evaluate(_MARK_TMPL.replace('__IDX__', str(index)))


def risk(cdp):
    raw = cdp.evaluate(RISK)
    return json.loads(raw) if raw else None


def meta(cdp):
    raw = cdp.evaluate(META)
    return json.loads(raw) if raw else None


def question_text(cdp):
    raw = cdp.evaluate(QUESTION_TEXT)
    return json.loads(raw) if raw else None


def units(cdp):
    raw = cdp.evaluate(DUMP_UNITS)
    return json.loads(raw) if raw and len(raw) > 100 else None


def homework_units(cdp):
    raw = cdp.evaluate(DUMP_HOMEWORK)
    return json.loads(raw) if raw and len(raw) > 5 else None


def courses(cdp):
    raw = cdp.evaluate(PICK_COURSES)
    if not raw:
        return 0, ''
    data = json.loads(raw)
    return int(data.get('n') or 0), data.get('raw') or ''


# A leading `/* dom:name */` comment on every snippet keeps the browser output of
# the JSON-RPC identical while letting tests (and crash logs) tell probes apart.
_MARKERS = {
    'HOOK': 'hook', 'CTRL': 'ctrl', 'PICK_COURSES': 'pick', 'CLICK_MY_COURSES': 'tab',
    'DUMP_UNITS': 'units', 'DUMP_HOMEWORK': 'homework', 'RISK': 'risk',
    'ACTIVE_INDEX': 'active', 'DONE_FLAG': 'done', 'QUESTION_TEXT': 'question',
    'META': 'meta', 'PROGRESS': 'progress', 'IFRAME_RECT': 'iframe',
    'LEFT_QUESTIONS': 'left', 'DISPLAY_NAME': 'display',
    'IFRAME_SRC': 'src', '_RECT_TMPL': 'rect', '_LABEL_TMPL': 'label',
    '_CHECKED_TMPL': 'checked', '_FOCUS_TMPL': 'focus', '_MARK_TMPL': 'mark',
}

for _name, _tag in _MARKERS.items():
    globals()[_name] = '/* dom:%s */' % _tag + globals()[_name]

