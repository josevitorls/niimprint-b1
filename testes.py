# -*- coding: utf-8 -*-
"""Testes que rodam SEM impressora.

    py testes.py

Uma impressora de mentira responde o protocolo da B1 no lugar da serial. Isso
permite testar justamente o que e caro testar no hardware: o que acontece
quando a impressora fica muda no meio de um trabalho. Esse caso ja aconteceu
de verdade -- a B1 ficou com a pagina aberta e nao parava de puxar papel em
branco -- e e o que os dois primeiros testes existem para impedir que volte.

Nada aqui abre porta serial. Pode rodar em CI.
"""
import struct
import sys
import unittest

import etiquetas
import fila as fila_mod
from fila import FilaImpressao
from niimbot import NiimbotPacket, PrinterClient, PrinterSilent
from niimbot import printer as printer_mod
from niimbot.printer import InfoEnum, RequestCodeEnum, SerialTransport

# Resposta real de GET_RFID capturada da B1 (firmware 13.06) com um rolo
# TT40*30-230 montado. 49 bytes: o niimprint original assumia que sobravam
# exatamente 5 depois do serial e estourava no unpack.
RFID_B1 = bytes.fromhex(
    "881df973eb9600000830383236323130341050433046433238333031303030383739"
    "011400d90500e6881df973eb960000")

# reqcode -> (codigo da resposta, corpo). Os offsets vem do _transceive.
ACKS = {
    RequestCodeEnum.SET_LABEL_TYPE: 16,
    RequestCodeEnum.SET_LABEL_DENSITY: 16,
    RequestCodeEnum.START_PRINT: 1,
    RequestCodeEnum.END_PRINT: 1,
    RequestCodeEnum.START_PAGE_PRINT: 1,
    RequestCodeEnum.END_PAGE_PRINT: 1,
    RequestCodeEnum.ALLOW_PRINT_CLEAR: 16,
    RequestCodeEnum.SET_DIMENSION: 1,
    RequestCodeEnum.SET_QUANTITY: 1,
}

LINHA_DE_IMAGEM = 0x85


class ImpressoraFalsa:
    """Transporte que fala o protocolo da B1 e obedece um roteiro de falhas.

    mudo: {reqcode: quantas vezes ignorar}. Simula o comando que nao volta --
    a origem do 'NoneType object has no attribute data' que derrubava o
    trabalho no meio.
    """

    def __init__(self, mudo=None):
        self.mudo = dict(mudo or {})
        self.enviados = []          # reqcodes recebidos, na ordem
        self.linhas = 0             # pacotes de imagem recebidos
        self._saida = bytearray()
        self._polls = 99            # 99 = ainda nao fechou pagina

    # -- lado do transporte -------------------------------------------------
    def write(self, data):
        buf = bytearray(data)
        while len(buf) > 4:
            n = buf[3] + 7
            if len(buf) < n:
                break
            self._tratar(NiimbotPacket.from_bytes(bytes(buf[:n])))
            del buf[:n]
        return len(data)

    def read(self, length):
        saiu = bytes(self._saida[:length])
        del self._saida[:length]
        return saiu

    def read_available(self):
        return b""

    # -- lado da impressora -------------------------------------------------
    def _responder(self, tipo, corpo):
        self._saida.extend(NiimbotPacket(tipo, corpo).to_bytes())

    def _tratar(self, pkt):
        req = pkt.type
        if req == LINHA_DE_IMAGEM:
            self.linhas += 1
            return
        self.enviados.append(req)
        if self.mudo.get(req):
            self.mudo[req] -= 1
            return                                  # fica calada de proposito

        if req == RequestCodeEnum.GET_INFO:
            chave = pkt.data[0]
            corpo = b"\x05" if chave == InfoEnum.LABELTYPE else b"\x01"
            self._responder(req + chave, corpo)
        elif req == RequestCodeEnum.GET_RFID:
            self._responder(req + 1, RFID_B1)
        elif req == RequestCodeEnum.GET_PRINT_STATUS:
            # A B1 so zera o contador no end_page_print; antes disso ela
            # devolve 100/100, que e lixo do trabalho anterior.
            p = (0, 0) if self._polls < 2 else (100, 100)
            self._polls += 1
            self._responder(req + 16, struct.pack(">HBB", 1, *p) + b"\x00" * 6)
        elif req in ACKS:
            if req == RequestCodeEnum.END_PAGE_PRINT:
                self._polls = 0
            self._responder(req + ACKS[req], b"\x01")


def imagem_pronta():
    return etiquetas.to_print(etiquetas.render_label("Teste", "linha 2"),
                              "landscape")


