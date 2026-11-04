# Monitoramento de ocupação de rede em tempo real (DAC)

Projeto do Desafio de Articulação de Competências (DAC), Ciência da Computação, 5º semestre (UCDB).

Um programa em Python captura pacotes reais (TCP, UDP e ICMP, em IPv4 e IPv6), calcula a ocupação da rede a cada 1 s e envia o resultado por MQTT para um ESP32 simulado no Wokwi. O ESP32 mostra o nível (0 a 9) num display de 7 segmentos e acende o LED verde (normal) ou o vermelho (alerta, a partir de 80%).

Equipe: Abner Saconi, Guilherme Luzzi, Kailani Menezes e Pietra Viegas. Professor: Eduardo Contar.

## Arquitetura

```
Placa de rede → Scapy + Npcap → Fila dinâmica → janela de 1 s → média móvel de 3 s → ocupação %
                                     │
                                     └─► Árvore de IPs → QuickSort → top consumidores
                                     └─► log CSV → Huffman (.huf)

ocupação % → OCUP,<ocupacao>,<nivel>,<alerta>,<valido> → MQTT (broker.hivemq.com) → ESP32 no Wokwi
                                                                                    → display 0-9 + LED verde/vermelho
```

A ocupação é a taxa medida dividida por uma capacidade de referência didática de 20 Mbit/s, calibrada em três cenários (ver `teste_3/calibracao_resultado.txt`). Ela não representa a capacidade real da rede.

## Onde está cada coisa

| Pasta | Conteúdo |
|---|---|
| [`teste_3/`](teste_3/README_3.md) | **Produto final**: sniffer, monitor, estruturas de dados, QuickSort, Huffman, calibração e testes automáticos |
| [`teste_2/`](teste_2/teste_2_README.md) | Contrato de dados Python → ESP32 e o **circuito usado no produto final** (`wokwi/sketch.ino` e `wokwi/diagram.json`) |
| [`teste/`](teste/README.md) | Teste 1: prova de conceito da comunicação por MQTT (um único dígito). Histórico; ainda aponta para o broker antigo |

## Como rodar

Requisitos (Windows): [Npcap](https://npcap.com) com "WinPcap API-compatible Mode" e Python 3.13 ou mais novo. Na raiz do repositório:

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install scapy paho-mqtt
```

1. Abra o circuito no Wokwi, dê Play e espere `MQTT conectado!` no monitor serial. O código e o circuito são os de `teste_2/wokwi/sketch.ino` e `teste_2/wokwi/diagram.json`.
   - Versão atual, com `broker.hivemq.com`: **https://wokwi.com/projects/479721217897169921**
   - Versão original dos Testes 1 e 2, com `broker.emqx.io`: https://wokwi.com/projects/478431213718363137
2. Em `teste_3/`, com a `.venv` ativada (`.\.venv\Scripts\Activate.ps1`), rode o monitor num terminal como administrador:

```
cd teste_3
python monitor.py                 # configuração calibrada: 20 Mbit/s, média de 3 s
python monitor.py --log           # também grava o log e comprime com Huffman ao parar
python monitor.py --sem-mqtt      # só mostra as janelas, sem enviar ao ESP32
```

3. Para parar, Ctrl+C uma vez e espere "Monitor finalizado". O relatório por protocolo e o top de consumidores aparecem no final.

Testes automáticos (não capturam pacotes): `python teste_estruturas.py`, `python teste_huffman.py` e `python teste_monitor.py`, dentro de `teste_3/`.

Todos os comandos e o formato de saída estão no [README do Teste 3](teste_3/README_3.md).

## Disciplinas integradas

| Disciplina | Onde aparece |
|---|---|
| Redes de Computadores Aplicada | Captura TCP/UDP/ICMP em IPv4 e IPv6, relatório de banda por protocolo (`sniffer_basico.py`, `monitor.py`) |
| Estruturas de Dados | Fila dinâmica em lista encadeada e árvore binária de busca por IP (`estruturas.py`) |
| Análise de Algoritmos | QuickSort com partição de Hoare e compressão de Huffman, com análise de complexidade (`estruturas.py`, `huffman.py`) |
| Eletrônica Digital | Circuito no Wokwi com ESP32, display de 7 segmentos e LEDs (`teste_2/wokwi/`). A decodificação é feita por software no ESP32, com aprovação do professor (decisão D15) |
| Autonomia Intelectual | Scrum adaptado no Trello, relatório de 20 decisões tecnológicas e autoavaliação da equipe |

## Documentos de entrega

Entregues à parte (não ficam no repositório):

- Artigo em PDF: justificativa, objetivos, metodologia, decisões, resultados e limitações.
- Relatório de decisões tecnológicas (D1 a D20).
- Autoavaliação da equipe.
- Vídeo da apresentação.
