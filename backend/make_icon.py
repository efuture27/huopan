# -*- coding: utf-8 -*-
"""生成货盘助手桌面图标（紫渐变圆角方块 + 白色「货」字）→ app_icon.ico"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "app_icon.ico")
SIZE = 512

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
# 竖向渐变背景
grad = Image.new("RGBA", (SIZE, SIZE))
gd = grad.load()
c1 = (124, 58, 237)    # #7C3AED
c2 = (168, 85, 247)    # #A855F7
for y in range(SIZE):
    t = y / (SIZE - 1)
    gd_col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
    for x in range(SIZE):
        gd[x, y] = gd_col

# 圆角遮罩
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.22), fill=255)
img.paste(grad, (0, 0), mask)

# 白色「货」字
draw = ImageDraw.Draw(img)
font = None
for path in [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
    if os.path.exists(path):
        try:
            font = ImageFont.truetype(path, int(SIZE * 0.62))
            break
        except Exception:
            continue
if font:
    box = draw.textbbox((0, 0), "货", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1] - SIZE * 0.02), "货", font=font, fill=(255, 255, 255, 255))

img.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ICON ->", OUT, os.path.getsize(OUT), "bytes")
