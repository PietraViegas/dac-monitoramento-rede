"""
Estruturas de dados do projeto DAC: fila dinâmica, árvore binária de busca e QuickSort.

Todas implementadas à mão (sem deque, dict ou sorted), porque fazem parte
dos objetivos da disciplina.

- Fila: buffer entre o sniffer (que enfileira) e o monitor (que desenfileira).
- ArvoreIP: acumula pacotes e bytes por endereço IP.
- quicksort: ordena os IPs para montar o top de consumidores.

Não depende do Scapy: dá para testar sem capturar nada.
"""

from __future__ import annotations

import ipaddress
import threading


# ===== Fila dinâmica =====

class _NoFila:
    __slots__ = ("valor", "proximo")

    def __init__(self, valor):
        self.valor = valor
        self.proximo: _NoFila | None = None


class Fila:
    """Fila (FIFO) em lista encadeada simples.

    Guarda ponteiros para o início e o fim, então enfileirar e desenfileirar
    custam O(1). É dinâmica: cada pacote ganha um nó novo, sem tamanho fixo.
    Tem trava porque o sniffer enfileira em outra thread.
    """

    def __init__(self):
        self._inicio: _NoFila | None = None
        self._fim: _NoFila | None = None
        self._tamanho = 0
        self.maior_tamanho = 0  # pico de pacotes esperando no buffer
        self._trava = threading.Lock()

    def enfileirar(self, valor):
        no = _NoFila(valor)
        with self._trava:
            if self._fim is None:
                self._inicio = no
            else:
                self._fim.proximo = no
            self._fim = no
            self._tamanho += 1
            if self._tamanho > self.maior_tamanho:
                self.maior_tamanho = self._tamanho

    def desenfileirar(self):
        """Remove e devolve o primeiro valor, ou None se a fila estiver vazia."""
        with self._trava:
            if self._inicio is None:
                return None
            no = self._inicio
            self._inicio = no.proximo
            if self._inicio is None:
                self._fim = None
            self._tamanho -= 1
            return no.valor

    def vazia(self):
        return self._tamanho == 0

    def __len__(self):
        return self._tamanho


# ===== Árvore binária de busca por IP =====

class _NoArvore:
    __slots__ = ("chave", "ip", "pacotes", "bytes_enviados", "bytes_recebidos", "esquerda", "direita")

    def __init__(self, chave, ip):
        self.chave = chave
        self.ip = ip
        self.pacotes = 0
        self.bytes_enviados = 0
        self.bytes_recebidos = 0
        self.esquerda: _NoArvore | None = None
        self.direita: _NoArvore | None = None


def _chave_ip(ip):
    """Chave numérica do IP: (versão, número). IPv4 vem antes de IPv6.

    Comparar o texto daria "10.0.0.2" < "9.0.0.1"; comparando o número,
    o percurso em ordem sai na ordem numérica dos endereços.
    """
    endereco = ipaddress.ip_address(ip)
    return (endereco.version, int(endereco))


