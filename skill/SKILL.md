---
name: niimprint-b1
description: Use when the user wants to print labels, badges, tags or stickers on a Niimbot B1 thermal printer connected over USB on Windows - drawing two-line centered labels from JSON/CSV data, running the print queue, calibrating a new roll size, or diagnosing truncated/blank/misaligned labels.
---

# Impressao na Niimbot B1 (USB, Windows)

Este repositorio imprime **etiquetas de duas linhas centralizadas** numa Niimbot B1
ligada por USB. A linha 1 sai em destaque (negrito, corpo maior) e a linha 2 embaixo,
menor. O corpo da fonte e escolhido sozinho para caber sem invadir a margem que
protege do corte.

O conteudo das duas linhas e definido por **templates** sobre as colunas do arquivo
de entrada -- cracha de evento e apenas o default, nao a unica coisa que da para
imprimir.

## Antes de qualquer impressao

**1. Teste a conexao. Isso nao gasta etiqueta.**

```
py etiquetas.py info
```

Se falhar, pare e diagnostique -- nao tente imprimir mesmo assim.

**2. Use `py`, nunca `python`.** No Windows o alias da Microsoft Store quebra o
comando `python`. Todo comando deste repositorio comeca com `py`.

**3. Nunca chute a porta COM.** O default e `COM3`, mas ela muda de USB para USB.
Para descobrir:

```
py -c "from serial.tools.list_ports import comports; [print(p.device, p.description) for p in comports()]"
```

A B1 aparece como `USB\VID_3513&PID_0002`. Alternativa: `SerialTransport(port="auto")`.

**4. Nunca rode `pip install -r requirements.txt` nem `poetry install`.** Esses
arquivos sao do upstream, pertencem ao diretorio `niimprint/`, fixam
`pillow==10.1.0` e travam `python = "~3.11"` -- nao instalam no 3.13 e nao sao
necessarios. As unicas dependencias sao:

```
py -m pip install pillow pyserial
```

## Fluxo normal

1. **Descubra as colunas do arquivo de entrada** antes de montar os templates. Leia
   o cabecalho do `.csv` ou as chaves do `.json`.
2. **Monte `--linha1` e `--linha2`** com `{Coluna}`. A busca ignora maiusculas e
   aceita nome com espaco (`{Job Title}`). Se o arquivo tiver cabecalho em ingles
   (`name`, `company`, `title`), os defaults ja funcionam.
3. **Gere o preview primeiro** e confira os PNGs em `preview/`:
   ```
   py etiquetas.py preview --in DADOS --linha1 "{A}" --linha2 "{B} - {C}"
   ```
4. **Imprima uma etiqueta so** para validar antes de rodar o lote:
   ```
   py etiquetas.py print --in DADOS --only 1 --linha1 "{A}" --linha2 "{B} - {C}"
   ```
5. **Imprima o lote.** Uma unica conexao serial, um trabalho completo por etiqueta.

Para integrar com outro sistema, use `fila.FilaImpressao` em vez da CLI:

```python
from fila import FilaImpressao

fila = FilaImpressao(porta="COM3", ao_terminar=baixa)
fila.imprimir("PAT-004821", "TI - Notebook Dell 5420", ref=item_id)
fila.encerrar()
```

`imprimir()` devolve o controle na hora; a thread da fila manda um trabalho por vez
e so comeca o proximo quando a impressora confirma que o papel parou.

## Regras que evitam desperdicio

**Sempre confira `resultado["completa"]`.** E o unico campo que diz se a etiqueta
saiu inteira. `False` significa que a B1 descartou linhas: a etiqueta esta truncada
e precisa ser reimpressa. A impressora **nao devolve erro** nesse caso -- todos os
comandos respondem `True`. Dar baixa sem checar isso marca um item como etiquetado
sem etiqueta na mao.

**Nunca baixe `row_delay` abaixo de `0.005` sem medir.** O default `0.005` foi
escolhido por cautela: entrega a etiqueta em 6,0 s com folga de buffer. `0.002`
entrega em 4,48 s mas gasta a folga inteira, e quando ela acabar a falha e
silenciosa. Se precisar mesmo de mais velocidade, meca com etiquetas de verdade
usando o painel:

```
py painel.py
```

Ele abre `http://127.0.0.1:8765` (so localhost, por decisao) com um cronometro por
etiqueta e botoes que trocam o `row_delay` a quente. Etiqueta incompleta aparece
marcada em vermelho.

**`PrinterBusy` nao se resolve repetindo o comando.** A excecao
`PrinterBusy: a impressora recusou o comando (0xDB codigo N)` significa que a B1
esta travada: tampa aberta, rolo acabado ou mal encaixado, ou um trabalho anterior
interrompido no meio (matar o processo Python durante a impressao causa isso).
Peca ao usuario para conferir a tampa e o rolo e, se persistir, **desligar e ligar
a impressora**. Atencao: comandos de leitura (`info`) continuam respondendo nesse
estado, entao "a impressora responde" nao quer dizer que ela vai imprimir.

**Nao mate o processo durante uma impressao.** Isso deixa a impressora no estado
acima. Use `fila.encerrar()`, que espera o que falta.

**Nao invente pausa entre etiquetas.** Nao existe flag de sleep e ela foi removida
de proposito: quem sabe quando a etiqueta acabou e a impressora, via
`wait_until_done()`, nao um tempo chutado.

## Diagnostico rapido

| Sintoma | Causa | Acao |
|---|---|---|
| `could not open port` / acesso negado | o app da Niimbot esta segurando a porta | fechar o app, inclusive o icone da bandeja |
| imprime so os primeiros milimetros | `row_delay` baixo demais | subir para `0.02` para confirmar, depois calibrar |
| etiqueta totalmente em branco | tipo de rolo errado | deixar o driver perguntar o `LABELTYPE` a impressora; nao forcar |
| sai claro ou borrado | densidade | `--density` de 1 a 5 (5 e o maximo) |
| sai de cabeca para baixo | orientacao no porta-etiqueta | `--rotate180` |
| corte no meio do texto | etiqueta parou fora do lugar | `py calibra.py --print` e conferir a regua |
| `A linha 1 ficou vazia no(s) registro(s) ...` | template nao casou com nenhuma coluna | usar uma das colunas listadas na propria mensagem |

## Outro tamanho de rolo

Mudar `LABEL_MM = (50, 80)` no topo de `etiquetas.py`. `DPI = 203` e `HEAD_PX = 384`
sao fatos fisicos da B1 e nao se mexem. Em etiqueta curta, baixar
`MARGEM_PAPEL_MM` de 6.0 para ~3.0. Depois: `preview` -> `py calibra.py --print --delay=0.005`
(imprime reguas em mm) -> `print --only 1`.

## Arquivos

| Arquivo | Para que |
|---|---|
| `etiquetas.py` | CLI (`info`/`preview`/`print`) e o desenho da etiqueta |
| `fila.py` | `FilaImpressao` -- e por aqui que se integra outro sistema |
| `painel.py` | pagina local com cronometro e troca de `row_delay` a quente |
| `calibra.py` | cartao de calibracao com reguas em mm |
| `diag.py` | diagnostico da porta serial |
| `niimbot/` | o driver corrigido -- **e este que roda** |
| `niimprint/` | o driver do upstream, intocado, so para diff. Nao importar |

Detalhes das 4 correcoes do driver, medicoes de tempo e referencia completa da API
estao no `README.md`.
