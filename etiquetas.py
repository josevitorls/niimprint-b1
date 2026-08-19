"""
Impressao de etiquetas/crachas em Niimbot B1 via USB (porta serial COM).

Uso rapido:
    py etiquetas.py info                  # testa a conexao (nao gasta etiqueta)
    py etiquetas.py preview               # gera PNGs em ./preview (nao imprime)
    py etiquetas.py print --only 1        # imprime SO o participante 1
    py etiquetas.py print                 # imprime todos

Fonte de dados: participantes.json (ou --in arquivo.csv, export do lu.ma).
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from niimbot import InfoEnum, PrinterClient, SerialTransport

# ---------------------------------------------------------------- constantes

DPI = 203                    # cabeca termica da B1
HEAD_PX = 384                # largura maxima de impressao da B1 (~48 mm)
LABEL_MM = (50, 80)          # (largura do rolo, comprimento da etiqueta)
FEED_PX = round(LABEL_MM[1] / 25.4 * DPI)   # 639 px = 80 mm

SS = 3                       # supersampling: desenha 3x maior e reduz (anti-serrilhado)
# O rolo tem 2 mm de gap entre etiquetas (onde fica o corte) e o liner tem 53 mm
# para uma etiqueta de 50 mm. No eixo do papel a margem protege o texto do corte;
# no eixo da cabeca ela e menos critica, porque a cabeca (48,06 mm) ja nao alcanca
# a borda da etiqueta.
MARGEM_PAPEL_MM = 6.0        # folga nas pontas do eixo de 80 mm
MARGEM_CABECA_MM = 4.0       # folga nas bordas do eixo de 50 mm
THRESHOLD = 150              # corte para binarizar (0-255); maior = tracos mais gordos

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"

BASE = Path(__file__).parent
DEFAULT_IN = BASE / "participantes.json"
PREVIEW_DIR = BASE / "preview"

# ------------------------------------------------------------------ layout


def _wrap(draw, text, font, max_w, max_lines):
    """Quebra o texto em ate max_lines linhas que caibam em max_w. None se nao couber."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            if not cur:
                return None          # palavra unica maior que a largura
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                return None
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


def _fit(draw, text, font_path, max_w, max_h, max_size, max_lines, min_size=14):
    """Maior corpo de fonte em que o texto (quebrado) cabe na caixa."""
    size = max_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, max_w, max_lines)
        if lines:
            lh = round(size * 1.18)
            if lh * len(lines) <= max_h:
                return font, lines, lh
        size -= 2

    # Chegou no piso e ainda nao coube. Devolver o texto sem quebra aqui
    # (era o que fazia antes) joga letra por cima da margem, e a margem e
    # justamente o que protege o texto do vinco entre as etiquetas.
    # Entao continua encolhendo, liberando uma linha a mais, ate caber.
    piso = max(8, min_size // 2)
    for size in range(min_size, piso - 1, -1):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, max_w, max_lines + 1)
        if lines:
            lh = round(size * 1.18)
            if lh * len(lines) <= max_h:
                return font, lines, lh

    font = ImageFont.truetype(font_path, piso)
    return font, _wrap(draw, text, font, max_w, 99) or [text], round(piso * 1.18)


