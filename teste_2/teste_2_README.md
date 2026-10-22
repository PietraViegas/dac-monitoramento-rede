# Teste 2: contrato de dados Python → ESP32

Valida o **formato de dados** combinado entre o programa Python (futuro sniffer) e o circuito (ESP32 no Wokwi), usando MQTT.

> Os valores de ocupação aqui são **inventados pelo script**. Este teste **não captura pacotes reais**.

## Arquivos

| Arquivo | Função |
|---|---|
| `publicador.py` | Finge ser o sniffer: gera e envia mensagens de teste pelo MQTT |
| `sketch.ino` | Código do ESP32: recebe, valida e mostra no display e nos LEDs |
| `diagram.json` | Circuito do Wokwi (display de 7 segmentos + LED verde + LED vermelho) |
| `relatorio_teste_comunicacao.txt` | Relatório completo com resultados e limitações |

## Formato da mensagem

```
OCUP,<ocupacao_pct>,<nivel>,<alerta>,<valido>
Exemplo: OCUP,85.5,8,1,1
```

| Campo | Significado |
|---|---|
| `ocupacao_pct` | Ocupação da rede, de 0.0 a 100.0 |
| `nivel` | Número de 0 a 9 mostrado no display (parte inteira de ocupação/10, máximo 9) |
| `alerta` | 0 = LED verde, 1 = LED vermelho (alerta = 1 quando a ocupação é 80% ou mais) |
| `valido` | 1 = dado válido, 0 = sem dados (display mostra um traço e os LEDs apagam) |

Broker: `broker.emqx.io:1883`. Tópico: `dac-teste-2026-ocupacao-74291`. Sem quebra de linha. Máximo de 20 caracteres.

Se o ESP32 ficar 3 s sem receber mensagem válida, ele entra em "sem dados". Mensagem inválida é ignorada.

## Como rodar

1. Abra o projeto no Wokwi com o `sketch.ino` e o `diagram.json`, dê Play e espere `MQTT conectado!` no monitor serial.
2. No terminal, dentro desta pasta:

```
pip install paho-mqtt
python publicador.py              # sequência de 0% a 100%
python publicador.py invalidas    # mensagens inválidas (devem ser ignoradas)
python publicador.py semdados     # estado "sem dados" e timeout
python publicador.py manual       # você digita a ocupação em %
```

## Resultado (22/10/2026)

| Teste | Resultado |
|---|---|
| Sequência 0 a 100% | Aprovado: nível 0 a 7 com LED verde, 8 e 9 com LED vermelho |
| Mensagens inválidas | Aprovado: 7 de 7 rejeitadas, display estável |
| Sem dados | Aprovado: `valido=0` imediato, timeout funciona (mais lento no Wokwi) |

Limitações: broker público pode perder mensagem ao reconectar; o Wokwi roda mais devagar que o tempo real, o que atrasa o timeout de 3 s. Detalhes no relatório.

## Diferença para o Teste 1 (pasta `teste`)

| | Teste 1 | Teste 2 |
|---|---|---|
| Objetivo | Provar que o Python consegue falar com o Wokwi por MQTT | Validar o formato de dados completo (contrato) |
| Mensagem | Um único dígito de 0 a 9 | `OCUP,ocupacao,nivel,alerta,valido` |
| Validação no ESP32 | Nenhuma | Completa (campos, faixas, coerência) |
| Estado "sem dados" | Não existia | `valido=0` e timeout de 3 s |
| Alerta | O ESP32 decidia sozinho | Vem na mensagem e é conferido |
| Problemas conhecidos | Buffer pequeno (100% era descartado) e dígito 4 errado | Corrigidos |
| Testes | Verificação simples | 3 cenários documentados |

O Teste 1 provou que a comunicação **é possível**. O Teste 2 provou que ela **segue um padrão que o resto da equipe pode usar**.

## Próximos passos

1. Sniffer com Scapy (captura real de pacotes).
2. Ligar a captura à função `montar_mensagem()` do `publicador.py`.
3. Circuito com portas lógicas, decodificador e multiplexador.