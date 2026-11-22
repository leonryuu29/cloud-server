"""画图：今日画廊拼图、可视化卡片（昨日小结/服务器状态）。"""
import datetime as dt
import pathlib
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
BG, CARD, INK, SUB, ACCENT = (235, 242, 252), (255, 255, 255), (40, 52, 74), (120, 132, 156), (79, 140, 255)


def font(size):
    return ImageFont.truetype(FONT, size)


def gallery(files: list[pathlib.Path], out: pathlib.Path, title: str) -> pathlib.Path:
    """把 n 张图拼成一张：每行 5 张竖图，顶部一行标题。"""
    cols, tw, th, gap, head = 5, 360, 500, 12, 90
    rows = (len(files) + cols - 1) // cols
    W = cols * tw + (cols + 1) * gap
    H = head + rows * th + (rows + 1) * gap
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.text((gap + 8, 22), title, font=font(42), fill=INK)
    for i, f in enumerate(files):
        try:
            im = Image.open(f).convert("RGB")
        except Exception:
            continue
        im = ImageOps.fit(im, (tw, th), method=Image.LANCZOS, centering=(0.5, 0.3))
        x = gap + (i % cols) * (tw + gap)
        y = head + gap + (i // cols) * (th + gap)
        canvas.paste(im, (x, y))
        d.rounded_rectangle((x + 8, y + 8, x + 52, y + 44), 8, fill=(0, 0, 0))
        d.text((x + 18, y + 10), str(i + 1), font=font(26), fill=(255, 255, 255))
    canvas.save(out, "JPEG", quality=88)
    return out


def _wrap(text: str, f, width: int, draw) -> list[str]:
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=f) > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def card(title: str, body: str, out: pathlib.Path, footer: str = "") -> pathlib.Path:
    """把一段文字排成一张好看的卡片图。body 里以 ## 开头的行当小标题，以 - 开头的行当列表项，
    形如「标签: 数值/最大值」或「标签: 45%」的行会画成进度条。"""
    W, pad = 1080, 56
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_title, f_h, f_txt = font(54), font(38), font(32)
    blocks = []                       # (kind, payload, height)
    for raw in body.strip().split("\n"):
        line = raw.rstrip()
        if not line:
            blocks.append(("gap", None, 18)); continue
        bar = re.match(r"^[-•]?\s*(.+?)[:：]\s*([\d.]+)\s*(?:/\s*([\d.]+)|%)", line)
        if bar and ("%" in line or bar.group(3)):
            v, m = float(bar.group(2)), float(bar.group(3) or 100)
            blocks.append(("bar", (line.lstrip("-• "), max(0.0, min(1.0, v / m if m else 0))), 84)); continue
        if line.startswith("##"):
            blocks.append(("h", line.lstrip("# "), 66)); continue
        wrapped = _wrap(line, f_txt, W - 2 * pad - 40, tmp)
        blocks.append(("t", wrapped, 46 * len(wrapped) + 6))
    H = 170 + sum(b[2] for b in blocks) + 110
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((24, 24, W - 24, H - 24), 36, fill=CARD)
    d.rounded_rectangle((24, 24, W - 24, 40), 8, fill=ACCENT)
    d.text((pad, 70), title, font=f_title, fill=INK)
    y = 170
    for kind, payload, h in blocks:
        if kind == "h":
            d.text((pad, y + 10), payload, font=f_h, fill=ACCENT)
        elif kind == "t":
            for i, ln in enumerate(payload):
                d.text((pad + 8, y + i * 46), ln, font=f_txt, fill=INK)
        elif kind == "bar":
            label, ratio = payload
            d.text((pad + 8, y), label, font=f_txt, fill=INK)
            x0, x1, by = pad + 8, W - pad - 8, y + 46
            d.rounded_rectangle((x0, by, x1, by + 20), 10, fill=(225, 232, 244))
            color = (90, 190, 120) if ratio < 0.7 else (245, 170, 60) if ratio < 0.9 else (230, 80, 80)
            d.rounded_rectangle((x0, by, x0 + max(20, int((x1 - x0) * ratio)), by + 20), 10, fill=color)
        y += h
    foot = footer or "大肥鱼 · " + dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    d.text((pad, H - 92), foot, font=font(26), fill=SUB)
    im.save(out, "PNG")
    return out
