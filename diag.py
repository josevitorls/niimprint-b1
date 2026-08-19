"""Diagnostico do dialogo com a B1. Nao imprime nada por padrao."""
import logging
import sys
import time

from PIL import Image

from niimbot import InfoEnum, PrinterClient, SerialTransport

logging.basicConfig(level="DEBUG", format="%(message)s")

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
do_print = "--print" in sys.argv

pr = PrinterClient(SerialTransport(port=port))

print("\n--- heartbeat ---")
try:
    print(pr.heartbeat())
except Exception as e:
    print("erro:", repr(e))

print("\n--- infos ---")
for k in (InfoEnum.DEVICETYPE, InfoEnum.LABELTYPE, InfoEnum.DENSITY,
          InfoEnum.PRINTSPEED, InfoEnum.SOFTVERSION, InfoEnum.HARDVERSION):
    try:
        print(k.name, "=", pr.get_info(k))
    except Exception as e:
        print(k.name, "erro:", repr(e))

print("\n--- rfid ---")
try:
    print(pr.get_rfid())
except Exception as e:
    print("erro:", repr(e))

if not do_print:
    print("\n(rode com --print para o teste de mancha preta)")
    raise SystemExit

print("\n--- teste: mancha preta 384x120 ---")
img = Image.new("1", (384, 120), 0)   # modo '1': 0 = preto

lt = 1
for a in sys.argv:
    if a.startswith("--type="):
        lt = int(a.split("=")[1])

print("set_label_density(5) ->", pr.set_label_density(5))
print("set_label_type(%d)    ->" % lt, pr.set_label_type(lt))
print("start_print          ->", pr.start_print())
print("start_page_print     ->", pr.start_page_print())
print("set_dimension        ->", pr.set_dimension(img.height, img.width))
try:
    print("set_quantity         ->", pr.set_quantity(1))
except Exception as e:
    print("set_quantity erro:", repr(e))

n = 0
for pkt in pr._encode_image(img):
    pr._send(pkt)
    n += 1
print("linhas enviadas:", n)

time.sleep(0.5)
try:
    print("print_status ->", pr.get_print_status())
except Exception as e:
    print("print_status erro:", repr(e))

print("end_page_print ->", pr.end_page_print())
time.sleep(0.3)
for _ in range(30):
    if pr.end_print():
        break
    time.sleep(0.1)
print("end_print ok")
