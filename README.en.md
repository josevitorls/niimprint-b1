<div align="center">

# 🏷️ niimprint-b1

### 🖨️ Two-line labels on the **Niimbot B1 over USB**, straight from Python — no Niimbot app

🇧🇷 [Português](README.md) &nbsp;·&nbsp; 🇬🇧 English

<br>

[![Niimbot B1](https://img.shields.io/badge/Niimbot-B1-FF6B35?style=for-the-badge&logoColor=white)](https://printers.niim.blue/)
[![USB Serial](https://img.shields.io/badge/USB-Serial%20COM-4C8EDA?style=for-the-badge&logo=usb&logoColor=white)](#-requirements)
[![Windows](https://img.shields.io/badge/Windows-11-0078D6?style=for-the-badge&logo=windows11&logoColor=white)](#-requirements)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](#-requirements)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/josevitorls/niimprint-b1/testes.yml?style=for-the-badge&label=tests&logo=github&logoColor=white)](https://github.com/josevitorls/niimprint-b1/actions/workflows/testes.yml)

<br>

<img src="docs/etiqueta-01.png" width="480" alt="Rendered label: one bold line on top, a smaller line below, all centered">

<sub>💡 One headline + one supporting line · centered on both axes · font size chosen automatically</sub>

</div>

> 🇧🇷 **The full documentation is in Portuguese, in [`README.md`](README.md)** — including the real timing measurements, the bug photos and the troubleshooting section. This page is the short version.

---

## 🎯 What it is

A **fork of [`AndBondStyle/niimprint`](https://github.com/AndBondStyle/niimprint)** targeting one specific setup:

> ### 🖨️ **Niimbot B1** &nbsp;•&nbsp; 🔌 **connected over USB** &nbsp;•&nbsp; 🪟 **on Windows**

It does three things:

1. 🏷️ **Draws and prints a two-line centered label** — headline on top, supporting line below. Font size is picked automatically and text wraps to two lines when needed, never crossing the margin that protects it from the cut.
2. 📋 **Queues the jobs** — the caller gets control back immediately, and the B1 receives one complete job at a time, starting the next only when the **printer** confirms the paper has stopped.
3. 🔧 **Fixes the driver** — upstream `niimprint` does not work on the B1 over USB. The [7 fixes](README.md#-as-7-correções-que-fazem-a-b1-funcionar) that make it work are the expensive part.

**All you need to understand is [how the data goes in](#-how-the-data-goes-in).** Everything else is the same for any content.

> 🌱 **Origin.** It was born at an event check-in desk, which is why the sample files are badges. But nothing here is event-specific — a label is just two lines of text, and you decide what goes in each one.

---

## ⚡ Three commands

```bash
py etiquetas.py info      # 🩺 test the connection, no label wasted
py etiquetas.py preview   # 🖼️ PNGs into preview/, nothing printed
py etiquetas.py print     # 🖨️ print them all, one complete job each
```

---

## 📥 How the data goes in

A `.json` (list of objects) **or** a `.csv` with a header. The columns are yours. Two templates decide what lands on each line — `{Column}` lookup is case-insensitive.

```bash
# the default (badge) — nothing to pass:
py etiquetas.py print --linha1 "{Nome}" --linha2 "{Empresa} - {Cargo}"

# asset tags:
py etiquetas.py print --in exemplo_ativos.csv \
    --linha1 "{Patrimonio}" --linha2 "{Setor} - {Responsavel}"

# a single big line, centered on the whole label:
py etiquetas.py print --in tables.csv --linha1 "{Table}" --linha2 ""
```

`linha1` = headline, `linha2` = supporting line. **An empty field leaves no hole:** `"{Company} - {Title}"` with no title prints `Acme Corp`, not `Acme Corp - `. If line 1 comes out empty for any record, the program stops before wasting a label and lists the columns your file actually has.

English headers work out of the box: `Name`/`Full Name` → `{Nome}`, `Company`/`Organization` → `{Empresa}`, `Title`/`Job Title`/`Role` → `{Cargo}`.

---

## 🧰 Requirements

| | Item | Value |
|:---:|---|---|
| 🐍 | Python | **3.13** — on Windows use `py`, not `python` |
| 🖨️ | Printer | **Niimbot B1** on a COM port (`USB\VID_3513&PID_0002`) |
| 📦 | Deps | `pillow`, `pyserial` |
| 🔤 | Fonts | **Segoe UI** / **Segoe UI Bold** (ship with Windows). Edit `FONT_BOLD`/`FONT_REG` in `etiquetas.py` for any other `.ttf` |
| 🏷️ | Roll | 50 × 80 mm transparent (B1 reports type `5`) |

```bash
py -m pip install pillow pyserial
```

> ⚠️ **Do not use `requirements.txt` or `poetry install`.** Both are upstream files belonging to `niimprint/`; they pin `pillow==10.1.0` and lock `python = "~3.11"`, so they will not install on 3.13. That is exactly why the driver was vendored into `niimbot/`.

---

## 📦 Library use

### The queue (recommended)

```python
from fila import FilaImpressao

fila = FilaImpressao(porta="COM3")           # opens the serial port once
fila.imprimir("José Vitor Lopes", "Lopes Advogados - Sócio")
fila.imprimir("PAT-004821", "IT - Dell 5420 laptop")
fila.encerrar()                              # drain and close
```

| Member | What it does |
|---|---|
| `FilaImpressao(porta, layout, densidade, rotate180, row_delay, ao_comecar, ao_terminar)` | Opens the port, starts the worker thread. `row_delay` is hot-swappable |
| `imprimir(linha1, linha2="", ref=None, **extras)` | Enqueues and returns the request dict **immediately** |
| `imprimir_cracha(nome, empresa, cargo, ref=None)` | Shortcut: `linha2 = "Company - Title"` |
| `aguardando` / `esperar()` / `encerrar()` | Pending count / block until drained / drain, stop, close |

`ref` is an opaque id of yours (check-in id, asset code). It comes back in `pedido["ref"]` in the callbacks so you can match the label to your record **without relying on the printed text**.

```python
def done(pedido, resultado, erro):
    if erro is not None or not resultado["completa"]:
        return                              # ⚠️ reprint: it did not come out whole
    mark_printed(pedido["ref"])

fila = FilaImpressao(porta="COM3", ao_terminar=done)
```

> ⚠️ **Always check `resultado["completa"]`.** `False` means the label came out truncated. Both callbacks run **on the queue thread**, and exceptions inside them are swallowed on purpose — a bad callback must not take the printing down.

### Drawing and loading

```python
from etiquetas import render_label, render_cracha, to_print, load_registros, formatar
```

| Function | Returns |
|---|---|
| `render_label(linha1, linha2="", layout="landscape")` | 1-bit image **in reading orientation**. Empty `linha2` centers line 1 on the whole label |
| `render_cracha(nome, empresa, cargo, layout=...)` | Three-field shortcut over `render_label` |
| `to_print(img, layout, rotate180=False)` | Rotates to paper orientation (width must be 384 px). **Required before printing** |
| `load_registros(path)` | List of dicts from the `.json`/`.csv`, all columns plus the canonical aliases |
| `formatar(template, registro)` | Applies a `"{Field} - {Other}"` template to one record |

### The driver directly

```python
from niimbot import PrinterClient, SerialTransport, PrinterBusy, PrinterSilent

pr = PrinterClient(SerialTransport(port="COM3"))   # open ONCE, keep it alive
r  = pr.print_image(to_print(render_label("PAT-004821", "IT"), "landscape"),
                    density=5, row_delay=0.005)
```

`print_image()` returns the source of truth:

```python
{"completa": True,          # ✅ the one field to always check
 "linhas_ok": 638, "esperado": 638,
 "status": {"page": 1, "progress1": 100, "progress2": 100,
            "ok": True,     # finished by confirmation, not by timeout
            "zerou": True}, # the progress counter reset: end signal is trustworthy
 "tempos": {"papel": 0.35, "envio": 3.71, "espera": 1.92, "total": 6.00}}
```

- `completa=False` with `status["ok"]=True` → the B1 dropped rows: raise `row_delay`.
- `PrinterBusy` → the printer **refused** the command. Retrying will not help; power-cycle it.
- `PrinterSilent` → a command got no answer after 6 tries. The job is closed automatically, so the printer will **not** run away feeding blank paper. In the queue, the next label still prints.

> 🌀 **If the B1 ever feeds blank labels non-stop, power-cycle it.** That was a driver bug: `print_image()` only closed the job on the happy path, so any mid-job failure left the page open. It is now wrapped in `try/finally` — `end_print()` always runs.

---

## 🧪 Tests

```bash
py testes.py
```

No printer, no serial port, no extra dependency — CI-friendly. A fake printer speaks the B1 protocol and **can go silent on command**, which is exactly the scenario that is expensive to reproduce on hardware.

It covers: the job always closing even when a command fails, the queue surviving a bad label and printing the next one, `get_rfid()` decoding the B1's real 49-byte reply, `port="auto"` finding the printer past a legacy `COM1`, and the rendered image matching the print head. The suite has eight test cases and **six of them fail** on the pre-fix version — that is how they were written. The other two (the happy path in `TrabalhoSempreFecha` and `Geometria`) are regression guards: they passed before the fix and must keep passing.

### 🖨️ Tests with the printer plugged in

```bash
py testes_hardware.py
```

Two things a fake printer cannot prove, because both depend on paper actually moving: that the queue prints **in order, one job at a time**, and that the B1 **stops** when a command fails mid-job instead of feeding blank paper until someone kills the power.

The second one is the bug this fork exists for. Waiting for it to happen on its own is not practical, so the script provokes it: it really sends `set_dimension` and swallows the reply in the transport, exactly as if the printer had gone silent. Then it prints one more label to prove the queue survived.

It burns ~6 labels, shows which roll is loaded and asks before printing — which is why it stays **out** of CI. Run it after touching the driver and before taking the printer to an event. Options: `--porta COM3`, `--so-fila` (skip the destructive half), `--sim` (no prompt).

> ✅ **Verified** on a B1 (firmware 13.06) with a 50 × 80 roll: three badges in 19.6 s, the broken label failed with `PrinterSilent`, **the printer stayed put**, and the next label printed normally.

---

## ⏱️ The `--rowdelay` pacing

> 🔥 **The B1 silently drops rows that arrive faster than it can print them.** No error is returned — every command answers `True`. The symptom is a label whose first millimetres are right and the rest blank.

`print_image()` reads the `0xD3` progress packets the printer emits every 200 rows and compares the last confirmed row against the image height. That is what fills `completa`, so a too-low `row_delay` now shows up as **`FAILED`** instead of a silently broken label.

| `row_delay` | 📤 send | ⏳ wait | 🏁 **ready** | |
|---|---|---|---|---|
| `0.020` | 13.38 s | 0.26 s | **13.97 s** | 🐢 full slack |
| `0.005` | 3.71 s | 1.92 s | **6.00 s** | ✅ **default** |
| `0.002` | 1.76 s | 2.34 s | **4.48 s** | ⚠️ slack at the edge |

Note what the **wait** column does as the send shrinks: it grows. That is the printer's internal buffer holding the difference. While the buffer copes, output is perfect. When it stops coping, it drops rows **silently** — which is why the default is `0.005` and not `0.002`.

---

## ⏲️ The timing panel

```bash
py painel.py
```

🌐 Local page at **http://127.0.0.1:8765** — *localhost only, by design: this drives a physical printer.* One button per record; the stopwatch starts on click and stops when the **printer** confirms that label is done. The `row_delay` buttons switch pacing **live**, so you can find the value where your printer starts dropping rows — it shows up as **🔴 INCOMPLETA** instead of a quietly broken label.

---

## 🔧 Another roll size

Everything size-dependent lives in the first lines of [`etiquetas.py`](etiquetas.py). In practice you change **one constant**:

```python
LABEL_MM = (50, 80)          # (roll width, label length) in mm
```

`DPI = 203` and `HEAD_PX = 384` are physical facts about the B1 — do not touch them. `MARGEM_PAPEL_MM = 6.0` is the margin protecting the text from the cut; on a short label, drop it to ~3 mm and calibrate with `py calibra.py --print --delay=0.005`. The roll **type** is not a constant: the driver asks the printer which roll it detected.

> 💡 **What about the roll's RFID?** `get_rfid()` gives you the product code, that roll's serial, the label count and the type — but **not** the millimetres. You cannot tell `(40, 30)` from `(50, 80)` without a product table, which this project does not ship. So `LABEL_MM` stays your call. What does work with no table at all is **detecting that the roll changed**: the `serial` is unique per roll, so storing the last one seen warns you before you print 50 × 80 on a 40 × 30 roll.

> ⚠️ On a roll **wider than 48 mm**, the head cannot reach the edge. That is a physical limit of the B1, not of this code.

---

## 🤖 Adoption via AI (Claude Code skill)

```powershell
New-Item -ItemType Directory -Force .claude\skills\niimprint-b1
Copy-Item skill\SKILL.md .claude\skills\niimprint-b1\
# or globally: $HOME\.claude\skills\niimprint-b1\
```

With [`skill/SKILL.md`](skill/SKILL.md) installed you can just ask — *"print a label for John at Acme, manager"* — and the agent handles the rest, following the rules that keep it from wasting labels: test the connection first, never guess the COM port, always check `completa`, treat `PrinterBusy` as "power-cycle it", never `pip install -r requirements.txt`.

---

## 📡 Why not Bluetooth

| | |
|---|---|
| 🔵 **Bluetooth** | The driver has `BluetoothTransport`, but Python's RFCOMM socket **does not exist on Windows**. |
| 📦 **`labbots/NiimPrintX`** | **Bluetooth only** (uses `bleak`, no serial transport) and needs `pycairo` + ImageMagick. |
| 🤖 **Android** | `pyserial` cannot reach USB on Android. |

Over USB the B1 shows up as a **serial port**, and `niimprint` speaks the same Niimbot protocol over serial. Protocol reference: **https://printers.niim.blue/interfacing/proto/** — framing is `0x55 0x55 <type> <len> <data> <xor> 0xAA 0xAA`.

---

## 🔗 Sibling project

[**`josevitorls/luma-etiquetas`**](https://github.com/josevitorls/luma-etiquetas) solves the same problem from the other end: it signs into your **Lu.ma** account, lists an event's guests and generates the badges **as a PDF** for any printer.

|  | `luma-etiquetas` | `niimprint-b1` (here) |
|---|---|---|
| 📥 Input | your Lu.ma account | any `.json` or `.csv` |
| 📤 Output | PDF, one page per label | direct print on the B1 over USB |
| 🖨️ Printer | any | Niimbot B1 |
| 🔧 Stack | Node / TypeScript | Python |

They are **independent** — this project knows nothing about Lu.ma. To bridge them, dump the guest list to a `.json` (`guests.map(extractBadgeFields)`) and point the CLI at it:

```bash
py etiquetas.py print --in guests.json --linha1 "{name}" --linha2 "{company} - {jobTitle}"
```

---

## 👥 Contributors

| | Who | What |
|:---:|---|---|
| 👤 | **[José Vitor Lopes](https://github.com/josevitorls)** | Author and maintainer of this fork. Defined the problem, provided the hardware, diagnosed the failures on real prints and made the engineering calls — including the cautious `row_delay` and the one-job-at-a-time queue |
| 🤖 | **[Claude Opus 5](https://claude.com/claude-code)** (via Claude Code) | Co-author. Reverse-engineering of the B1's behaviour, the 7 driver fixes, calibration, queue, timing panel and documentation |
| 🍴 | **[AndBondStyle](https://github.com/AndBondStyle)** | Author of the [`niimprint`](https://github.com/AndBondStyle/niimprint) this forks from |
| 🧬 | **[kjy00302](https://github.com/kjy00302)** | Author of the original [`niimprint`](https://github.com/kjy00302/niimprint) and of the Niimbot protocol implementation |
| 📡 | **[niim.blue](https://printers.niim.blue/)** | Community protocol documentation |

Got it working on another roll? [Open an issue](https://github.com/josevitorls/niimprint-b1/issues) saying which roll, which firmware and which `row_delay` — that is exactly the information missing from the internet about the B1.

---

## 📄 License

**MIT** — see [`LICENSE`](LICENSE). `kjy00302`'s original copyright notice is preserved; this fork's work was added as a second line. Upstream's readme is kept at [`UPSTREAM-readme.md`](UPSTREAM-readme.md).

<div align="center">
<br>

Built with a **Niimbot B1**, a **USB** cable and a **Windows** laptop. 🏷️🔌🪟

</div>
