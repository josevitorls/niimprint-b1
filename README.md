<div align="center">

# 🏷️ niimprint-b1

### 🖨️ Impressão de crachás na **Niimbot B1 via USB**, direto do Python — sem o app da Niimbot

<br>

[![Niimbot B1](https://img.shields.io/badge/Niimbot-B1-FF6B35?style=for-the-badge&logoColor=white)](https://printers.niim.blue/)
[![USB Serial](https://img.shields.io/badge/USB-Serial%20COM-4C8EDA?style=for-the-badge&logo=usb&logoColor=white)](#-o-que-você-precisa)
[![Windows](https://img.shields.io/badge/Windows-11-0078D6?style=for-the-badge&logo=windows11&logoColor=white)](#-o-que-você-precisa)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](#-o-que-você-precisa)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

[![Bluetooth](https://img.shields.io/badge/Bluetooth-não%20usado-9CA3AF?style=flat-square&logo=bluetooth&logoColor=white)](#-por-que-não-bluetooth-e-por-que-não-o-niimprintx)
[![Fork de](https://img.shields.io/badge/fork%20de-AndBondStyle%2Fniimprint-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/AndBondStyle/niimprint)
[![Etiqueta](https://img.shields.io/badge/rolo-50%20×%2080%20mm%20transparente-A855F7?style=flat-square)](#-layout-da-etiqueta)
[![Tempo](https://img.shields.io/badge/clique%20→%20etiqueta-6,0%20s-16A34A?style=flat-square)](#-o-painel-de-tempo-painelpy)

<br>

<img src="docs/etiqueta-01.png" width="480" alt="Etiqueta renderizada: nome em negrito na primeira linha, empresa e cargo na segunda, tudo centralizado">

<sub>💡 Linha 1: **Nome** · Linha 2: **Empresa - Cargo** · bloco centralizado nos dois eixos</sub>

</div>

---

## 🎯 Do que se trata

Este é um **fork de [`AndBondStyle/niimprint`](https://github.com/AndBondStyle/niimprint)** focado num cenário único e específico:

> ### 🖨️ **Niimbot B1** &nbsp;•&nbsp; 🔌 **conectada por USB** &nbsp;•&nbsp; 🪟 **rodando no Windows**

O caso de uso que o guiou é o **balcão de check-in de um evento**: chega uma pessoa, o operador acha o nome na lista, faz o check-in e comanda a impressão. **Uma etiqueta por vez, sob demanda.** Se o operador for mais rápido que a impressora, uma fila absorve a diferença — nenhum trabalho se perde e cada impressão sai unitária, sem aperto.

```mermaid
flowchart LR
    A["👤 Pessoa chega"] --> B["🔎 Operador acha o nome"]
    B --> C["✅ Check-in"]
    C --> D["🖱️ Comanda a impressão"]
    D --> E["📋 Fila<br/>devolve o controle na hora"]
    E --> F["🖨️ Niimbot B1<br/>um trabalho por vez"]
    F --> G["🏷️ Crachá na mão<br/>~6 s"]
    F -.->|"a impressora confirma<br/>o fim de verdade"| E

    style A fill:#FEF3C7,stroke:#F59E0B,color:#000
    style E fill:#DBEAFE,stroke:#3B82F6,color:#000
    style F fill:#FFE4D6,stroke:#FF6B35,color:#000
    style G fill:#DCFCE7,stroke:#22C55E,color:#000
```

---

## ⚡ Começando em 3 comandos

```bash
py etiquetas.py info
```
🩺 Testa a conexão e mostra firmware/bateria. **Não gasta etiqueta.** Use sempre primeiro no dia do evento.

```bash
py etiquetas.py preview
```
🖼️ Gera os PNGs em `preview/` no sentido de leitura, sem imprimir.

```bash
py etiquetas.py print
```
🖨️ Imprime todos, um trabalho completo por etiqueta, numa única conexão serial.

<div align="center">

| 🏷️ | 🏷️ | 🏷️ |
|:---:|:---:|:---:|
| <img src="docs/etiqueta-01.png" width="220"> | <img src="docs/etiqueta-02.png" width="220"> | <img src="docs/etiqueta-03.png" width="220"> |
| nome curto | nome longo, quebra em 2 linhas | acentuação |

<sub>Saída real de `py etiquetas.py preview` — 639 × 384 px, no sentido de leitura</sub>

</div>

---

## 🧰 O que você precisa

| | Item | Valor |
|:---:|---|---|
| 🐍 | Python | **3.13** — no Windows use `py`, não `python` (o alias da Microsoft Store quebra o segundo) |
| 🖨️ | Impressora | **Niimbot B1** numa porta COM (`USB\VID_3513&PID_0002`) |
| 🔌 | Conexão | **USB** — aparece como porta serial (`COM3` por padrão aqui) |
| 📦 | Dependências | `pillow`, `pyserial` |
| ⚙️ | Firmware testado | 13.06 / hardware 12.9 |
| 🏷️ | Rolo | 50 × 80 mm transparente (a B1 reporta tipo `5`) |

```bash
py -m pip install pillow pyserial
```

> ⚠️ **Não use `requirements.txt` nem `poetry install`.** Esses dois arquivos são do
> upstream e pertencem ao `niimprint/`: eles fixam `pillow==10.1.0`, exigem `click` e
> travam `python = "~3.11"` — ou seja, **não instalam no 3.13**. Foi exatamente por
> isso que o driver foi vendorizado em `niimbot/`. A solução da B1 precisa só de
> `pillow` + `pyserial`, em qualquer versão recente.

### 🗂️ O que tem neste repositório

| Arquivo | 🎬 |
|---|---|
| `etiquetas.py` | 🏷️ CLI principal: `info` · `preview` · `print` |
| `fila.py` | 📋 Fila de impressão — **é por aqui que você liga o seu sistema** |
| `painel.py` | ⏱️ Painel local com cronômetro (http://127.0.0.1:8765) |
| `calibra.py` | 📐 Cartão de calibração com réguas em mm nos dois eixos |
| `diag.py` | 🩺 Diagnóstico da porta serial |
| `niimbot/` | 🔧 **O driver corrigido** — é este que roda |
| `niimprint/` | 📚 O driver original do upstream, intocado, para referência/diff |
| `requirements.txt` `pyproject.toml` | 📚 Do upstream, para o `niimprint/` — [não use](#-o-que-você-precisa) |

> 🧭 **Por que dois drivers?** `niimprint/` é o código do projeto-base, preservado exatamente como veio — é o que faz disto um *fork* de verdade e permite ver o diff. `niimbot/` é a cópia com as correções que fazem a B1 funcionar de verdade por USB, e é a que os scripts importam. As correções estão detalhadas [logo abaixo](#-as-4-correções-que-fazem-a-b1-funcionar).

---

## 🔗 Ligando ao seu sistema de check-in

O jeito recomendado é a **fila**: `imprimir()` devolve o controle na hora e uma única thread manda um trabalho por vez para a B1.

```python
from fila import FilaImpressao

fila = FilaImpressao(porta="COM3")          # abre a serial uma vez só

# a cada check-in:
fila.imprimir("José Vitor Lopes", "Lopes Advogados", "Sócio")

# no fim do evento:
fila.encerrar()                             # espera o que falta e fecha
```

📌 `fila.aguardando` diz quantos pedidos ainda não começaram · `fila.esperar()` bloqueia até esvaziar · `fila.row_delay = 0.01` vale do próximo pedido em diante.

`imprimir()` aceita um quarto argumento opcional, `ref`: um identificador seu (o id do check-in, por exemplo). Ele volta em `pedido["ref"]` nos callbacks, para você casar a etiqueta com o registro no seu sistema sem depender do nome.

Para dar baixa no seu sistema quando cada etiqueta sair:

```python
def baixa(pedido, resultado, erro):
    if erro is not None or not resultado["completa"]:
        return                              # ⚠️ reimprima: não saiu inteira
    marcar_impresso(pedido["Nome"])

fila = FilaImpressao(porta="COM3", ao_terminar=baixa)
```

> ⚠️ **Sempre confira `resultado["completa"]`.** `False` = a etiqueta saiu truncada. A fila avisa no console, mas quem dá baixa é o seu código.

<details>
<summary>🔧 <b>Sem fila, chamando o driver direto</b> (bloqueia até a etiqueta sair)</summary>

```python
from etiquetas import render_label, to_print
from niimbot import PrinterClient, SerialTransport

pr = PrinterClient(SerialTransport(port="COM3"))   # abra UMA vez

def imprimir(nome, empresa, cargo):
    img = render_label(nome, empresa, cargo, layout="landscape")
    r = pr.print_image(to_print(img, "landscape"), density=5, row_delay=0.005)
    return r["completa"]
```

Mantenha o `PrinterClient` vivo enquanto o check-in roda — reabrir a porta serial por etiqueta deixa lento e dá falha intermitente.

</details>

---

## 🚩 Opções da CLI

| Flag | Default | Para quê |
|---|---|---|
| `--in arquivo` | `participantes.json` | 📄 Entrada `.json` ou `.csv` |
| `--port COM3` | `COM3` | 🔌 Porta serial da impressora |
| `--layout landscape\|portrait` | `landscape` | 🔄 `landscape` = texto no sentido dos 80 mm (crachá deitado) |
| `--density 1..5` | `5` | 🌡️ Densidade térmica. Baixe se borrar; suba se sair claro |
| `--copies N` | `1` | 🧾 Cópias por participante |
| `--only N` | — | 1️⃣ Imprime só o N-ésimo |
| `--rotate180` | — | 🙃 Se sair de cabeça para baixo no porta-crachá |
| `--rowdelay 0.005` | `0.005` | ⏱️ **Ritmo de envio das linhas.** [Não mexa sem ler](#️-o-ritmo-de-envio---rowdelay) |

> 🚫 Não existe flag de pausa entre etiquetas. Ela foi **removida de propósito** — quem sabe quando a etiqueta acabou é a impressora, não um `sleep` chutado.

---

## 🩹 As 4 correções que fazem a B1 funcionar

Esta é a parte que custou caro para descobrir e que sustenta todo o resto. Cada item é uma diferença real entre `niimprint/` (upstream) e `niimbot/` (o que roda aqui).

### 1️⃣ `end_print()` não espera nada

Na B1 ele responde `True` na primeira tentativa, com a etiqueta **ainda saindo da cabeça**. O `while not end_print()` do driver original é decorativo. Confiar nele faz uma etiqueta atropelar a outra.

### 2️⃣ `get_print_status()` estava quebrado — e tem uma armadilha

A B1 devolve **10 bytes**; o upstream desempacotava 4 (formato da B21) e estourava `unpack requires a buffer of 4 bytes`. Corrigido fatiando `packet.data[:4]`. Ele devolve:

- 📥 `progress1` — quanto a impressora **recebeu**
- 🖨️ `progress2` — quanto ela **imprimiu** ← *o sinal de fim de verdade*

**🪤 A armadilha do contador velho.** Parada, a B1 responde `100/100` — o resultado do trabalho **anterior**. Ela não zera no `start_print`, e sim no `end_page_print`:

```
após start_print       p1=100 p2=100   ← ainda o trabalho ANTERIOR
após última linha      p1=100 p2=100   ← ainda
após end_page_print    p1=  0 p2=  0   ← zera só aqui
+0,75 s                p1=100 p2=100   ← terminou de verdade ✅
```

Por isso `wait_until_done()` **só aceita `100/100` depois de ter visto o contador zerar**. Aceitar o primeiro `100/100` daria "terminei" instantâneo com a etiqueta ainda na cabeça — e pior, reportando `completa=True`. **Falha silenciosa é o pior modo de falhar aqui.**

### 3️⃣ O `read()` que custava meio segundo por comando

O upstream lia a resposta com `read(1024)` numa serial com `timeout=0.5`. O pyserial só devolve quando junta os 1024 bytes **ou** quando o timeout estoura — e a B1 responde com ~8 bytes. Resultado: **todo comando custava 0,5 s cravados**. São 7 comandos antes da primeira linha = 3,5 s de papel parado.

| | por comando | etiqueta inteira |
|---|---|---|
| ❌ antes | 0,50 s | 19,03 s |
| ✅ depois | **0,05 s** | **13,97 s** |

### 4️⃣ O `_recv()` que girava para sempre

Com respostas parciais passando a ser comuns, apareceu um laço infinito que estava no upstream desde sempre: se o buffer tinha um pacote pela metade, o `while` não saía nunca (não havia `break`) e o processo travava em **100% de CPU**. Corrigido com um `break` quando o pacote ainda está incompleto.

---

## ⏱️ O ritmo de envio (`--rowdelay`)

> 🔥 **A B1 descarta silenciosamente as linhas que chegam mais rápido do que ela imprime.** Não devolve erro: todos os comandos respondem `True`. O sintoma é a etiqueta sair com o começo do desenho correto e o resto em branco.

<div align="center">
<img src="docs/foto-bug-truncamento.jpg" width="300" alt="Etiqueta impressa mostrando apenas os primeiros milímetros do texto, o resto em branco">

<sub>😱 O sintoma: mandando as 639 linhas em rajada, a B1 imprimia só os primeiros ~10 mm dos 80 mm</sub>
</div>

Durante o envio a impressora emite pacotes de progresso do tipo `0xD3` a cada 200 linhas, com o número da linha processada:

```
5555 d3 03 00c7 01 16 aaaa   →  0x00C7 = linha 199
5555 d3 03 027e 01 ad aaaa   →  0x027E = linha 638
```

`print_image()` lê esses pacotes e compara a última linha confirmada com a última linha da imagem — é isso que preenche `completa` no retorno. Um `--rowdelay` baixo demais agora aparece como **`FALHOU`**, não como etiqueta torta silenciosa. 🎉

### 📊 Medição real nesta máquina

Com etiqueta de verdade, sem nenhuma linha perdida em nenhum dos três:

| `row_delay` | 📤 envio | ⏳ espera | 🏁 **pronta** | |
|---|---|---|---|---|
| `0,020` | 13,38 s | 0,26 s | **13,97 s** | 🐢 folga total |
| `0,005` | 3,71 s | 1,92 s | **6,00 s** | ✅ **default** |
| `0,002` | 1,76 s | 2,34 s | **4,48 s** | ⚠️ folga no limite |

Repare no que a coluna **espera** faz enquanto o envio encolhe: **ela cresce.** Não é ruído — é a folga sendo gasta.

- 🐢 A `0,020` as linhas chegam mais devagar do que a B1 imprime: quando a última entra, não há nada pendente (espera 0,26 s).
- ⚠️ A `0,002` as linhas chegam **mais rápido** do que ela imprime, e o que segura a diferença é o buffer interno dela — ao fim do envio ainda restam 2,3 s de fila para revelar.

Enquanto o buffer aguenta, sai perfeito. Quando não aguentar, ele **descarta calado**.

> 🎯 **Por isso o default é `0,005` e não `0,002`.** Os 1,5 s a mais de velocidade custam a folga inteira, e a falha não avisa — sai uma etiqueta truncada, com o nome de alguém pela metade, no balcão do evento.

---

## ⏲️ O painel de tempo (`painel.py`)

```bash
py painel.py
```

🌐 Página local em **http://127.0.0.1:8765** — *só localhost, por decisão: isto comanda uma impressora física, não vai para a rede.*

Um botão por participante: o cronômetro dispara no clique e para quando a **impressora confirma** o fim daquela etiqueta. Ele existe porque de fora só dá para ver a etiqueta saindo, sem saber quando o procedimento começou.

| Coluna | O que é |
|---|---|
| 📋 **fila** | esperando a etiqueta anterior. Zero quando a fila está vazia |
| 🎨 **render** | desenhar a imagem em memória (~0,05 s) |
| 📜 **papel anda** | do clique até a primeira linha entrar no fio |
| 📤 **envio** | as 639 linhas, no ritmo do `row_delay` |
| ⏳ **espera** | do fim do envio até a impressora dizer que terminou |
| 🏁 **pronta** | **clique → etiqueta na mão.** É o número que importa |

> 💡 **Não confunda "começou" com "pronta".** A B1 imprime conforme as linhas chegam, então o papel anda quase de imediato — "começou a imprimir" é um número fácil e enganoso.

Os botões de `row_delay` trocam o ritmo **a quente**, valendo do próximo pedido em diante. É para isso que o painel serve de verdade: clicar em `0,020` / `0,010` / `0,005` / `0,002` com etiquetas de verdade e ver em qual valor a B1 começa a descartar linhas — a etiqueta aparece marcada **🔴 INCOMPLETA**, em vez de sair torta em silêncio.

---

## 📐 Layout da etiqueta

O rolo é **50 × 80 mm transparente** (a impressora reporta tipo `5`):

| | medida |
|---|---|
| 🏷️ corpo da etiqueta | 50 × 80 mm |
| ✂️ gap entre etiquetas (onde é o corte) | **2,0 mm** → passo de 82 mm |
| 📏 largura do liner | 53 mm (1,5 mm livres de cada lado) |
| 🖨️ largura útil da cabeça | 384 px = **48,06 mm** — *não alcança a borda da etiqueta* |
| 🖼️ imagem enviada | **384 × 639 px** (48,06 × 80,0 mm) |

- **Linha 1:** Nome, em negrito. **Linha 2:** Empresa - Cargo. Bloco centralizado nos dois eixos.
- **Margens** (`MARGEM_PAPEL_MM` / `MARGEM_CABECA_MM` no topo de `etiquetas.py`): **6 mm** no eixo dos 80 mm e **4 mm** no eixo dos 50 mm. A do eixo do papel é a que importa — é nela que o texto encostaria no corte se a etiqueta parasse fora do lugar.
- **Fonte auto-ajustável:** encolhe e, se preciso, quebra em duas linhas. Se nem no tamanho mínimo couber, continua encolhendo em vez de estourar a margem — a margem é justamente o que protege do corte.
- Renderização com **supersampling 3×** e binarização por limiar, para traço limpo no térmico.

### 📏 Cartão de calibração

```bash
py calibra.py --print --delay=0.005
```

<div align="center">
<img src="docs/foto-calibracao-regua.jpg" width="260" alt="Etiqueta de calibração impressa com réguas em milímetros e a palavra TOPO">
&nbsp;&nbsp;
<img src="docs/foto-calibracao-limpa.jpg" width="330" alt="Etiqueta com marca de 10 mm impressa no canto">

<sub>Réguas em mm nos dois eixos + marcador de orientação. Se a régua chegar aos 70 mm, o ritmo é seguro ✅</sub>
</div>

---

## 📥 Entrada de dados

**JSON** (`participantes.json`):

```json
[
  {"Nome": "José Vitor Lopes", "Empresa": "Lopes Advogados", "Cargo": "Sócio"}
]
```

**CSV** — o leitor reconhece os cabeçalhos, sem diferenciar maiúsculas:

| Campo | Cabeçalhos aceitos |
|---|---|
| 👤 nome | `Nome` · `Name` · `Full Name` |
| 🏢 empresa | `Empresa` · `Company` · `Organization` |
| 💼 cargo | `Cargo` · `Title` · `Job Title` · `Role` |

> 🧪 Os participantes em `participantes.json` e `exemplo_luma.csv` são **fictícios** — servem só para exercitar acentuação, nomes longos e quebra de linha.

---

## 🆘 Problemas comuns

<details>
<summary>🚫 <b><code>could not open port COM3</code> / acesso negado</b></summary>

O app da Niimbot (ou o driver dele) está segurando a porta. **Feche o app**, incluindo o ícone da bandeja.
</details>

<details>
<summary>🔍 <b>A porta não é COM3</b></summary>

A porta pode mudar de USB. Para descobrir:

```bash
py -c "from serial.tools.list_ports import comports; [print(p.device, p.description) for p in comports()]"
```
</details>

<details>
<summary>🌫️ <b>Sai claro ou borrado</b></summary>

Mexa em `--density` (5 é o máximo da B1). Etiqueta transparente costuma pedir densidade alta.
</details>

<details>
<summary>🙃 <b>Sai invertido no porta-crachá</b></summary>

Use `--rotate180`.
</details>

<details>
<summary>✂️ <b>Imprime o começo do desenho e o resto sai em branco</b></summary>

O `--rowdelay` está baixo demais: a B1 descartou linhas. **Suba o valor.** `0.02` é o ritmo com folga total (14 s por etiqueta) e serve para confirmar que o problema era o ritmo, não outra coisa.
</details>

<details>
<summary>⬜ <b>Etiqueta sai totalmente em branco</b></summary>

Tipo de rolo errado. O driver pergunta à impressora qual rolo ela detectou (`LABELTYPE`); neste rolo transparente ela responde `5`. Forçar o tipo `1` faz sair em branco.
</details>

<details>
<summary>🛑 <b><code>PrinterBusy: a impressora recusou o comando (0xDB codigo N)</code></b></summary>

A B1 está travada e não aceita `start_print`. Causas: tampa aberta, rolo acabado ou mal encaixado, ou um **trabalho anterior interrompido no meio** (matar o processo Python durante a impressão faz exatamente isso).

Feche a tampa, confira o rolo e, se persistir, **desligue e ligue a impressora** — é o que destrava.

⚠️ Consultas de leitura (`info`, `get_print_status`) continuam respondendo normalmente nesse estado, então *"a impressora responde"* não quer dizer que ela vai imprimir.
</details>

<details>
<summary>💥 <b>Uma etiqueta atropela a outra</b></summary>

Não deveria mais acontecer. Se acontecer, veja se `resultado["status"]["zerou"]` está `False`: significa que o contador de progresso não zerou e a espera caiu para tempo fixo.
</details>

---

## 📡 Por que não Bluetooth (e por que não o NiimPrintX)

| | |
|---|---|
| 🔵 **Bluetooth** | O driver tem `BluetoothTransport`, mas o socket RFCOMM do Python **não existe no Windows**. No dia do evento, use USB. |
| 📦 **`labbots/NiimPrintX`** | É **exclusivamente Bluetooth** (usa `bleak`, não tem transporte serial) e ainda exige `pycairo` + ImageMagick. |
| 🤖 **Android** | O `pyserial` não acessa USB no Android (precisa da API USB Host do Java). O notebook com Windows é a rota confiável. |

A B1 ligada por USB aparece como **porta serial** — e o `niimprint` fala o mesmo protocolo Niimbot por serial. É o caminho certo para USB. O driver foi copiado para dentro do projeto porque o `pyproject.toml` do upstream trava `python = "~3.11"` e não instala no 3.13.

---

## 📖 Referência do protocolo

Framing: `0x55 0x55 <tipo> <len> <dados> <xor> 0xAA 0xAA`

📚 Documentação da comunidade: **https://printers.niim.blue/interfacing/proto/**

---

## 🙏 Créditos & licença

<div align="center">

**MIT** — veja [`LICENSE`](LICENSE)

Fork de **[AndBondStyle/niimprint](https://github.com/AndBondStyle/niimprint)**, que por sua vez vem de **[kjy00302/niimprint](https://github.com/kjy00302/niimprint)**.

O readme original do upstream está preservado em [`UPSTREAM-readme.md`](UPSTREAM-readme.md).

<br>

Feito para um balcão de check-in de verdade, com uma **Niimbot B1**, um cabo **USB** e um notebook **Windows**. 🏷️🔌🪟

</div>
