# Teste 3: captura real de tráfego → ocupação → ESP32

Captura pacotes reais da placa de rede com Scapy, calcula a **ocupação da rede** a cada 1 segundo e envia o resultado por MQTT para o ESP32 (Wokwi), que mostra o nível (0 a 9) no display e acende o LED verde ou vermelho.

Diferente do Teste 2, aqui os valores **vêm da rede de verdade**, e não de um script que inventa números.

```
Placa de rede → Scapy (sniffer) → soma por janela de 1 s → ocupação %
                                                              │
                                    MQTT (broker.hivemq.com) ◄┘
                                                │
                                         ESP32 no Wokwi → display 0-9 + LED verde/vermelho
```

## Arquivos

| Arquivo | Função |
|---|---|
| `sniffer_basico.py` | Captura e **imprime** os pacotes (hora, protocolo, tamanho, origem → destino). Também define `extrair_registro()`, usada pelo monitor |
| `monitor.py` | Captura + fila + janela de 1 s + média móvel + envio MQTT. Ao parar: relatório por protocolo, top de consumidores e compressão do log. É o programa principal |
| `estruturas.py` | Fila dinâmica, árvore binária de busca por IP e QuickSort, feitas à mão (sem `deque`/`sorted`) |
| `huffman.py` | Compressão e descompressão Huffman (com heap mínimo próprio). Usado pelo monitor e também pela linha de comando |
| `teste_estruturas.py`, `teste_huffman.py`, `teste_monitor.py` | Testes automáticos. Não capturam pacotes (não precisam de administrador) |
| `publicador.py` | **Cópia** do `teste_2/publicador.py`. O monitor importa dele `montar_mensagem()`, o broker e o tópico |
| `calibrar.py` | Mede 3 cenários (normal, vídeo, speedtest) e recomenda a capacidade de referência. Grava `calibracao_resultado.txt` |

Use o `sketch.ino` e o `diagram.json` da pasta `teste_2` (não mudaram).

## Requisitos (Windows)

1. **Npcap** (npcap.com), instalado com a opção "WinPcap API-compatible Mode".
2. `pip install scapy paho-mqtt`
3. Se der erro de permissão ao capturar, abrir o terminal como administrador.

## Como rodar

**Só ver os pacotes (sem MQTT):**

```
python sniffer_basico.py --listar                         # lista as interfaces
python sniffer_basico.py                                  # captura 50 pacotes e mostra o resumo
python sniffer_basico.py --limite 0                       # até Ctrl+C
python sniffer_basico.py --filtro "icmp or icmp6"         # só ping
python sniffer_basico.py --iface "Wi-Fi"                  # escolhe a interface
```

**Monitor completo (com o Wokwi rodando e mostrando `MQTT conectado!`):**

```
python monitor.py                                         # usa o CAPACIDADE_REF_BPS do publicador.py (hoje 20 Mbit/s)
python monitor.py --capacidade 20000000 --media 3         # configuração calibrada: 20 Mbit/s, média de 3 s
python monitor.py --sem-mqtt                              # só mostra as janelas, sem enviar
python monitor.py --duracao 30                            # para sozinho após 30 s
python monitor.py --top 5                                 # ao parar, mostra os 5 IPs que mais trafegaram (padrão 10; 0 desliga)
python monitor.py --log                                   # grava trafego_log.csv e, ao parar, comprime em trafego_log.csv.huf
python monitor.py --log meu_log.csv                       # escolhe o nome do log
python huffman.py comprimir trafego_log.csv               # comprime qualquer arquivo
python huffman.py descomprimir trafego_log.csv.huf        # gera trafego_log.csv.descomprimido
```

**Testes (qualquer computador, sem rede):**

```
python teste_estruturas.py                                # fila, árvore e QuickSort
python teste_huffman.py                                   # Huffman: ida e volta, códigos, arquivos inválidos
python teste_monitor.py                                   # fila -> janela/árvore/log, relatório, formato do log (precisa do scapy instalado)
python calibrar.py                                        # refaz a calibração da referência (3 cenários de 30 s)
```

Para parar, **Ctrl+C uma vez só** e esperar "Monitor finalizado". Ao parar, o display do ESP32 volta ao traço ("sem dados").

