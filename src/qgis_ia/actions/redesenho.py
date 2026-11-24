# -*- coding: utf-8 -*-
"""
Redesenho de um Plano de Coleta (P1/P2) existente sobre a rede viária, no padrão
do Anexo G e com os lotes do novo edital.

Para cada circuito do .gdb atual:
  1. traduz as linhas de coleta atuais para trechos da rede (ArquivoRua);
  2. descarta o que ficou fora do lote (Quadro 01 do edital / camada de RAs);
  3. calcula a rota na rede (cobrindo todos os trechos de coleta, respeitando mão
     única se pedido) — o que o veículo só atravessa vira "via de passagem";
  4. corta as linhas em 50-130 m (quebrando só fora dos cruzamentos);
  5. refaz polígono, pontos de início/fim, Código RA, Nome do Circuito e
     Endereçamento (a partir da camada de vias com endereço).
Grava um .gdb novo (o atual não é alterado), um GeoPackage de pendências e
roda a validação do Anexo G.

Só usa osgeo, shapely e networkx (todos no Python do QGIS).
"""
import datetime as _dt
import heapq
import math
import os
import re
from collections import Counter, defaultdict

from osgeo import gdal, ogr, osr
import shapely
from shapely import wkb as swkb
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point
from shapely.ops import linemerge, substring, unary_union
from shapely.strtree import STRtree

try:
    from .. import edital_slu as E
    from . import slu
except ImportError:  # testes fora do pacote
    import edital_slu as E
    import slu

LIN_MAX = 130.0          # coleta: linhas de 50 a 130 m (item 4.2.1.3)
LIN_MIN = 50.0
TOL_NO = 0.1             # arredondamento para casar extremidades da rede (m)
BUF_MAPA = 3.0           # tolerância para casar linhas atuais com a rede (m)
FRACAO_MIN = 0.5         # fração do trecho coberta pela linha atual para contar
SEM_NOME = {"via sem nome", "", None}


# ======================================================================= leitura
def _abrir(path, restaurar_shx=False):
    if restaurar_shx:
        gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
    try:
        ds = gdal.OpenEx(path, gdal.OF_VECTOR)
    finally:
        if restaurar_shx:
            gdal.SetConfigOption("SHAPE_RESTORE_SHX", None)
    if ds is None:
        dica = ""
        if path.lower().endswith(".shp") and not os.path.exists(path[:-4] + ".shx"):
            dica = (" Falta o arquivo .shx do shapefile; copie-o para a pasta ou use "
                    "restaurar_shx=true (o GDAL recria o .shx ao lado do .shp).")
        raise ValueError(f"Não consegui abrir {path}.{dica}")
    return ds


def _ler(path, camada=None, campos=(), restaurar_shx=False):
    """Lista de (geometria shapely 2D, {campo: valor}). Converte curvas em retas."""
    ds = _abrir(path, restaurar_shx)
    lyr = ds.GetLayerByName(camada) if camada else ds.GetLayer(0)
    if lyr is None:
        raise ValueError(f"Camada '{camada}' não encontrada em {path}")
    nomes = {lyr.GetLayerDefn().GetFieldDefn(i).GetName().lower():
             lyr.GetLayerDefn().GetFieldDefn(i).GetName()
             for i in range(lyr.GetLayerDefn().GetFieldCount())}
    out = []
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        g = g.GetLinearGeometry()
        g.FlattenTo2D()
        attrs = {}
        for c in campos:
            real = nomes.get(c.lower())
            attrs[c] = f.GetField(real) if real and f.IsFieldSetAndNotNull(real) else None
        attrs["_fid"] = f.GetFID()
        out.append((swkb.loads(bytes(g.ExportToWkb())), attrs))
    return out


def _linhas(g):
    if g.geom_type == "LineString":
        return [g]
    if g.geom_type == "MultiLineString":
        return list(g.geoms)
    return []


