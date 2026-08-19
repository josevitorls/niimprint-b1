"""
Impressao de etiquetas de duas linhas centralizadas na Niimbot B1 via USB.

A etiqueta tem sempre a mesma forma: uma linha de destaque (negrito, corpo
grande) e uma linha de apoio (menor), as duas centralizadas, com o corpo da
fonte escolhido automaticamente para caber. O que muda de um uso para outro e
so o QUE entra em cada linha -- e isso voce diz com --linha1 e --linha2.

Uso rapido:
    py etiquetas.py info                  # testa a conexao (nao gasta etiqueta)
    py etiquetas.py preview               # gera PNGs em ./preview (nao imprime)
    py etiquetas.py print --only 1        # imprime SO o registro 1
    py etiquetas.py print                 # imprime todos

    # outro conteudo, mesmo programa:
    py etiquetas.py preview --in ativos.csv \
        --linha1 "{Patrimonio}" --linha2 "{Setor} - {Responsavel}"

Fonte de dados: qualquer .json (lista de objetos) ou .csv com cabecalho.
O default e participantes.json com --linha1 "{Nome}" --linha2 "{Empresa} - {Cargo}".
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from niimbot import InfoEnum, PrinterClient, SerialTransport

# ---------------------------------------------------------------- constantes

DPI = 203                    # FIXO: resolucao da cabeca termica da B1
HEAD_PX = 384                # FIXO: largura maxima de impressao da B1 (~48 mm)
LABEL_MM = (50, 80)          # MUDE AQUI para outro rolo: (largura, comprimento) em mm
FEED_PX = round(LABEL_MM[1] / 25.4 * DPI)   # derivado: 639 px = 80 mm

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

# O caso de origem deste projeto (cracha de evento) virou so o default. Troque
# pela linha de comando (--linha1/--linha2) sem editar nada aqui.
LINHA1_PADRAO = "{Nome}"
LINHA2_PADRAO = "{Empresa} - {Cargo}"

# Apelidos de coluna reconhecidos ao ler o arquivo: a chave e o nome canonico
# que o template usa, os valores sao como o campo pode aparecer no arquivo.
APELIDOS = {
    "Nome": ("nome", "name", "full name"),
    "Empresa": ("empresa", "company", "organization"),
    "Cargo": ("cargo", "title", "job title", "role"),
}

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


def render_label(linha1, linha2="", layout="landscape"):
    """Desenha a etiqueta e devolve uma imagem 1-bit no sentido de LEITURA.

    linha1 sai em negrito e no maior corpo que couber; linha2 sai embaixo, em
    peso normal e menor. As duas sao centralizadas e quebram em ate 2 linhas
    cada se precisarem. linha2 vazia e valida: a linha1 fica sozinha, centrada
    na etiqueta inteira.

    O resultado ainda NAO esta no sentido do papel -- passe por to_print()."""
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

    nome = (linha1 or "").strip()
    sub = (linha2 or "").strip()

    # Prefere o destaque em 1 linha, desde que nao fique bem menor que a versao em 2.
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


def render_cracha(nome, empresa, cargo, layout="landscape"):
    """Atalho para o caso que deu origem a este projeto: cracha de evento.

    E so render_label() com linha2 = "Empresa - Cargo", pulando o separador
    quando um dos dois vem vazio."""
    return render_label(nome, " - ".join(p for p in (empresa, cargo) if p), layout)


def to_print(img, layout, rotate180=False):
    """Gira o desenho pro sentido do papel: largura tem que ser 384 px."""
    if layout == "landscape":
        img = img.rotate(-90, expand=True)   # 639x384 -> 384x639
    if rotate180:
        img = img.rotate(180)
    assert img.width <= HEAD_PX, "Imagem larga demais para a B1 (max %d px)" % HEAD_PX
    return img


# -------------------------------------------------------------------- dados


def load_registros(path):
    """Le um .json (lista de objetos) ou .csv com cabecalho.

    Devolve os registros como estao no arquivo -- TODAS as colunas ficam
    disponiveis para os templates de linha. Por conveniencia, quando o arquivo
    usa os nomes em ingles do lu.ma (name/company/title), os apelidos canonicos
    Nome/Empresa/Cargo sao acrescentados para que os templates padrao funcionem
    sem que voce precise renomear coluna nenhuma."""
    path = Path(path)
    if not path.exists():
        sys.exit("Arquivo nao encontrado: " + str(path))
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = [rows]

    registros = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        reg = {(k.strip() if isinstance(k, str) else k): ("" if v is None else str(v).strip())
               for k, v in row.items() if k}
        if not any(reg.values()):
            continue                      # linha em branco do CSV
        for canonico, apelidos in APELIDOS.items():
            if reg.get(canonico):
                continue
            for chave, valor in reg.items():
                if isinstance(chave, str) and chave.lower() in apelidos and valor:
                    reg[canonico] = valor
                    break
        registros.append(reg)
    return registros


# Mantido porque a fila e o painel ja importavam este nome.
load_people = load_registros


_CAMPO = re.compile(r"(\{[^{}]*\})")
_REPETIDOS = re.compile(r"([-–—|/,;:])(\s*[-–—|/,;:])+")
_VAZIOS = re.compile(r"\(\s*\)|\[\s*\]")
_PONTAS = re.compile(r"^[\s\-–—|/,;:]+|[\s\-–—|/,;:]+$")


def formatar(template, registro):
    """Preenche "{Campo} - {Outro}" com os valores do registro.

    A busca do campo ignora maiusculas/minusculas e o acesso a colunas com
    espaco no nome funciona ("{Job Title}").

    Campo ausente ou vazio nao deixa buraco: o separador que sobraria e
    removido. "{Empresa} - {Cargo}" sem cargo imprime "Lopes Advogados", e
    "{Setor} - {Item} / {Serie}" sem item imprime "TI - ABC123" -- os dois
    separadores que se encostaram viram um so. Se nenhum campo tiver valor o
    resultado e "", mesmo que o template tenha texto fixo."""
    partes = [p for p in _CAMPO.split(template or "") if p]
    pedacos, campos = [], []
    for parte in partes:
        if parte.startswith("{") and parte.endswith("}"):
            valor = _valor(registro, parte[1:-1])
            campos.append(valor)
            pedacos.append(valor)
        else:
            pedacos.append(parte)

    if not campos:
        return (template or "").strip()   # template sem nenhum {campo}
    if not any(campos):
        return ""                         # nada para dizer: nao imprime so a moldura

    texto = re.sub(r"\s+", " ", "".join(pedacos))
    texto = _VAZIOS.sub("", texto)         # "({Cargo})" sem cargo vira "()": some
    texto = _REPETIDOS.sub(r"\1", texto)
    return _PONTAS.sub("", re.sub(r"\s+", " ", texto))


def _valor(registro, chave):
    alvo = (chave or "").strip().lower()
    for k, v in registro.items():
        if isinstance(k, str) and k.strip().lower() == alvo:
            return (v or "").strip()
    return ""


def linhas_de(registro, args):
    """As duas linhas da etiqueta para um registro, segundo os templates."""
    return formatar(args.linha1, registro), formatar(args.linha2, registro)


def slug(text):
    keep = "".join(c if c.isalnum() else "_" for c in text)
    return keep.strip("_")[:40] or "etiqueta"


# ----------------------------------------------------------------- comandos


def cmd_preview(args, registros):
    PREVIEW_DIR.mkdir(exist_ok=True)
    for i, reg in enumerate(registros, 1):
        l1, l2 = linhas_de(reg, args)
        img = render_label(l1, l2, args.layout)
        out = PREVIEW_DIR / ("%02d_%s_%s.png" % (i, slug(l1), args.layout))
        img.save(out)
        print("  %s  (%dx%d px)  %s | %s" % (out.name, img.width, img.height, l1, l2))
    print("\n%d previa(s) em %s" % (len(registros), PREVIEW_DIR))


def open_printer(args):
    print("Conectando em %s ..." % args.port)
    return PrinterClient(SerialTransport(port=args.port))


def cmd_info(args, registros):
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


def cmd_print(args, registros):
    PREVIEW_DIR.mkdir(exist_ok=True)
    trabalhos = []
    for i, reg in enumerate(registros, 1):
        l1, l2 = linhas_de(reg, args)
        view = render_label(l1, l2, args.layout)
        view.save(PREVIEW_DIR / ("%02d_%s_%s.png" % (i, slug(l1), args.layout)))
        img = to_print(view, args.layout, args.rotate180)
        for _ in range(args.copies):
            trabalhos.append((l1, img))

    total = len(trabalhos)
    print("%d registro(s) x %d copia(s) = %d etiqueta(s)" % (len(registros), args.copies, total))

    pr = open_printer(args)

    # Uma etiqueta = um trabalho completo, e cada um so termina quando a
    # impressora confirma que imprimiu (print_image bloqueia no get_print_status).
    # Nao ha pausa chutada entre etiquetas: e a impressora que sabe onde o papel
    # parou e que acha o vinco com o sensor dela.
    falhas = []
    for n, (rotulo, img) in enumerate(trabalhos, 1):
        print("  [%d/%d] %s ... " % (n, total, rotulo), end="", flush=True)
        r = pr.print_image(img, density=args.density, row_delay=args.rowdelay)
        if r["completa"]:
            print("ok")
        else:
            falhas.append((rotulo, r))
            print("FALHOU (linha %s de %d)" % (r["linhas_ok"], r["esperado"]))

    if falhas:
        print("")
        print("Estas etiquetas nao sairam inteiras -- reimprima:")
        for rotulo, r in falhas:
            if not r["status"].get("zerou", True):
                motivo = ("o contador de progresso nao zerou -- a impressora nao "
                          "deu sinal confiavel de fim (a espera caiu para tempo fixo)")
            elif not r["status"].get("ok"):
                motivo = "a impressora nao confirmou o fim da impressao"
            else:
                motivo = "linhas descartadas; suba o --rowdelay"
            print("  %s: %s" % (rotulo, motivo))
    print("")
    print("Concluido.")


# -------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description="Etiquetas de duas linhas centralizadas na Niimbot B1 (USB/Windows)",
        epilog='Exemplo: py etiquetas.py preview --in ativos.csv '
               '--linha1 "{Patrimonio}" --linha2 "{Setor} - {Responsavel}"')
    ap.add_argument("cmd", choices=["info", "preview", "print"])
    ap.add_argument("--in", dest="infile", default=str(DEFAULT_IN),
                    help="arquivo .json (lista de objetos) ou .csv com cabecalho "
                         "(default: participantes.json)")
    ap.add_argument("--linha1", default=LINHA1_PADRAO,
                    help='template da linha de destaque; use {Coluna} '
                         '(default: "%s")' % LINHA1_PADRAO)
    ap.add_argument("--linha2", default=LINHA2_PADRAO,
                    help='template da linha de apoio; passe "" para deixar so a '
                         'linha 1 (default: "%s")' % LINHA2_PADRAO)
    ap.add_argument("--port", default="COM3", help="porta serial da B1 (default: COM3)")
    ap.add_argument("--layout", choices=["landscape", "portrait"], default="landscape",
                    help="landscape = texto no sentido dos 80 mm (default)")
    ap.add_argument("--density", type=int, default=5, choices=range(1, 6),
                    help="densidade de impressao 1-5 (default: 5)")
    ap.add_argument("--copies", type=int, default=1, help="copias por registro")
    ap.add_argument("--only", type=int, help="usa apenas o N-esimo registro (1-based)")
    ap.add_argument("--rotate180", action="store_true", help="gira 180 graus")
    ap.add_argument("--rowdelay", type=float, default=0.005,
                    help="pausa por linha enviada (s); a B1 descarta linhas se a rajada chegar rapido demais")
    args = ap.parse_args()

    registros = [] if args.cmd == "info" else load_registros(args.infile)
    if args.only:
        if not 1 <= args.only <= len(registros):
            sys.exit("--only fora do intervalo (1..%d)" % len(registros))
        registros = [registros[args.only - 1]]
    if args.cmd != "info":
        if not registros:
            sys.exit("Nenhum registro encontrado em " + args.infile)
        vazios = [i for i, r in enumerate(registros, 1) if not formatar(args.linha1, r)]
        if vazios:
            sys.exit("A linha 1 ficou vazia no(s) registro(s) %s. O template %r nao "
                     "casou com nenhuma coluna do arquivo -- colunas disponiveis: %s"
                     % (", ".join(map(str, vazios[:5])), args.linha1,
                        ", ".join(registros[vazios[0] - 1].keys())))

    {"info": cmd_info, "preview": cmd_preview, "print": cmd_print}[args.cmd](args, registros)


if __name__ == "__main__":
    main()