## O que cada linha do monitor significa

```
19:47:35  TCP  276  UDP    0  ICMP    2  OUTROS    0  |  1096.0 kbit/s | ocupação 100.0% | nível 9 VERMELHO
```

- `TCP/UDP/ICMP/OUTROS`: quantidade de pacotes na janela de 1 s.
- `kbit/s`: taxa (média, se usar `--media`) de TCP + UDP + ICMP. **OUTROS (ex: ARP) não entra na conta.**
- `ocupação`: taxa dividida pela capacidade de referência (`--capacidade`), limitada a 100%.
- `nível`: parte inteira de ocupação/10, máximo 9. Alerta (vermelho) quando a ocupação é **80% ou mais**.

## Ao parar: relatório, top de consumidores e log

Exemplo ilustrativo da saída (os números não são de uma medição real):

```
RELATÓRIO DE BANDA POR PROTOCOLO (62.0 s de captura)
Protocolo    Pacotes         Bytes  Média kbit/s  % dos bytes
TCP            8,412     9,871,220        1273.7        96.1%
...
TOTAL          8,950    10,271,804        1325.4       100.0%
Ocupação usa só TCP+UDP+ICMP: média de 1318.2 kbit/s

TOP 5 CONSUMIDORES (bytes enviados + recebidos, TCP+UDP+ICMP)
  #  IP                                        Pacotes      Enviados     Recebidos         Total
  1  192.168.0.10                                  733       294,995       284,856       579,851
  ...
Árvore: 6 IPs, altura 5. Fila: pico de 1174 pacotes esperando.
```

O IP do próprio PC costuma ficar em 1º, porque todo o tráfego capturado passa por ele. Os seguintes são os servidores com que ele mais conversou.

O relatório soma todas as janelas da execução. Diferente da ocupação, ele mostra também OUTROS (ex: ARP).

Com `--log`, cada pacote vira uma linha de `trafego_log.csv` (`hora,protocolo,tamanho,origem,destino`; `-` quando não tem IP). O log é gravado na thread principal, depois que o pacote sai da fila, para não atrasar a captura. Ao parar, o monitor comprime o log com Huffman e mostra o resultado:

```
Huffman: trafego_log.csv (118,879 bytes) -> trafego_log.csv.huf (60,157 bytes)
         50.6% do tamanho original, economia de 49.4%; 40 símbolos, média de 4.02 bits por byte (antes: 8)
```

O log é sobrescrito a cada execução. Logs muito pequenos (poucas linhas) podem ficar maiores depois de comprimidos, porque o cabeçalho guarda a frequência de cada símbolo (9 bytes por símbolo).

## Estruturas de dados (`estruturas.py`)

```
sniffer (thread) ──enfileirar──► Fila ──desenfileirar (a cada 1 s)──► Janela (ocupação → MQTT)
                                                                  └──► ArvoreIP ──ao parar──► QuickSort ──► top N
```

| Estrutura | Como funciona | Complexidade |
|---|---|---|
| `Fila` | Lista encadeada com ponteiros para início e fim. Buffer entre o sniffer (outra thread, por isso tem trava) e o monitor. Guarda o pico de tamanho | Enfileirar e desenfileirar O(1) |
| `ArvoreIP` | Árvore binária de busca sem balanceamento. Chave = IP como número (IPv4 antes de IPv6). Cada nó soma pacotes, bytes enviados (IP de origem) e recebidos (IP de destino) | Busca/inserção O(log n) em média, O(n) no pior caso (IPs chegando em ordem). Percurso em ordem O(n) |
| `quicksort` | In-place, pivô do meio, partição de Hoare. Recursão sempre na parte menor | O(n log n) em média, O(n²) no pior caso. Memória extra O(log n). Não é estável |

O top de consumidores pega o percurso em ordem da árvore (O(n)) e ordena por bytes totais com o QuickSort (O(n log n)). Só entram TCP, UDP e ICMP, a mesma regra da ocupação.

## Huffman (`huffman.py`)

