# -*- coding: utf-8 -*-
"""
產生每個主題的背景插畫(SVG),再內嵌成 data URI 寫進 static/style.css。
全部是這支程式畫出來的原創圖形,沒有用到任何外部素材,不會有授權問題。
改圖就改這裡,然後重跑:  python3 tools/make_bg.py
"""
import base64, math, random, re
from pathlib import Path

W, H = 1600, 1000
BASE = Path(__file__).resolve().parent.parent
CSS = BASE / "static" / "style.css"

def svg(body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'preserveAspectRatio="xMidYMid slice">{defs}{body}</svg>')

def uri(s):
    return "data:image/svg+xml;base64," + base64.b64encode(s.encode("utf-8")).decode()

def blob(cx, cy, r, color, op):
    return (f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{color}" '
            f'opacity="{op}" filter="url(#soft)"/>')

SOFT = '<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">' \
       '<feGaussianBlur stdDeviation="60"/></filter>'
GLOW = '<filter id="glow" x="-60%" y="-60%" width="220%" height="220%">' \
       '<feGaussianBlur stdDeviation="7" result="b"/><feMerge>' \
       '<feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'

# ---------------------------------------------------------------- Deep Learning
def art_dl():
    rnd = random.Random(7)
    d = f'<defs>{SOFT}{GLOW}</defs>'
    p  = [blob(180, 120, 300, "#6D5BFF", .30), blob(1450, 860, 340, "#00C6E0", .28),
          blob(900, 180, 260, "#9B6BFF", .18), blob(420, 900, 260, "#3FD6C8", .18)]
    # 五層神經網路,畫密一點,不管畫面怎麼裁切都看得出是網路
    layers, xs = [], [130, 470, 810, 1150, 1480]
    counts = [6, 10, 10, 8, 5]
    for x, n in zip(xs, counts):
        gap = H / (n + 1)
        layers.append([(x, gap * (i + 1) + rnd.uniform(-16, 16)) for i in range(n)])
    for a, b in zip(layers, layers[1:]):
        for (x1, y1) in a:
            for (x2, y2) in b:
                o = rnd.choice([.16, .22, .30, .42])
                w = 2.0 if o > .28 else 1.3
                p.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                         f'stroke="#4C2FD7" stroke-width="{w}" opacity="{o}"/>')
    for i, lay in enumerate(layers):
        col = ["#4C2FD7", "#6D5BFF", "#7C3AED", "#2AA9E0", "#00B8D9"][i]
        for (x, y) in lay:
            r = rnd.uniform(13, 20)
            p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r+11:.0f}" fill="{col}" opacity=".18"/>')
            p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{col}" opacity=".8" filter="url(#glow)"/>')
            p.append(f'<circle cx="{x-r*.3:.0f}" cy="{y-r*.3:.0f}" r="{r*.32:.0f}" fill="#fff" opacity=".6"/>')
    # 飄浮粒子
    for _ in range(90):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rnd.uniform(1.5,4):.1f}" '
                 f'fill="#00B8D9" opacity="{rnd.uniform(.25,.6):.2f}"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 科技(電路板)
