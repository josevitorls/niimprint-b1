"""Testes que precisam da impressora ligada -- e que GASTAM ETIQUETA.

    py testes_hardware.py

O `testes.py` cobre o driver com uma impressora de mentira e roda na CI. Ele
nao consegue provar duas coisas, porque as duas dependem do papel andando:

  1. a fila realmente imprime, na ordem, um trabalho por vez;
  2. quando um comando falha no meio, a B1 **para** em vez de sair puxando
     papel em branco ate alguem desligar no botao.

O item 2 e o defeito que originou este fork. Reproduzi-lo esperando acontecer
sozinho e inviavel, entao aqui ele e provocado: o `set_dimension` e enviado de
verdade e a resposta e engolida no transporte, como se a impressora tivesse
ficado muda. E o cenario caro de reproduzir, de graca.

Nao entra no `testes.py` nem na CI de proposito: gasta etiqueta, precisa de
hardware e demora. Rode quando mexer no driver, antes de confiar nele num
evento.

    py testes_hardware.py --porta COM3     # se o auto nao achar
    py testes_hardware.py --so-fila        # sem o teste destrutivo
    py testes_hardware.py --sim            # nao pergunta (uso em script)

IMPORTANTE: confira o `LABEL_MM` em `etiquetas.py` antes de rodar. O script
mostra qual rolo esta na impressora, mas nao tem como saber a medida dele --
o RFID nao carrega milimetros (veja "Adaptando para outro rolo" no README).
"""
import argparse
import sys
import time

import etiquetas
from etiquetas import render_label, to_print
from fila import FilaImpressao
from niimbot import PrinterClient, PrinterSilent, SerialTransport
from niimbot.printer import RequestCodeEnum

ETIQUETAS_POR_TESTE = 3


# ------------------------------------------------------------------ apoio


def _cabecalho(titulo):
    print("\n" + "=" * 62)
    print(titulo)
    print("=" * 62)


def _rolo(porta):
    """Mostra o rolo montado. Serve de conferencia visual antes de gastar papel."""
    p = PrinterClient(SerialTransport(port=porta))
    try:
        r = p.get_rfid()
    except Exception as e:                       # rolo ausente ou sem RFID
        print("nao consegui ler o rolo: %r" % e)
        return None
    if r is None:
        print("a impressora nao respondeu com um rolo (sem papel?)")
        return None
    print("rolo na impressora : %s  (serial %s)" % (r["barcode"], r["serial"]))
    print("etiquetas restantes: ~%d de %d"
          % (r["total_len"] - r["used_len"], r["total_len"]))
    return r


def _coletor():
    """Devolve (eventos, ao_comecar, ao_terminar) prontos para a fila."""
    eventos = []

    def comecou(pedido):
        print("  -> %s" % pedido["ref"])

    def terminou(pedido, resultado, erro):
        eventos.append((pedido["ref"], resultado, erro))
        if erro:
            print("  <- %s ERRO %s: %s" % (pedido["ref"], type(erro).__name__, erro))
        else:
            print("  <- %s ok, completa=%s" % (pedido["ref"], resultado["completa"]))

    return eventos, comecou, terminou


def _saiu_inteira(par):
    resultado, erro = par
    return erro is None and resultado is not None and resultado["completa"]


# ------------------------------------------------------- teste 1: a fila


def teste_fila(porta, layout):
    """Tres cracha seguidos pela fila. Prova ordem, unitariedade e callbacks."""
    _cabecalho("1/2  A fila imprime tres etiquetas, uma de cada vez")

    # Conferir o desenho ANTES de mandar para o papel: se a geometria estiver
    # errada, o assert avisa sem gastar etiqueta.
    img = to_print(render_label("Conferencia", "de geometria", layout), layout)
    print("imagem para o papel: %d x %d px  (LABEL_MM = %s)"
          % (img.width, img.height, (etiquetas.LABEL_MM,)))
    assert img.width == etiquetas.HEAD_PX, "largura tem de ser a da cabeca"
    assert img.height == etiquetas.FEED_PX, "altura tem de ser o comprimento do rolo"

    eventos, comecou, terminou = _coletor()
    fila = FilaImpressao(porta=porta, layout=layout,
                         ao_comecar=comecou, ao_terminar=terminou)
    t0 = time.monotonic()
    fila.imprimir_cracha("Jose Vitor Lopes", "Lopes Advogados", "Socio", ref="L1")
    fila.imprimir_cracha("Maria Eduarda Nascimento", "Prefeitura Municipal",
                         "Secretaria de Inovacao", ref="L2")
    fila.imprimir_cracha("Patricia Lima", "Vertex", "CTO", ref="L3")
    enfileirou_em = time.monotonic() - t0
    fila.encerrar()
    total = time.monotonic() - t0

    por_ref = {ref: (res, err) for ref, res, err in eventos}
    ordem = [e[0] for e in eventos] == ["L1", "L2", "L3"]
    inteiras = all(_saiu_inteira(por_ref.get(r, (None, None)))
                   for r in ("L1", "L2", "L3"))

    print("\nenfileirar devolveu o controle em %.3f s" % enfileirou_em)
    print("tres etiquetas em %.1f s (%.1f s cada)" % (total, total / 3))
    print("as tres sairam inteiras ....", "sim" if inteiras else "NAO")
    print("ordem preservada ...........", "sim" if ordem else "NAO")
    return inteiras and ordem and enfileirou_em < 1.0


