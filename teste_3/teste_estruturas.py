"""
Testes de estruturas.py (fila, árvore por IP e QuickSort).

Não precisa de Scapy, Npcap nem rede: usa dados inventados e compara
com o resultado das funções prontas do Python (sorted, dict).

Uso:
    python teste_estruturas.py
"""

import ipaddress
import random

from estruturas import ArvoreIP, Fila, quicksort, top_consumidores


def teste_fila():
    fila = Fila()
    assert fila.vazia() and fila.desenfileirar() is None

    for i in range(5):
        fila.enfileirar(i)
    assert len(fila) == 5
    # sai na mesma ordem em que entrou (FIFO); vazia devolve None
    assert [fila.desenfileirar() for _ in range(6)] == [0, 1, 2, 3, 4, None]

    fila.enfileirar(7)  # continua funcionando depois de esvaziar
    assert fila.desenfileirar() == 7
    assert fila.vazia() and fila.maior_tamanho == 5
    print("Fila: OK")


def teste_quicksort():
    for _ in range(3000):
        n = random.randint(0, 60)
        maximo = random.choice([3, 1000])  # 3 = muitos valores repetidos
        lista = [random.randint(0, maximo) for _ in range(n)]
        assert quicksort(lista[:]) == sorted(lista)
        assert quicksort(lista[:], decrescente=True) == sorted(lista, reverse=True)

    # lista já ordenada: com o pivô do meio não cai no pior caso nem estoura a recursão
    grande = list(range(100_000))
    assert quicksort(grande[:]) == grande
    print("QuickSort: OK (3000 listas aleatórias + 100 mil já ordenados)")


def teste_arvore():
    arvore = ArvoreIP()
    esperado = {}  # ip -> [pacotes, enviados, recebidos], calculado com dict
    ips = [f"10.0.{random.randint(0, 3)}.{random.randint(0, 255)}" for _ in range(300)]
    ips += ["8.8.8.8", "::1", "2001:db8::1"]

    for _ in range(5000):
        origem, destino = random.sample(ips, 2)
        tamanho = random.randint(60, 1500)
        arvore.registrar({"ip_origem": origem, "ip_destino": destino, "tamanho": tamanho})
        for ip in (origem, destino):
            esperado.setdefault(ip, [0, 0, 0])
        esperado[origem][0] += 1
        esperado[origem][1] += tamanho
        esperado[destino][0] += 1
        esperado[destino][2] += tamanho

    # pacote sem IP (ex: ARP) é ignorado
    arvore.registrar({"ip_origem": None, "ip_destino": None, "tamanho": 99})

    assert len(arvore) == len(esperado)
    for r in arvore.em_ordem():
        assert [r["pacotes"], r["bytes_enviados"], r["bytes_recebidos"]] == esperado[r["ip"]]

    # em ordem = ordem numérica do IP, IPv4 antes de IPv6
    def chave(ip):
        endereco = ipaddress.ip_address(ip)
        return (endereco.version, int(endereco))
    assert [r["ip"] for r in arvore.em_ordem()] == sorted(esperado, key=chave)

    assert arvore.buscar("1.2.3.4") is None
    google = arvore.buscar("8.8.8.8")
    assert google is not None and google["pacotes"] == esperado["8.8.8.8"][0]

    top = top_consumidores(arvore, 5)
    totais = sorted((e[1] + e[2] for e in esperado.values()), reverse=True)
    assert [t["bytes_total"] for t in top] == totais[:5]
    print(f"Árvore: OK ({len(arvore)} IPs, altura {arvore.altura()})")


def teste_arvore_degenerada():
    """IPs chegando em ordem: pior caso, a árvore vira uma lista (altura = n)."""
    arvore = ArvoreIP()
    for i in range(5000):
        arvore.registrar({
            "ip_origem": str(ipaddress.ip_address(i)),
            "ip_destino": str(ipaddress.ip_address(i + 1)),
            "tamanho": 1,
        })
    assert len(arvore.em_ordem()) == 5001
    print(f"Árvore degenerada: OK (5001 IPs, altura {arvore.altura()})")


if __name__ == "__main__":
    teste_fila()
    teste_quicksort()
    teste_arvore()
    teste_arvore_degenerada()
    print("\nTodos os testes passaram.")