class ArvoreIP:
    """Árvore binária de busca (sem balanceamento) com chave = endereço IP.

    Cada nó acumula os pacotes e os bytes enviados (IP como origem) e
    recebidos (IP como destino).

    Busca e inserção custam O(h), h = altura da árvore:
    - em média O(log n), porque os IPs chegam em ordem variada;
    - no pior caso O(n), se os IPs chegarem já ordenados (a árvore vira uma lista).
    O percurso em ordem custa O(n).
    """

    def __init__(self):
        self._raiz: _NoArvore | None = None
        self._tamanho = 0

    def _buscar_no(self, chave):
        no = self._raiz
        while no is not None and no.chave != chave:
            no = no.esquerda if chave < no.chave else no.direita
        return no

    def _buscar_ou_inserir(self, ip):
        chave = _chave_ip(ip)
        if self._raiz is None:
            self._raiz = _NoArvore(chave, ip)
            self._tamanho += 1
            return self._raiz
        no = self._raiz
        while True:
            if chave == no.chave:
                return no
            lado = "esquerda" if chave < no.chave else "direita"
            filho = getattr(no, lado)
            if filho is None:
                filho = _NoArvore(chave, ip)
                setattr(no, lado, filho)
                self._tamanho += 1
                return filho
            no = filho

    def registrar(self, registro):
        """Soma um pacote (registro do sniffer) ao IP de origem e ao de destino."""
        if registro["ip_origem"] is None:
            return
        origem = self._buscar_ou_inserir(registro["ip_origem"])
        origem.pacotes += 1
        origem.bytes_enviados += registro["tamanho"]

        destino = self._buscar_ou_inserir(registro["ip_destino"])
        destino.pacotes += 1
        destino.bytes_recebidos += registro["tamanho"]

    def buscar(self, ip):
        """Devolve os totais de um IP (dict) ou None se ele nunca apareceu."""
        no = self._buscar_no(_chave_ip(ip))
        return _no_para_dict(no) if no else None

    def em_ordem(self):
        """Lista de dicts com os totais de cada IP, em ordem numérica de IP.

        Usa uma pilha em vez de recursão, para não estourar o limite do
        Python se a árvore ficar degenerada (muito alta).
        """
        saida = []
        pilha = []
        no = self._raiz
        while pilha or no is not None:
            while no is not None:
                pilha.append(no)
                no = no.esquerda
            no = pilha.pop()
            saida.append(_no_para_dict(no))
            no = no.direita
        return saida

    def altura(self):
        """Altura da árvore (0 = vazia). Mostra o quanto ela está desbalanceada."""
        maior = 0
        pilha = [(self._raiz, 1)] if self._raiz else []
        while pilha:
            no, nivel = pilha.pop()
            maior = max(maior, nivel)
            for filho in (no.esquerda, no.direita):
                if filho is not None:
                    pilha.append((filho, nivel + 1))
        return maior

    def __len__(self):
        return self._tamanho


def _no_para_dict(no):
    return {
        "ip": no.ip,
        "pacotes": no.pacotes,
        "bytes_enviados": no.bytes_enviados,
        "bytes_recebidos": no.bytes_recebidos,
        "bytes_total": no.bytes_enviados + no.bytes_recebidos,
    }


# ===== QuickSort =====

def quicksort(itens, chave=lambda x: x, decrescente=False):
    """Ordena a lista no próprio lugar (in-place) e a devolve.

    Pivô: elemento do meio. Partição de Hoare, que lida bem com valores
    repetidos (comum aqui: muitos IPs com o mesmo número de bytes).

    Complexidade:
    - tempo: O(n log n) em média; O(n²) no pior caso (pivô sempre o menor
      ou o maior valor). O pivô do meio evita o pior caso em listas já ordenadas;
    - memória extra: O(log n), porque a recursão vai sempre para a parte menor
      e a parte maior é tratada no laço.
    Não é estável (itens iguais podem trocar de ordem).
    """
    if decrescente:
        def antes(a, b):
            return a > b
    else:
        def antes(a, b):
            return a < b
    _quicksort(itens, 0, len(itens) - 1, chave, antes)
    return itens


def _quicksort(itens, inicio, fim, chave, antes):
    while inicio < fim:
        meio = _particionar(itens, inicio, fim, chave, antes)
        if meio - inicio < fim - meio:
            _quicksort(itens, inicio, meio, chave, antes)
            inicio = meio + 1
        else:
            _quicksort(itens, meio + 1, fim, chave, antes)
            fim = meio


def _particionar(itens, inicio, fim, chave, antes):
    """Partição de Hoare: tudo em [inicio, j] vem antes ou empata com tudo em [j+1, fim]."""
    pivo = chave(itens[(inicio + fim) // 2])
    i, j = inicio - 1, fim + 1
    while True:
        i += 1
        while antes(chave(itens[i]), pivo):
            i += 1
        j -= 1
        while antes(pivo, chave(itens[j])):
            j -= 1
        if i >= j:
            return j
        itens[i], itens[j] = itens[j], itens[i]


def top_consumidores(arvore, n):
    """Os n IPs com mais bytes (enviados + recebidos), do maior para o menor."""
    lista = arvore.em_ordem()
    quicksort(lista, chave=lambda r: r["bytes_total"], decrescente=True)
    return lista[:n]
