"""服务器日报卡：资源仪表 + 服务状态 + 昨天定时任务执行情况 + 图库/备份/数据。"""
import pathlib

from PIL import Image, ImageDraw

from report import F, gradient

W, PAD = 1080, 48
BG, INK, SUB = (241, 245, 249), (30, 41, 59), (100, 116, 139)
OK, WARN, BAD = (34, 197, 94), (245, 158, 11), (239, 68, 68)


def _color(r):
    return OK if r < .7 else WARN if r < .9 else BAD


def render(out: pathlib.Path, *, date_label: str, verdict: str, gauges: list[tuple[str, float, str]],
           services: list[tuple[str, bool, str]], jobs: list[tuple[str, str, bool]],
           facts: list[tuple[str, str]], comment: str) -> pathlib.Path:
    from report import wrap
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    cmt = wrap(tmp, comment, F(30), W - 2 * PAD - 70) if comment else []
    H = 290 + 370 + (110 + 56 * len(services)) + (110 + 52 * len(jobs)) + (110 + 52 * ((len(facts) + 1) // 2)) \
        + (100 + 44 * len(cmt) if cmt else 0) + 5 * 28 + 80
    im = Image.new("RGB", (W, H), BG)
    im.paste(gradient(W, 260, (15, 23, 42), (30, 64, 175)), (0, 0))
    d = ImageDraw.Draw(im)
    d.text((PAD, 48), "大肥鱼 · 服务器日报", font=F(30), fill=(191, 219, 254))
    d.text((PAD, 90), date_label, font=F(56), fill=(255, 255, 255))
    d.text((PAD, 172), verdict, font=F(32), fill=(219, 234, 254))
    y = 290

    def panel(h, title):
        nonlocal y
        d.rounded_rectangle((PAD, y, W - PAD, y + h), 28, fill=(255, 255, 255))
        d.text((PAD + 32, y + 26), title, font=F(34), fill=INK)
        top = y
        y += h + 28
        return top

    # 资源仪表：圆环
    top = panel(370, "资源")
    cw = (W - 2 * PAD) // len(gauges)
    for i, (label, ratio, detail) in enumerate(gauges):
        cx, cy, r = PAD + cw * i + cw // 2, top + 185, 82
        d.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=(226, 232, 240), width=18)
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + int(360 * max(.01, min(1, ratio))), fill=_color(ratio), width=18)
        pct = f"{ratio * 100:.0f}%"
        d.text((cx - d.textlength(pct, font=F(40)) / 2, cy - 26), pct, font=F(40), fill=INK)
        d.text((cx - d.textlength(label, font=F(28)) / 2, cy + r + 14), label, font=F(28), fill=INK)
        d.text((cx - d.textlength(detail, font=F(22)) / 2, cy + r + 50), detail, font=F(22), fill=SUB)
    # 服务状态
    top = panel(110 + 56 * len(services), "服务")
    for i, (name, ok, note) in enumerate(services):
        yy = top + 92 + i * 56
        d.ellipse((PAD + 34, yy + 8, PAD + 58, yy + 32), fill=OK if ok else BAD)
        d.text((PAD + 76, yy), name, font=F(30), fill=INK)
        d.text((W - PAD - 32 - d.textlength(note, font=F(26)), yy + 4), note, font=F(26), fill=SUB)
    # 定时任务
    top = panel(110 + 52 * len(jobs), "过去 24 小时的推送")
    for i, (name, when, ok) in enumerate(jobs):
        yy = top + 92 + i * 52
        mark, col = {True: ("√", OK), False: ("×", BAD), None: ("·", SUB)}[ok]
        d.text((PAD + 34, yy), mark, font=F(30), fill=col)
        d.text((PAD + 76, yy), name[:16], font=F(28), fill=INK)
        d.text((W - PAD - 32 - d.textlength(when, font=F(26)), yy + 2), when, font=F(26), fill=SUB)
    # 其他数据
    top = panel(110 + 52 * ((len(facts) + 1) // 2), "数据")
    half = (W - 2 * PAD) // 2
    for i, (k, v) in enumerate(facts):
        x = PAD + 34 + (i % 2) * half
        yy = top + 92 + (i // 2) * 52
        d.text((x, yy), k, font=F(26), fill=SUB)
        d.text((x + 150, yy), v, font=F(28), fill=INK)
    if cmt:
        top = panel(100 + 44 * len(cmt), "大肥鱼说")
        for i, ln in enumerate(cmt):
            d.text((PAD + 34, top + 84 + i * 44), ln, font=F(30), fill=INK)
    im = im.crop((0, 0, W, y + 20))
    im.save(out, "PNG")
    return out
