"""
Testes de huffman.py (heap, códigos e compressão/descompressão).

Não precisa de Scapy nem rede.

Uso:
    python teste_huffman.py
"""

import os
import random
import tempfile

from huffman import (HeapMinimo, comprimir, comprimir_arquivo, contar_frequencias,
                     descomprimir, descomprimir_arquivo, gerar_codigos, montar_arvore)


def teste_heap():
    for _ in range(500):
        valores = [random.randint(0, 50) for _ in range(random.randint(0, 40))]
        heap = HeapMinimo()
        for v in valores:
            heap.inserir(v)
        assert [heap.remover_menor() for _ in range(len(heap))] == sorted(valores)
    print("Heap mínimo: OK")


def teste_codigos():
    # exemplo clássico: a=45 b=13 c=12 d=16 e=9 f=5 -> 224 bits no total
    frequencias = [0] * 256
    for letra, freq in zip(b"abcdef", [45, 13, 12, 16, 9, 5]):
        frequencias[letra] = freq
    codigos = gerar_codigos(montar_arvore(frequencias))
    assert sum(frequencias[s] * len(c) for s, c in codigos.items()) == 224
    assert len(codigos[ord("a")]) == 1  # o mais frequente tem o código mais curto

    # nenhum código é prefixo de outro (senão a decodificação seria ambígua)
    lista = list(codigos.values())
    for a in lista:
        for b in lista:
            assert a == b or not b.startswith(a)
    print("Códigos de Huffman: OK (224 bits no exemplo clássico, sem prefixos)")


def teste_ida_e_volta():
    casos = [
        b"",
        b"a",
        b"aaaaaaaa",
        b"ab",
        bytes(range(256)) * 3,
        "Ocupação, ação, ñ, 日本".encode("utf-8"),
    ]
    for _ in range(300):
        alfabeto = random.choice([b"ab", b"TCPUDP0123456789.,-\n", bytes(range(256))])
        casos.append(bytes(random.choice(alfabeto) for _ in range(random.randint(0, 2000))))
    for dados in casos:
        assert descomprimir(comprimir(dados)) == dados, dados[:40]
    print(f"Comprimir + descomprimir: OK ({len(casos)} entradas, incluindo vazia e 1 símbolo)")


def teste_log_comprime():
    linhas = ["hora,protocolo,tamanho,origem,destino\n"]
    for i in range(5000):
        protocolo = random.choice(["TCP", "TCP", "TCP", "UDP", "ICMP"])
        linhas.append(f"19:47:{i % 60:02d}.{i % 1000:03d},{protocolo},{random.choice([66, 1514, 74])},"
                      f"192.168.0.10,142.250.{random.randint(0, 3)}.{random.randint(1, 20)}\n")
    pasta = tempfile.mkdtemp()
    caminho = os.path.join(pasta, "log.csv")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.writelines(linhas)

    estatisticas = comprimir_arquivo(caminho)
    assert estatisticas["comprimido"] < estatisticas["original"] * 0.6  # log repetitivo comprime bem
    restaurado = descomprimir_arquivo(estatisticas["saida"])
    with open(caminho, "rb") as a, open(restaurado, "rb") as b:
        assert a.read() == b.read()

    # frequências batem com a contagem do Python
    with open(caminho, "rb") as arquivo:
        dados = arquivo.read()
    assert contar_frequencias(dados)[ord(",")] == dados.count(b",")
    taxa = estatisticas["comprimido"] / estatisticas["original"] * 100
    print(f"Log de 5000 pacotes: OK ({estatisticas['original']:,} -> {estatisticas['comprimido']:,} bytes, {taxa:.1f}%)")


def teste_arquivo_invalido():
    try:
        descomprimir(b"nada disso")
    except ValueError:
        pass
    else:
        raise AssertionError("deveria recusar arquivo sem cabeçalho HUF1")
    try:
        descomprimir(comprimir(b"abcdefgh" * 100)[:-10])
    except ValueError:
        pass
    else:
        raise AssertionError("deveria recusar arquivo truncado")
    print("Arquivos inválidos: OK (recusados)")


if __name__ == "__main__":
    teste_heap()
    teste_codigos()
    teste_ida_e_volta()
    teste_log_comprime()
    teste_arquivo_invalido()
    print("\nTodos os testes passaram.")
