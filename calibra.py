"""
Cartao de calibracao: uma etiqueta que revela area util, orientacao e escala.

    py calibra.py            # so gera preview/CALIBRACAO.png
    py calibra.py --print    # imprime
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from niimbot import PrinterClient, SerialTransport

# preview/ nao vem no clone (esta no .gitignore), entao criamos na hora --
# e ancorado no diretorio do script, para funcionar de qualquer cwd.
SAIDA = Path(__file__).resolve().parent / "preview" / "CALIBRACAO.png"

W, H = 384, 639          # largura da cabeca x comprimento de 80 mm @203dpi
DPI = 203

img = Image.new("L", (W, H), 255)
d = ImageDraw.Draw(img)
f_big = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 44)
f_sm = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 20)

# Borda: se aparecer inteira, a area util esta correta.
d.rectangle([0, 0, W - 1, H - 1], outline=0, width=4)

# Quadrado solido de 60x60 no canto superior ESQUERDO -> mostra a orientacao.
d.rectangle([12, 12, 72, 72], fill=0)

d.text((W // 2, 110), "TOPO", font=f_big, fill=0, anchor="mm")

# Faixa solida de largura total, 30 px de altura.
d.rectangle([0, 150, W - 1, 180], fill=0)

# Regua no eixo do papel: traco + rotulo em mm a cada 10 mm.
for mm in range(10, 80, 10):
    y = round(mm / 25.4 * DPI)
    d.line([12, y, 90, y], fill=0, width=3)
    d.text((100, y), "%d mm" % mm, font=f_sm, fill=0, anchor="lm")

# Regua na largura da cabeca: traco + rotulo a cada 10 mm.
for mm in range(10, 50, 10):
    x = round(mm / 25.4 * DPI)
    if x < W - 10:
        d.line([x, H - 90, x, H - 40], fill=0, width=3)
        d.text((x, H - 110), "%d" % mm, font=f_sm, fill=0, anchor="mm")
d.text((W // 2, H - 25), "largura (mm)", font=f_sm, fill=0, anchor="mm")

img = img.point(lambda p: 0 if p < 150 else 255, mode="L").convert("1")
SAIDA.parent.mkdir(parents=True, exist_ok=True)
img.save(SAIDA)
print("preview/CALIBRACAO.png  (%dx%d px = %.1f x %.1f mm)"
      % (W, H, W / DPI * 25.4, H / DPI * 25.4))

if "--print" in sys.argv:
    port = "COM3"
    lt = None
    delay = 0.0
    for a in sys.argv:
        if a.startswith("--port="):
            port = a.split("=")[1]
        elif a.startswith("--type="):
            lt = int(a.split("=")[1])
        elif a.startswith("--delay="):
            delay = float(a.split("=")[1])
    pr = PrinterClient(SerialTransport(port=port))
    print("imprimindo (label_type=%s, row_delay=%.4fs, ~%.1fs de envio) ..."
          % (lt if lt is not None else "auto", delay, delay * H))
    pr.print_image(img, density=5, label_type=lt, row_delay=delay, sniff=True)
    print("ok  (ultima linha confirmada: %s de %d)" % (pr.last_ack, H - 1))
    if pr.chatter:
        print("a impressora falou durante o envio:")
        for _pg, i, hexdata in pr.chatter[:20]:
            print("  apos linha %d: %s" % (i, hexdata))
        print("  (%d eventos no total)" % len(pr.chatter))
    else:
        print("a impressora nao mandou nada durante o envio")