# ========================================================================= rede
class Rede:
    """Grafo dirigido da malha viária com índice espacial."""

    def __init__(self, rede_path, rede_camada, sentidos_path=None, respeitar_sentido=True,
                 vias_endereco=None, restaurar_shx=False, campo_sentido="sentido_proposto"):
        bruto = _ler(rede_path, rede_camada, ("ID", "compriment"))
        sentido = {}
        if sentidos_path and respeitar_sentido:
            # FT/TF = mão única em relação ao desenho do trecho; demais = mão dupla
            for _, a in _ler(sentidos_path, None, ("ID", campo_sentido)):
                if a["ID"] is not None:
                    sentido[a["ID"]] = a[campo_sentido]
        self.geom, self.u, self.v, self.comp, self.sent = [], [], [], [], []
        self.no_xy = {}
        nos = {}

        def no(p):
            k = (round(p[0] / TOL_NO), round(p[1] / TOL_NO))
            if k not in nos:
                nos[k] = len(nos)
                self.no_xy[nos[k]] = (p[0], p[1])
            return nos[k]

        for g, a in bruto:
            partes = _linhas(g)
            if not partes:
                continue
            ln = partes[0] if len(partes) == 1 else linemerge(partes)
            if ln.geom_type != "LineString":
                ln = LineString([c for p in partes for c in p.coords])
            self.geom.append(ln)
            self.u.append(no(ln.coords[0]))
            self.v.append(no(ln.coords[-1]))
            self.comp.append(ln.length)
            s = sentido.get(a["ID"], "B")
            self.sent.append(s if s in ("FT", "TF") else "B")
        self.n = len(self.geom)
        self.grau = Counter(self.u) + Counter(self.v)
        # adjacência: no -> [(vizinho, custo, idx_trecho, direcao)] ; direcao 1 = u->v
        self.adj = defaultdict(list)    # na mão
        self.radj = defaultdict(list)   # na mão, invertida (para chegar a um nó)
        self.uadj = defaultdict(list)   # ignorando a mão
        for i in range(self.n):
            u, v, c = self.u[i], self.v[i], self.comp[i]
            if self.sent[i] in ("B", "FT"):
                self.adj[u].append((v, c, i, 1))
                self.radj[v].append((u, c, i, 1))
            if self.sent[i] in ("B", "TF"):
                self.adj[v].append((u, c, i, -1))
                self.radj[u].append((v, c, i, -1))
            self.uadj[u].append((v, c, i, 1))
            self.uadj[v].append((u, c, i, -1))
        self.arvore = STRtree(self.geom)
        self.mid = [g.interpolate(0.5, normalized=True) for g in self.geom]
        self.endereco = [None] * self.n
        self.legenda = [None] * self.n
        if vias_endereco:
            self._juntar_enderecos(vias_endereco, restaurar_shx)

    def _juntar_enderecos(self, path, restaurar_shx):
        vias = _ler(path, None, ("Endereco", "legenda"), restaurar_shx)
        arv = STRtree([g for g, _ in vias])
        idx_rede, idx_via = arv.query_nearest(self.mid, max_distance=5.0, all_matches=False)
        for i, j in zip(idx_rede, idx_via):
            self.endereco[i] = vias[j][1]["Endereco"]
            self.legenda[i] = vias[j][1]["legenda"]

    def no_mais_proximo(self, p, candidatos):
        melhor, dmin = None, float("inf")
        for n in candidatos:
            x, y = self.no_xy[n]
            d = (x - p.x) ** 2 + (y - p.y) ** 2
            if d < dmin:
                melhor, dmin = n, d
        return melhor

    def trechos_cobertos(self, linhas):
        """Trechos da rede cobertos (>= FRACAO_MIN) pelas linhas informadas."""
        if not linhas:
            return set()
        area = unary_union([ln.buffer(BUF_MAPA, cap_style="flat") for ln in linhas])
        cand = self.arvore.query(area, predicate="intersects")
        out = set()
        for i in cand:
            g = self.geom[i]
            if g.length == 0:
                continue
            if g.intersection(area).length >= FRACAO_MIN * g.length:
                out.add(int(i))
        return out


# ============================================================ vias de passagem
def _arcos(rede, idx, liberados=()):
    """Arcos (origem, destino) permitidos para o trecho."""
    s = "B" if idx in liberados else rede.sent[idx]
    out = []
    if s in ("B", "FT"):
        out.append((rede.u[idx], rede.v[idx]))
    if s in ("B", "TF"):
        out.append((rede.v[idx], rede.u[idx]))
    return out


def _caminho(rede, origens, alvos, reverso=False, dirigido=True, limite=15000.0):
    """Dijkstra multi-origem até o primeiro nó de 'alvos'. Devolve lista de trechos."""
    adj = rede.radj if reverso else rede.adj
    if not dirigido:
        adj = rede.uadj
    dist, ant, fila = {}, {}, []
    for o in origens:
        dist[o] = 0.0
        fila.append((0.0, o))
    heapq.heapify(fila)
    while fila:
        d, n = heapq.heappop(fila)
        if d > dist.get(n, float("inf")):
            continue
        if n in alvos:
            trechos = []
            while n in ant:
                n, idx = ant[n]
                trechos.append(idx)
            return trechos
        if d > limite:
            break
        for viz, custo, idx, _ in adj[n]:
            nd = d + custo
            if nd < dist.get(viz, float("inf")):
                dist[viz] = nd
                ant[viz] = (n, idx)
                heapq.heappush(fila, (nd, viz))
    return None


