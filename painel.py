"""Painel local de cronometragem da impressao.

Serve uma pagina em http://127.0.0.1:8765 com um botao por registro. O
cronometro dispara no clique e para quando a impressora confirma que terminou
aquela etiqueta -- nao quando o comando foi aceito.

    py painel.py
    py painel.py --port COM3 --http 8765 --rowdelay 0.005

Para que serve: hoje so da para ver a etiqueta saindo, sem saber quando o
procedimento comecou. O painel mostra os pedacos do tempo separados,
porque eles tem causas diferentes:

    fila     esperando a etiqueta anterior (0 quando a fila esta vazia)
    render   desenhar a imagem em memoria
    papel    ate a primeira linha entrar no fio -- e quando o papel anda
    envio    as 639 linhas, no ritmo do --rowdelay
    espera   do fim do envio ate a impressora dizer que terminou

O numero que importa e "pronta": clique -> etiqueta na mao. A B1 imprime
conforme as linhas chegam, entao o papel comeca a andar quase de imediato --
"comecou a imprimir" e um numero facil e enganoso. Ficar de olho no "pronta".

O painel tambem troca o row_delay a quente, para medir 0,020 / 0,010 / 0,005
com etiquetas de verdade e ver em qual valor a impressora comeca a descartar
linhas (a etiqueta sai marcada como INCOMPLETA).
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from etiquetas import LINHA1_PADRAO, LINHA2_PADRAO, formatar, load_registros

PAGINA = """<!doctype html>
<meta charset="utf-8">
<title>Painel de tempo - Niimbot B1</title>
<style>
  :root {
    --bg:#12141a; --card:#1b1e26; --linha:#2a2f3a; --txt:#e7e9ee;
    --fraco:#8b93a5; --ok:#3ddc84; --ruim:#ff6b6b; --meio:#ffc857; --azul:#5aa9ff;
  }
  * { box-sizing:border-box }
  body { margin:0; padding:24px; background:var(--bg); color:var(--txt);
         font:15px/1.5 "Segoe UI",system-ui,sans-serif }
  h1 { font-size:20px; margin:0 0 4px }
  .sub { color:var(--fraco); margin-bottom:20px }
  .cartao { background:var(--card); border:1px solid var(--linha);
            border-radius:10px; padding:16px; margin-bottom:16px }
  .cartao h2 { font-size:13px; text-transform:uppercase; letter-spacing:.08em;
               color:var(--fraco); margin:0 0 12px; font-weight:600 }
  button { font:inherit; color:var(--txt); background:#242833;
           border:1px solid var(--linha); border-radius:8px; padding:10px 16px;
           cursor:pointer }
  button:hover:not(:disabled) { background:#2e3342; border-color:#3d4356 }
  button:disabled { opacity:.4; cursor:not-allowed }
  .pessoa { display:block; width:100%; text-align:left; margin-bottom:8px }
  .pessoa b { display:block; font-size:16px }
  .pessoa span { color:var(--fraco); font-size:13px }
  .rd { display:flex; gap:8px; align-items:center; flex-wrap:wrap }
  .rd button.on { background:var(--azul); border-color:var(--azul); color:#08111d;
                  font-weight:600 }
  .rd input { font:inherit; width:90px; background:#242833; color:var(--txt);
              border:1px solid var(--linha); border-radius:8px; padding:9px 10px }
  table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums }
  th { text-align:right; font-size:11px; text-transform:uppercase;
       letter-spacing:.06em; color:var(--fraco); padding:0 10px 8px;
       font-weight:600 }
  th:first-child, td:first-child { text-align:left }
  td { padding:9px 10px; border-top:1px solid var(--linha); text-align:right }
  td.n { color:var(--fraco) }
  .pronta { color:var(--ok); font-weight:600; font-size:16px }
  .correndo { color:var(--meio); font-weight:600; font-size:16px }
  .falhou { color:var(--ruim); font-weight:600 }
  .alvo { color:var(--fraco); font-size:12px }
  .aviso { background:#3a1f22; border-color:#5e2b30; color:#ffb3b3 }
  .rodape { display:flex; gap:28px; flex-wrap:wrap; margin-top:14px;
            padding-top:14px; border-top:1px solid var(--linha) }
  .rodape div span { display:block; color:var(--fraco); font-size:11px;
                     text-transform:uppercase; letter-spacing:.06em }
  .rodape div b { font-size:20px; font-variant-numeric:tabular-nums }
</style>

<h1>Painel de tempo &mdash; Niimbot B1</h1>
<div class="sub">O cronometro comeca no clique e para quando a impressora
confirma o fim da etiqueta. Meta: <b>3 a 5 s</b> ate a etiqueta pronta.</div>

<div id="erro" class="cartao aviso" style="display:none">
  <div id="erroTxt"></div>
  <button style="margin-top:10px" onclick="acao('/reconectar')">Tentar reconectar</button>
</div>

<div class="cartao">
  <h2>Ritmo de envio (row_delay)</h2>
  <div class="rd" id="rd"></div>
  <div class="alvo" style="margin-top:10px">Cada linha da etiqueta custa esse
    tempo &times; 639 linhas. Baixar acelera; baixar demais faz a B1 descartar
    linhas e a etiqueta sai marcada <b>INCOMPLETA</b>.</div>
</div>

<div class="cartao">
  <h2>Comandar impressao</h2>
  <div id="pessoas"></div>
  <button id="todos" style="margin-top:6px">Mandar todos de uma vez (testa a fila)</button>
</div>

<div class="cartao">
  <h2>Cronometro</h2>
  <table>
    <thead><tr>
      <th>Etiqueta</th><th>Fila</th><th>Render</th><th>Papel anda</th>
      <th>Envio</th><th>Espera</th><th>Pronta</th>
    </tr></thead>
    <tbody id="linhas"></tbody>
  </table>
  <div class="rodape">
    <div><span>Etiquetas</span><b id="qtd">0</b></div>
    <div><span>Media unitaria</span><b id="media">-</b></div>
    <div><span>Total do lote</span><b id="total">-</b></div>
    <div><span>Na fila</span><b id="fila">0</b></div>
  </div>
  <button style="margin-top:14px" onclick="acao('/limpar')">Limpar cronometro</button>
</div>

<script>
const RDS = [0.020, 0.010, 0.005, 0.002];
let ultimo = null, tPoll = 0;

function s(v) { return v == null ? "-" : v.toFixed(2).replace(".", ",") + "s"; }

async function acao(url, corpo) {
  const r = await fetch(url, {method:"POST", body: JSON.stringify(corpo || {})});
  pintar(await r.json());
}

function pintar(d) {
  ultimo = d; tPoll = performance.now();

  document.getElementById("erro").style.display = d.erro ? "" : "none";
  if (d.erro) document.getElementById("erroTxt").textContent = d.erro;

  const rd = document.getElementById("rd");
  if (rd.dataset.v !== String(d.row_delay)) {
    rd.dataset.v = String(d.row_delay);
    rd.innerHTML = "";
    for (const v of RDS) {
      const b = document.createElement("button");
      b.textContent = v.toFixed(3).replace(".", ",") + " s";
      if (Math.abs(v - d.row_delay) < 1e-9) b.className = "on";
      b.onclick = () => acao("/rowdelay", {v});
      rd.appendChild(b);
    }
    const inp = document.createElement("input");
    inp.placeholder = "outro"; inp.type = "number"; inp.step = "0.001"; inp.min = "0";
    inp.onchange = () => { if (inp.value !== "") acao("/rowdelay", {v: +inp.value}); };
    rd.appendChild(inp);
  }

  const ps = document.getElementById("pessoas");
  if (ps.childElementCount !== d.itens.length) {
    ps.innerHTML = "";
    d.itens.forEach((p, i) => {
      const b = document.createElement("button");
      b.className = "pessoa";
      b.innerHTML = "<b></b><span></span>";
      b.querySelector("b").textContent = p.linha1;
      b.querySelector("span").textContent = p.linha2;
      b.onclick = () => acao("/imprimir", {i});
      ps.appendChild(b);
    });
  }
  document.getElementById("todos").onclick = () => acao("/imprimir", {todos:true});

  const tb = document.getElementById("linhas");
  tb.innerHTML = "";
  for (const j of d.jobs) {
    const tr = document.createElement("tr");
    let fim;
    if (j.estado === "pronta")      fim = '<span class="pronta">' + s(j.total) + "</span>";
    else if (j.estado === "falhou") fim = '<span class="falhou">' + s(j.total) + " INCOMPLETA</span>";
    else if (j.estado === "erro")   fim = '<span class="falhou">erro</span>';
    // A mensagem do erro (PrinterBusy, porta ocupada) vale mais que a palavra
    // "erro": ela diz o que fazer.
    else fim = '<span class="correndo" data-t="' + j.decorrido + '">' + s(j.decorrido) + "</span>";
    tr.innerHTML =
      "<td>" + j.rotulo + (j.estado === "fila" ? ' <span class="alvo">na fila</span>' : "") + "</td>" +
      '<td class="n">' + s(j.fila) + "</td>" +
      '<td class="n">' + s(j.render) + "</td>" +
      "<td>" + s(j.ate_papel) + "</td>" +
      '<td class="n">' + s(j.envio) + "</td>" +
      '<td class="n">' + s(j.espera) + "</td>" +
      "<td>" + fim + "</td>";
    tb.appendChild(tr);
    if (j.msg) {
      const tr2 = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7; td.className = "falhou"; td.style.textAlign = "left";
      td.style.borderTop = "0"; td.style.paddingTop = "0";
      td.textContent = j.msg;
      tr2.appendChild(td); tb.appendChild(tr2);
    }
  }
  document.getElementById("qtd").textContent = d.prontas;
  document.getElementById("media").textContent = s(d.media);
  document.getElementById("total").textContent = s(d.lote);
  document.getElementById("fila").textContent = d.aguardando;
}

// Entre dois polls o cronometro continua andando na tela, para nao dar
// impressao de travado.
function tique() {
  if (ultimo) {
    const dt = (performance.now() - tPoll) / 1000;
    for (const el of document.querySelectorAll(".correndo[data-t]"))
      el.textContent = s(+el.dataset.t + dt);
  }
  requestAnimationFrame(tique);
}

async function poll() {
  try { pintar(await (await fetch("/dados")).json()); } catch (e) {}
  setTimeout(poll, 250);
}
poll(); tique();
</script>
"""


class Painel:
    """Guarda o estado que a pagina mostra. Um registro por clique."""

    def __init__(self, registros, porta, row_delay,
                 linha1=LINHA1_PADRAO, linha2=LINHA2_PADRAO):
        # O painel so precisa das duas linhas ja prontas: quem decide o que entra
        # em cada uma sao os templates, os mesmos do etiquetas.py.
        self.itens = [{"linha1": formatar(linha1, r), "linha2": formatar(linha2, r)}
                      for r in registros]
        self.row_delay = row_delay
        self.jobs = []
        self.erro = None
        self._trava = threading.Lock()
        self._porta = porta
        self.fila = None
        self.conectar()

    def conectar(self):
        if self.fila is not None:
            return
        try:
            from fila import FilaImpressao
            self.fila = FilaImpressao(porta=self._porta, row_delay=self.row_delay,
                                      ao_comecar=self._comecou,
                                      ao_terminar=self._terminou)
            self.erro = None
        except Exception as e:
            self.erro = ("Nao consegui abrir a impressora em %s: %s. "
                         "Se o app da Niimbot estiver aberto (inclusive na "
                         "bandeja), feche-o -- ele segura a porta serial."
                         % (self._porta, e))

    def clicar(self, indice):
        it = self.itens[indice]
        with self._trava:
            job = {"id": len(self.jobs), "rotulo": it["linha1"], "estado": "fila",
                   "t_click": time.monotonic(), "t_fim": None, "tempos": None,
                   "completa": None, "msg": None}
            self.jobs.append(job)
        if self.fila is None:
            job["estado"] = "erro"
            return
        self.fila.imprimir(it["linha1"], it["linha2"], ref=job["id"])
        print("[painel] clique -> %s" % it["linha1"])

    def _achar(self, pedido):
        ref = pedido.get("ref")
        with self._trava:
            if isinstance(ref, int) and 0 <= ref < len(self.jobs):
                return self.jobs[ref]
        return None

    def _comecou(self, pedido):
        job = self._achar(pedido)
        if job:
            job["estado"] = "imprimindo"

    def _terminou(self, pedido, resultado, erro):
        job = self._achar(pedido)
        if not job:
            return
        job["t_fim"] = time.monotonic()
        if erro is not None:
            job["estado"] = "erro"
            job["msg"] = str(erro) or repr(erro)
            print("[painel] %s: ERRO %s" % (job["nome"], job["msg"]))
            return
        job["tempos"] = resultado["tempos"]
        job["completa"] = resultado["completa"]
        job["estado"] = "pronta" if resultado["completa"] else "falhou"
        print("[painel] %s: %.2fs (row_delay %.3f)%s"
              % (job["nome"], job["t_fim"] - job["t_click"],
                 resultado.get("row_delay", self.row_delay),
                 "" if resultado["completa"] else "  INCOMPLETA"))

    def limpar(self):
        with self._trava:
            if any(j["estado"] in ("fila", "imprimindo") for j in self.jobs):
                return                      # nao apaga o que ainda esta correndo
            self.jobs = []

    def set_row_delay(self, v):
        v = max(0.0, min(0.2, float(v)))
        self.row_delay = v
        if self.fila:
            self.fila.row_delay = v         # vale do proximo pedido em diante

    def dados(self):
        agora = time.monotonic()
        with self._trava:
            jobs = list(self.jobs)
        saida, prontas, soma = [], 0, 0.0
        primeiro = ultimo = None
        for j in jobs:
            t = j["tempos"] or {}
            # "papel anda" e cumulativo desde o clique: a pessoa nao ve a fila
            # nem o render, ve a etiqueta parada e depois andando.
            ate_papel = None
            if t:
                ate_papel = t.get("fila", 0) + t.get("render", 0) + t.get("papel", 0)
            total = (j["t_fim"] - j["t_click"]) if j["t_fim"] else None
            if j["estado"] == "pronta":
                prontas += 1
                soma += total
            if j["t_fim"]:
                primeiro = j["t_click"] if primeiro is None else min(primeiro, j["t_click"])
                ultimo = j["t_fim"] if ultimo is None else max(ultimo, j["t_fim"])
            saida.append({
                "rotulo": j["rotulo"], "estado": j["estado"],
                "fila": t.get("fila"), "render": t.get("render"),
                "ate_papel": ate_papel, "envio": t.get("envio"),
                "espera": t.get("espera"), "total": total,
                "decorrido": agora - j["t_click"], "msg": j.get("msg"),
            })
        return {
            "itens": self.itens,
            "jobs": saida,
            "prontas": prontas,
            "media": (soma / prontas) if prontas else None,
            "lote": (ultimo - primeiro) if primeiro is not None else None,
            "aguardando": self.fila.aguardando if self.fila else 0,
            "row_delay": self.row_delay,
            "erro": self.erro,
        }


def fazer_handler(painel):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass                            # o poll de 250 ms inundaria o console

        def _json(self, obj):
            corpo = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            if self.path.startswith("/dados"):
                return self._json(painel.dados())
            if self.path == "/":
                corpo = PAGINA.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                return self.wfile.write(corpo)
            self.send_error(404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                corpo = {}
            if self.path == "/imprimir":
                if corpo.get("todos"):
                    for i in range(len(painel.itens)):
                        painel.clicar(i)
                else:
                    painel.clicar(int(corpo["i"]))
            elif self.path == "/rowdelay":
                painel.set_row_delay(corpo["v"])
            elif self.path == "/limpar":
                painel.limpar()
            elif self.path == "/reconectar":
                painel.conectar()
            else:
                return self.send_error(404)
            self._json(painel.dados())

    return H


def main():
    ap = argparse.ArgumentParser(description="Painel local de cronometragem")
    ap.add_argument("--in", dest="entrada", default="participantes.json")
    ap.add_argument("--linha1", default=LINHA1_PADRAO, help="template da linha de destaque")
    ap.add_argument("--linha2", default=LINHA2_PADRAO, help="template da linha de apoio")
    ap.add_argument("--port", default="COM3", help="porta serial da impressora")
    ap.add_argument("--http", type=int, default=8765, help="porta da pagina")
    ap.add_argument("--rowdelay", type=float, default=0.005)
    args = ap.parse_args()

    painel = Painel(load_registros(args.entrada), args.port, args.rowdelay,
                    args.linha1, args.linha2)
    if painel.erro:
        print("[painel] " + painel.erro)

    # 127.0.0.1 de proposito: isto comanda uma impressora fisica, nao vai para
    # a rede.
    srv = ThreadingHTTPServer(("127.0.0.1", args.http), fazer_handler(painel))
    print("[painel] abra http://127.0.0.1:%d   (Ctrl+C para parar)" % args.http)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[painel] encerrando...")
        if painel.fila:
            painel.fila.encerrar()


if __name__ == "__main__":
    main()
