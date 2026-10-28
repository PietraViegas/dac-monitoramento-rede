"""
Compressão de arquivos com o código de Huffman (usada no log do monitor).

Implementado à mão (sem heapq): a fila de prioridade é um heap mínimo próprio.
Trabalha com bytes, então comprime qualquer arquivo (o log é texto UTF-8).

Uso:
    python huffman.py comprimir trafego_log.csv              # gera trafego_log.csv.huf
    python huffman.py descomprimir trafego_log.csv.huf       # gera trafego_log.csv.descomprimido
    python huffman.py descomprimir trafego_log.csv.huf saida.csv

Formato do arquivo .huf:
    "HUF1" | tamanho original (8 bytes) | nº de símbolos (2 bytes)
    | para cada símbolo: byte (1) + frequência (8) | bits codificados

O descompressor recria a mesma árvore a partir das frequências, por isso
a construção da árvore precisa ser determinística (desempate pela ordem).

Complexidade (n = bytes do arquivo, k = símbolos diferentes, k <= 256):
- contar frequências: O(n);
- montar a árvore com o heap: O(k log k);
- codificar: O(n); decodificar: O(total de bits), no máximo O(n·k).
"""

import sys
from typing import TypedDict

MAGICO = b"HUF1"


class Estatisticas(TypedDict):
    entrada: str
    saida: str
    original: int
    comprimido: int
    simbolos: int
    bits_por_simbolo: float


# ===== Heap mínimo (fila de prioridade) =====

class HeapMinimo:
    """Heap binário em lista: o menor item fica sempre na posição 0.

    Inserir e remover o menor custam O(log n). Os itens precisam ser
    comparáveis com < (aqui são tuplas (frequência, ordem, nó)).
    """

    def __init__(self):
        self._itens = []

    def inserir(self, item):
        itens = self._itens
        itens.append(item)
        i = len(itens) - 1
        while i > 0:  # sobe enquanto for menor que o pai
            pai = (i - 1) // 2
            if not itens[i] < itens[pai]:
                break
            itens[i], itens[pai] = itens[pai], itens[i]
            i = pai

    def remover_menor(self):
        itens = self._itens
        menor = itens[0]
        ultimo = itens.pop()
        if itens:
            itens[0] = ultimo
            i = 0
            while True:  # desce trocando com o menor filho
                esquerdo, direito = 2 * i + 1, 2 * i + 2
                alvo = i
                if esquerdo < len(itens) and itens[esquerdo] < itens[alvo]:
                    alvo = esquerdo
                if direito < len(itens) and itens[direito] < itens[alvo]:
                    alvo = direito
                if alvo == i:
                    break
                itens[i], itens[alvo] = itens[alvo], itens[i]
                i = alvo
        return menor

    def __len__(self):
        return len(self._itens)


# ===== Árvore de Huffman =====

class _NoHuffman:
    __slots__ = ("simbolo", "esquerda", "direita")

    def __init__(self, simbolo=None, esquerda=None, direita=None):
        self.simbolo = simbolo  # byte (0-255) nas folhas, None nos nós internos
        self.esquerda = esquerda
        self.direita = direita


def contar_frequencias(dados):
    """Lista de 256 posições: quantas vezes cada byte aparece."""
    frequencias = [0] * 256
    for byte in dados:
        frequencias[byte] += 1
    return frequencias


def montar_arvore(frequencias):
    """Junta sempre os 2 nós de menor frequência até sobrar 1 (a raiz).

    O "ordem" desempata frequências iguais e garante que o compressor e o
    descompressor montem exatamente a mesma árvore.
    """
    heap = HeapMinimo()
    ordem = 0
    for simbolo in range(256):
        if frequencias[simbolo]:
            heap.inserir((frequencias[simbolo], ordem, _NoHuffman(simbolo)))
            ordem += 1
    if len(heap) == 0:
        return None
    while len(heap) > 1:
        freq_a, _, a = heap.remover_menor()
        freq_b, _, b = heap.remover_menor()
        heap.inserir((freq_a + freq_b, ordem, _NoHuffman(esquerda=a, direita=b)))
        ordem += 1
    return heap.remover_menor()[2]


def gerar_codigos(raiz):
    """Dicionário byte -> código em texto ("0101"). Esquerda = 0, direita = 1."""
    codigos = {}
    if raiz is None:
        return codigos
    if raiz.simbolo is not None:  # arquivo com um único símbolo: código "0"
        codigos[raiz.simbolo] = "0"
        return codigos
    pilha = [(raiz, "")]
    while pilha:
        no, codigo = pilha.pop()
        if no.simbolo is not None:
            codigos[no.simbolo] = codigo
        else:
            pilha.append((no.esquerda, codigo + "0"))
            pilha.append((no.direita, codigo + "1"))
    return codigos