def _vias_de_passagem(rede, req):
    """Trechos de passagem mínimos para que o caminhão consiga ir e voltar entre
    todas as partes do circuito (componente fortemente conexo), respeitando a mão.
    Devolve (passagem, n_contramao)."""
    import networkx as nx
    passagem = set()
    liberados = set()   # trechos usados na contramão (sem caminho respeitando a mão)
    for _ in range(200):
        G = nx.DiGraph()
        for i in req | passagem:
            G.add_edges_from(_arcos(rede, i, liberados))
            G.add_nodes_from((rede.u[i], rede.v[i]))
        comps = list(nx.strongly_connected_components(G))
        if len(comps) <= 1:
            break
        C = nx.condensation(G, comps)
        mudou = False
        for c in C.nodes:
            membros = C.nodes[c]["members"]
            outros = set(G.nodes) - membros
            for reverso, grau in ((False, C.out_degree(c)), (True, C.in_degree(c))):
                if grau:
                    continue
                trechos = _caminho(rede, membros, outros, reverso=reverso)
                if trechos is None:
                    trechos = _caminho(rede, membros, outros, dirigido=False)
                    if trechos and not set(trechos) <= liberados:
                        liberados |= set(trechos)
                        mudou = True
                if trechos:
                    novos = set(trechos) - req - passagem
                    if novos:
                        passagem |= novos
                        mudou = True
        if not mudou:
            break
    return passagem, liberados


def _ordem_bfs(rede, req, inicio):
    """Trechos de coleta em ordem de proximidade (pela rede) a partir do início;
    usada para ordenar o Endereçamento."""
    por_no = defaultdict(list)
    for i in req:
        por_no[rede.u[i]].append(i)
        por_no[rede.v[i]].append(i)
    vistos, ordem, fila = set(), [], [inicio]
    nos_vistos = {inicio}
    while fila or len(vistos) < len(req):
        if not fila:  # parte desconectada: recomeça pelo trecho restante mais baixo
            resto = min(set(req) - vistos)
            fila = [rede.u[resto]]
            nos_vistos.add(rede.u[resto])
        n = fila.pop(0)
        for i in sorted(por_no[n]):
            if i in vistos:
                continue
            vistos.add(i)
            ordem.append(i)
            outro = rede.v[i] if rede.u[i] == n else rede.u[i]
            if outro not in nos_vistos:
                nos_vistos.add(outro)
                fila.append(outro)
    return ordem


# ================================================================= segmentação
def _segmentar(rede, trechos, desloc):
    """Junta trechos em nós de passagem (grau 2) e corta em pedaços <= 130 m.

    trechos: {idx: deslocamento}. Devolve [(LineString, deslocamento, [idx...])].
    """
    por_no = defaultdict(list)
    for i in trechos:
        por_no[rede.u[i]].append(i)
        por_no[rede.v[i]].append(i)

    def emendavel(n):
        ts = por_no[n]
        return len(ts) == 2 and rede.grau[n] == 2 and desloc[ts[0]] == desloc[ts[1]] \
            and ts[0] != ts[1]

    visto = set()
    cadeias = []
    for i in trechos:
        if i in visto:
            continue
        cadeia = [i]
        visto.add(i)
        for ponta in (rede.u[i], rede.v[i]):
            n, ultimo = ponta, i
            while emendavel(n):
                prox = [t for t in por_no[n] if t != ultimo][0]
                if prox in visto:
                    break
                visto.add(prox)
                cadeia.append(prox)
                n = rede.v[prox] if rede.u[prox] == n else rede.u[prox]
                ultimo = prox
        cadeias.append(cadeia)

    out = []
    for cadeia in cadeias:
        g = linemerge([rede.geom[t] for t in cadeia])
        partes = [g] if g.geom_type == "LineString" else list(g.geoms)
        for ln in partes:
            n = max(1, math.ceil(ln.length / LIN_MAX - 1e-9))
            passo = ln.length / n
            for k in range(n):
                pedaco = substring(ln, k * passo, (k + 1) * passo)
                out.append((pedaco, desloc[cadeia[0]], cadeia))
    return out


# ============================================================ ajuste à frota
def _chave_frota(d):
    pa = d["pa"]
    return pa["id_tipo_equipamento"], pa["turno"]


def _juntar(destino, origem, dados):
    destino["req"] |= origem["req"]
    destino["cts"] += origem["cts"]
    destino["pg"] = unary_union([destino["pg"].buffer(0), origem["pg"].buffer(0)])
    if 0 in origem["pts"]:
        destino["pts"][0] = origem["pts"][0]   # termina onde o segundo terminava
    destino["km"] += origem["km"]
    destino["fundidos"] += [origem["cod"]] + origem["fundidos"]
    dados.remove(origem)


