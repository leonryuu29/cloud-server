"""「今日推荐品鉴」卡片：渐变头 + 数字小卡 + 横向条形图 + 必听列表 + 点评。"""
import pathlib

from PIL import Image, ImageDraw

from report import F, gradient, wrap

W, PAD = 1080, 48
BG, INK, SUB = (245, 243, 252), (36, 40, 62), (130, 132, 156)
BAR_COLORS = [(236, 72, 153), (139, 92, 246), (59, 130, 246), (16, 185, 129), (245, 158, 11),
              (239, 68, 68), (20, 184, 166), (99, 102, 241)]


def render(out: pathlib.Path, *, title: str, subtitle: str, stats: list[tuple[str, str]],
           charts: list[tuple[str, list[tuple[str, float]]]], picks: list[tuple[str, str]],
           sections: list[tuple[str, str]], footer: str) -> pathlib.Path:
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    inner = W - 2 * PAD - 56
    pick_lines = [(n, wrap(tmp, r, F(28), inner - 60)) for n, r in picks]
    sec_lines = [(t, wrap(tmp, b, F(30), inner)) for t, b in sections]
    H = (300 + 200 + sum(110 + 54 * len(rows) for _, rows in charts)
         + (110 + sum(52 + 40 * len(l) + 18 for _, l in pick_lines) if picks else 0)
         + sum(100 + 44 * len(l) for _, l in sec_lines) + 30 * (len(charts) + len(sections) + 1) + 110)
    im = Image.new("RGB", (W, H), BG)
    im.paste(gradient(W, 300, (236, 72, 153), (139, 92, 246)), (0, 0))
    d = ImageDraw.Draw(im)
    d.text((PAD, 50), "大肥鱼 · 网易云品鉴", font=F(30), fill=(255, 228, 240))
    d.text((PAD, 92), title, font=F(58), fill=(255, 255, 255))
    for i, ln in enumerate(wrap(d, subtitle, F(32), W - 2 * PAD)[:2]):
        d.text((PAD, 176 + i * 44), ln, font=F(32), fill=(255, 240, 248))
    y = 268
    cw = (W - 2 * PAD - 3 * 20) // 4
    for i, (k, v) in enumerate(stats[:4]):
        x = PAD + i * (cw + 20)
        d.rounded_rectangle((x, y, x + cw, y + 160), 28, fill=(255, 255, 255))
        d.text((x + 24, y + 24), k, font=F(26), fill=SUB)
        d.text((x + 24, y + 66), v, font=F(52), fill=INK)
    y += 200
    for ctitle, rows in charts:
        h = 110 + 54 * len(rows)
        d.rounded_rectangle((PAD, y, W - PAD, y + h), 28, fill=(255, 255, 255))
        d.text((PAD + 28, y + 24), ctitle, font=F(34), fill=INK)
        top = max((v for _, v in rows), default=1) or 1
        for i, (label, v) in enumerate(rows):
            ry = y + 90 + i * 54
            lab = label
            while d.textlength(lab, font=F(26)) > 290 and len(lab) > 1:
                lab = lab[:-1]
            d.text((PAD + 28, ry), lab, font=F(26), fill=INK)
            x0, x1 = PAD + 330, W - PAD - 110
            d.rounded_rectangle((x0, ry + 6, x1, ry + 30), 12, fill=(240, 238, 248))
            d.rounded_rectangle((x0, ry + 6, x0 + max(24, int((x1 - x0) * v / top)), ry + 30), 12,
                                fill=BAR_COLORS[i % len(BAR_COLORS)])
            d.text((x1 + 16, ry), f"{v:g}%" if ctitle.endswith("%") or "分布" in ctitle else f"{v:g}",
                   font=F(26), fill=SUB)
        y += h + 30
    if picks:
        h = 110 + sum(52 + 40 * len(l) + 18 for _, l in pick_lines)
        d.rounded_rectangle((PAD, y, W - PAD, y + h), 28, fill=(255, 255, 255))
        d.text((PAD + 28, y + 24), "今日必听", font=F(34), fill=INK)
        yy = y + 92
        for i, (name, lines) in enumerate(pick_lines):
            c = BAR_COLORS[i % len(BAR_COLORS)]
            d.ellipse((PAD + 28, yy + 4, PAD + 72, yy + 48), fill=c)
            d.text((PAD + 42, yy + 8), str(i + 1), font=F(28), fill=(255, 255, 255))
            d.text((PAD + 90, yy + 4), name[:30], font=F(32), fill=INK)
            for j, ln in enumerate(lines):
                d.text((PAD + 90, yy + 52 + j * 40), ln, font=F(28), fill=SUB)
            yy += 52 + 40 * len(lines) + 18
        y += h + 30
    for i, (stitle, lines) in enumerate(sec_lines):
        h = 100 + 44 * len(lines)
        c = BAR_COLORS[(i + 3) % len(BAR_COLORS)]
        d.rounded_rectangle((PAD, y, W - PAD, y + h), 28, fill=(255, 255, 255))
        d.rounded_rectangle((PAD, y, PAD + 14, y + h), 7, fill=c)
        d.text((PAD + 40, y + 22), stitle, font=F(34), fill=INK)
        for j, ln in enumerate(lines):
            d.text((PAD + 40, y + 84 + j * 44), ln, font=F(30), fill=INK)
        y += h + 30
    d.text((PAD, y + 10), footer, font=F(24), fill=SUB)
    im = im.crop((0, 0, W, min(H, y + 70)))
    im.save(out, "PNG")
    return out