# --------------------------------------------- teste 2: a etiqueta quebrada


def teste_quebra(porta, layout, espera=5.0):
    """Amordaca o set_dimension no meio de um trabalho e ve o que a B1 faz.

    Este e o teste que importa. Antes da correcao, `print_image` so chamava
    `end_print()` no caminho feliz: a pagina ficava aberta e a impressora
    puxava papel em branco sem parar. Agora `end_print()` roda no `finally`.
    """
    _cabecalho("2/2  Uma etiqueta quebrada de proposito nao derruba a fila")

    eventos, comecou, terminou = _coletor()
    fila = FilaImpressao(porta=porta, layout=layout,
                         ao_comecar=comecou, ao_terminar=terminou)

    # A mordaca fica no transporte, nao no driver: o comando SAI de verdade e
    # so a resposta some. E o que a impressora muda faz na pratica.
    transporte = fila._impressora._transport
    write_real, read_real = transporte.write, transporte.read
    estado = {"armado": False, "mudo": False, "engolidas": 0}

    def write_espiao(data):
        # 55 55 <tipo> <len> <dados> <xor> aa aa
        if estado["armado"] and len(data) > 2 and data[2] == RequestCodeEnum.SET_DIMENSION:
            estado["mudo"] = True
            print("     [mordaca] set_dimension enviado, resposta sera engolida")
        return write_real(data)

    def read_espiao(length):
        if estado["mudo"]:
            estado["engolidas"] += 1
            read_real(length)        # drena o fio para nao sujar o proximo trabalho
            return b""
        return read_real(length)

    transporte.write, transporte.read = write_espiao, read_espiao

    print("etiqueta 1 -- normal, so para ter uma referencia boa")
    fila.imprimir("Antes", "deve sair inteira", ref="L1")
    fila.esperar()

    print("\netiqueta 2 -- com o set_dimension mudo")
    estado["armado"] = True
    fila.imprimir("Quebrada", "nao deve sair", ref="L2")
    fila.esperar()
    estado["armado"] = estado["mudo"] = False

    print("\n     olhando a impressora por %.0f s: ela NAO pode puxar papel..."
          % espera)
    time.sleep(espera)

    print("\netiqueta 3 -- a prova de que a fila sobreviveu")
    fila.imprimir("Depois", "a fila sobreviveu", ref="L3")
    fila.esperar()
    fila.encerrar()

    por_ref = {ref: (res, err) for ref, res, err in eventos}
    boa = _saiu_inteira(por_ref.get("L1", (None, None)))
    quebrou = isinstance(por_ref.get("L2", (None, None))[1], PrinterSilent)
    seguinte = _saiu_inteira(por_ref.get("L3", (None, None)))

    print("\nrespostas engolidas: %d" % estado["engolidas"])
    print("1. a etiqueta boa saiu .....................", "sim" if boa else "NAO")
    print("2. a quebrada falhou com PrinterSilent .....", "sim" if quebrou else "NAO")
    if quebrou:
        print("   mensagem: %s" % por_ref["L2"][1])
    print("3. a fila imprimiu a seguinte ..............", "sim" if seguinte else "NAO")
    print("4. a impressora ficou parada ...............  confira o papel")
    return boa and quebrou and seguinte


# -------------------------------------------------------------------- cli


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Testes com a impressora ligada. Gastam etiqueta.")
    ap.add_argument("--porta", default="auto", help="COM3, /dev/ttyUSB0... (default: auto)")
    ap.add_argument("--layout", default="landscape", choices=("landscape", "portrait"))
    ap.add_argument("--so-fila", action="store_true",
                    help="pula o teste destrutivo (metade das etiquetas)")
    ap.add_argument("--sim", action="store_true", help="nao pedir confirmacao")
    args = ap.parse_args(argv)

    testes = [("fila", teste_fila)]
    if not args.so_fila:
        testes.append(("quebra", teste_quebra))
    gasto = ETIQUETAS_POR_TESTE * len(testes)

    print(__doc__.split("\n")[0])
    print("\nIsto vai imprimir de verdade e consumir cerca de %d etiquetas." % gasto)
    _rolo(args.porta)
    print("LABEL_MM em etiquetas.py: %s -- tem de bater com o rolo acima."
          % (etiquetas.LABEL_MM,))

    if not args.sim:
        try:
            if input("\nseguir? [s/N] ").strip().lower() not in ("s", "sim", "y"):
                print("cancelado, nenhuma etiqueta gasta.")
                return 0
        except EOFError:
            print("\nsem terminal interativo -- use --sim para rodar assim mesmo.")
            return 2

    resultados = [(nome, f(args.porta, args.layout)) for nome, f in testes]

    _cabecalho("VEREDITO")
    for nome, ok in resultados:
        print("%-8s %s" % (nome, "passou" if ok else "FALHOU"))
    tudo = all(ok for _, ok in resultados)
    print("\n%s" % ("tudo certo -- pode confiar no driver neste rolo." if tudo
                    else "algo falhou. NAO leve para um evento assim."))
    return 0 if tudo else 1


if __name__ == "__main__":
    sys.exit(main())
