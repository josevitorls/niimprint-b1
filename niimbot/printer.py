import abc
import enum
import logging
import math
import socket
import struct
import time

import serial
from PIL import Image, ImageOps
from serial.tools.list_ports import comports as list_comports

from .packet import NiimbotPacket


class InfoEnum(enum.IntEnum):
    DENSITY = 1
    PRINTSPEED = 2
    LABELTYPE = 3
    LANGUAGETYPE = 6
    AUTOSHUTDOWNTIME = 7
    DEVICETYPE = 8
    SOFTVERSION = 9
    BATTERY = 10
    DEVICESERIAL = 11
    HARDVERSION = 12


class RequestCodeEnum(enum.IntEnum):
    GET_INFO = 64  # 0x40
    GET_RFID = 26  # 0x1A
    HEARTBEAT = 220  # 0xDC
    SET_LABEL_TYPE = 35  # 0x23
    SET_LABEL_DENSITY = 33  # 0x21
    START_PRINT = 1  # 0x01
    END_PRINT = 243  # 0xF3
    START_PAGE_PRINT = 3  # 0x03
    END_PAGE_PRINT = 227  # 0xE3
    ALLOW_PRINT_CLEAR = 32  # 0x20
    SET_DIMENSION = 19  # 0x13
    SET_QUANTITY = 21  # 0x15
    GET_PRINT_STATUS = 163  # 0xA3


class PrinterBusy(RuntimeError):
    """A impressora recusou o comando (resposta 0xDB).

    Acontece quando a B1 esta travada: tampa aberta, rolo acabado ou mal
    encaixado, ou um trabalho anterior interrompido no meio. Ela so volta a
    aceitar start_print depois de destravar -- na pratica, desligar e ligar.
    """

    def __init__(self, dados: bytes):
        self.codigo = dados[0] if dados else None
        super().__init__(
            "a impressora recusou o comando (0xDB codigo %s). Verifique a "
            "tampa, o rolo e se sobrou trabalho travado; se persistir, "
            "desligue e ligue a B1." % (self.codigo,))


def _packet_to_int(x):
    return int.from_bytes(x.data, "big")


class PrinterSilent(RuntimeError):
    """A impressora recebeu o comando e nao respondeu nada.

    _transceive desiste depois de 6 tentativas e devolve None. O niimprint
    original fazia bool(packet.data[0]) direto em cima disso, e o None virava
    um AttributeError sem contexto -- no meio de um trabalho aberto, o erro
    que chegava ao usuario nao dizia qual comando tinha ficado mudo.
    """