def render_label(nome, empresa, cargo, layout="landscape"):
    """Imagem 1-bit no sentido de LEITURA (como o cracha e lido por quem olha)."""
    if layout == "landscape":
        cw, ch = FEED_PX, HEAD_PX          # 80 mm x 50 mm, texto no sentido longo
    else:
        cw, ch = HEAD_PX, FEED_PX          # 50 mm x 80 mm, texto no sentido curto

    W, H = cw * SS, ch * SS
    # Margem no sentido do papel maior que na largura da cabeca: e nesse eixo
    # que o texto encosta no vinco se a etiqueta parar um pouco fora do lugar.
    # Com 7% em ambos sobravam 3,8 mm, e qualquer desalinho ja comia letra.
    mx = round(MARGEM_PAPEL_MM / 25.4 * DPI * SS)   # eixo dos 80 mm
    my = round(MARGEM_CABECA_MM / 25.4 * DPI * SS)  # eixo dos 50 mm
    if layout != "landscape":
        mx, my = my, mx
    usable_w = W - 2 * mx
    usable_h = H - 2 * my

    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)

    sub = " - ".join(p for p in (empresa, cargo) if p)

    # Prefere o nome em 1 linha, desde que nao fique bem menor que a versao em 2 linhas.
    uma = _fit(d, nome, FONT_BOLD, usable_w, usable_h * 0.55,
               max_size=round(usable_h * 0.30), max_lines=1, min_size=14 * SS)
    duas = _fit(d, nome, FONT_BOLD, usable_w, usable_h * 0.55,
                max_size=round(usable_h * 0.30), max_lines=2, min_size=14 * SS)
    f_nome, l_nome, lh_nome = uma if (len(uma[1]) == 1 and
                                      uma[0].size >= 0.72 * duas[0].size) else duas
    if sub:
        f_sub, l_sub, lh_sub = _fit(
            d, sub, FONT_REG, usable_w, usable_h * 0.28, max_size=round(f_nome.size * 0.62),
            max_lines=2, min_size=10 * SS,
        )
    else:
        f_sub, l_sub, lh_sub = None, [], 0

    gap = round(lh_nome * 0.35) if sub else 0
    block_h = lh_nome * len(l_nome) + gap + lh_sub * len(l_sub)
    y = (H - block_h) / 2

    for line in l_nome:
        d.text((W / 2, y + lh_nome / 2), line, font=f_nome, fill=0, anchor="mm")
        y += lh_nome
    y += gap
    for line in l_sub:
        d.text((W / 2, y + lh_sub / 2), line, font=f_sub, fill=0, anchor="mm")
        y += lh_sub

    img = img.resize((cw, ch), Image.LANCZOS)
    return img.point(lambda p: 0 if p < THRESHOLD else 255, mode="L").convert("1")


def to_print(img, layout, rotate180=False):
    """Gira o desenho pro sentido do papel: largura tem que ser 384 px."""
    if layout == "landscape":
        img = img.rotate(-90, expand=True)   # 639x384 -> 384x639
    if rotate180:
        img = img.rotate(180)
    assert img.width <= HEAD_PX, "Imagem larga demais para a B1 (max %d px)" % HEAD_PX
    return img


# -------------------------------------------------------------------- dados


def load_people(path):
    path = Path(path)
    if not path.exists():
        sys.exit("Arquivo nao encontrado: " + str(path))
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        rows = json.loads(path.read_text(encoding="utf-8"))

    def pick(row, *keys):
        for k in keys:
            for rk, rv in row.items():
                if rk and rk.strip().lower() == k:
                    return (rv or "").strip()
        return ""

    people = []
    for row in rows:
        nome = pick(row, "nome", "name", "full name")
        if not nome:
            continue
        people.append({
            "Nome": nome,
            "Empresa": pick(row, "empresa", "company", "organization"),
            "Cargo": pick(row, "cargo", "title", "job title", "role"),
        })
    return people


def slug(text):
    keep = "".join(c if c.isalnum() else "_" for c in text)
    return keep.strip("_")[:40] or "etiqueta"


# ----------------------------------------------------------------- comandos


def cmd_preview(args, people):
    PREVIEW_DIR.mkdir(exist_ok=True)
    for i, p in enumerate(people, 1):
        img = render_label(p["Nome"], p["Empresa"], p["Cargo"], args.layout)
        out = PREVIEW_DIR / ("%02d_%s_%s.png" % (i, slug(p["Nome"]), args.layout))
        img.save(out)
        print("  %s  (%dx%d px)" % (out.name, img.width, img.height))
    print("\n%d previa(s) em %s" % (len(people), PREVIEW_DIR))


def open_printer(args):
    print("Conectando em %s ..." % args.port)
    return PrinterClient(SerialTransport(port=args.port))


