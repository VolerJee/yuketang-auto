"""Human-ish pointer movement over CDP.

The platform scores automation per rule group; the two that actually fire are
`pointer.center-hit-ratio` and `pointer.click-directness`, so the cursor never
lands on the exact centre and always travels in two stages with an overshoot.
"""

import random
import time

import dom

RADIO = '.el-radio.homeworkElRadio'
CHECKBOX = '.el-checkbox'


class Pointer:
    def __init__(self, cdp, log=None):
        self.cdp = cdp
        self.log = log or (lambda _m: None)
        self.x = 420.0
        self.y = 320.0

    def _move(self, x, y):
        self.cdp.mouse_move(int(x), int(y))

    def leg(self, tx, ty, steps):
        sx, sy = self.x, self.y
        cx = (sx + tx) / 2 + random.uniform(-140, 140)
        cy = (sy + ty) / 2 + random.uniform(-110, 110)
        for i in range(1, steps + 1):
            t = i / float(steps)
            mt = 1 - t
            x = mt * mt * sx + 2 * mt * t * cx + t * t * tx + random.uniform(-2, 2)
            y = mt * mt * sy + 2 * mt * t * cy + t * t * ty + random.uniform(-2, 2)
            self._move(x, y)
            if 0.25 < t < 0.8 and random.randint(1, 100) <= 12:
                time.sleep(random.uniform(0.04, 0.16))
            else:
                time.sleep(random.uniform(0.006, 0.016))
        self.x, self.y = tx, ty

    def to(self, tx, ty):
        near_x = tx + random.uniform(-45, 45)
        near_y = ty + random.uniform(-35, 35)
        self.leg(near_x, near_y, random.randint(22, 37))
        time.sleep(random.uniform(0.07, 0.26))
        self.leg(tx, ty, random.randint(7, 14))

    @staticmethod
    def aim(rect):
        w = max(8, int(rect.get('w') or 8))
        h = max(8, int(rect.get('h') or 8))
        span_x = min(int(w * 0.25), 8) or 2
        span_y = min(int(h * 0.25), 7) or 2
        ox = random.randint(-span_x, span_x)
        oy = random.randint(-span_y, span_y)
        return int(rect['x'] + w / 2.0 + ox), int(rect['y'] + h / 2.0 + oy)

    def click(self, rect):
        ax, ay = self.aim(rect)
        self.to(ax, ay)
        time.sleep(random.uniform(0.12, 0.38))
        self._move(ax + random.randint(-3, 3), ay + random.randint(-3, 3))
        time.sleep(random.uniform(0.06, 0.14))
        self.cdp.mouse_press(ax, ay)
        time.sleep(random.uniform(0.095, 0.23))
        self.cdp.mouse_release(ax, ay)
        self.x, self.y = ax, ay

    def drift(self, times):
        for _ in range(times):
            self.x += random.randint(-18, 18)
            self.y += random.randint(-12, 12)
            self._move(self.x, self.y)
            time.sleep(random.uniform(0.12, 0.42))

    def click_label(self, cdp, label):
        rect = dom.label_rect(cdp, label)
        if not rect:
            return False
        self.click(rect)
        return True

    def select(self, cdp, selector, index):
        rect = dom.rect(cdp, selector, index)
        if rect:
            self.click(rect)
            time.sleep(random.uniform(0.26, 0.52))

        if dom.is_checked(cdp, selector, index) == 'True':
            return True

        if dom.focus_option(cdp, selector, index) != 'ok':
            return False

        cdp.key_space(True)
        time.sleep(random.uniform(0.07, 0.16))
        cdp.key_space(False)
        time.sleep(random.uniform(0.25, 0.5))

        if dom.is_checked(cdp, selector, index) == 'True':
            self.log('      （鼠标未选中，已用键盘补选）')
            return True

        cdp.key_space(True)
        time.sleep(0.1)
        cdp.key_space(False)
        time.sleep(0.35)
        return dom.is_checked(cdp, selector, index) == 'True'
