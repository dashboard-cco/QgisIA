# -*- coding: utf-8 -*-
"""
Planilha de soltura: qual veículo sai para qual circuito, em cada dia e turno.

A frota é dimensionada a partir dos circuitos do .gdb (quando não há lista de
placas): cada circuito recebe um veículo fixo do seu tipo de equipamento; um
veículo só assume outro circuito se não houver sobreposição de horário em nenhum
dos dias (com um intervalo mínimo entre eles). Os veículos recebem códigos
sequenciais (VA01, VA02...). As placas são digitadas uma vez na aba Frota e
aparecem na soltura por fórmula.
"""
import os
import re
from collections import Counter, defaultdict

from osgeo import gdal

try:
    from .. import edital_slu as E
    from . import slu
except ImportError:
    import edital_slu as E
    import slu

SEMANA = 7 * 1440


def _min(v):
    m = re.search(r"(\d{1,2}):(\d{2})", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _hhmm(m):
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _intervalos(dias, ini, fim, folga):
    """Intervalos ocupados na semana (minutos), com a folga no fim."""
    dur = (fim - ini) % 1440 or 1440
    out = []
    for d, ativo in enumerate(dias):
        if ativo:
            a = d * 1440 + ini
            b = a + dur + folga
            if b <= SEMANA:
                out.append((a, b))
            else:  # domingo à noite invade a segunda
                out.append((a, SEMANA))
                out.append((0, b - SEMANA))
    return out


def _conflita(ocupado, novos):
    return any(a < d and c < b for a, b in novos for c, d in ocupado)


def _alocar(circuitos, folga, dois_turnos, limites=None):
    """First-fit por tipo de equipamento. Devolve (veiculos, sem_veiculo).

    Sem 'limites', cria quantos veículos forem precisos. Com 'limites'
    ({tipo: {"Diurno": n, "Noturno": m}}, a frota do edital), a frota é fixa: com
    dois_turnos os m veículos do noturno são os mesmos n do diurno (os primeiros m);
    sem dois_turnos são n + m veículos distintos. O que não cabe vai para sem_veiculo.
    """
    veiculos = []  # {"tipo", "ocupado", "circuitos", "turnos", "pode": set(turnos)}
    sem_veiculo = []
    if limites:
        for tipo, lim in sorted(limites.items()):
            n, m = int(lim.get("Diurno", 0)), int(lim.get("Noturno", 0))
            if dois_turnos:
                for k in range(max(n, m)):
                    pode = ({"Diurno"} if k < n else set()) | ({"Noturno"} if k < m else set())
                    veiculos.append({"tipo": tipo, "ocupado": [], "circuitos": [],
                                     "turnos": set(), "pode": pode})
            else:
                veiculos += [{"tipo": tipo, "ocupado": [], "circuitos": [], "turnos": set(),
                              "pode": {"Diurno"}} for _ in range(n)]
                veiculos += [{"tipo": tipo, "ocupado": [], "circuitos": [], "turnos": set(),
                              "pode": {"Noturno"}} for _ in range(m)]
    # noturno primeiro quando a frota é fixa: é o turno com menos veículos
    ordem = sorted(circuitos, key=lambda c: (c["equip"],
                                             0 if (limites and c["turno"] == "Noturno") else 1,
                                             -sum(c["dias"]), c["ini"], c["codigo"]))
    for c in ordem:
        iv = _intervalos(c["dias"], c["ini"], c["fim"], folga)
        escolhido = None
        for v in veiculos:
            if v["tipo"] != c["equip"]:
                continue
            if "pode" in v and c["turno"] not in v["pode"]:
                continue
            if not dois_turnos and v["turnos"] and c["turno"] not in v["turnos"]:
                continue
            if not _conflita(v["ocupado"], iv):
                escolhido = v
                break
        if escolhido is None:
            if limites:
                sem_veiculo.append(c)
                continue
            escolhido = {"tipo": c["equip"], "ocupado": [], "circuitos": [], "turnos": set()}
            veiculos.append(escolhido)
        escolhido["ocupado"].extend(iv)
        escolhido["circuitos"].append(c)
        escolhido["turnos"].add(c["turno"])
    return veiculos, sem_veiculo


def _ler_circuitos(gdb_path):
    ds = gdal.OpenEx(gdb_path, gdal.OF_VECTOR)
    if ds is None:
        raise ValueError(f"Não abri {gdb_path}")
    km = defaultdict(lambda: [0.0, 0.0])
    ll = ds.GetLayerByName("st_circuito_planejado")
    if ll is not None:
        for f in ll:
            g = f.GetGeometryRef()
            if g is not None:
                km[f.GetField("codigo_circuito")][1 if f.GetField("deslocamento") == 1 else 0] \
                    += g.Length() / 1000
    out, sem_horario = [], []
    for f in ds.GetLayerByName("lm_area_circuito_planejado"):
        cod = f.GetField("codigo_circuito")
        ini, fim = _min(f.GetField("horario_inicio")), _min(f.GetField("horario_termino"))
        dias = [int(f.GetField(d) or 0) for d in E.DIAS_CAMPOS]
        if ini is None or fim is None or not any(dias):
            sem_horario.append(cod)
            continue
        ra = f.GetField("codigo_ra")
        out.append({
            "codigo": cod, "nome": f.GetField("nome_circuito"), "ra": E.RA.get(ra, ra),
            "dias": dias, "ini": ini, "fim": fim,
            "turno": f.GetField("turno") or ("Noturno" if ini >= 18 * 60 else "Diurno"),
            "equip": f.GetField("id_tipo_equipamento"),
            "frequencia": f.GetField("frequencia"),
            "destino": f.GetField("local_destinacao"), "pesagem": f.GetField("local_pesagem"),
            "km_coleta": round(km[cod][0], 1), "km_passagem": round(km[cod][1], 1),
            "tipo_servico": E.TIPO_SERVICO_DESC.get(f.GetField("id_tipo_servico")),
        })
    return out, sem_horario


def slu_planilha_soltura(gdb_path, saida_xlsx, intervalo_min=60, dois_turnos=True,
                         servico=None, lote=None, prefixo_veiculo="VA", frota="edital"):
    """Gera a planilha de soltura (.xlsx) do plano: soltura por dia/turno, frota
    (aba Frota, com placas a preencher), grade semanal por veículo, resumo de
    veículos por dia/turno (necessário x edital) e a lista de circuitos.

    frota="edital" usa a frota do Anexo R do lote (VA01... na ordem do edital) e marca
    "SEM VEÍCULO" o que não couber; frota="dimensionar" cria quantos veículos forem
    precisos; ou um dict {codigo_equipamento: {"Diurno": n, "Noturno": m}}."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    servico, lote = slu._servico_lote_de_gdb(gdb_path, servico, lote)
    prefixo = E.lote_codigo(servico, lote)
    circuitos, sem_horario = _ler_circuitos(gdb_path)
    if frota == "edital":
        limites = E.FROTA_ANEXO_R.get((servico, lote))
        if limites is None:
            raise ValueError(f"Sem frota do Anexo R cadastrada para {servico} lote {lote}; "
                             "use frota='dimensionar' ou informe um dict.")
    elif frota in (None, "dimensionar"):
        limites = None
    else:
        limites = {int(k): v for k, v in dict(frota).items()}
    veiculos, sem_veiculo = _alocar(circuitos, int(intervalo_min), bool(dois_turnos), limites)
    necessario, _ = _alocar(circuitos, int(intervalo_min), bool(dois_turnos))
    por_tipo = Counter(v["tipo"] for v in veiculos)
    if limites:
        ordem_v = veiculos  # ordem do edital: os primeiros fazem diurno e noturno
    else:
        ordem_v = sorted(veiculos, key=lambda v: (v["tipo"],
                                                  min(c["ini"] for c in v["circuitos"]),
                                                  min(c["codigo"] for c in v["circuitos"])))
    for n, v in enumerate(ordem_v, start=1):
        v["id"] = f"{prefixo_veiculo}{n:02d}"
        for c in v["circuitos"]:
            c["veiculo"] = v["id"]
    for c in sem_veiculo:
        c["veiculo"] = "SEM VEÍCULO"

    wb = Workbook()
    azul = PatternFill("solid", fgColor="1F4E78")
    claro = PatternFill("solid", fgColor="DDEBF7")
    noite = PatternFill("solid", fgColor="E7E6F7")
    amarelo = PatternFill("solid", fgColor="FFF2CC")
    vermelho = PatternFill("solid", fgColor="F8CBAD")
    fino = Side(style="thin", color="A6A6A6")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def cabecalho(ws, linha, colunas, larguras):
        for i, (t, w) in enumerate(zip(colunas, larguras), start=1):
            c = ws.cell(linha, i, t)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = azul
            c.alignment = centro
            c.border = borda
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = ws.cell(linha + 1, 1)

    titulo = (f"Planilha de Soltura — {servico} {E.SERVICOS[servico]['nome']} — "
              f"{prefixo} (Lote {lote:02d})")

    # ------------------------------------------------------------ Soltura
    ws = wb.active
    ws.title = "Soltura"
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = ("Placa vem da aba Frota. Motorista e coletores: preencher. Horários do plano "
                "de serviço (.gdb).")
    ws["A2"].font = Font(italic=True, color="595959")
    cols = ["Dia", "Turno", "Saída (início)", "Término", "Veículo", "Placa", "Equipamento",
            "Código Circuito", "Nome do Circuito", "RA", "Tipo de Serviço", "Frequência",
            "Km coleta", "Km passagem", "Destinação", "Pesagem", "Motorista", "Coletores",
            "Observação"]
    cabecalho(ws, 4, cols, (11, 9, 9, 9, 13, 11, 30, 11, 30, 18, 30, 26, 9, 9, 24, 24, 20, 24, 24))
    lin = 5
    contagem = defaultdict(Counter)  # (dia, turno) -> tipo -> nº veículos
    for d, nome_dia in enumerate(E.DIAS_NOMES):
        do_dia = [c for c in circuitos if c["dias"][d]]
        do_dia.sort(key=lambda c: (0 if c["turno"] == "Diurno" else 1, c["ini"], c["veiculo"]))
        for c in do_dia:
            contagem[(nome_dia, c["turno"])][c["equip"]] += 1
            vals = [nome_dia, c["turno"], _hhmm(c["ini"]), _hhmm(c["fim"]), c["veiculo"],
                    f'=IFERROR(IF(VLOOKUP(E{lin},Frota!$A:$D,4,FALSE)="","",'
                    f'VLOOKUP(E{lin},Frota!$A:$D,4,FALSE)),"")',
                    E.EQUIPAMENTOS.get(c["equip"], c["equip"]), c["codigo"], c["nome"], c["ra"],
                    c["tipo_servico"], c["frequencia"], c["km_coleta"], c["km_passagem"],
                    c["destino"], c["pesagem"], None, None, None]
            if c["veiculo"] == "SEM VEÍCULO":
                vals[5] = None
                vals[18] = "Sem veículo na frota do Anexo R para este dia/turno"
            for i, v in enumerate(vals, start=1):
                cel = ws.cell(lin, i, v)
                cel.border = borda
                if c["veiculo"] == "SEM VEÍCULO":
                    cel.fill = vermelho
                elif c["turno"] == "Noturno":
                    cel.fill = noite
            if c["veiculo"] != "SEM VEÍCULO":
                for i in (17, 18, 19):
                    ws.cell(lin, i).fill = amarelo
            lin += 1
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{lin - 1}"

    # ------------------------------------------------------------ Frota
    wf = wb.create_sheet("Frota")
    wf["A1"] = (f"Frota do Anexo R — {prefixo}" if limites else f"Frota dimensionada — {prefixo}")
    wf["A1"].font = Font(bold=True, size=13)
    wf["A2"] = "Preencha a coluna Placa (amarela); ela aparece automaticamente na Soltura."
    wf["A2"].font = Font(italic=True, color="595959")
    cabecalho(wf, 4, ["Veículo", "Código Equip.", "Equipamento", "Placa", "Nº circuitos",
                      "Turnos em uso", "Circuitos", "Km coleta/semana", "Turnos no edital"],
              (13, 9, 34, 12, 10, 16, 60, 14, 16))
    for r, v in enumerate(ordem_v, start=5):
        kms = sum(c["km_coleta"] * sum(c["dias"]) for c in v["circuitos"])
        vals = [v["id"], v["tipo"], E.EQUIPAMENTOS.get(v["tipo"], v["tipo"]), None,
                len(v["circuitos"]),
                " e ".join(sorted(v["turnos"])) or "Reserva (sem circuito)",
                ", ".join(f"{c['codigo']} ({c['turno'][0]} {''.join(E.DIAS_INICIAL[i] for i, a in enumerate(c['dias']) if a)})"
                          for c in sorted(v["circuitos"], key=lambda c: c["ini"])),
                round(kms, 1), " e ".join(sorted(v.get("pode", v["turnos"])))]
        for i, val in enumerate(vals, start=1):
            cel = wf.cell(r, i, val)
            cel.border = borda
        wf.cell(r, 4).fill = amarelo

    # ------------------------------------------------------------ Grade semanal
    wg = wb.create_sheet("Grade semanal")
    wg["A1"] = "Circuito de cada veículo por dia e turno (D = diurno, N = noturno)"
    wg["A1"].font = Font(bold=True, size=13)
    cab = ["Veículo", "Placa"] + [f"{dn[:3]} {t}" for dn in E.DIAS_NOMES for t in ("D", "N")]
    cabecalho(wg, 3, cab, [13, 11] + [9] * 14)
    for r, v in enumerate(ordem_v, start=4):
        wg.cell(r, 1, v["id"]).border = borda
        cel = wg.cell(r, 2, f'=IFERROR(IF(VLOOKUP(A{r},Frota!$A:$D,4,FALSE)="","",'
                            f'VLOOKUP(A{r},Frota!$A:$D,4,FALSE)),"")')
        cel.border = borda
        for d in range(7):
            for k, t in enumerate(("Diurno", "Noturno")):
                cods = [str(c["codigo"]) for c in v["circuitos"] if c["dias"][d] and c["turno"] == t]
                cel = wg.cell(r, 3 + d * 2 + k, "\n".join(cods) or None)
                cel.border = borda
                cel.alignment = centro
                if cods:
                    cel.fill = claro if t == "Diurno" else noite

    # ------------------------------------------------------------ Resumo
    wr = wb.create_sheet("Resumo")
    wr["A1"] = titulo
    wr["A1"].font = Font(bold=True, size=13)
    tipos = sorted({c["equip"] for c in circuitos} | set(limites or {}))
    cab = ["Dia", "Turno"]
    for t in tipos:
        nome = E.EQUIPAMENTOS.get(t, t)
        cab += [f"{nome} — circuitos", f"{nome} — edital"] if limites else [nome]
    cabecalho(wr, 3, cab, [12, 10] + [22] * (len(cab) - 2))
    r = 4
    falta_total = 0
    for dn in E.DIAS_NOMES:
        for t in ("Diurno", "Noturno"):
            cnt = contagem.get((dn, t), Counter())
            if not cnt:
                continue
            vals = [dn, t]
            for k in tipos:
                vals.append(cnt.get(k, 0))
                if limites:
                    vals.append(limites.get(k, {}).get(t, 0))
            for i, val in enumerate(vals, start=1):
                wr.cell(r, i, val).border = borda
            if limites:
                for j, k in enumerate(tipos):
                    col = 3 + 2 * j
                    if cnt.get(k, 0) > limites.get(k, {}).get(t, 0):
                        wr.cell(r, col).fill = vermelho
                        falta_total += 1
            r += 1
    r += 1
    wr.cell(r, 1, "Frota" + (" do Anexo R (em uso / total)" if limites else " necessária")) \
        .font = Font(bold=True)
    r += 1
    for t in tipos:
        wr.cell(r, 1, E.EQUIPAMENTOS.get(t, t))
        usados = sum(1 for v in veiculos if v["tipo"] == t and v["circuitos"])
        wr.cell(r, 3, f"{usados} / {por_tipo.get(t, 0)}" if limites else por_tipo.get(t, 0))
        r += 1
    if limites:
        r += 1
        wr.cell(r, 1, "Circuitos sem veículo (por semana)").font = Font(bold=True)
        wr.cell(r, 3, len(sem_veiculo))
        r += 1
        wr.cell(r, 1, "Frota que os circuitos atuais exigiriam (sem limite)")
        wr.cell(r, 3, len(necessario))
        r += 1
    r += 1
    wr.cell(r, 1, f"Intervalo mínimo entre circuitos do mesmo veículo: {intervalo_min} min. "
                  + ("Veículos do noturno são os primeiros do diurno (mesmo caminhão, outra "
                     "guarnição)." if dois_turnos else "Cada veículo faz um só turno."))
    wr.cell(r, 1).font = Font(italic=True, color="595959")
    wr.column_dimensions["A"].width = 44

    # ------------------------------------------------------------ Circuitos
    wc = wb.create_sheet("Circuitos")
    cabecalho(wc, 1, ["Código Circuito", "Nome do Circuito", "Veículo", "Turno", "Início",
                      "Término", "Frequência", "Equipamento", "Km coleta", "Km passagem"],
              (11, 32, 13, 9, 8, 8, 30, 32, 9, 9))
    for r, c in enumerate(sorted(circuitos, key=lambda c: c["codigo"]), start=2):
        vals = [c["codigo"], c["nome"], c["veiculo"], c["turno"], _hhmm(c["ini"]),
                _hhmm(c["fim"]), c["frequencia"], E.EQUIPAMENTOS.get(c["equip"], c["equip"]),
                c["km_coleta"], c["km_passagem"]]
        for i, val in enumerate(vals, start=1):
            wc.cell(r, i, val).border = borda
    wc.auto_filter.ref = f"A1:J{len(circuitos) + 1}"

    os.makedirs(os.path.dirname(os.path.abspath(saida_xlsx)), exist_ok=True)
    wb.save(saida_xlsx)
    pico = max(contagem.items(), key=lambda kv: sum(kv[1].values())) if contagem else None
    return {
        "success": True, "xlsx": saida_xlsx, "circuitos": len(circuitos),
        "frota_usada": "Anexo R" if limites else "dimensionada",
        "circuitos_sem_horario_ou_dias": sem_horario,
        "frota": {E.EQUIPAMENTOS.get(t, t): n for t, n in sorted(por_tipo.items())},
        "frota_total": len(veiculos),
        "veiculos_reserva": [v["id"] for v in veiculos if not v["circuitos"]],
        "frota_que_os_circuitos_exigem": len(necessario),
        "circuitos_sem_veiculo": [{"codigo": c["codigo"], "nome": c["nome"], "turno": c["turno"],
                                   "equipamento": E.EQUIPAMENTOS.get(c["equip"], c["equip"])}
                                  for c in sorted(sem_veiculo, key=lambda c: c["codigo"])],
        "pico": {"dia_turno": f"{pico[0][0]} {pico[0][1]}",
                 "veiculos": sum(pico[1].values())} if pico else None,
        "linhas_soltura": lin - 5,
    }


TOOLS = {"slu_planilha_soltura": slu_planilha_soltura}