def _planejar_fusoes(dados, limites, distancia, entre_ras=False):
    """Junta circuitos inteiros até que, em cada dia, o nº de circuitos de cada
    turno/equipamento caiba na frota do edital. Só junta circuitos com os mesmos
    dias, horário, turno, equipamento e RA (no Plano Piloto, a mesma Asa), vizinhos
    até 'distancia'; sempre o par de menor km somado (equilibra a carga).
    entre_ras=True permite, em último caso, juntar circuitos vizinhos de RAs diferentes.
    Devolve ([(cod_destino, cod_origem)], [descrição do que não coube])."""
    fusoes = []

    def excesso():
        cont = Counter()
        for d in dados:
            eq, t = _chave_frota(d)
            for i, nome in enumerate(E.DIAS_CAMPOS):
                if d["pa"][nome]:
                    cont[(i, eq, t)] += 1
        return {k: n for k, n in cont.items()
                if k[1] in limites and n > limites[k[1]].get(k[2], 0)}

    def compativeis(a, b, mesma_ra):
        pa, pb = a["pa"], b["pa"]
        if _chave_frota(a) != _chave_frota(b):
            return False
        if any(bool(pa[n]) != bool(pb[n]) for n in E.DIAS_CAMPOS):
            return False
        if (pa["horario_inicio"], pa["horario_termino"]) != \
                (pb["horario_inicio"], pb["horario_termino"]):
            return False
        if mesma_ra and a["ra"] != b["ra"]:
            return False
        # Plano Piloto: Asa Norte e Asa Sul nunca no mesmo circuito (Tabela 1, Nome)
        if 1 in (a["ra"], b["ra"]):
            asa = lambda d: re.match(r"^(Asa (Norte|Sul))\b", d["pa"]["nome_circuito"] or "")
            ma, mb = asa(a), asa(b)
            if not (ma and mb and ma.group(1) == mb.group(1)):
                return False
        return a["pg"].distance(b["pg"]) <= distancia

    while True:
        exc = excesso()
        if not exc:
            return fusoes, []
        alvo = {(eq, t) for _, eq, t in exc}
        dias_exc = {(i, eq, t) for i, eq, t in exc}
        melhor = None
        for mesma_ra in (True,) if not entre_ras else (True, False):
            cands = [d for d in dados if _chave_frota(d) in alvo and any(
                (i, *_chave_frota(d)) in dias_exc
                for i, n in enumerate(E.DIAS_CAMPOS) if d["pa"][n])]
            for i, a in enumerate(cands):
                for b in cands[i + 1:]:
                    if compativeis(a, b, mesma_ra):
                        km = a["km"] + b["km"]
                        if melhor is None or km < melhor[0]:
                            melhor = (km, a, b)
            if melhor:
                break
        if melhor is None:
            return fusoes, [f"{E.DIAS_NOMES[i]} {t}: {n} circuitos de "
                            f"{E.EQUIPAMENTOS.get(eq, eq)} para {limites[eq].get(t, 0)} "
                            "veículos" for (i, eq, t), n in sorted(exc.items())]
        _, a, b = melhor
        destino, origem = (a, b) if a["km"] >= b["km"] else (b, a)
        fusoes.append((destino["cod"], origem["cod"]))
        _juntar(destino, origem, dados)


# =========================================================== nomes e endereços
def _endereco_texto(enderecos):
    vistos, out = set(), []
    for e in enderecos:
        if e is None:
            continue
        e = str(e).strip()
        if e.lower() in SEM_NOME or e in vistos:
            continue
        vistos.add(e)
        out.append(e)
    return "; ".join(out)


def _asa(enderecos, nome_antigo):
    m = re.match(r"^(Asa (Norte|Sul))\b", nome_antigo or "")
    if m:
        return m.group(1)
    n = s = 0
    for e in enderecos:
        for tok in re.findall(r"\b[A-Z]{2,5}\b", str(e or "")):
            if tok.endswith("N"):
                n += 1
            elif tok.endswith("S"):
                s += 1
    return "Asa Norte" if n >= s else "Asa Sul"


def _hora(v):
    return v if v else None


