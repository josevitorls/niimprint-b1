"""Fila de impressao: recebe pedidos na hora e imprime um de cada vez.

Serve para qualquer aplicacao que peca etiquetas sob demanda -- um posto de
check-in, um balcao de retirada, uma bancada de etiquetagem. O padrao e sempre
o mesmo: quem opera e mais rapido que a impressora em rajadas curtas. A fila
absorve isso: quem comanda a impressao devolve o controle na hora, e uma unica
thread manda para a B1 um trabalho completo por vez, esperando cada um terminar
de verdade.

    from fila import FilaImpressao

    fila = FilaImpressao(porta="COM3")     # abre a serial uma vez so
    fila.imprimir("Jose Vitor Lopes", "Lopes Advogados - Socio")
    fila.imprimir("PAT-004821", "TI - Notebook Dell 5420")
    ...
    fila.encerrar()                        # espera o que falta e fecha

Nada de sleep entre etiquetas: quem diz quando acabou e a impressora
(ver print_image em niimbot/printer.py).
"""
import queue
import threading
import time

from etiquetas import render_label, to_print
from niimbot import PrinterClient, SerialTransport


class FilaImpressao:
    def __init__(self, porta="COM3", layout="landscape", densidade=5,
                 rotate180=False, row_delay=0.005, ao_terminar=None,
                 ao_comecar=None):
        """ao_terminar(pedido, resultado, erro) e chamado depois de cada
        etiqueta, na thread da fila. Use para dar baixa no seu sistema.
            Confira resultado["completa"]: False = a etiqueta saiu
            truncada e precisa ser reimpressa. erro nao-None = nem
            chegou a imprimir.
        ao_comecar(pedido) e chamado quando o pedido sai da fila e vai para a
        impressora -- serve para mostrar "imprimindo agora" na tela.
        row_delay pode ser trocado a quente: o worker le o valor a cada
        etiqueta, entao mudar o atributo vale do proximo pedido em diante."""
        self.layout = layout
        self.densidade = densidade
        self.rotate180 = rotate180
        self.row_delay = row_delay
        self.ao_terminar = ao_terminar
        self.ao_comecar = ao_comecar

        self._pedidos = queue.Queue()
        self._impressora = PrinterClient(SerialTransport(port=porta))
        self._parar = threading.Event()
        self._worker = threading.Thread(target=self._rodar, daemon=True)
        self._worker.start()

    def imprimir(self, linha1, linha2="", ref=None, **extras):
        """Enfileira uma etiqueta de duas linhas e devolve o controle na hora.

        linha1 sai em destaque, linha2 embaixo (pode ser ""). Devolve o dict do
        pedido, que reaparece nos callbacks.

        ref e um identificador opaco seu (o id do check-in, o codigo do item).
        Ele volta em pedido["ref"] nos callbacks, para voce casar a etiqueta com
        o registro no seu sistema sem depender do texto impresso. Qualquer outro
        campo passado em extras tambem viaja junto no pedido."""
        pedido = {"linha1": linha1, "linha2": linha2, "ref": ref}
        pedido.update(extras)
        # O instante do enfileiramento anda ao lado do pedido, nao dentro dele:
        # o dict do pedido e a interface com o sistema de quem chama e nao deve
        # ganhar campos que sao instrumentacao nossa.
        self._pedidos.put((pedido, time.monotonic()))
        return pedido

    def imprimir_cracha(self, nome, empresa, cargo, ref=None):
        """Atalho para cracha de evento: linha2 = "Empresa - Cargo".

        Os tres campos originais tambem viajam no pedido (pedido["Nome"] etc.),
        para os callbacks poderem usa-los."""
        return self.imprimir(nome, " - ".join(p for p in (empresa, cargo) if p),
                             ref=ref, Nome=nome, Empresa=empresa, Cargo=cargo)

    @property
    def aguardando(self):
        """Quantos pedidos ainda nao comecaram a imprimir."""
        return self._pedidos.qsize()

    def esperar(self):
        """Bloqueia ate a fila esvaziar. Use antes de desligar a maquina."""
        self._pedidos.join()

    def encerrar(self):
        """Espera o que falta, para a thread e fecha a porta serial."""
        self.esperar()
        self._parar.set()
        self._pedidos.put(None)          # destrava o get()
        self._worker.join(timeout=5)

    def _rodar(self):
        while not self._parar.is_set():
            item = self._pedidos.get()
            if item is None:
                # Sentinela de encerramento. Nao leva task_done(): ele e posto
                # DEPOIS do join(), com o contador da fila ja zerado, e um
                # task_done() a mais levanta ValueError dentro da thread.
                continue
            pedido, t_enfileirado = item
            espera_fila = time.monotonic() - t_enfileirado
            if self.ao_comecar:
                try:
                    self.ao_comecar(pedido)
                except Exception:
                    pass
            resultado, erro = None, None
            try:
                t0 = time.monotonic()
                img = render_label(pedido["linha1"], pedido.get("linha2", ""),
                                   self.layout)
                t_render = time.monotonic() - t0
                resultado = self._impressora.print_image(
                    to_print(img, self.layout, self.rotate180),
                    density=self.densidade, row_delay=self.row_delay)
                resultado["tempos"]["render"] = t_render
                resultado["tempos"]["fila"] = espera_fila
                resultado["row_delay"] = self.row_delay
            except Exception as e:       # uma etiqueta ruim nao derruba a fila
                erro = e
            finally:
                self._pedidos.task_done()
            # Uma etiqueta truncada nao pode sumir calada. No CLI isto vira
            # "FALHOU"; aqui era engolido se o callback nao olhasse o resultado.
            if erro is not None:
                print("[fila] ERRO em %s: %r" % (pedido["linha1"], erro))
            elif not resultado["completa"]:
                print("[fila] INCOMPLETA: %s (linha %s de %d) -- reimprima"
                      % (pedido["linha1"], resultado["linhas_ok"],
                         resultado["esperado"]))

            if self.ao_terminar:
                try:
                    self.ao_terminar(pedido, resultado, erro)
                except Exception:
                    pass