class TrabalhoSempreFecha(unittest.TestCase):
    """O caso que virou impressora desgovernada na bancada."""

    def test_end_print_mesmo_com_comando_mudo(self):
        falsa = ImpressoraFalsa(mudo={RequestCodeEnum.SET_DIMENSION: 1})
        pr = PrinterClient(falsa)
        with self.assertRaises(PrinterSilent):
            pr.print_image(imagem_pronta(), row_delay=0)
        self.assertIn(RequestCodeEnum.END_PRINT, falsa.enviados,
                      "trabalho ficou aberto: a B1 continuaria puxando papel")

    def test_erro_diz_qual_comando_ficou_mudo(self):
        falsa = ImpressoraFalsa(mudo={RequestCodeEnum.SET_DIMENSION: 1})
        pr = PrinterClient(falsa)
        try:
            pr.print_image(imagem_pronta(), row_delay=0)
        except PrinterSilent as e:
            self.assertIn("set_dimension", str(e))
        else:
            self.fail("deveria ter levantado PrinterSilent")

    def test_sucesso_fecha_o_trabalho_uma_vez_so(self):
        falsa = ImpressoraFalsa()
        pr = PrinterClient(falsa)
        r = pr.print_image(imagem_pronta(), row_delay=0)
        self.assertTrue(r["completa"])
        self.assertTrue(r["status"]["zerou"])
        self.assertEqual(falsa.enviados.count(RequestCodeEnum.END_PRINT), 1)
        self.assertEqual(falsa.linhas, etiquetas.FEED_PX)


class FilaSeRecupera(unittest.TestCase):
    """Uma etiqueta ruim nao pode levar a fila junto -- e a proxima tem de sair."""

    def setUp(self):
        self.original = fila_mod.SerialTransport
        self.falsa = ImpressoraFalsa(mudo={RequestCodeEnum.SET_DIMENSION: 1})
        fila_mod.SerialTransport = lambda port: self.falsa

    def tearDown(self):
        fila_mod.SerialTransport = self.original

    def test_proxima_etiqueta_sai_depois_de_uma_falha(self):
        vistos = []
        f = FilaImpressao(porta="falsa", row_delay=0,
                          ao_terminar=lambda p, r, e: vistos.append((p, r, e)))
        f.imprimir("Primeira", "esta vai falhar")
        f.imprimir("Segunda", "esta tem de sair")
        f.esperar()
        f.encerrar()

        self.assertEqual(len(vistos), 2)
        (p1, r1, e1), (p2, r2, e2) = vistos
        self.assertIsInstance(e1, PrinterSilent)
        self.assertIsNone(r1)
        self.assertIsNone(e2, "a fila morreu junto com a etiqueta ruim")
        self.assertTrue(r2["completa"])
        self.assertEqual(p2["linha1"], "Segunda")
        # dois trabalhos abertos, dois fechados: nenhum ficou pendurado
        self.assertEqual(falsos_end_print(self.falsa), 2)


def falsos_end_print(falsa):
    return falsa.enviados.count(RequestCodeEnum.END_PRINT)


class LeituraDoRolo(unittest.TestCase):
    def test_rfid_da_b1_nao_estoura(self):
        pr = PrinterClient(ImpressoraFalsa())
        r = pr.get_rfid()
        self.assertEqual(r["barcode"], "08262104")
        self.assertEqual(r["serial"], "PC0FC28301000879")
        self.assertEqual(r["total_len"], 276)
        self.assertEqual(r["used_len"], 217)
        self.assertEqual(r["type"], 5)


class PortaAutomatica(unittest.TestCase):
    class Porta:
        def __init__(self, device, vid=None):
            self.device, self.vid = device, vid
            self.description, self.hwid = device, device

    def setUp(self):
        self.original = printer_mod.list_comports

    def tearDown(self):
        printer_mod.list_comports = self.original

    def test_ignora_a_com1_legada(self):
        # O caso real: um Windows com a COM1 de ACPI sempre presente. O
        # niimprint original desistia aqui e o "auto" nunca funcionava.
        printer_mod.list_comports = lambda: [self.Porta("COM1"),
                                             self.Porta("COM3", vid=0x3513)]
        self.assertEqual(SerialTransport._detect_port(SerialTransport), "COM3")

    def test_ambiguidade_lista_as_candidatas(self):
        printer_mod.list_comports = lambda: [self.Porta("COM3", vid=0x3513),
                                             self.Porta("COM4", vid=0x3513)]
        with self.assertRaises(RuntimeError) as ctx:
            SerialTransport._detect_port(SerialTransport)
        self.assertIn("COM3", str(ctx.exception))
        self.assertIn("COM4", str(ctx.exception))


class Geometria(unittest.TestCase):
    def test_imagem_cabe_na_cabeca(self):
        img = imagem_pronta()
        self.assertEqual(img.width, etiquetas.HEAD_PX)
        self.assertEqual(img.height, etiquetas.FEED_PX)


if __name__ == "__main__":
    sys.exit(not unittest.main(exit=False, verbosity=2).result.wasSuccessful())