# ===================================================================== principal
def slu_redesenhar_coleta(gdb_atual, rede_gdb, pasta_saida, regioes, vias_endereco=None,
                          sentidos=None, rede_camada="ArquivoRua", servico=None, lote=None,
                          respeitar_sentido=True, buffer_poligono=25.0, circuitos=None,
                          restaurar_shx=False, sobrescrever=False, carregar=True,
                          campo_sentido="sentido_proposto", ajustar_frota=False,
                          distancia_fusao=1500.0):
    """Redesenha um plano de coleta (CC/CS) existente sobre a rede viária, no padrão
    do Anexo G e com os lotes do novo edital. Grava <pasta_saida>/<CC01>.gdb novo,
    <CC01>_pendencias.gpkg e devolve o resumo com a validação."""
    t0 = _dt.datetime.now()
    servico, lote = slu._servico_lote_de_gdb(gdb_atual, servico, lote)
    if E.SERVICOS[servico]["grupo"] != "coleta":
        raise ValueError("Redesenho por rede só para coleta (P1/P2) nesta versão.")
    lote_cod = E.lote_codigo(servico, lote)

    # ---------------------------------------------------- RAs e limite do lote
    ras = _ler(regioes, None, ("ra_cira", "Lote", "ra_nome"), restaurar_shx)
    ra_geom = {int(a["ra_cira"]): g for g, a in ras if a["ra_cira"] is not None}
    ra_lote = {int(a["ra_cira"]): int(a["Lote"]) for _, a in ras
               if a["ra_cira"] is not None and a["Lote"] is not None}
    limite_lote = unary_union([g for r, g in ra_geom.items() if ra_lote.get(r) == lote])
    arv_ra = STRtree(list(ra_geom.values()))
    ra_ids = list(ra_geom.keys())

    def ra_de(geoms):
        """RA com maior extensão/área dentro dela."""
        peso = Counter()
        for g in geoms:
            for k in arv_ra.query(g, predicate="intersects"):
                inter = g.intersection(ra_geom[ra_ids[k]])
                peso[ra_ids[k]] += inter.length if g.geom_type.endswith("String") else \
                    (inter.area or 1.0)
        return peso.most_common(1)[0][0] if peso else None

    # ---------------------------------------------------- rede
    rede = Rede(rede_gdb, rede_camada, sentidos, respeitar_sentido, vias_endereco,
                restaurar_shx, campo_sentido)

    # ---------------------------------------------------- plano atual
    campos_pol = ["codigo_circuito", "codigo_ra", "nome_circuito", "horario_inicio",
                  "horario_termino", "frequencia", "id_tipo_servico", "id_tipo_equipamento",
                  "local_pesagem", "local_destinacao", "turno", "ciclo", "flag_semana",
                  "enderecamento"] + E.DIAS_CAMPOS
    pols = _ler(gdb_atual, "lm_area_circuito_planejado", campos_pol)
    lins = _ler(gdb_atual, "st_circuito_planejado", ("codigo_circuito", "deslocamento"))
    pts = _ler(gdb_atual, "st_circuito_inicio_fim",
               ("codigo_circuito", "tipo", "horario", "turno", "endereco"))
    conts = _ler(gdb_atual, "st_conteiner", ("codigo_circuito", "codigo_conteiner"))
    linhas_por = defaultdict(list)
    for g, a in lins:
        if a["deslocamento"] != 1:
            linhas_por[a["codigo_circuito"]].extend(_linhas(g))
    pts_por = defaultdict(list)
    for g, a in pts:
        pts_por[a["codigo_circuito"]].append((g, a))
    conts_por = defaultdict(list)
    for g, a in conts:
        conts_por[a["codigo_circuito"]].append((g, a))
    if circuitos:
        alvo = {int(c) for c in circuitos}
        pols = [p for p in pols if p[1]["codigo_circuito"] in alvo]

    # ---------------------------------------------------- redesenho circuito a circuito
    resultado = []
    excluidos = []
    avisos = []
    coleta_usada = set()
    dados = []   # fase 1: trechos de coleta, RA e lote de cada circuito
    for pg, pa in sorted(pols, key=lambda x: x[1]["codigo_circuito"] or 0):
        cod = pa["codigo_circuito"]
        ts = pa["id_tipo_servico"]
        ts_cod = E.tipo_servico_do_codigo(servico, cod) if cod else None
        if ts_cod is not None and ts != ts_cod:
            tem_cont = bool(conts_por.get(cod))
            tem_linha = bool(linhas_por.get(cod))
            coerente = {0: tem_linha and not tem_cont, 1: tem_linha and not tem_cont,
                        5: tem_cont and not tem_linha, 6: tem_cont and not tem_linha,
                        8: tem_cont and tem_linha, 9: tem_cont and tem_linha}.get(ts_cod)
            if coerente:
                avisos.append(f"{cod}: Tipo de Serviço corrigido de {ts} para {ts_cod} "
                              f"({E.TIPO_SERVICO_DESC.get(ts_cod)}), como indica o código e "
                              "os dados do circuito")
                ts = ts_cod
            else:
                avisos.append(f"{cod}: Tipo de Serviço {ts} difere do código ({ts_cod}); "
                              "não corrigido — confira")
        req = rede.trechos_cobertos(linhas_por.get(cod, []))
        fora = {i for i in req if not limite_lote.contains(rede.mid[i])}
        req -= fora
        cts = [(g, a) for g, a in conts_por.get(cod, []) if limite_lote.contains(g)]
        base = [rede.geom[i] for i in req] or [g for g, _ in cts] or [pg]
        ra = ra_de(base)
        if ra is None or ra_lote.get(ra) != lote:
            excluidos.append({"codigo_circuito": cod, "nome_antigo": pa["nome_circuito"],
                              "ra": ra, "ra_nome": E.RA.get(ra),
                              "lote_novo": ra_lote.get(ra),
                              "motivo": "circuito passa a outro lote no novo edital"})
            continue
        if fora:
            avisos.append(f"{cod}: {len(fora)} trechos fora do Lote {lote} removidos")
        dados.append({"pg": pg, "pa": pa, "cod": cod, "ts": ts, "req": req, "cts": cts,
                      "ra": ra, "pts": {a["tipo"]: (g, a) for g, a in pts_por.get(cod, [])},
                      "km": sum(rede.comp[i] for i in req) / 1000, "fundidos": []})

    # fase 2: junta circuitos para caber na frota do edital (Anexo R)
    fusoes = []
    if ajustar_frota:
        limites = E.FROTA_ANEXO_R.get((servico, lote))
        if limites:
            fusoes, sem_solucao = _planejar_fusoes(dados, limites, distancia_fusao)
            for s in sem_solucao:
                avisos.append(f"Frota insuficiente mesmo juntando circuitos: {s}")
            for d in dados:
                if d["fundidos"]:
                    avisos.append(f"{d['cod']}: recebeu os circuitos {d['fundidos']} para caber "
                                  f"na frota do Anexo R ({d['km']:.1f} km de coleta)")

    # fase 3: rota, linhas, pontos, polígono e atributos
    for d in dados:
        pg, pa, cod, ts, req, cts, ra = (d["pg"], d["pa"], d["cod"], d["ts"], d["req"],
                                         d["cts"], d["ra"])
        passagem, contramao = set(), set()
        if req:
            passagem, contramao = _vias_de_passagem(rede, req)
            if contramao:
                avisos.append(f"{cod}: {len(contramao)} trecho(s) só conectam na contramão "
                              "pelo sentido proposto — confira a mão dessas vias")
        desloc = {i: 0 for i in req}
        desloc.update({i: 1 for i in passagem})
        coleta_usada |= req
        segs = _segmentar(rede, desloc, desloc) if desloc else []

        # pontos de início e fim: os atuais, encaixados no nó de coleta mais próximo
        pontos = []
        ordem = []
        if req and ts in (0, 1, 8, 9):
            nos_req = {rede.u[i] for i in req} | {rede.v[i] for i in req}
            antigos = d["pts"]
            prim = min(req)
            ref_ini = antigos[1][0] if 1 in antigos else Point(rede.no_xy[rede.u[prim]])
            n_ini = rede.no_mais_proximo(ref_ini, nos_req)
            ordem = _ordem_bfs(rede, req, n_ini)
            if 0 in antigos:
                n_fim = rede.no_mais_proximo(antigos[0][0], nos_req - {n_ini}) or n_ini
            else:
                ult = ordem[-1]
                n_fim = rede.v[ult] if rede.v[ult] != n_ini else rede.u[ult]
            for tipo, n_no, hora in ((1, n_ini, pa["horario_inicio"]),
                                     (0, n_fim, pa["horario_termino"])):
                ant = antigos.get(tipo, (None, {}))[1]
                idx = next((i for i in req if n_no in (rede.u[i], rede.v[i])), None)
                pontos.append((Point(rede.no_xy[n_no]), {
                    "tipo": tipo, "horario": ant.get("horario") or hora,
                    "turno": pa["turno"] or ant.get("turno"),
                    "endereco": (rede.endereco[idx] if idx is not None else None)
                    or ant.get("endereco")}))

        # polígono: área de coleta (recortada no lote) + faixa das vias de passagem
        partes = []
        col = [s[0] for s in segs if s[1] == 0]
        pas = [s[0] for s in segs if s[1] == 1]
        if col:
            partes.append(unary_union(col).buffer(buffer_poligono))
        if cts:
            partes.append(unary_union([g for g, _ in cts]).buffer(20.0))
        if ts in (0, 1, 8, 9) and pg is not None:
            partes.append(pg.buffer(0))
        poly = unary_union(partes).intersection(limite_lote.buffer(buffer_poligono + 5))
        if pas:
            poly = unary_union([poly, unary_union(pas).buffer(5.0)])
        if pontos:
            poly = unary_union([poly] + [p.buffer(2.0) for p, _ in pontos])
        if poly.geom_type == "Polygon":
            poly = MultiPolygon([poly])
        elif poly.geom_type == "GeometryCollection":
            poly = MultiPolygon([g for g in poly.geoms if g.geom_type == "Polygon"])

        # atributos
        dias = [pa[d] or 0 for d in E.DIAS_CAMPOS]
        ends = [rede.endereco[i] for i in (ordem or sorted(req))]
        end_pp = _endereco_texto(ends)
        cods_cont = ", ".join(str(a["codigo_conteiner"]) for _, a in cts
                              if a["codigo_conteiner"] is not None)
        if ts in (5, 6):
            enderecamento = cods_cont
        elif ts in (8, 9):
            enderecamento = f"Coleta porta a porta - {end_pp} & Coleta Contêineres - {cods_cont}"
        else:
            enderecamento = end_pp
        nome_ra = _asa(ends, pa["nome_circuito"]) if ra == 1 else None
        try:
            nome = E.nome_circuito(servico, cod, dias, pa["ciclo"] or 0, codigo_ra=ra,
                                   nome_ra=nome_ra)
        except ValueError as e:
            nome = pa["nome_circuito"]
            avisos.append(f"{cod}: nome mantido ({e})")
        resultado.append({
            "codigo": cod, "ra": ra, "poligono": poly, "segmentos": segs, "pontos": pontos,
            "conteineres": cts,
            "attrs": {**{k: pa[k] for k in campos_pol}, "id_tipo_servico": ts,
                      "codigo_ra": ra, "nome_circuito": nome,
                      "enderecamento": enderecamento[:5000],
                      "frequencia": E.frequencia_texto(dias),
                      "ciclo": pa["ciclo"] or 0, "flag_semana": pa["flag_semana"] or 0},
            "km_coleta": sum(rede.comp[i] for i, d in desloc.items() if d == 0) / 1000,
            "km_passagem": sum(rede.comp[i] for i, d in desloc.items() if d == 1) / 1000,
        })

    # ---------------------------------------------------- grava o .gdb novo
    criado = slu.slu_criar_gdb(servico, lote, pasta_saida, sobrescrever=sobrescrever,
                               carregar=False)
    gdb_novo = criado["gdb"]
    _gravar(gdb_novo, resultado, lote_cod)

    # ---------------------------------------------------- pendências
    pend_path = os.path.join(pasta_saida, f"{lote_cod}_pendencias.gpkg")
    sem_circuito = []
    for i in range(rede.n):
        if i in coleta_usada or rede.legenda[i] != "VIA URBANA":
            continue
        if limite_lote.contains(rede.mid[i]):
            sem_circuito.append(i)
    _gravar_pendencias(pend_path, rede, sem_circuito, ra_geom, ra_ids, arv_ra, excluidos, pols)

    validacao = slu.slu_validar_gdb(gdb_novo, relatorio_xlsx=os.path.join(
        pasta_saida, f"{lote_cod}_validacao.xlsx"))
    if carregar:
        slu._carregar_no_projeto(gdb_novo, [c["nome"] for c in E.esquema(servico, lote)],
                                 grupo=f"{lote_cod} redesenhado")
    km_ra = Counter()
    for i in sem_circuito:
        p = rede.mid[i]
        for k in arv_ra.query(p, predicate="within"):
            km_ra[E.RA.get(ra_ids[k], ra_ids[k])] += rede.comp[i] / 1000
    return {
        "success": True, "gdb": gdb_novo, "pendencias_gpkg": pend_path,
        "circuitos_redesenhados": len(resultado),
        "circuitos_excluidos": excluidos,
        "fusoes": [{"fica": a, "entra": b} for a, b in fusoes],
        "km_coleta": round(sum(r["km_coleta"] for r in resultado), 1),
        "km_passagem": round(sum(r["km_passagem"] for r in resultado), 1),
        "vias_urbanas_sem_circuito_km_por_ra": {k: round(v, 1) for k, v in km_ra.most_common()},
        "avisos": avisos[:100],
        "validacao": {k: validacao[k] for k in ("erros", "avisos", "por_regra",
                                                "aprovado_sem_erros")},
        "relatorio_validacao": validacao.get("relatorio_xlsx"),
        "minutos": round((_dt.datetime.now() - t0).total_seconds() / 60, 1),
        "parametros": {"respeitar_sentido": respeitar_sentido, "campo_sentido": campo_sentido,
                       "buffer_poligono": buffer_poligono},
    }


