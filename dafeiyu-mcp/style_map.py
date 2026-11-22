"""「今日 30 首风格地图」卡片：按风格分组列出每一首，组头写一句适合什么时候听；收藏过的歌手打星标。"""
import pathlib

from PIL import Image, ImageDraw

from music_card import BAR_COLORS, BG, INK, PAD, SUB, W
from report import F, gradient, wrap


def render(out: pathlib.Path, *, title: str, subtitle: str,
           groups: list[tuple[str, str, list[tuple[int, str, str, bool]]]], footer: str) -> pathlib.Path:
    """groups: [(风格名, 适合什么时候听, [(序号, 歌名, 歌手, 是否收藏过的歌手)])]"""
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    inner = W - 2 * PAD - 80
    layout = []
    for name, when, songs in groups:
        when_lines = wrap(tmp, when, F(26), inner) if when else []
        song_lines = []
        for idx, s, a, fav in songs:
            text = f"{s}  —  {a}"
            ls = wrap(tmp, text, F(28), inner - 70)
            song_lines.append((idx, ls, fav))
        h = 96 + 38 * len(when_lines) + sum(16 + 40 * len(ls) for _, ls, _ in song_lines) + 24
        layout.append((name, when_lines, song_lines, h))
    H = 260 + sum(h + 26 for *_, h in layout) + 90
    im = Image.new("RGB", (W, H), BG)
    im.paste(gradient(W, 230, (139, 92, 246), (59, 130, 246)), (0, 0))
    d = ImageDraw.Draw(im)
    d.text((PAD, 46), "大肥鱼 · 网易云品鉴", font=F(30), fill=(230, 235, 255))
    d.text((PAD, 86), title, font=F(54), fill=(255, 255, 255))
    d.text((PAD, 164), subtitle, font=F(30), fill=(235, 240, 255))
    y = 260
    for gi, (name, when_lines, song_lines, h) in enumerate(layout):
        c = BAR_COLORS[gi % len(BAR_COLORS)]
        d.rounded_rectangle((PAD, y, W - PAD, y + h), 28, fill=(255, 255, 255))
        d.rounded_rectangle((PAD, y, PAD + 14, y + h), 7, fill=c)
        d.text((PAD + 40, y + 22), f"{name}", font=F(36), fill=INK)
        cnt = f"{len(song_lines)} 首"
        d.text((W - PAD - 30 - d.textlength(cnt, font=F(28)), y + 28), cnt, font=F(28), fill=c)
        yy = y + 80
        for ln in when_lines:
            d.text((PAD + 40, yy), ln, font=F(26), fill=SUB); yy += 38
        yy += 6
        for idx, ls, fav in song_lines:
            d.rounded_rectangle((PAD + 40, yy + 4, PAD + 92, yy + 40), 10, fill=c)
            num = f"{idx:02d}"
            d.text((PAD + 66 - d.textlength(num, font=F(24)) / 2, yy + 8), num, font=F(24), fill=(255, 255, 255))
            for j, ln in enumerate(ls):
                d.text((PAD + 108, yy + j * 40), ln, font=F(28), fill=INK)
            if fav:
                d.text((W - PAD - 62, yy), "★", font=F(30), fill=(245, 158, 11))
            yy += 16 + 40 * len(ls)
        y += h + 26
    d.text((PAD, y + 4), footer, font=F(24), fill=SUB)
    im = im.crop((0, 0, W, min(H, y + 60)))
    im.save(out, "PNG")
    return out
