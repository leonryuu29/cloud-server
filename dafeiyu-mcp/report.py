"""大肥鱼日报：一张竖版长图。
统计（消息数、时段分布、高峰、最晚）由代码算，内容（做了/学了/聊了/心情/点评）由 AI 写。"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
W = 1080
BG = (243, 246, 252)
INK, SUB = (36, 44, 66), (128, 138, 160)
PALETTE = {  # 每个板块一个颜色
    "done": (255, 159, 67), "learned": (84, 160, 255), "chatted": (155, 89, 182),
    "mood": (46, 204, 113), "comment": (255, 107, 129),
}


def F(size):
    return ImageFont.truetype(FONT, size)


def wrap(d, text, font, width):
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if d.textlength(cur + ch, font=font) > width:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
    return [l for l in lines if l.strip()] or [""]


def gradient(w, h, top, bottom):
    g = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        gd.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g


def render(out: pathlib.Path, *, date_label: str, headline: str, stats: dict, hours: list[int],
           sections: list[tuple[str, str, str]], server: dict | None = None) -> pathlib.Path:
    """sections: [(key, 标题, 内容)]，key 决定颜色。stats: {"消息": 42, ...} 最多 4 个。"""
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    pad, inner = 48, W - 2 * 48 - 56
    # 预先排版，算高度
    sec_layout = []
    for key, title, body in sections:
        lines = []
        for item in str(body).split("\n"):
            item = item.strip().lstrip("-•· ")
            if item:
                lines += wrap(tmp, "· " + item, F(32), inner - 20)
        sec_layout.append((key, title, lines, 96 + 46 * len(lines) + 24))
    H = 330 + 220 + 400 + sum(s[3] + 28 for s in sec_layout) + (190 if server else 0) + 90
    im = Image.new("RGB", (W, H), BG)
    im.paste(gradient(W, 300, (108, 92, 231), (84, 160, 255)), (0, 0))
    d = ImageDraw.Draw(im)
    # 头部
    d.text((pad, 52), "大肥鱼日报", font=F(30), fill=(225, 230, 255))
    d.text((pad, 92), date_label, font=F(60), fill=(255, 255, 255))
    for i, ln in enumerate(wrap(d, headline, F(34), W - 2 * pad)[:2]):
        d.text((pad, 178 + i * 46), ln, font=F(34), fill=(240, 244, 255))
    y = 270
    # 统计小卡片（压在渐变上）
    items = list(stats.items())[:4]
    cw = (W - 2 * pad - 3 * 20) // 4
    for i, (k, v) in enumerate(items):
        x = pad + i * (cw + 20)
        d.rounded_rectangle((x, y, x + cw, y + 170), 28, fill=(255, 255, 255))
        d.text((x + 26, y + 26), str(k), font=F(28), fill=SUB)
        d.text((x + 26, y + 72), str(v), font=F(56), fill=INK)
    y += 210
    # 时段分布柱状图
    d.rounded_rectangle((pad, y, W - pad, y + 370), 28, fill=(255, 255, 255))
    d.text((pad + 28, y + 24), "聊天时段分布", font=F(34), fill=INK)
    peak = max(hours) if any(hours) else 0
    if peak:
        ph = hours.index(peak)
        d.text((W - pad - 300, y + 30), f"高峰 {ph:02d}:00-{ph + 1:02d}:00", font=F(28), fill=(108, 92, 231))
    cx0, cx1, base = pad + 36, W - pad - 28, y + 300
    bw = (cx1 - cx0) / 24
    for h, n in enumerate(hours):
        bh = 0 if not peak else int(200 * n / peak)
        color = (108, 92, 231) if n == peak and n else (165, 180, 252) if n else (230, 234, 244)
        x = cx0 + h * bw
        d.rounded_rectangle((x + 4, base - max(bh, 6), x + bw - 4, base), 6, fill=color)
        if h % 3 == 0:
            d.text((x + 2, base + 12), f"{h:02d}", font=F(22), fill=SUB)
    y += 400
    # 内容板块
    for key, title, lines, h in sec_layout:
        color = PALETTE.get(key, (84, 160, 255))
        d.rounded_rectangle((pad, y, W - pad, y + h), 28, fill=(255, 255, 255))
        d.rounded_rectangle((pad, y, pad + 14, y + h), 7, fill=color)
        d.rounded_rectangle((pad + 40, y + 26, pad + 40 + 16, y + 26 + 40), 8, fill=color)
        d.text((pad + 72, y + 24), title, font=F(36), fill=INK)
        for i, ln in enumerate(lines):
            d.text((pad + 44, y + 96 + i * 46), ln, font=F(32), fill=INK)
        y += h + 28
    # 服务器状态条
    if server:
        d.rounded_rectangle((pad, y, W - pad, y + 160), 28, fill=(255, 255, 255))
        d.text((pad + 28, y + 20), "服务器", font=F(30), fill=INK)
        d.text((W - pad - 260, y + 22), server.get("status", ""), font=F(26), fill=SUB)
        bars = server.get("bars", [])[:3]
        bwid = (W - 2 * pad - 56 - 2 * 24) // max(1, len(bars))
        for i, (label, ratio) in enumerate(bars):
            x = pad + 28 + i * (bwid + 24)
            d.text((x, y + 72), f"{label} {ratio * 100:.0f}%", font=F(26), fill=SUB)
            d.rounded_rectangle((x, y + 114, x + bwid, y + 132), 9, fill=(230, 234, 244))
            c = (46, 204, 113) if ratio < .7 else (255, 159, 67) if ratio < .9 else (231, 76, 60)
            d.rounded_rectangle((x, y + 114, x + max(18, int(bwid * ratio)), y + 132), 9, fill=c)
        y += 190
    d.text((pad, H - 70), "—— 由住在云服务器里的大肥鱼整理", font=F(24), fill=SUB)
    im.save(out, "PNG")
    return out