# ===== Comprimir / descomprimir =====

def comprimir(dados):
    """bytes -> bytes no formato .huf."""
    frequencias = contar_frequencias(dados)
    codigos = gerar_codigos(montar_arvore(frequencias))

    saida = bytearray(MAGICO)
    saida += len(dados).to_bytes(8, "big")
    saida += len(codigos).to_bytes(2, "big")
    for simbolo in range(256):
        if frequencias[simbolo]:
            saida.append(simbolo)
            saida += frequencias[simbolo].to_bytes(8, "big")

    # (valor, nº de bits) de cada código, para juntar os bits num inteiro
    tabela = {s: (int(c, 2), len(c)) for s, c in codigos.items()}
    acumulador = 0
    bits = 0
    for byte in dados:
        valor, tamanho = tabela[byte]
        acumulador = (acumulador << tamanho) | valor
        bits += tamanho
        while bits >= 8:
            bits -= 8
            saida.append((acumulador >> bits) & 0xFF)
        acumulador &= (1 << bits) - 1
    if bits:  # completa o último byte com zeros
        saida.append((acumulador << (8 - bits)) & 0xFF)
    return bytes(saida)


def descomprimir(dados):
    """bytes no formato .huf -> bytes originais."""
    if dados[:4] != MAGICO:
        raise ValueError("não é um arquivo .huf (cabeçalho inválido)")
    tamanho_original = int.from_bytes(dados[4:12], "big")
    quantidade = int.from_bytes(dados[12:14], "big")

    frequencias = [0] * 256
    posicao = 14
    for _ in range(quantidade):
        simbolo = dados[posicao]
        frequencias[simbolo] = int.from_bytes(dados[posicao + 1:posicao + 9], "big")
        posicao += 9

    raiz = montar_arvore(frequencias)
    saida = bytearray()
    if raiz is None:
        return bytes(saida)
    if raiz.simbolo is not None:  # um único símbolo repetido
        return bytes([raiz.simbolo]) * tamanho_original

    no = raiz
    for byte in dados[posicao:]:
        for deslocamento in range(7, -1, -1):
            no = no.direita if (byte >> deslocamento) & 1 else no.esquerda
            if no.simbolo is not None:
                saida.append(no.simbolo)
                if len(saida) == tamanho_original:
                    return bytes(saida)  # ignora os zeros de enchimento
                no = raiz
    raise ValueError("arquivo .huf truncado")


def comprimir_arquivo(entrada, saida=None) -> Estatisticas:
    """Comprime um arquivo e devolve as estatísticas (dict)."""
    saida = saida or entrada + ".huf"
    with open(entrada, "rb") as arquivo:
        dados = arquivo.read()
    comprimido = comprimir(dados)
    with open(saida, "wb") as arquivo:
        arquivo.write(comprimido)
    frequencias = contar_frequencias(dados)
    codigos = gerar_codigos(montar_arvore(frequencias))
    bits_codigo = sum(frequencias[s] * len(c) for s, c in codigos.items())
    return {
        "entrada": entrada,
        "saida": saida,
        "original": len(dados),
        "comprimido": len(comprimido),
        "simbolos": len(codigos),
        "bits_por_simbolo": bits_codigo / len(dados) if dados else 0.0,
    }


def descomprimir_arquivo(entrada, saida=None):
    if saida is None:
        saida = (entrada[:-4] if entrada.endswith(".huf") else entrada) + ".descomprimido"
    with open(entrada, "rb") as arquivo:
        dados = descomprimir(arquivo.read())
    with open(saida, "wb") as arquivo:
        arquivo.write(dados)
    return saida


def formatar_estatisticas(e: Estatisticas):
    taxa = e["comprimido"] / e["original"] * 100 if e["original"] else 0.0
    return (
        f"Huffman: {e['entrada']} ({e['original']:,} bytes) -> {e['saida']} ({e['comprimido']:,} bytes)\n"
        f"         {taxa:.1f}% do tamanho original, economia de {100 - taxa:.1f}%; "
        f"{e['simbolos']} símbolos, média de {e['bits_por_simbolo']:.2f} bits por byte (antes: 8)"
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3) or argv[0] not in ("comprimir", "descomprimir"):
        print(__doc__)
        return 1
    if argv[0] == "comprimir":
        print(formatar_estatisticas(comprimir_arquivo(*argv[1:])))
    else:
        print(f"Descomprimido em {descomprimir_arquivo(*argv[1:])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