def cmd_info(args, people):
    pr = open_printer(args)
    for label, key in (("Modelo (tipo)", InfoEnum.DEVICETYPE),
                       ("Firmware", InfoEnum.SOFTVERSION),
                       ("Hardware", InfoEnum.HARDVERSION),
                       ("Bateria", InfoEnum.BATTERY),
                       ("Serial", InfoEnum.DEVICESERIAL)):
        try:
            print("  %-15s: %s" % (label, pr.get_info(key)))
        except Exception as exc:
            print("  %-15s: erro (%s)" % (label, exc))
    try:
        print("  %-15s: %s" % ("Rolo (RFID)", pr.get_rfid()))
    except Exception:
        pass
    print("\nConexao OK.")


def cmd_print(args, people):
    PREVIEW_DIR.mkdir(exist_ok=True)
    trabalhos = []
    for i, p in enumerate(people, 1):
        view = render_label(p["Nome"], p["Empresa"], p["Cargo"], args.layout)
        view.save(PREVIEW_DIR / ("%02d_%s_%s.png" % (i, slug(p["Nome"]), args.layout)))
        img = to_print(view, args.layout, args.rotate180)
        for _ in range(args.copies):
            trabalhos.append((p["Nome"], img))

    total = len(trabalhos)
    print("%d participante(s) x %d copia(s) = %d etiqueta(s)" % (len(people), args.copies, total))

    pr = open_printer(args)

    # Uma etiqueta = um trabalho completo, e cada um so termina quando a
    # impressora confirma que imprimiu (print_image bloqueia no get_print_status).
    # Nao ha pausa chutada entre etiquetas: e a impressora que sabe onde o papel
    # parou e que acha o vinco com o sensor dela.
    falhas = []
    for n, (nome, img) in enumerate(trabalhos, 1):
        print("  [%d/%d] %s ... " % (n, total, nome), end="", flush=True)
        r = pr.print_image(img, density=args.density, row_delay=args.rowdelay)
        if r["completa"]:
            print("ok")
        else:
            falhas.append((nome, r))
            print("FALHOU (linha %s de %d)" % (r["linhas_ok"], r["esperado"]))

    if falhas:
        print("")
        print("Estas etiquetas nao sairam inteiras -- reimprima:")
        for nome, r in falhas:
            if not r["status"].get("zerou", True):
                motivo = ("o contador de progresso nao zerou -- a impressora nao "
                          "deu sinal confiavel de fim (a espera caiu para tempo fixo)")
            elif not r["status"].get("ok"):
                motivo = "a impressora nao confirmou o fim da impressao"
            else:
                motivo = "linhas descartadas; suba o --rowdelay"
            print("  %s: %s" % (nome, motivo))
    print("")
    print("Concluido.")


# -------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Etiquetas de participantes na Niimbot B1")
    ap.add_argument("cmd", choices=["info", "preview", "print"])
    ap.add_argument("--in", dest="infile", default=str(DEFAULT_IN),
                    help="participantes.json ou .csv (default: participantes.json)")
    ap.add_argument("--port", default="COM3", help="porta serial da B1 (default: COM3)")
    ap.add_argument("--layout", choices=["landscape", "portrait"], default="landscape",
                    help="landscape = texto no sentido dos 80 mm (default)")
    ap.add_argument("--density", type=int, default=5, choices=range(1, 6),
                    help="densidade de impressao 1-5 (default: 5)")
    ap.add_argument("--copies", type=int, default=1, help="copias por participante")
    ap.add_argument("--only", type=int, help="imprime apenas o N-esimo participante (1-based)")
    ap.add_argument("--rotate180", action="store_true", help="gira 180 graus")
    ap.add_argument("--rowdelay", type=float, default=0.005,
                    help="pausa por linha enviada (s); a B1 descarta linhas se a rajada chegar rapido demais")
    args = ap.parse_args()

    people = [] if args.cmd == "info" else load_people(args.infile)
    if args.only:
        if not 1 <= args.only <= len(people):
            sys.exit("--only fora do intervalo (1..%d)" % len(people))
        people = [people[args.only - 1]]
    if args.cmd != "info" and not people:
        sys.exit("Nenhum participante encontrado no arquivo de entrada.")

    {"info": cmd_info, "preview": cmd_preview, "print": cmd_print}[args.cmd](args, people)


if __name__ == "__main__":
    main()