def art_tech():
    rnd = random.Random(11)
    d = f'<defs>{SOFT}{GLOW}</defs>'
    p = [blob(1400, 150, 320, "#1F6FEB", .22), blob(200, 850, 300, "#00A6A6", .22)]
    def trace(x, y):
        pts = [(x, y)]
        for _ in range(rnd.randint(3, 6)):
            x2 = x + rnd.choice([-1, 1]) * rnd.randint(60, 220)
            y2 = y + rnd.choice([-1, 1]) * rnd.randint(60, 180)
            x2, y2 = max(20, min(W - 20, x2)), max(20, min(H - 20, y2))
            mx = x2
            pts += [(mx, y), (x2, y2)]
            x, y = x2, y2
        return pts
    for _ in range(16):
        pts = trace(rnd.randint(40, W - 40), rnd.randint(40, H - 40))
        dd = " ".join(f"{'M' if i==0 else 'L'}{a:.0f} {b:.0f}" for i, (a, b) in enumerate(pts))
        p.append(f'<path d="{dd}" fill="none" stroke="#1F6FEB" stroke-width="2" '
                 f'opacity="{rnd.uniform(.18,.4):.2f}" stroke-linejoin="round"/>')
        for (a, b) in pts[::3]:
            p.append(f'<circle cx="{a:.0f}" cy="{b:.0f}" r="5" fill="#00A6A6" opacity=".45"/>')
    # 晶片
    for (cx, cy, w, h) in [(430, 300, 190, 150), (1080, 660, 220, 160), (1300, 260, 130, 110)]:
        p.append(f'<rect x="{cx}" y="{cy}" width="{w}" height="{h}" rx="14" fill="#1F6FEB" opacity=".16"/>')
        p.append(f'<rect x="{cx}" y="{cy}" width="{w}" height="{h}" rx="14" fill="none" '
                 f'stroke="#1F6FEB" stroke-width="2.5" opacity=".45"/>')
        for i in range(6):
            yy = cy + h * (i + 1) / 7
            p.append(f'<line x1="{cx-22}" y1="{yy:.0f}" x2="{cx}" y2="{yy:.0f}" stroke="#00A6A6" stroke-width="3" opacity=".45"/>')
            p.append(f'<line x1="{cx+w}" y1="{yy:.0f}" x2="{cx+w+22}" y2="{yy:.0f}" stroke="#00A6A6" stroke-width="3" opacity=".45"/>')
        p.append(f'<circle cx="{cx+26}" cy="{cy+26}" r="7" fill="#1F6FEB" opacity=".5"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 歷史(水墨山水)
def art_history():
    d = f'<defs>{SOFT}</defs>'
    p = [blob(1250, 220, 260, "#C08A4E", .22), blob(300, 780, 280, "#9A3B2E", .12)]
    p.append(f'<circle cx="1230" cy="230" r="86" fill="#9A3B2E" opacity=".16"/>')
    def mountain(y0, pts, color, op):
        d2 = f"M0 {H} L0 {y0}"
        for (x, y) in pts:
            d2 += f" Q{x-70:.0f} {y-60:.0f} {x:.0f} {y:.0f}"
        d2 += f" L{W} {H} Z"
        return f'<path d="{d2}" fill="{color}" opacity="{op}"/>'
    p.append(mountain(700, [(260, 540), (520, 660), (820, 470), (1120, 620), (1400, 500), (W, 610)], "#7A5C3E", .16))
    p.append(mountain(820, [(300, 700), (640, 790), (980, 660), (1300, 780), (W, 720)], "#7A5C3E", .22))
    p.append(mountain(920, [(380, 840), (760, 900), (1180, 820), (W, 880)], "#5A4430", .18))
    # 遠帆與飛鳥
    for (x, y, s) in [(980, 780, 1), (1060, 800, .8)]:
        p.append(f'<path d="M{x} {y} l{28*s:.0f} -{40*s:.0f} l0 {40*s:.0f} Z" fill="#5A4430" opacity=".35"/>')
    for (x, y, s) in [(420, 300, 1), (480, 260, .8), (540, 310, .9), (1000, 360, .7)]:
        p.append(f'<path d="M{x} {y} q{14*s:.0f} -{12*s:.0f} {28*s:.0f} 0 q{14*s:.0f} -{12*s:.0f} {28*s:.0f} 0" '
                 f'fill="none" stroke="#5A4430" stroke-width="3" opacity=".38" stroke-linecap="round"/>')
    # 印章
    p.append('<rect x="120" y="120" width="92" height="92" rx="10" fill="none" stroke="#9A3B2E" stroke-width="6" opacity=".35"/>')
    p.append('<rect x="140" y="140" width="52" height="52" rx="4" fill="#9A3B2E" opacity=".22"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 人文(祥雲)
def art_human():
    rnd = random.Random(3)
    d = f'<defs>{SOFT}</defs>'
    p = [blob(260, 200, 300, "#3F51A8", .20), blob(1350, 780, 300, "#B03A6E", .18)]
    def cloud(x, y, s, col, op):
        u = []
        for i in range(3):
            r = 40 * s * (1 - i * .18)
            u.append(f'<circle cx="{x+i*58*s:.0f}" cy="{y-i*10*s:.0f}" r="{r:.0f}" fill="none" '
                     f'stroke="{col}" stroke-width="{4*s:.1f}" opacity="{op}"/>')
        u.append(f'<path d="M{x-50*s:.0f} {y+30*s:.0f} q{60*s:.0f} {26*s:.0f} {150*s:.0f} 0 '
                 f'q{60*s:.0f} -{26*s:.0f} {120*s:.0f} 0" fill="none" stroke="{col}" '
                 f'stroke-width="{4*s:.1f}" opacity="{op}" stroke-linecap="round"/>')
        return "".join(u)
    for _ in range(9):
        p.append(cloud(rnd.uniform(60, W - 260), rnd.uniform(80, H - 120),
                       rnd.uniform(.7, 1.5), rnd.choice(["#3F51A8", "#B03A6E"]),
                       f"{rnd.uniform(.16,.32):.2f}"))
    # 竹枝
    for (x, sc) in [(150, 1.1), (1470, .9)]:
        p.append(f'<path d="M{x} {H} C{x+30*sc:.0f} {H-300:.0f} {x-20*sc:.0f} {H-560:.0f} {x+40*sc:.0f} {H-820:.0f}" '
                 f'fill="none" stroke="#3F5A3A" stroke-width="{9*sc:.0f}" opacity=".22" stroke-linecap="round"/>')
        for i in range(5):
            yy = H - 160 - i * 150
            p.append(f'<path d="M{x+16:.0f} {yy} q{80*sc:.0f} -{30*sc:.0f} {140*sc:.0f} -{10*sc:.0f}" '
                     f'fill="none" stroke="#3F5A3A" stroke-width="{5*sc:.0f}" opacity=".20" stroke-linecap="round"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 地理(等高線地圖)
def art_geo():
    rnd = random.Random(5)
    d = f'<defs>{SOFT}</defs>'
    p = [blob(1300, 750, 320, "#0E7C86", .22), blob(280, 220, 280, "#C2641B", .18)]
    def ring(cx, cy, r, wob, col, op):
        pts = []
        for a in range(0, 360, 12):
            rr = r + math.sin(math.radians(a * 3 + wob)) * r * .16 + math.cos(math.radians(a * 5)) * r * .08
            pts.append(f"{cx + rr*math.cos(math.radians(a)):.0f} {cy + rr*math.sin(math.radians(a)):.0f}")
        return f'<polygon points="{" ".join(pts)}" fill="none" stroke="{col}" stroke-width="1.8" opacity="{op}"/>'
    for (cx, cy, n, col) in [(430, 640, 9, "#0E7C86"), (1180, 330, 8, "#C2641B"), (900, 800, 6, "#0E7C86")]:
        for i in range(n):
            p.append(ring(cx, cy, 42 + i * 44, i * 37, col, f"{.34 - i*.028:.2f}"))
    for i in range(7):
        y = 80 + i * 150
        p.append(f'<path d="M0 {y} Q400 {y-46} 800 {y} T1600 {y}" fill="none" stroke="#0E7C86" '
                 f'stroke-width="1.2" opacity=".16"/>')
    # 指北針
    cx, cy = 1420, 170
    p.append(f'<circle cx="{cx}" cy="{cy}" r="72" fill="none" stroke="#C2641B" stroke-width="3" opacity=".35"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="54" fill="none" stroke="#C2641B" stroke-width="1.5" opacity=".25"/>')
    p.append(f'<path d="M{cx} {cy-62} L{cx+20} {cy} L{cx} {cy+62} L{cx-20} {cy} Z" fill="#C2641B" opacity=".32"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 娛樂(聚光燈)
def art_star():
    rnd = random.Random(13)
    d = f'<defs>{SOFT}{GLOW}</defs>'
    p = [blob(300, 60, 300, "#E0367A", .28), blob(1300, 120, 300, "#7A3DBD", .26)]
    for (x0, x1, x2, col) in [(340, 60, 720, "#E0367A"), (900, 620, 1300, "#7A3DBD"), (1320, 1020, 1580, "#E0367A")]:
        p.append(f'<path d="M{x0} -20 L{x1} {H} L{x2} {H} Z" fill="{col}" opacity=".13"/>')
    def star(x, y, r, col, op):
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * .42
            a = math.radians(i * 36 - 90)
            pts.append(f"{x+rr*math.cos(a):.1f} {y+rr*math.sin(a):.1f}")
        return f'<polygon points="{" ".join(pts)}" fill="{col}" opacity="{op}"/>'
    for _ in range(26):
        p.append(star(rnd.uniform(40, W - 40), rnd.uniform(40, H - 40), rnd.uniform(9, 26),
                      rnd.choice(["#E0367A", "#7A3DBD", "#F2A93B"]), f"{rnd.uniform(.18,.45):.2f}"))
    for _ in range(30):
        p.append(f'<circle cx="{rnd.uniform(0,W):.0f}" cy="{rnd.uniform(0,H):.0f}" '
                 f'r="{rnd.uniform(4,22):.0f}" fill="#F2A93B" opacity="{rnd.uniform(.08,.22):.2f}"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 趣聞(泡泡)
def art_fun():
    rnd = random.Random(17)
    d = f'<defs>{SOFT}</defs>'
    p = [blob(250, 780, 300, "#1F7A5A", .22), blob(1350, 220, 300, "#E08A00", .22)]
    for _ in range(34):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r = rnd.uniform(18, 92)
        col = rnd.choice(["#1F7A5A", "#E08A00", "#2E8FD0"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{col}" opacity="{rnd.uniform(.07,.16):.2f}"/>')
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="none" stroke="{col}" '
                 f'stroke-width="2" opacity="{rnd.uniform(.18,.36):.2f}"/>')
        p.append(f'<circle cx="{x-r*.35:.0f}" cy="{y-r*.35:.0f}" r="{r*.17:.0f}" fill="#fff" opacity=".5"/>')
    # 問號與驚嘆號
    for (x, y, s, col) in [(1180, 700, 1.3, "#E08A00"), (380, 260, 1.0, "#1F7A5A")]:
        p.append(f'<text x="{x}" y="{y}" font-size="{150*s:.0f}" font-family="Georgia,serif" '
                 f'fill="{col}" opacity=".16">?</text>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 即時新聞(報紙)
def art_news():
    rnd = random.Random(23)
    d = f'<defs>{SOFT}</defs>'
    p = [blob(1350, 200, 300, "#2F6F8F", .20), blob(260, 800, 280, "#B03A2E", .16)]
    for c in range(5):
        x = 90 + c * 300
        p.append(f'<line x1="{x+250}" y1="60" x2="{x+250}" y2="{H-60}" stroke="#2F6F8F" stroke-width="1.5" opacity=".18"/>')
        y = 120
        while y < H - 90:
            wdt = rnd.uniform(120, 240)
            p.append(f'<rect x="{x}" y="{y:.0f}" width="{wdt:.0f}" height="7" rx="3.5" fill="#2F6F8F" opacity="{rnd.uniform(.08,.18):.2f}"/>')
            y += 22
            if rnd.random() < .12:
                p.append(f'<rect x="{x}" y="{y:.0f}" width="200" height="26" rx="5" fill="#B03A2E" opacity=".16"/>')
                y += 44
    p.append('<rect x="90" y="60" width="640" height="34" rx="8" fill="#B03A2E" opacity=".22"/>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- Python(程式碼)
def art_python():
    rnd = random.Random(29)
    d = f'<defs>{SOFT}</defs>'
    p = [blob(1330, 780, 300, "#D99100", .22), blob(260, 200, 300, "#2B6CB0", .22)]
    # 編輯器視窗
    for (x, y, w, h) in [(150, 150, 620, 420), (860, 470, 600, 400)]:
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#2B6CB0" opacity=".08"/>')
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="none" stroke="#2B6CB0" stroke-width="2" opacity=".28"/>')
        p.append(f'<line x1="{x}" y1="{y+46}" x2="{x+w}" y2="{y+46}" stroke="#2B6CB0" stroke-width="2" opacity=".22"/>')
        for i, col in enumerate(["#E05252", "#E0B252", "#4FAF6D"]):
            p.append(f'<circle cx="{x+28+i*26}" cy="{y+23}" r="7" fill="{col}" opacity=".5"/>')
        yy = y + 80
        while yy < y + h - 26:
            ind = rnd.choice([0, 0, 26, 26, 52])
            wdt = rnd.uniform(90, w - 120 - ind)
            col = rnd.choice(["#2B6CB0", "#2B6CB0", "#D99100", "#4FAF6D"])
            p.append(f'<rect x="{x+34+ind}" y="{yy:.0f}" width="{wdt:.0f}" height="9" rx="4.5" '
                     f'fill="{col}" opacity="{rnd.uniform(.14,.30):.2f}"/>')
            yy += 28
    for (x, y, t, s) in [(1180, 260, "{ }", 1.5), (420, 760, "&lt;/&gt;", 1.1), (900, 180, "def", 1.0)]:
        p.append(f'<text x="{x}" y="{y}" font-size="{86*s:.0f}" font-family="monospace" '
                 f'fill="#2B6CB0" opacity=".14">{t}</text>')
    return svg("".join(p), d)

# ---------------------------------------------------------------- 綜合 / 預設(脈衝波)
def art_default():
    rnd = random.Random(31)
    d = f'<defs>{SOFT}{GLOW}</defs>'
    p = [blob(240, 180, 300, "#1F53B5", .18), blob(1380, 820, 300, "#F0762A", .18)]
    for k in range(5):
        y = 180 + k * 170
        amp = 26 + k * 5
        seg, x = [f"M0 {y}"], 0
        while x < W:
            if rnd.random() < .22:
                seg.append(f"L{x+30} {y} L{x+52} {y-amp*2.2:.0f} L{x+74} {y+amp*1.4:.0f} L{x+96} {y}")
                x += 126
            else:
                seg.append(f"L{x+60} {y}")
                x += 60
        p.append(f'<path d="{" ".join(seg)}" fill="none" stroke="{"#1F53B5" if k%2==0 else "#F0762A"}" '
                 f'stroke-width="2.6" opacity="{.30 - k*.03:.2f}" stroke-linejoin="round" stroke-linecap="round"/>')
    for _ in range(40):
        p.append(f'<circle cx="{rnd.uniform(0,W):.0f}" cy="{rnd.uniform(0,H):.0f}" '
                 f'r="{rnd.uniform(2,5):.0f}" fill="#1F53B5" opacity="{rnd.uniform(.10,.26):.2f}"/>')
    return svg("".join(p), d)

ARTS = {"": art_default, "mix": art_default, "pytorch": art_dl, "tech": art_tech,
        "history": art_history, "human": art_human, "geo": art_geo, "star": art_star,
        "fun": art_fun, "news": art_news, "python": art_python}

def build_css():
    lines = ["/* ===== \u4e3b\u984c\u80cc\u666f\u63d2\u756b\uff08\u7531 tools/make_bg.py \u7522\u751f\uff0c\u539f\u5275\u5716\u5f62\uff0c\u52ff\u624b\u6539\uff09 ===== */"]
    # \u6bcf\u5f35\u63d2\u756b\u7684\u6fc3\u6de1\u4e0d\u540c\uff0c\u500b\u5225\u8abf\u5230\u770b\u5f97\u898b\u53c8\u4e0d\u6436\u6587\u5b57
    OPACITY = {"": .62, "mix": .62, "pytorch": .34, "tech": .42, "python": .55,
               "geo": .72, "history": .58, "human": .78, "star": .55,
               "fun": .58, "news": .58}
    for key, fn in ARTS.items():
        u = uri(fn())
        sel = "body" if key == "" else f'body[data-topic="{key}"]'
        lines.append(f'{sel}{{--art:url("{u}");--pattern-opacity:{OPACITY[key]}}}')
    return "\n".join(lines) + "\n"

def main():
    css = CSS.read_text(encoding="utf-8")
    mark = "/* ===== 主題背景插畫"
    if mark in css:
        css = css[:css.index(mark)].rstrip() + "\n\n"
    css = css.rstrip() + "\n\n" + build_css()
    CSS.write_text(css, encoding="utf-8")
    print("已寫入 style.css，共", len(ARTS), "張背景，CSS 大小", len(css)//1024, "KB")

if __name__ == "__main__":
    main()
