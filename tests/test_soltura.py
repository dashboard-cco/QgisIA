# -*- coding: utf-8 -*-
"""Testes da alocação de veículos da planilha de soltura.

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_soltura.py
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "src", "qgis_ia"))
sys.path.insert(0, os.path.join(AQUI, "..", "src", "qgis_ia", "actions"))
import soltura as S  # noqa: E402

FALHAS = []


def _alocar_n(*a, **k):
    return S._alocar(*a, **k)[0]


S._alocar_n = _alocar_n


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


def circ(cod, dias, ini, fim, turno, equip=0):
    return {"codigo": cod, "dias": dias, "ini": ini, "fim": fim, "turno": turno, "equip": equip}


SQS = [1, 0, 1, 0, 1, 0, 0]
TQS = [0, 1, 0, 1, 0, 1, 0]
DIA = [1, 1, 1, 1, 1, 1, 0]
D = (7 * 60, 15 * 60 + 20)
N = (19 * 60, 3 * 60 + 20)

# dias alternados no mesmo horário: 1 veículo
v = S._alocar_n([circ(1, SQS, *D, "Diurno"), circ(2, TQS, *D, "Diurno")], 60, True)
check(len(v) == 1, "SQS + TQS dividem o veículo")
# mesmo dia e horário: 2 veículos
v = S._alocar_n([circ(1, SQS, *D, "Diurno"), circ(2, SQS, *D, "Diurno")], 60, True)
check(len(v) == 2, "mesmo dia e horário não dividem")
# diurno + noturno no mesmo veículo só se permitido
c = [circ(1, DIA, *D, "Diurno"), circ(2, DIA, *N, "Noturno")]
check(len(S._alocar_n(c, 60, True)) == 1, "diurno + noturno no mesmo veículo")
check(len(S._alocar_n(c, 60, False)) == 2, "um turno por veículo")
# noturno que passa da meia-noite conflita com diurno que começa cedo demais
c = [circ(1, DIA, *N, "Noturno"), circ(2, DIA, 3 * 60 + 30, 11 * 60, "Diurno")]
check(len(S._alocar_n(c, 60, True)) == 2, "respeita folga após a meia-noite")
# tipos de equipamento diferentes não dividem
v = S._alocar_n([circ(1, SQS, *D, "Diurno", 0), circ(2, TQS, *D, "Diurno", 1)], 60, True)
check(len(v) == 2, "equipamentos diferentes")
# domingo à noite invade a segunda de manhã
dom = [0, 0, 0, 0, 0, 0, 1]
seg = [1, 0, 0, 0, 0, 0, 0]
c = [circ(1, dom, 22 * 60, 6 * 60, "Noturno"), circ(2, seg, 6 * 60 + 30, 12 * 60, "Diurno")]
check(len(S._alocar_n(c, 60, True)) == 2, "virada da semana")

# frota fixa do edital: 2 diurno / 1 noturno (o noturno é o 1º veículo do diurno)
lim = {0: {"Diurno": 2, "Noturno": 1}}
c = [circ(1, DIA, *N, "Noturno"), circ(2, DIA, *N, "Noturno"),
     circ(3, DIA, *D, "Diurno"), circ(4, DIA, *D, "Diurno"), circ(5, DIA, *D, "Diurno")]
v, sem = S._alocar(c, 60, True, lim)
check(len(v) == 2, "frota fixa: 2 veículos")
check(sorted(x["codigo"] for x in sem) == [2, 5], f"sobram 1 noturno e 1 diurno ({[x['codigo'] for x in sem]})")
check(v[0]["turnos"] == {"Diurno", "Noturno"} and v[1]["turnos"] == {"Diurno"},
      "1º veículo faz os dois turnos; 2º só diurno")
# sem dois turnos: n + m veículos distintos
v, sem = S._alocar(c, 60, False, lim)
check(len(v) == 3 and len(sem) == 2, "frota fixa sem dois turnos: 3 veículos")
# veículo sem circuito fica como reserva
v, sem = S._alocar([circ(1, SQS, *D, "Diurno")], 60, True, {0: {"Diurno": 3, "Noturno": 0}})
check(len(v) == 3 and sum(1 for x in v if not x["circuitos"]) == 2 and not sem, "reservas")

print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)