def _ogr(g):
    return ogr.CreateGeometryFromWkb(shapely.to_wkb(g))


def _gravar(gdb, resultado, lote_cod):
    ds = gdal.OpenEx(gdb, gdal.OF_VECTOR | gdal.OF_UPDATE)
    lp = ds.GetLayerByName("lm_area_circuito_planejado")
    ll = ds.GetLayerByName("st_circuito_planejado")
    lt = ds.GetLayerByName("st_circuito_inicio_fim")
    lc = ds.GetLayerByName("st_conteiner")
    ds.StartTransaction(force=True) if hasattr(ds, "StartTransaction") else None
    for r in resultado:
        a = r["attrs"]
        f = ogr.Feature(lp.GetLayerDefn())
        f.SetGeometry(_ogr(r["poligono"]))
        f.SetField("lote", lote_cod)
        for k, v in a.items():
            if v is None or lp.GetLayerDefn().GetFieldIndex(k) < 0:
                continue
            f.SetField(k, v)
        lp.CreateFeature(f)
        for geom, desloc, _ in r["segmentos"]:
            f = ogr.Feature(ll.GetLayerDefn())
            f.SetGeometry(_ogr(MultiLineString([geom])))
            f.SetField("lote", lote_cod)
            f.SetField("codigo_circuito", r["codigo"])
            f.SetField("codigo_ra", r["ra"])
            f.SetField("deslocamento", desloc)
            ll.CreateFeature(f)
        for geom, pa in r["pontos"]:
            f = ogr.Feature(lt.GetLayerDefn())
            f.SetGeometry(_ogr(geom))
            f.SetField("lote", lote_cod)
            f.SetField("codigo_circuito", r["codigo"])
            f.SetField("codigo_ra", r["ra"])
            for k in ("tipo", "horario", "turno", "endereco"):
                if pa.get(k) is not None:
                    f.SetField(k, pa[k])
            lt.CreateFeature(f)
        for geom, ca in r["conteineres"]:
            f = ogr.Feature(lc.GetLayerDefn())
            f.SetGeometry(_ogr(geom))
            f.SetField("lote", lote_cod)
            f.SetField("codigo_circuito", r["codigo"])
            f.SetField("codigo_ra", r["ra"])
            if ca.get("codigo_conteiner") is not None:
                f.SetField("codigo_conteiner", ca["codigo_conteiner"])
            lc.CreateFeature(f)
    if hasattr(ds, "CommitTransaction"):
        try:
            ds.CommitTransaction()
        except Exception:
            pass
    ds = None