1. Conta quantas vezes cada byte aparece no arquivo.
2. Coloca cada byte num **heap mínimo** (fila de prioridade) pela frequência e junta sempre os dois menores até sobrar a raiz da árvore.
3. Percorre a árvore: esquerda = `0`, direita = `1`. Bytes frequentes (`,`, dígitos, `TCP`) ganham códigos curtos.
4. Grava o cabeçalho (`HUF1`, tamanho original, frequências) e os bits. O descompressor recria a mesma árvore a partir das frequências; empates são resolvidos pela ordem de chegada, então a árvore sai sempre igual.

| Etapa | Complexidade (n = bytes do arquivo, k = símbolos diferentes, k ≤ 256) |
|---|---|
| Contar frequências | O(n) |
| Montar a árvore (heap) | O(k log k) |
| Comprimir | O(n) |
| Descomprimir | O(total de bits), no máximo O(n·k) |

## Regras de medição

- O tamanho de cada pacote é `len(pacote)`: bytes do quadro inteiro, **incluindo cabeçalhos**.
- Conta o tráfego **nos dois sentidos** (o que sai e o que entra).
- Aceita **IPv4 e IPv6**. ICMPv6 conta como ICMP.
- A duração da janela é medida de verdade (não assume 1,000 s).
- O próprio tráfego MQTT do monitor também é capturado (desprezível).

## Formato enviado ao ESP32

```
OCUP,<ocupacao_pct>,<nivel>,<alerta>,<valido>      exemplo: OCUP,85.5,8,1,1
```

Tópico `dac-teste-2026-ocupacao-74291`, QoS 0, sem retain, sem quebra de linha. Detalhes em `teste_2/README.md`.

## Resultados observados

| Teste | Resultado |
|---|---|
| Captura TCP/UDP/ICMP | Funciona. Em 100 pacotes: TCP 91, UDP 5, ICMP 4, OUTROS 0 |
| IPv6 | A 1ª versão classificava IPv6 como OUTROS (41 de 50 pacotes). Corrigido |
| Ping | 1 pedido + 1 resposta por segundo, 74 bytes cada (14 + 20 + 8 + 32) |
| Monitor com tráfego real | 62 s de captura, display e LEDs acompanharam o nível |
| Referência de 1 Mbit/s, sem média | Tráfego normal fica em 10 a 300 kbit/s, mas rajadas chegaram a 14 Mbit/s; o vermelho acendeu em 16 de 62 s |
| Calibração (26/10/2026) | p95 da média móvel: normal 0,63 / vídeo 9,37 Mbit/s; speedtest com mediana de 38,01 Mbit/s. Referência definida em **20 Mbit/s** |
| Monitor com 20 Mbit/s e média de 3 s | O vídeo ficou verde e o speedtest acendeu o vermelho |

## Decisões tomadas

- **Capacidade de referência: 20 Mbit/s, com média móvel de 3 s** (calibração de 26/10/2026; ver `calibracao_resultado.txt` e a decisão D11). Antes o padrão era 1 Mbit/s, e o vermelho acendia em 16 de 62 s em uso normal. A proposta inicial de 10 Mbit/s foi descartada porque o p95 do vídeo (9,37 Mbit/s na média móvel) ocuparia cerca de 94% dela.
- **Vídeo gera rajadas** (o navegador enche um buffer e depois quase para): a média móvel de 3 s resolve, e foi validada com tráfego real.
- **Circuito:** a decodificação do display e o acionamento dos LEDs ficam **por software no ESP32**, via MQTT. O professor aprovou essa escolha por e-mail em 26/10/2026 (justificativa: otimizar o tempo de desenvolvimento e focar na estabilidade da integração). Deve constar em "Tomadas de decisão tecnológica" e na "Justificativa da solução" do PDF (decisão D15).
- **Broker:** desde 25/10/2026 é o `broker.hivemq.com`, porque o `broker.emqx.io` ficou inacessível (ver `registro_incidente_broker_mqtt.txt`). O endereço está em `publicador.py` (`BROKER`) e no `sketch.ino` (`servidor`).

## Ainda não implementado (objetivos da DAC)

Nenhum dos objetivos de código. Fila, árvore por IP e QuickSort estão em `estruturas.py`; Huffman em `huffman.py`; log e relatório por protocolo no `monitor.py`.

O circuito com portas lógicas, decodificador e multiplexador **não será feito**: o professor aprovou manter a lógica por software no ESP32.