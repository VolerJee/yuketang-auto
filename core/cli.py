"""Entry point: python core\\cli.py <walk|homework|wait-login>."""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dom
from cdp import CDP, alive
from util import Config, Log, Paths, write_text
from walker import Walker, discover_courses, extract_units, run_homework
from win import Restorer


def _root_default():
    return os.path.dirname(HERE)


def _open(port, url_like='yuketang'):
    session = CDP(port, url_like)
    session.enable()
    session.add_init_script(dom.HOOK)
    return session


def cmd_wait_login(args):
    import time

    deadline = time.time() + args.timeout
    dead = 0
    while time.time() < deadline:
        if not alive(args.port):
            dead += 1
            if dead >= 3:
                print('浏览器已关闭')
                return 1
            time.sleep(4)
            continue
        dead = 0
        try:
            session = CDP(args.port, 'yuketang')
            text = str(session.evaluate("((document.body&&document.body.innerText)||'')") or '')
            cards = int(str(session.evaluate(
                "String(document.querySelectorAll('.el-card').length)") or 0))
            session.close()
            if '我听的课' in text or '我教的课' in text or cards > 0:
                return 0
        except Exception:
            pass
        time.sleep(3)
        if int(time.time()) % 30 < 3:
            print('      还在等登录…')
    return 1


def cmd_walk(args):
    paths = Paths(args.root)
    cfg = Config(args.root)
    log = Log(paths.log('ykt_all.log'))
    restorer = Restorer(args.browser_pid or None)

    session = _open(args.port)
    course_list = discover_courses(session, log)

    try:
        name = str(session.evaluate(dom.DISPLAY_NAME) or '').strip()
        if name:
            write_text(paths.datafile('user.txt'), name)
            log('欢迎，%s' % name)
    except Exception:
        pass

    homework_on = cfg.has_key and cfg.homework_enabled
    summary = []
    for course in course_list:
        if not alive(args.port):
            log('浏览器已关闭，程序退出')
            break
        log('')
        log('=== 开始课程：%s (%s) ===' % (course['name'], course['cid']))
        units = extract_units(session, course, paths, log)
        if not units:
            summary.append('%s: 结构失败' % course['name'])
            continue
        Walker(session, cfg, paths, log, restorer, homework_on).run(units, course['cid'], args.port)
        summary.append('%s: %s 单元' % (course['name'], units.get('total')))

    log('')
    log('=== 全部结束 ===')
    for line in summary:
        log('  ' + line)
    session.close()
    return 0


def cmd_homework(args):
    paths = Paths(args.root)
    cfg = Config(args.root)
    log = Log(paths.log('homework.log'))
    if not cfg.has_key:
        log('config.json 里没有 apiKey，无法答题')
        return 1
    restorer = Restorer(args.browser_pid or None)
    session = _open(args.port)
    course_list = discover_courses(session, log)
    run_homework(session, cfg, paths, log, restorer, course_list, max_q=args.max_q)
    session.close()
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog='ykt')
    ap.add_argument('command', choices=['walk', 'homework', 'wait-login'])
    ap.add_argument('--root', default=_root_default())
    ap.add_argument('--port', type=int, default=9340)
    ap.add_argument('--browser-pid', type=int, default=0)
    ap.add_argument('--max-q', type=int, default=60)
    ap.add_argument('--timeout', type=int, default=900)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {
        'walk': cmd_walk,
        'homework': cmd_homework,
        'wait-login': cmd_wait_login,
    }
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print('已中断')
        return 130
    except Exception as exc:
        print('出错：%s' % exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