def _gravar_pendencias(path, rede, sem_circuito, ra_geom, ra_ids, arv_ra, excluidos, pols):
    if os.path.exists(path):
        os.remove(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(E.EPSG)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    l1 = ds.CreateLayer("vias_urbanas_sem_circuito", srs, ogr.wkbLineString)
    for nome, tipo in (("trecho", ogr.OFTInteger), ("codigo_ra", ogr.OFTInteger),
                       ("ra", ogr.OFTString), ("endereco", ogr.OFTString),
                       ("comprimento", ogr.OFTReal)):
        l1.CreateField(ogr.FieldDefn(nome, tipo))
    ds.StartTransaction()
    for i in sem_circuito:
        f = ogr.Feature(l1.GetLayerDefn())
        f.SetGeometry(_ogr(rede.geom[i]))
        ks = arv_ra.query(rede.mid[i], predicate="within")
        if len(ks):
            f.SetField("codigo_ra", ra_ids[ks[0]])
            f.SetField("ra", E.RA.get(ra_ids[ks[0]]))
        f.SetField("trecho", i)
        f.SetField("endereco", rede.endereco[i])
        f.SetField("comprimento", round(rede.comp[i], 1))
        l1.CreateFeature(f)
    ds.CommitTransaction()
    l2 = ds.CreateLayer("circuitos_para_outro_lote", srs, ogr.wkbMultiPolygon)
    for nome, tipo in (("codigo_circuito", ogr.OFTInteger), ("nome_antigo", ogr.OFTString),
                       ("ra", ogr.OFTString), ("lote_novo", ogr.OFTInteger)):
        l2.CreateField(ogr.FieldDefn(nome, tipo))
    geo = {a["codigo_circuito"]: g for g, a in pols}
    for ex in excluidos:
        f = ogr.Feature(l2.GetLayerDefn())
        g = geo.get(ex["codigo_circuito"])
        if g is not None:
            g = MultiPolygon([g]) if g.geom_type == "Polygon" else g
            f.SetGeometry(_ogr(g))
        f.SetField("codigo_circuito", ex["codigo_circuito"])
        f.SetField("nome_antigo", ex["nome_antigo"])
        f.SetField("ra", ex["ra_nome"])
        if ex["lote_novo"] is not None:
            f.SetField("lote_novo", ex["lote_novo"])
        l2.CreateFeature(f)
    ds = None


TOOLS = {"slu_redesenhar_coleta": slu_redesenhar_coleta}