class BaseTransport(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def read(self, length: int) -> bytes:
        raise NotImplementedError

    @abc.abstractmethod
    def write(self, data: bytes):
        raise NotImplementedError


class BluetoothTransport(BaseTransport):
    def __init__(self, address: str):
        self._sock = socket.socket(
            socket.AF_BLUETOOTH,
            socket.SOCK_STREAM,
            socket.BTPROTO_RFCOMM,
        )
        self._sock.connect((address, 1))

    def read(self, length: int) -> bytes:
        return self._sock.recv(length)

    def write(self, data: bytes):
        return self._sock.send(data)


class SerialTransport(BaseTransport):
    def __init__(self, port: str = "auto"):
        port = port if port != "auto" else self._detect_port()
        self._serial = serial.Serial(port=port, baudrate=115200, timeout=0.5)

    # A B1 se apresenta no Windows como USB serial nativo com VID 0x3513.
    VID_NIIMBOT = 0x3513

    def _detect_port(self):
        """Acha a impressora sozinho, ignorando portas que nao sao dela.

        O niimprint original desistia assim que existisse mais de uma porta
        serial -- e quase toda maquina Windows tem uma COM1 legada de ACPI que
        nunca vai ser uma impressora. Na pratica o "auto" nunca funcionava.
        Filtrar pelo VID resolve o caso comum; se ainda sobrar ambiguidade, o
        erro lista as candidatas para voce escolher.
        """
        todas = list(list_comports())
        if not todas:
            raise RuntimeError("Nenhuma porta serial encontrada.")
        candidatas = [p for p in todas
                      if getattr(p, "vid", None) == self.VID_NIIMBOT] or todas
        if len(candidatas) == 1:
            return candidatas[0].device
        msg = ("Mais de uma porta candidata. Passe a porta explicitamente, "
               "por exemplo SerialTransport(port=\"COM3\"):")
        for p in candidatas:
            msg += "\n- %s : %s [%s]" % (p.device, p.description, p.hwid)
        raise RuntimeError(msg)

    def read(self, length: int) -> bytes:
        """Le uma resposta sem pagar o timeout inteiro.

        O niimprint pedia read(1024). O pyserial so devolve quando junta os
        1024 bytes OU quando o timeout de 0,5 s estoura -- e a B1 responde com
        ~8 bytes. Resultado: TODO comando custava 0,5 s cravados. Sao 7
        comandos antes da primeira linha, ou seja 3,5 s de papel parado, mais
        0,5 s por consulta de status no fim.

        Aqui bloqueia so ate o primeiro byte chegar e depois leva o que ja
        esta no buffer. Se o resto do pacote ainda estiver no fio, quem chama
        (_transceive) tenta de novo e o _packetbuf acumula."""
        dados = self._serial.read(1)
        if dados:
            pendente = min(length - 1, self._serial.in_waiting)
            if pendente > 0:
                dados += self._serial.read(pendente)
        return dados

    def read_available(self) -> bytes:
        """Le so o que ja chegou, sem bloquear. Usado pra escutar a impressora
        enquanto as linhas estao sendo enviadas."""
        n = self._serial.in_waiting
        return self._serial.read(n) if n else b""

    def write(self, data: bytes):
        n = self._serial.write(data)
        self._serial.flush()  # espera sair do buffer do SO antes de seguir
        return n


class PrinterClient:
    def __init__(self, transport):
        self._transport = transport
        self._packetbuf = bytearray()

    def wait_until_done(self, timeout: float = 25.0, poll: float = 0.05,
                        graca: float = 1.5):
        """Espera a impressora dizer que terminou de IMPRIMIR, nao so de receber.

        get_print_status devolve progress1 = quanto ela ja recebeu e progress2 =
        quanto ela ja imprimiu. Enquanto o papel anda, progress2 fica atras.
        Medido na B1: depois do end_page_print, progress2 leva ~0,75 s para ir
        de 0 a 100.

        Nao da para trocar isto por end_print(): na B1 ele responde True na
        primeira tentativa, com a etiqueta ainda saindo. Era o que fazia a versao
        antiga atropelar uma etiqueta na outra.

        A armadilha: PARADA, a B1 responde 100/100 -- o resultado do trabalho
        anterior. Ela so zera no end_page_print, nao no start_print. Medido:

            apos start_print      p1=100 p2=100   <- lixo do trabalho anterior
            apos ultima linha     p1=100 p2=100   <- ainda lixo
            apos end_page_print   p1=  0 p2=  0   <- zerou aqui
            +0,75s                p1=100 p2=100   <- terminou de verdade

        Por isso 100/100 so vale depois de a gente ter visto o contador zerar.
        Aceitar o primeiro 100/100 daria "terminei" instantaneo com a etiqueta
        ainda na cabeca -- e pior, com completa=True, falhando calado.

        Se o zero nao vier em `graca` segundos, o contador esta presumidamente
        preso; ai nao ha sinal em que confiar e a espera cai para um tempo fixo.

        Devolve o ultimo status lido, com "ok" False se estourou o tempo e
        "zerou" dizendo se o sinal foi confiavel.
        """
        limite = time.monotonic() + timeout
        prazo_zero = time.monotonic() + graca
        ultimo = None
        zerou = False
        while time.monotonic() < limite:
            try:
                ultimo = self.get_print_status()
            except Exception:
                time.sleep(poll)
                continue
            completo = ultimo["progress1"] >= 100 and ultimo["progress2"] >= 100
            if not completo:
                zerou = True
            elif zerou:
                ultimo["ok"] = True
                ultimo["zerou"] = True
                return ultimo
            elif time.monotonic() > prazo_zero:
                time.sleep(2.0)
                ultimo = dict(ultimo)
                ultimo["ok"] = True
                ultimo["zerou"] = False
                return ultimo
            time.sleep(poll)
        ultimo = dict(ultimo or {})
        ultimo["ok"] = False
        ultimo["zerou"] = zerou
        return ultimo

    def print_image(self, image: Image, density: int = 3, label_type: int = None,
                    row_delay: float = 0.005, timeout: float = 25.0,
                    sniff: bool = False):
        """Imprime UMA etiqueta como um trabalho completo, do inicio ao fim.

        So devolve o controle quando a impressora confirma que imprimiu a pagina
        inteira. Nao existe sleep chutado entre etiquetas: quem sabe onde o papel
        parou e a impressora, que enxerga o vinco com o sensor dela. Chamar isto
        em sequencia imprime uma de cada vez, sem aperto.

        row_delay: pausa por linha enviada. A B1 descarta linhas se a rajada
        chegar mais rapido do que ela imprime, e nao devolve erro nenhum.
            0,005 e o default por medicao: 0,020 leva 14,0 s por etiqueta,
            0,005 leva 6,0 s e 0,002 leva 4,5 s, todos sem linha perdida. O
            passo de 0,005 para 0,002 rende 1,5 s e gasta a folga inteira --
            nao vale, porque a falha nao avisa: sai uma etiqueta truncada.
        sniff: guarda em self.chatter o hex bruto do que a impressora falou.

        Devolve um dict:
            linhas_ok  ultima linha que a impressora confirmou
            esperado   ultima linha da imagem (image.height - 1)
            completa   True se a pagina inteira foi aceita e impressa
            status     ultimo get_print_status
            tempos     papel / envio / espera / total, em segundos
        """
        t_inicio = time.monotonic()
        # O tipo precisa bater com o rolo instalado. Forcar 1 (com gap) num rolo
        # transparente (tipo 5) faz a etiqueta sair em branco na B1.
        # None = pergunta a impressora qual rolo ela detectou.
        if label_type is None:
            label_type = self.get_info(InfoEnum.LABELTYPE) or 1
        self.set_label_density(density)
        self.set_label_type(label_type)
        self.start_print()
        encerrado = False
        try:
            self.start_page_print()
            self.set_dimension(image.height, image.width)
            self.set_quantity(1)  # aceito pela B1 (firmware 13.06)

            self.chatter = []
            progresso = bytearray()
            read_avail = getattr(self._transport, "read_available", None)
            t_papel = None
            for i, pkt in enumerate(self._encode_image(image)):
                self._send(pkt)
                if t_papel is None:
                    # A B1 imprime conforme as linhas chegam: quando a primeira linha
                    # entra no fio, o papel ja comecou a andar.
                    t_papel = time.monotonic()
                if row_delay:
                    time.sleep(row_delay)
                if read_avail:
                    extra = read_avail()
                    if extra:
                        progresso.extend(extra)
                        if sniff:
                            self.chatter.append((0, i, extra.hex()))
            t_envio_fim = time.monotonic()
            self.end_page_print()
            if read_avail:
                progresso.extend(read_avail())

            status = self.wait_until_done(timeout=timeout)
            t_fim = time.monotonic()
            self.end_print()
            encerrado = True

            self.last_ack = self._last_progress_row(progresso)
            esperado = image.height - 1
            return {"linhas_ok": self.last_ack,
                    "esperado": esperado,
                    "completa": bool(status.get("ok")) and (
                        self.last_ack is None or self.last_ack >= esperado),
                    "status": status,
                    "tempos": {
                        # papel: do inicio do trabalho ate a primeira linha sair --
                        #        e quando a etiqueta comeca a se mexer.
                        # envio: as 639 linhas, no ritmo do row_delay.
                        # espera: do fim do envio ate a impressora confirmar o fim.
                        "papel": (t_papel or t_inicio) - t_inicio,
                        "envio": t_envio_fim - (t_papel or t_inicio),
                        "espera": t_fim - t_envio_fim,
                        "total": t_fim - t_inicio,
                    }}
        finally:
            # end_print() SEMPRE. Sem isto, qualquer excecao no meio do
            # trabalho deixa a B1 com a pagina aberta: ela continua puxando
            # papel em branco e so para no botao de desligar. Foi assim que
            # uma etiqueta ruim virou uma impressora desgovernada.
            if not encerrado:
                try:
                    self.end_print()
                except Exception:
                    pass


    @staticmethod
    def _last_progress_row(buf: bytes):
        """Le os pacotes de progresso 0xD3 que a B1 emite a cada 200 linhas.
        Formato: 55 55 d3 03 <linha:2> <pagina:1> <checksum> aa aa"""
        last = None
        for i in range(len(buf) - 5):
            if buf[i] == 0x55 and buf[i + 1] == 0x55 and buf[i + 2] == 0xD3:
                last = int.from_bytes(buf[i + 4:i + 6], "big")
        return last

    def _encode_image(self, image: Image):
        img = ImageOps.invert(image.convert("L")).convert("1")
        for y in range(img.height):
            line_data = [img.getpixel((x, y)) for x in range(img.width)]
            line_data = "".join("0" if pix == 0 else "1" for pix in line_data)
            line_data = int(line_data, 2).to_bytes(math.ceil(img.width / 8), "big")
            counts = (0, 0, 0)  # confirmado na B1: zeros funcionam
            header = struct.pack(">H3BB", y, *counts, 1)
            pkt = NiimbotPacket(0x85, header + line_data)
            yield pkt

    def _recv(self):
        packets = []
        self._packetbuf.extend(self._transport.read(1024))
        while len(self._packetbuf) > 4:
            pkt_len = self._packetbuf[3] + 7
            if len(self._packetbuf) < pkt_len:
                # Pacote pela metade: o resto ainda esta no fio. Sai e deixa o
                # buffer acumular ate a proxima leitura.
                # (No niimprint original nao havia este break: com um pacote
                # incompleto no buffer o laco girava para sempre, travando o
                # processo em 100% de CPU. So nao aparecia porque read(1024)
                # esperava o timeout inteiro e quase sempre trazia o pacote
                # completo de uma vez.)
                break
            packet = NiimbotPacket.from_bytes(self._packetbuf[:pkt_len])
            self._log_buffer("recv", packet.to_bytes())
            packets.append(packet)
            del self._packetbuf[:pkt_len]
        return packets

    def _send(self, packet):
        self._transport.write(packet.to_bytes())

    def _log_buffer(self, prefix: str, buff: bytes):
        msg = ":".join(f"{i:#04x}"[-2:] for i in buff)
        logging.debug(f"{prefix}: {msg}")

    def _transceive(self, reqcode, data, respoffset=1):
        respcode = respoffset + reqcode
        packet = NiimbotPacket(reqcode, data)
        self._log_buffer("send", packet.to_bytes())
        self._send(packet)
        resp = None
        for _ in range(6):
            for packet in self._recv():
                if packet.type == 219:
                    # 0xDB e a recusa da impressora. O niimprint levantava um
                    # ValueError vazio, que nao dizia nada -- e este e
                    # justamente o erro que aparece quando a B1 esta travada
                    # (tampa aberta, papel acabado ou trabalho anterior
                    # abortado no meio). Sem o codigo nao da para agir.
                    raise PrinterBusy(packet.data)
                elif packet.type == 0:
                    raise NotImplementedError
                elif packet.type == respcode:
                    resp = packet
            if resp:
                return resp
            time.sleep(0.1)
        return resp

    def _exigir(self, nome, reqcode, data, respoffset=1):
        """Como _transceive, mas a resposta e obrigatoria."""
        packet = self._transceive(reqcode, data, respoffset)
        if packet is None:
            raise PrinterSilent(
                "sem resposta a %s (req 0x%02X) apos 6 tentativas" % (nome, reqcode))
        return packet

    def _comando(self, nome, reqcode, data, respoffset=1):
        """Comando de controle: devolve o ack da impressora como bool."""
        return bool(self._exigir(nome, reqcode, data, respoffset).data[0])

    def get_info(self, key):
        if packet := self._transceive(RequestCodeEnum.GET_INFO, bytes((key,)), key):
            match key:
                case InfoEnum.DEVICESERIAL:
                    return packet.data.hex()
                case InfoEnum.SOFTVERSION:
                    return _packet_to_int(packet) / 100
                case InfoEnum.HARDVERSION:
                    return _packet_to_int(packet) / 100
                case _:
                    return _packet_to_int(packet)
        else:
            return None

    def get_rfid(self):
        packet = self._exigir("get_rfid", RequestCodeEnum.GET_RFID, b"\x01")
        data = packet.data

        if data[0] == 0:
            return None
        uuid = data[0:8].hex()
        idx = 8

        barcode_len = data[idx]
        idx += 1
        barcode = data[idx : idx + barcode_len].decode()

        idx += barcode_len
        serial_len = data[idx]
        idx += 1
        serial = data[idx : idx + serial_len].decode()

        idx += serial_len
        # A B1 devolve mais bytes depois deste bloco (repete o uuid, entre
        # outros). O niimprint fatiava ate o fim e o unpack estourava com
        # "requires a buffer of 5 bytes". Le so os 5 que interessam.
        total_len, used_len, type_ = struct.unpack(">HHB", data[idx:idx + 5])
        return {
            "uuid": uuid,
            "barcode": barcode,
            "serial": serial,
            "used_len": used_len,
            "total_len": total_len,
            "type": type_,
        }

    def heartbeat(self):
        packet = self._exigir("heartbeat", RequestCodeEnum.HEARTBEAT, b"\x01")
        closingstate = None
        powerlevel = None
        paperstate = None
        rfidreadstate = None

        match len(packet.data):
            case 20:
                paperstate = packet.data[18]
                rfidreadstate = packet.data[19]
            case 13:
                closingstate = packet.data[9]
                powerlevel = packet.data[10]
                paperstate = packet.data[11]
                rfidreadstate = packet.data[12]
            case 19:
                closingstate = packet.data[15]
                powerlevel = packet.data[16]
                paperstate = packet.data[17]
                rfidreadstate = packet.data[18]
            case 10:
                closingstate = packet.data[8]
                powerlevel = packet.data[9]
                rfidreadstate = packet.data[8]
            case 9:
                closingstate = packet.data[8]

        return {
            "closingstate": closingstate,
            "powerlevel": powerlevel,
            "paperstate": paperstate,
            "rfidreadstate": rfidreadstate,
        }

    def set_label_type(self, n):
        assert 1 <= n <= 6
        return self._comando("set_label_type", RequestCodeEnum.SET_LABEL_TYPE,
                             bytes((n,)), 16)

    def set_label_density(self, n):
        assert 1 <= n <= 5  # B21 has 5 levels, not sure for D11
        return self._comando("set_label_density", RequestCodeEnum.SET_LABEL_DENSITY,
                             bytes((n,)), 16)

    def start_print(self):
        return self._comando("start_print", RequestCodeEnum.START_PRINT, b"\x01")

    def end_print(self):
        return self._comando("end_print", RequestCodeEnum.END_PRINT, b"\x01")

    def start_page_print(self):
        return self._comando("start_page_print", RequestCodeEnum.START_PAGE_PRINT, b"\x01")

    def end_page_print(self):
        return self._comando("end_page_print", RequestCodeEnum.END_PAGE_PRINT, b"\x01")

    def allow_print_clear(self):
        return self._comando("allow_print_clear", RequestCodeEnum.ALLOW_PRINT_CLEAR,
                             b"\x01", 16)

    def set_dimension(self, w, h):
        return self._comando("set_dimension", RequestCodeEnum.SET_DIMENSION,
                             struct.pack(">HH", w, h))

    def set_quantity(self, n):
        return self._comando("set_quantity", RequestCodeEnum.SET_QUANTITY,
                             struct.pack(">H", n))

    def get_print_status(self):
        packet = self._exigir("get_print_status", RequestCodeEnum.GET_PRINT_STATUS,
                              b"\x01", 16)
        # A B1 devolve 10 bytes; o niimprint original desempacotava 4 (formato
        # da B21) e estourava. Os 4 primeiros sao os que interessam.
        page, progress1, progress2 = struct.unpack(">HBB", packet.data[:4])
        return {"page": page, "progress1": progress1, "progress2": progress2,
                "raw": packet.data.hex()}
