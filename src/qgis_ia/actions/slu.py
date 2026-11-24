# -*- coding: utf-8 -*-
"""
Actions: Planos de Serviço do SLU-DF (Edital Pregão 90005/2026, Anexo G).

Cria os arquivos exigidos (File Geodatabase .gdb, tabela .xlsx, texto .docx),
confere um .gdb contra as regras do Anexo G e preenche os campos calculáveis.

Usa só GDAL/OGR (osgeo), openpyxl e a biblioteca padrão. Nada aqui importa o
QGIS no topo do módulo, então dá para testar fora do QGIS. A única parte que
usa o QGIS (carregar camadas no projeto) importa sob demanda.
"""
import datetime as _dt
import os
import re
import shutil
import unicodedata
import zipfile
from xml.sax.saxutils import escape as _xml

from osgeo import gdal, ogr, osr

try:
    from .. import edital_slu as E
except ImportError:  # execução fora do pacote (testes)
    import edital_slu as E


_GEOM = {"Point": ogr.wkbPoint, "MultiLineString": ogr.wkbMultiLineString,
         "MultiPolygon": ogr.wkbMultiPolygon}
MAX_ITENS_RETORNO = 200
TOL = 0.01  # tolerância geométrica, em metros


def _exc():
    """Liga exceções do GDAL só dentro do bloco (não mexe no resto do QGIS)."""
    return gdal.ExceptionMgr(useExceptions=True)


def _srs():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(E.EPSG)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def _servico_lote_de_gdb(gdb_path, servico=None, lote=None):
    """Deduz serviço e lote do nome do arquivo (ex.: CC01.gdb -> P1, 1)."""
    base = os.path.splitext(os.path.basename(os.path.normpath(gdb_path)))[0].upper()
    m = re.match(r"^([A-Z]{2})0?([123])", base)
    if servico is None:
        if not m or m.group(1) not in E.SIGLA_PARA_SERVICO:
            raise ValueError(f"Não deu para deduzir o serviço pelo nome '{base}'. "
                             "Informe 'servico' (P1..P12) e 'lote'.")
        servico = E.SIGLA_PARA_SERVICO[m.group(1)]
    if lote is None:
        if not m:
            raise ValueError("Informe 'lote' (1, 2 ou 3).")
        lote = int(m.group(2))
    return E.normaliza_servico(servico), E.normaliza_lote(lote)


# =============================================================== criar .gdb
def slu_criar_gdb(servico, lote, pasta_saida, sobrescrever=False, carregar=True,
                  limite_df=None, turnos=None, numero_equipes=None):
    """Cria o File Geodatabase vazio no padrão do Anexo G (camadas, campos,
    apelidos, domínios e SIRGAS 2000 / UTM 23S).

    Para serviços sob demanda (P3, P4, P7, P8, P10, P11, P12), se 'limite_df'
    (arquivo vetorial com o limite do DF) for informado, já grava 1 polígono por
    turno, com lote, código, nome, dias (seg-sáb) e endereçamento preenchidos.
    """
    servico, lote = E.normaliza_servico(servico), E.normaliza_lote(lote)
    camadas = E.esquema(servico, lote)
    if not camadas:
        raise ValueError(f"{servico} ({E.SERVICOS[servico]['nome']}) não exige .gdb "
                         "(item 3.2 do Anexo G). Gere só o .docx e o .xlsx.")
    codigo = E.lote_codigo(servico, lote)
    os.makedirs(pasta_saida, exist_ok=True)
    path = os.path.join(pasta_saida, f"{codigo}.gdb")
    if os.path.exists(path):
        if not sobrescrever:
            raise FileExistsError(f"Já existe: {path}. Use sobrescrever=true para recriar.")
        shutil.rmtree(path)

    with _exc():
        drv = ogr.GetDriverByName("OpenFileGDB")
        ds = drv.CreateDataSource(path)
        for nome, (desc, tipo, valores) in E.dominios(servico, lote).items():
            if tipo == "int":
                dom = ogr.CreateCodedFieldDomain(nome, desc, ogr.OFTInteger, ogr.OFSTInt16,
                                                 {str(k): v for k, v in valores.items()})
            else:
                dom = ogr.CreateCodedFieldDomain(nome, desc, ogr.OFTString, ogr.OFSTNone,
                                                 {str(k): v for k, v in valores.items()})
            ds.AddFieldDomain(dom)

        srs = _srs()
        for cam in camadas:
            lyr = ds.CreateLayer(cam["nome"], srs, _GEOM[cam["geometria"]],
                                 options=["GEOMETRY_NAME=Shape"])
            for c in cam["campos"]:
                lyr.CreateField(_field_defn(c))

        inseridos = 0
        if limite_df and E.SERVICOS[servico]["grupo"] == "demanda":
            inseridos = _inserir_poligonos_demanda(ds, servico, lote, limite_df,
                                                   turnos or ["Diurno"], numero_equipes)
        ds = None

    if carregar:
        _carregar_no_projeto(path, [c["nome"] for c in camadas], grupo=codigo)
    return {"success": True, "gdb": path, "servico": servico, "lote": codigo,
            "camadas": [{"nome": c["nome"], "geometria": c["geometria"],
                         "campos": [f["nome"] for f in c["campos"]]} for c in camadas],
            "poligonos_inseridos": inseridos}


def _field_defn(c):
    tipo = c["tipo"]
    if tipo == "str":
        fd = ogr.FieldDefn(c["nome"], ogr.OFTString)
        fd.SetWidth(c["tamanho"] or 255)
    elif tipo == "int16":
        fd = ogr.FieldDefn(c["nome"], ogr.OFTInteger)
        fd.SetSubType(ogr.OFSTInt16)
    elif tipo == "int":
        fd = ogr.FieldDefn(c["nome"], ogr.OFTInteger)
    elif tipo == "real":
        fd = ogr.FieldDefn(c["nome"], ogr.OFTReal)
    elif tipo == "datetime":
        fd = ogr.FieldDefn(c["nome"], ogr.OFTDateTime)
    else:
        raise ValueError(tipo)
    if c.get("apelido"):
        fd.SetAlternativeName(c["apelido"])
    if c.get("dominio"):
        fd.SetDomainName(c["dominio"])
    return fd


def _inserir_poligonos_demanda(ds, servico, lote, limite_df, turnos, numero_equipes):
    src = gdal.OpenEx(limite_df, gdal.OF_VECTOR)
    if src is None:
        raise ValueError(f"Não abri o limite do DF: {limite_df}")
    sl = src.GetLayer(0)
    uniao = None
    for f in sl:
        g = f.GetGeometryRef()
        if g is None:
            continue
        g = g.Clone()
        uniao = g if uniao is None else uniao.Union(g)
    if uniao is None:
        raise ValueError("O arquivo de limite do DF não tem geometrias.")
    s_srs = sl.GetSpatialRef()
    if s_srs is not None:
        s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        uniao.TransformTo(_srs())
    uniao = ogr.ForceToMultiPolygon(uniao)

    lyr = ds.GetLayerByName("lm_area_circuito_planejado")
    dias = [1, 1, 1, 1, 1, 1, 0]  # diário = segunda a sábado (Tabela 3)
    n = 0
    for turno in turnos:
        turno = str(turno).strip().capitalize()
        cod = E.codigo_circuito_demanda(servico, lote, turno)
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetGeometry(uniao)
        f.SetField("lote", E.lote_codigo(servico, lote))
        f.SetField("codigo_circuito", cod)
        f.SetField("nome_circuito", E.nome_circuito(servico, cod, dias, 0, lote=lote))
        f.SetField("enderecamento", f"Lote {lote:02d}")
        for campo, v in zip(E.DIAS_CAMPOS, dias):
            f.SetField(campo, v)
        f.SetField("frequencia", E.frequencia_texto(dias))
        f.SetField("id_tipo_servico", E.SERVICOS[servico]["codigo"])
        f.SetField("ciclo", 0)
        f.SetField("flag_semana", 0)
        f.SetField("turno", turno)
        if numero_equipes is not None:
            f.SetField("numero_equipes", int(numero_equipes))
        lyr.CreateFeature(f)
        n += 1
    return n


def _carregar_no_projeto(gdb_path, nomes, grupo=None):
    """Adiciona as camadas do .gdb ao projeto aberto (só dentro do QGIS)."""
    try:
        from qgis.core import QgsProject, QgsVectorLayer
    except ImportError:
        return []
    proj = QgsProject.instance()
    root = proj.layerTreeRoot()
    node = root.findGroup(grupo) if grupo else None
    if grupo and node is None:
        node = root.insertGroup(0, grupo)
    carregadas = []
    for nome in nomes:
        lyr = QgsVectorLayer(f"{gdb_path}|layername={nome}", nome, "ogr")
        if lyr.isValid():
            proj.addMapLayer(lyr, node is None)
            if node is not None:
                node.addLayer(lyr)
            carregadas.append(nome)
    return carregadas


# ============================================================ leitura .gdb
class _Gdb:
    """Leitura simplificada de um .gdb: camadas e campos sem diferenciar maiúsculas."""

    def __init__(self, path, update=False):
        flags = gdal.OF_VECTOR | (gdal.OF_UPDATE if update else 0)
        self.ds = gdal.OpenEx(path, flags)
        if self.ds is None:
            raise ValueError(f"Não consegui abrir o .gdb: {path}")
        self.camadas = {}
        for i in range(self.ds.GetLayerCount()):
            lyr = self.ds.GetLayerByIndex(i)
            self.camadas[lyr.GetName().lower()] = lyr

    def layer(self, nome):
        return self.camadas.get(nome.lower())

    @staticmethod
    def campos(lyr):
        d = lyr.GetLayerDefn()
        return {d.GetFieldDefn(i).GetName().lower(): d.GetFieldDefn(i).GetName()
                for i in range(d.GetFieldCount())}


def _val(f, campos, nome):
    real = campos.get(nome.lower())
    if real is None:
        return None
    idx = f.GetFieldIndex(real)
    if not f.IsFieldSetAndNotNull(idx):
        return None
    v = f.GetField(idx)
    return v.strip() if isinstance(v, str) else v


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _ponto_ref(g):
    if g is None or g.IsEmpty():
        return None, None
    try:
        p = g.PointOnSurface() if g.GetDimension() == 2 else None
    except Exception:
        p = None
    if p is None or p.IsEmpty():
        if g.GetGeometryType() in (ogr.wkbPoint, ogr.wkbPoint25D):
            p = g
        else:
            env = g.GetEnvelope()
            return (env[0] + env[1]) / 2, (env[2] + env[3]) / 2
    return round(p.GetX(), 3), round(p.GetY(), 3)


# ================================================================ validar
class _Relatorio:
    def __init__(self):
        self.itens = []

    def add(self, nivel, regra, msg, camada="", fid=None, codigo=None, geom=None):
        x, y = _ponto_ref(geom) if geom is not None else (None, None)
        self.itens.append({"nivel": nivel, "regra": regra, "camada": camada, "fid": fid,
                           "codigo_circuito": codigo, "mensagem": msg, "x": x, "y": y})

    def erro(self, *a, **k):
        self.add("erro", *a, **k)

    def aviso(self, *a, **k):
        self.add("aviso", *a, **k)


def slu_validar_gdb(gdb_path, servico=None, lote=None, topologia_linhas=True,
                    relatorio_xlsx=None, carregar_erros=False):
    """Confere o .gdb contra o Anexo G: esquema, CRS, atributos (códigos, nomes,
    frequência, ciclo/semana, domínios) e regras topológicas. Devolve um resumo e
    os primeiros problemas; o relatório completo vai para 'relatorio_xlsx'."""
    servico, lote = _servico_lote_de_gdb(gdb_path, servico, lote)
    grupo = E.SERVICOS[servico]["grupo"]
    lote_cod = E.lote_codigo(servico, lote)
    rel = _Relatorio()
    t0 = _dt.datetime.now()

    gdb = _Gdb(gdb_path)
    esperado = E.esquema(servico, lote)

    # ------------------------------------------------ esquema e CRS
    for cam in esperado:
        lyr = gdb.layer(cam["nome"])
        if lyr is None:
            rel.erro("esquema", f"Camada obrigatória ausente: {cam['nome']}", cam["nome"])
            continue
        campos = _Gdb.campos(lyr)
        for c in cam["campos"]:
            if c["nome"].lower() not in campos:
                nivel = "aviso" if c["nome"] in ("ciclo", "flag_semana", "turno") else "erro"
                rel.add(nivel, "esquema", f"Campo ausente: {c['nome']}", cam["nome"])
        if lyr.GetName() != cam["nome"]:
            rel.aviso("esquema", f"Nome da camada '{lyr.GetName()}' difere do padrão "
                      f"'{cam['nome']}' (maiúsculas/minúsculas)", cam["nome"])
        srs = lyr.GetSpatialRef()
        if srs is None or not srs.IsSame(_srs()):
            code = srs.GetAuthorityCode(None) if srs is not None else None
            if str(code) != str(E.EPSG):
                rel.erro("crs", f"CRS deve ser SIRGAS 2000 / UTM 23S (EPSG:{E.EPSG}); "
                         f"encontrado: {srs.GetName() if srs else 'nenhum'}", cam["nome"])

    # ------------------------------------------------ polígonos
    lpol = gdb.layer("lm_area_circuito_planejado")
    poligonos = {}   # codigo -> {"geom", "ra", "tipo_servico", "fid"}
    if lpol is not None:
        cp = _Gdb.campos(lpol)
        vistos = {}
        lpol.ResetReading()
        for f in lpol:
            fid, g = f.GetFID(), f.GetGeometryRef()
            g = g.Clone() if g is not None else None
            cod = _int(_val(f, cp, "codigo_circuito"))
            ctx = dict(camada="lm_area_circuito_planejado", fid=fid, codigo=cod, geom=g)
            _checa_lote(rel, _val(f, cp, "lote"), lote_cod, ctx)
            ts = _int(_val(f, cp, "id_tipo_servico"))
            for m in E.valida_codigo_circuito(servico, lote, cod, ts):
                rel.erro("codigo_circuito", m, **ctx)
            if cod is not None:
                if cod in vistos:
                    rel.erro("codigo_circuito", f"Código Circuito {cod} duplicado "
                             f"(também no FID {vistos[cod]})", **ctx)
                vistos[cod] = fid
            ra = _int(_val(f, cp, "codigo_ra"))
            _checa_ra(rel, ra, grupo, lote, ctx)
            if g is None or g.IsEmpty():
                rel.erro("geometria", "Polígono sem geometria", **ctx)
            elif not g.IsValid():
                rel.erro("geometria", "Polígono com geometria inválida", **ctx)
            dias = [_int(_val(f, cp, d)) for d in E.DIAS_CAMPOS]
            for d, v in zip(E.DIAS_NOMES, dias):
                if v not in (0, 1):
                    rel.erro("dias", f"Campo {d} deve ser 0 ou 1 (está {v})", **ctx)
            ciclo = _int(_val(f, cp, "ciclo"))
            semana = _int(_val(f, cp, "flag_semana"))
            if semana is None:
                semana = _int(_val(f, cp, "semana_execucao"))
            _checa_ciclo(rel, ciclo, semana, "ciclo" in cp, ctx)
            freq = _val(f, cp, "frequencia")
            esperado_freq = E.frequencia_texto(dias)
            if not freq:
                rel.erro("frequencia", "Frequência vazia", **ctx)
            elif _norm(freq) != _norm(esperado_freq):
                rel.aviso("frequencia", f"Frequência '{freq}' não confere com os dias "
                          f"marcados (esperado '{esperado_freq}')", **ctx)
            nome = _val(f, cp, "nome_circuito")
            if cod is not None:
                ok, info = E.valida_nome_circuito(servico, nome, cod, dias, ciclo or 0, ra, lote)
                if not ok:
                    rel.erro("nome_circuito", f"Nome '{nome}': {info}", **ctx)
            for campo, rot in (("horario_inicio", "Horário de Início"),
                               ("horario_termino", "Horário de Término")):
                if _val(f, cp, campo) is None:
                    rel.erro("horario", f"{rot} vazio", **ctx)
            _checa_tipo_servico(rel, servico, ts, ctx)
            eq = _int(_val(f, cp, "id_tipo_equipamento"))
            if eq is None:
                rel.erro("equipamento", "Tipo de Equipamento vazio", **ctx)
            elif eq not in E.EQUIPAMENTOS:
                rel.erro("equipamento", f"Tipo de Equipamento {eq} fora da Tabela 4", **ctx)
            elif grupo in E.EQUIPAMENTOS_POR_GRUPO and eq not in E.EQUIPAMENTOS_POR_GRUPO[grupo]:
                rel.aviso("equipamento", f"Equipamento {eq} ({E.EQUIPAMENTOS[eq]}) incomum para "
                          f"{E.SERVICOS[servico]['nome']}", **ctx)
            end = _val(f, cp, "enderecamento")
            _checa_enderecamento(rel, end, grupo, ts, lote, ctx)
            if not _val(f, cp, "local_destinacao") and grupo != "demanda":
                rel.aviso("destinacao", "Local de Destinação vazio", **ctx)
            if grupo == "coleta" and not _val(f, cp, "local_pesagem"):
                rel.aviso("pesagem", "Local de Pesagem vazio", **ctx)
            turno = _val(f, cp, "turno")
            if turno is not None and turno not in E.TURNOS:
                rel.erro("turno", f"Turno '{turno}' deve ser 'Diurno' ou 'Noturno'", **ctx)
            if grupo == "demanda":
                if cod is not None and len(str(cod)) == 5 and turno in E.TURNOS:
                    t = "01" if turno == "Diurno" else "02"
                    if str(cod)[3:] != t:
                        rel.erro("codigo_circuito", f"Código {cod} indica turno "
                                 f"{str(cod)[3:]} mas o campo Turno é {turno}", **ctx)
                neq = _int(_val(f, cp, "numero_equipes"))
                if not neq or neq <= 0:
                    rel.erro("numero_equipes", "Número de Equipes vazio ou zero", **ctx)
            if cod is not None and g is not None and not g.IsEmpty():
                if cod in poligonos:
                    poligonos[cod]["geom"] = poligonos[cod]["geom"].Union(g)
                else:
                    poligonos[cod] = {"geom": g, "ra": ra, "tipo_servico": ts, "fid": fid}
        _checa_sobreposicao_poligonos(rel, poligonos)

    # ------------------------------------------------ linhas
    precisa_linha = _circuitos_que_precisam(poligonos, grupo, "linha")
    linhas_por_circ = {}
    llin = gdb.layer("st_circuito_planejado")
    if llin is not None and grupo != "demanda":
        cl = _Gdb.campos(llin)
        lmin, lmax = (50, 130) if grupo == "coleta" else (50, 200)
        geoms = []
        llin.ResetReading()
        for f in llin:
            fid, g = f.GetFID(), f.GetGeometryRef()
            g = g.Clone() if g is not None else None
            cod = _int(_val(f, cl, "codigo_circuito"))
            ctx = dict(camada="st_circuito_planejado", fid=fid, codigo=cod, geom=g)
            _checa_lote(rel, _val(f, cl, "lote"), lote_cod, ctx)
            _checa_filho(rel, cod, _int(_val(f, cl, "codigo_ra")), poligonos, ctx)
            desl = _int(_val(f, cl, "deslocamento"))
            if desl not in (0, 1):
                rel.erro("deslocamento", f"Deslocamento deve ser 0 (via de coleta/varrição) ou "
                         f"1 (via de passagem); está {desl}", **ctx)
            if g is None or g.IsEmpty():
                rel.erro("geometria", "Linha sem geometria", **ctx)
                continue
            if g.GetGeometryCount() > 1 and ogr.GT_Flatten(g.GetGeometryType()) == \
                    ogr.wkbMultiLineString:
                rel.erro("single_part", f"Linha multipart ({g.GetGeometryCount()} partes): "
                         "Must Be Single Part", **ctx)
            comp = g.Length()
            if comp > lmax + TOL:
                rel.erro("comprimento", f"Linha com {comp:.1f} m (máx. {lmax} m)", **ctx)
            elif comp < lmin - TOL:
                rel.aviso("comprimento", f"Linha com {comp:.1f} m (mín. {lmin} m; aceito só em "
                          "rotatórias e cruzamentos)", **ctx)
            if not g.IsSimple():
                rel.aviso("self_intersect", "Linha cruza a si mesma (Must Not Self-Intersect; "
                          "exceção só em tesourinhas/viadutos)", **ctx)
            if cod in poligonos and not _dentro(g, poligonos[cod]):
                rel.erro("linha_dentro_poligono", "Linha fora do polígono do seu circuito "
                         "(Must Be Inside)", **ctx)
            if cod is not None:
                linhas_por_circ.setdefault(cod, []).append(g)
            geoms.append((fid, cod, g))
        if topologia_linhas:
            _checa_topologia_linhas(rel, geoms)
    for cod in sorted(precisa_linha - set(linhas_por_circ)):
        rel.erro("circuito_sem_linha", f"Circuito {cod} não tem linhas de rota",
                 "st_circuito_planejado", codigo=cod, geom=poligonos[cod]["geom"])

    # ------------------------------------------------ pontos início/fim
    lpt = gdb.layer("st_circuito_inicio_fim")
    precisa_ponto = _circuitos_que_precisam(poligonos, grupo, "ponto")
    tipos_por_circ = {}
    if lpt is not None and grupo != "demanda":
        cpt = _Gdb.campos(lpt)
        lpt.ResetReading()
        for f in lpt:
            fid, g = f.GetFID(), f.GetGeometryRef()
            g = g.Clone() if g is not None else None
            cod = _int(_val(f, cpt, "codigo_circuito"))
            ctx = dict(camada="st_circuito_inicio_fim", fid=fid, codigo=cod, geom=g)
            _checa_lote(rel, _val(f, cpt, "lote"), lote_cod, ctx)
            _checa_filho(rel, cod, _int(_val(f, cpt, "codigo_ra")), poligonos, ctx)
            tipo = _int(_val(f, cpt, "tipo"))
            if tipo not in (0, 1):
                rel.erro("tipo_ponto", f"Tipo deve ser 1 (início) ou 0 (fim); está {tipo}", **ctx)
            elif cod is not None:
                tipos_por_circ.setdefault(cod, []).append(tipo)
            turno = _val(f, cpt, "turno")
            if turno not in E.TURNOS:
                rel.erro("turno", f"Turno '{turno}' deve ser 'Diurno' ou 'Noturno'", **ctx)
            if _val(f, cpt, "horario") is None:
                rel.erro("horario", "Horário vazio", **ctx)
            if not _val(f, cpt, "endereco"):
                rel.aviso("endereco", "Endereço Início/Fim vazio", **ctx)
            if g is None or g.IsEmpty():
                rel.erro("geometria", "Ponto sem geometria", **ctx)
                continue
            if cod in poligonos and not poligonos[cod]["geom"].Contains(g):
                rel.erro("ponto_dentro_poligono", "Ponto fora do polígono do seu circuito "
                         "(Must Be Properly Inside)", **ctx)
            linhas = linhas_por_circ.get(cod)
            if linhas and min(g.Distance(lg) for lg in linhas) > TOL:
                rel.erro("ponto_sobre_linha", "Ponto não está sobre uma linha do circuito "
                         "(Point Must Be Covered By Line)", **ctx)
    for cod in sorted(precisa_ponto):
        tipos = tipos_por_circ.get(cod, [])
        if tipos.count(1) != 1 or tipos.count(0) != 1:
            rel.erro("inicio_fim", f"Circuito {cod} deve ter 1 ponto de início e 1 de fim "
                     f"(tem {tipos.count(1)} início e {tipos.count(0)} fim)",
                     "st_circuito_inicio_fim", codigo=cod, geom=poligonos[cod]["geom"])

    # ------------------------------------------------ contêineres (coleta)
    if grupo == "coleta":
        lct = gdb.layer("st_conteiner")
        com_conteiner = set()
        if lct is not None:
            cc = _Gdb.campos(lct)
            vistos = {}
            lct.ResetReading()
            for f in lct:
                fid, g = f.GetFID(), f.GetGeometryRef()
                g = g.Clone() if g is not None else None
                cod = _int(_val(f, cc, "codigo_circuito"))
                ctx = dict(camada="st_conteiner", fid=fid, codigo=cod, geom=g)
                _checa_lote(rel, _val(f, cc, "lote"), lote_cod, ctx)
                _checa_filho(rel, cod, _int(_val(f, cc, "codigo_ra")), poligonos, ctx)
                ce = _int(_val(f, cc, "codigo_conteiner"))
                if ce is None:
                    rel.erro("codigo_conteiner", "Código do Equipamento vazio", **ctx)
                elif (ce, cod) in vistos:
                    rel.aviso("codigo_conteiner", f"Contêiner {ce} repetido no circuito {cod}",
                              **ctx)
                vistos[(ce, cod)] = fid
                if cod in poligonos:
                    com_conteiner.add(cod)
                    ts = _int(str(cod)[1]) if len(str(cod)) == 6 else None
                    if ts in (0, 1):
                        rel.erro("conteiner_circuito", f"Contêiner ligado ao circuito {cod}, que "
                                 "é porta a porta (deve ser ponto a ponto ou misto)", **ctx)
                    if g is not None and not poligonos[cod]["geom"].Contains(g):
                        rel.erro("ponto_dentro_poligono", "Contêiner fora do polígono do seu "
                                 "circuito (Must Be Properly Inside)", **ctx)
        for cod in sorted(_circuitos_que_precisam(poligonos, grupo, "conteiner") - com_conteiner):
            rel.erro("circuito_sem_conteiner", f"Circuito ponto a ponto/misto {cod} sem "
                     "contêineres", "st_conteiner", codigo=cod, geom=poligonos[cod]["geom"])

    # ------------------------------------------------ quantificação (varrição)
    if grupo == "varricao":
        lq = gdb.layer("st_quantificacao")
        qtd = {}
        if lq is not None:
            cq = _Gdb.campos(lq)
            lq.ResetReading()
            for f in lq:
                fid, g = f.GetFID(), f.GetGeometryRef()
                g = g.Clone() if g is not None else None
                cod = _int(_val(f, cq, "codigo_circuito"))
                ctx = dict(camada="st_quantificacao", fid=fid, codigo=cod, geom=g)
                _checa_lote(rel, _val(f, cq, "lote"), lote_cod, ctx)
                _checa_filho(rel, cod, _int(_val(f, cq, "codigo_ra")), poligonos, ctx)
                qtd[cod] = qtd.get(cod, 0) + 1
                ext = _val(f, cq, "extensao_sarjeta")
                if ext is None or ext <= 0:
                    rel.erro("extensao_sarjeta", "Extensão de Sarjeta vazia ou zero", **ctx)
        for cod in poligonos:
            n = qtd.get(cod, 0)
            if n != 1:
                rel.erro("quantificacao", f"Circuito {cod} deve ter exatamente 1 Linha de "
                         f"Quantificação (tem {n})", "st_quantificacao", codigo=cod,
                         geom=poligonos[cod]["geom"])

    gdb = None
    erros = [i for i in rel.itens if i["nivel"] == "erro"]
    avisos = [i for i in rel.itens if i["nivel"] == "aviso"]
    por_regra = {}
    for i in rel.itens:
        k = f"{i['nivel']}:{i['regra']}"
        por_regra[k] = por_regra.get(k, 0) + 1
    out = {
        "gdb": gdb_path, "servico": servico, "lote": lote_cod,
        "circuitos": len(poligonos), "erros": len(erros), "avisos": len(avisos),
        "aprovado_sem_erros": not erros,
        "por_regra": dict(sorted(por_regra.items(), key=lambda kv: -kv[1])),
        "itens": rel.itens[:MAX_ITENS_RETORNO],
        "itens_omitidos": max(0, len(rel.itens) - MAX_ITENS_RETORNO),
        "segundos": round((_dt.datetime.now() - t0).total_seconds(), 1),
        "observacao": "Regra 'Must Not Have Dangles' não é conferida: o Anexo G admite "
                      "exceções (ruas sem saída, limite entre circuitos) que só o "
                      "técnico consegue marcar.",
    }
    if relatorio_xlsx:
        out["relatorio_xlsx"] = _salvar_relatorio(rel.itens, out, relatorio_xlsx)
    if carregar_erros:
        out["camada_erros"] = _camada_erros(rel.itens, os.path.basename(gdb_path))
    return out


def _checa_lote(rel, valor, esperado, ctx):
    if valor is None:
        rel.erro("lote", f"Lote vazio (deve ser '{esperado}')", **ctx)
    elif valor != esperado:
        rel.erro("lote", f"Lote '{valor}' deve ser '{esperado}' (maiúsculas)", **ctx)


def _checa_ra(rel, ra, grupo, lote, ctx):
    if grupo == "demanda":
        if ra is not None:
            rel.erro("codigo_ra", "Serviço sob demanda: Código RA deve ficar nulo", **ctx)
        return
    if ra is None:
        rel.erro("codigo_ra", "Código RA vazio", **ctx)
    elif not (E.RA_MIN <= ra <= E.RA_MAX):
        rel.erro("codigo_ra", f"Código RA {ra} fora do intervalo 1-35", **ctx)
    elif any(ra in s for s in E.RA_POR_LOTE.values()) and ra not in E.RA_POR_LOTE[lote]:
        rel.aviso("codigo_ra", f"RA {ra} ({E.RA[ra]}) não pertence ao Lote {lote} "
                  "(Quadro 01 do edital)", **ctx)


def _checa_ciclo(rel, ciclo, semana, tem_campo, ctx):
    if not tem_campo:
        return
    if ciclo not in (0, 1, 2):
        rel.erro("ciclo", f"Ciclo deve ser 0, 1 ou 2; está {ciclo}", **ctx)
        return
    validos = {0: {0}, 1: {1, 2}, 2: {1, 2, 3, 4}}[ciclo]
    if semana not in validos:
        rel.erro("semana", f"Ciclo {ciclo} ({E.CICLO[ciclo]}) exige Semana em "
                 f"{sorted(validos)}; está {semana}", **ctx)


def _checa_tipo_servico(rel, servico, ts, ctx):
    info = E.SERVICOS[servico]
    if ts is None:
        rel.erro("tipo_servico", "Tipo de Serviço vazio", **ctx)
    elif info["grupo"] == "coleta" and ts not in info["tipos_servico"]:
        rel.erro("tipo_servico", f"Tipo de Serviço {ts} inválido para {info['nome']} "
                 f"({'/'.join(map(str, info['tipos_servico']))})", **ctx)
    elif info["grupo"] != "coleta" and ts != info["codigo"]:
        rel.erro("tipo_servico", f"Tipo de Serviço deve ser {info['codigo']}; está {ts}", **ctx)


def _checa_enderecamento(rel, end, grupo, ts, lote, ctx):
    if not end:
        rel.erro("enderecamento", "Endereçamento vazio", **ctx)
        return
    if grupo == "demanda":
        if end != f"Lote {lote:02d}":
            rel.aviso("enderecamento", f"Endereçamento deve ser 'Lote {lote:02d}'", **ctx)
    elif ts in (5, 6):
        if not re.fullmatch(r"[\d\s,;]+", end):
            rel.aviso("enderecamento", "Circuito ponto a ponto: o endereçamento deve ser a "
                      "lista dos códigos dos contêineres, em ordem de coleta", **ctx)
    elif ts in (8, 9):
        if "coleta porta a porta" not in end.lower() or "&" not in end:
            rel.aviso("enderecamento", "Circuito misto: use 'Coleta porta a porta - "
                      "<endereços> & Coleta Contêineres - <códigos>'", **ctx)


def _checa_filho(rel, cod, ra, poligonos, ctx):
    if cod is None:
        rel.erro("codigo_circuito", "Código Circuito vazio", **ctx)
    elif cod not in poligonos:
        rel.erro("codigo_circuito", f"Circuito {cod} não existe na camada de polígonos", **ctx)
    elif ra is None:
        rel.erro("codigo_ra", "Código RA vazio", **ctx)
    elif poligonos[cod]["ra"] is not None and ra != poligonos[cod]["ra"]:
        rel.aviso("codigo_ra", f"Código RA {ra} difere do polígono do circuito "
                  f"({poligonos[cod]['ra']})", **ctx)


def _circuitos_que_precisam(poligonos, grupo, oque):
    """Quais circuitos exigem linhas / pontos início-fim / contêineres."""
    out = set()
    for cod, p in poligonos.items():
        s = str(cod)
        if grupo == "varricao" and oque in ("linha", "ponto"):
            out.add(cod)
        elif grupo == "coleta" and len(s) == 6:
            ts = int(s[1])
            if oque in ("linha", "ponto") and ts in (0, 1, 8, 9):
                out.add(cod)
            if oque == "conteiner" and ts in (5, 6, 8, 9):
                out.add(cod)
    return out


def _dentro(g, pol):
    buf = pol.get("buf")
    if buf is None:
        buf = pol["buf"] = pol["geom"].Buffer(TOL)
    return buf.Contains(g)


def _envelopes_cruzam(a, b):
    return not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2])


def _checa_sobreposicao_poligonos(rel, poligonos):
    itens = [(cod, p["geom"], p["geom"].GetEnvelope(), p["fid"]) for cod, p in poligonos.items()]
    for i in range(len(itens)):
        ci, gi, ei, fi = itens[i]
        for j in range(i + 1, len(itens)):
            cj, gj, ej, _ = itens[j]
            if not _envelopes_cruzam(ei, ej) or not gi.Intersects(gj):
                continue
            inter = gi.Intersection(gj)
            area = inter.GetArea() if inter is not None else 0
            if area > 1.0:
                rel.aviso("poligono_overlap", f"Polígonos dos circuitos {ci} e {cj} se sobrepõem "
                          f"em {area:.0f} m² (Must Not Overlap; exceção se a área é atendida "
                          "por dois circuitos)", "lm_area_circuito_planejado", fi, ci, inter)


def _extremos(g):
    pts = []
    for k in range(max(1, g.GetGeometryCount())):
        part = g.GetGeometryRef(k) if g.GetGeometryCount() else g
        n = part.GetPointCount()
        if n:
            pts.append(part.GetPoint_2D(0))
            pts.append(part.GetPoint_2D(n - 1))
    return pts


def _checa_topologia_linhas(rel, geoms, celula=250.0):
    """Must Not Overlap e Must Not Intersect entre linhas, com grade espacial."""
    grade = {}
    envs = {}
    for idx, (fid, cod, g) in enumerate(geoms):
        e = g.GetEnvelope()
        envs[idx] = e
        for cx in range(int(e[0] // celula), int(e[1] // celula) + 1):
            for cy in range(int(e[2] // celula), int(e[3] // celula) + 1):
                grade.setdefault((cx, cy), []).append(idx)
    testados = set()
    for membros in grade.values():
        for a_i in range(len(membros)):
            ia = membros[a_i]
            for ib in membros[a_i + 1:]:
                par = (ia, ib) if ia < ib else (ib, ia)
                if par in testados:
                    continue
                testados.add(par)
                if not _envelopes_cruzam(envs[ia], envs[ib]):
                    continue
                fa, ca, ga = geoms[ia]
                fb, cb, gb = geoms[ib]
                if not ga.Intersects(gb):
                    continue
                inter = ga.Intersection(gb)
                if inter is None or inter.IsEmpty():
                    continue
                if inter.GetDimension() >= 1 and inter.Length() > TOL:
                    if ca == cb:
                        rel.erro("linha_overlap", f"Linhas FID {fa} e {fb} do mesmo circuito se "
                                 f"sobrepõem em {inter.Length():.1f} m (Must Not Overlap)",
                                 "st_circuito_planejado", fa, ca, inter)
                    else:
                        rel.aviso("linha_overlap_circuitos", f"Linha FID {fa} (circuito {ca}) "
                                  f"sobrepõe a FID {fb} (circuito {cb}) em "
                                  f"{inter.Length():.1f} m (Must Not Overlap; confira se é a "
                                  "mesma via em circuitos distintos)",
                                  "st_circuito_planejado", fa, ca, inter)
                    continue
                pts =[inter] if inter.GetGeometryCount() == 0 else \
                    [inter.GetGeometryRef(k) for k in range(inter.GetGeometryCount())]
                for p in pts:
                    if p.GetPointCount() == 0:
                        continue
                    x, y = p.GetX(), p.GetY()
                    ea = any(abs(x - px) <= TOL and abs(y - py) <= TOL for px, py in _extremos(ga))
                    eb = any(abs(x - px) <= TOL and abs(y - py) <= TOL for px, py in _extremos(gb))
                    if not (ea and eb):
                        rel.aviso("linha_intersect", f"Linhas FID {fa} e {fb} se cruzam sem "
                                  "quebra no cruzamento (Must Not Intersect; exceção em "
                                  "tesourinhas/viadutos)", "st_circuito_planejado", fa, ca, p)
                        break


def _salvar_relatorio(itens, resumo, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    for k in ("gdb", "servico", "lote", "circuitos", "erros", "avisos", "aprovado_sem_erros"):
        ws.append([k, str(resumo[k])])
    ws.append([])
    ws.append(["Regra", "Ocorrências"])
    for k, v in resumo["por_regra"].items():
        ws.append([k, v])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 60
    w2 = wb.create_sheet("Problemas")
    cab = ["nivel", "regra", "camada", "fid", "codigo_circuito", "mensagem", "x", "y"]
    w2.append(cab)
    for c in w2[1]:
        c.font = Font(bold=True)
    verm = PatternFill("solid", fgColor="F8D7DA")
    amar = PatternFill("solid", fgColor="FFF3CD")
    for i in itens:
        w2.append([i[k] for k in cab])
        fill = verm if i["nivel"] == "erro" else amar
        w2.cell(w2.max_row, 1).fill = fill
    w2.auto_filter.ref = w2.dimensions
    w2.freeze_panes = "A2"
    for col, w in zip("ABCDEFGH", (8, 22, 28, 8, 16, 90, 14, 14)):
        w2.column_dimensions[col].width = w
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return path


def _camada_erros(itens, nome_base):
    try:
        from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
    except ImportError:
        return None
    lyr = QgsVectorLayer(f"Point?crs=EPSG:{E.EPSG}&field=nivel:string(10)&field=regra:string(40)"
                         "&field=camada:string(40)&field=fid:integer&field=codigo_circuito:integer"
                         "&field=mensagem:string(255)", f"Problemas {nome_base}", "memory")
    feats = []
    for i in itens:
        if i["x"] is None:
            continue
        f = QgsFeature(lyr.fields())
        f.setAttributes([i["nivel"], i["regra"], i["camada"], i["fid"], i["codigo_circuito"],
                         i["mensagem"][:255]])
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i["x"], i["y"])))
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    lyr.updateExtents()
    QgsProject.instance().addMapLayer(lyr)
    return lyr.name()


# ============================================================== preencher
def slu_preencher_atributos(gdb_path, servico=None, lote=None, sobrescrever=False, backup=True):
    """Preenche os campos que o Anexo G define por regra: lote, frequência e nome
    do circuito (a partir dos dias e do ciclo), tipo de serviço (do código), semana
    padrão, código RA das linhas/pontos (do polígono), turno com inicial maiúscula,
    extensão da sarjeta (comprimento da linha de quantificação) e endereçamento dos
    serviços sob demanda. Com sobrescrever=false só preenche campos vazios."""
    servico, lote = _servico_lote_de_gdb(gdb_path, servico, lote)
    grupo = E.SERVICOS[servico]["grupo"]
    lote_cod = E.lote_codigo(servico, lote)
    copia = None
    if backup:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.normpath(gdb_path)
        copia = base[:-4] + f"_backup_{stamp}.gdb" if base.lower().endswith(".gdb") \
            else base + f"_backup_{stamp}"
        shutil.copytree(base, copia)

    alterados = {}
    pendencias = []
    with _exc():
        gdb = _Gdb(gdb_path, update=True)

        def grava(lyr, f, campos, nome, valor):
            real = campos.get(nome.lower())
            if real is None:
                return False
            atual = _val(f, campos, nome)
            if atual == valor or (atual not in (None, "") and not sobrescrever):
                return False
            if valor is None:
                f.SetFieldNull(real)
            else:
                f.SetField(real, valor)
            return True

        ra_por_circ = {}
        lpol = gdb.layer("lm_area_circuito_planejado")
        if lpol is not None:
            cp = _Gdb.campos(lpol)
            n = 0
            lpol.ResetReading()
            feats = list(lpol)
            for f in feats:
                mud = False
                cod = _int(_val(f, cp, "codigo_circuito"))
                mud |= _forca(f, cp, "lote", lote_cod)
                dias = [_int(_val(f, cp, d)) for d in E.DIAS_CAMPOS]
                if any(d is not None for d in dias):
                    for campo, v in zip(E.DIAS_CAMPOS, dias):
                        if v is None:
                            mud |= grava(lpol, f, cp, campo, 0)
                    dias = [d or 0 for d in dias]
                ciclo = _int(_val(f, cp, "ciclo"))
                if ciclo is None and "ciclo" in cp:
                    mud |= grava(lpol, f, cp, "ciclo", 0)
                    ciclo = 0
                if ciclo == 0 and _val(f, cp, "flag_semana") is None:
                    mud |= grava(lpol, f, cp, "flag_semana", 0)
                if any(dias):
                    mud |= grava(lpol, f, cp, "frequencia", E.frequencia_texto(dias))
                if cod is not None and _val(f, cp, "id_tipo_servico") is None:
                    ts = E.tipo_servico_do_codigo(servico, cod)
                    if ts is not None:
                        mud |= grava(lpol, f, cp, "id_tipo_servico", ts)
                ra = _int(_val(f, cp, "codigo_ra"))
                if grupo == "demanda":
                    mud |= _forca(f, cp, "codigo_ra", None)
                    mud |= grava(lpol, f, cp, "enderecamento", f"Lote {lote:02d}")
                    turno = _val(f, cp, "turno")
                    if turno:
                        mud |= _forca(f, cp, "turno", turno.capitalize())
                ra_por_circ[cod] = ra
                if cod is not None and any(dias):
                    nome_atual = _val(f, cp, "nome_circuito")
                    try:
                        if grupo == "demanda":
                            novo = E.nome_circuito(servico, cod, dias, ciclo or 0, lote=lote)
                        elif ra == 1:
                            m = re.match(r"^(Asa (Norte|Sul))\b", nome_atual or "")
                            novo = E.nome_circuito(servico, cod, dias, ciclo or 0,
                                                   nome_ra=m.group(1)) if m else None
                            if novo is None:
                                pendencias.append(f"Circuito {cod} (Plano Piloto): escreva "
                                                  "'Asa Norte' ou 'Asa Sul' no início do nome")
                        elif ra is not None:
                            novo = E.nome_circuito(servico, cod, dias, ciclo or 0, codigo_ra=ra)
                        else:
                            novo = None
                            pendencias.append(f"Circuito {cod}: sem Código RA, nome não gerado")
                    except ValueError as e:
                        novo = None
                        pendencias.append(f"Circuito {cod}: {e}")
                    if novo:
                        mud |= grava(lpol, f, cp, "nome_circuito", novo)
                if mud:
                    lpol.SetFeature(f)
                    n += 1
            alterados["lm_area_circuito_planejado"] = n

        for nome in ("st_circuito_inicio_fim", "st_circuito_planejado", "st_conteiner",
                     "st_quantificacao"):
            lyr = gdb.layer(nome)
            if lyr is None:
                continue
            c = _Gdb.campos(lyr)
            n = 0
            lyr.ResetReading()
            feats = list(lyr)
            for f in feats:
                mud = _forca(f, c, "lote", lote_cod)
                cod = _int(_val(f, c, "codigo_circuito"))
                if cod in ra_por_circ and ra_por_circ[cod] is not None:
                    mud |= grava(lyr, f, c, "codigo_ra", ra_por_circ[cod])
                turno = _val(f, c, "turno")
                if turno and turno.capitalize() in E.TURNOS and turno != turno.capitalize():
                    mud |= _forca(f, c, "turno", turno.capitalize())
                if nome == "st_quantificacao":
                    g = f.GetGeometryRef()
                    if g is not None:
                        mud |= grava(lyr, f, c, "extensao_sarjeta", round(g.Length(), 2))
                if mud:
                    lyr.SetFeature(f)
                    n += 1
            alterados[nome] = n
        gdb = None
    return {"success": True, "gdb": gdb_path, "lote": lote_cod, "backup": copia,
            "feicoes_alteradas": alterados, "pendencias": pendencias[:100],
            "dica": "Rode slu_validar_gdb em seguida para ver o que ainda falta."}


def _forca(f, campos, nome, valor):
    real = campos.get(nome.lower())
    if real is None:
        return False
    if _val(f, campos, nome) == valor:
        return False
    if valor is None:
        f.SetFieldNull(real)
    else:
        f.SetField(real, valor)
    return True


# ================================================================ .xlsx
def slu_exportar_xlsx(gdb_path, saida_xlsx, servico=None, lote=None):
    """Tabela .xlsx com as tabelas de atributos do .gdb (item 3.1.2): uma aba por
    camada, cabeçalhos com os nomes do Anexo G, horários em HH:MM:SS e códigos com
    a descrição do domínio ao lado."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    servico, lote = _servico_lote_de_gdb(gdb_path, servico, lote)
    doms = {k: v[2] for k, v in E.dominios(servico, lote).items()}
    gdb = _Gdb(gdb_path)
    wb = Workbook()
    wb.remove(wb.active)
    resumo = {}
    ordem = [c["nome"] for c in E.esquema(servico, lote)]
    nomes = [n for n in ordem if gdb.layer(n) is not None]
    for nome in nomes:
        lyr = gdb.layer(nome)
        defn = lyr.GetLayerDefn()
        campos = []
        for i in range(defn.GetFieldCount()):
            fd = defn.GetFieldDefn(i)
            if fd.GetName().lower() in ("shape_length", "shape_area"):
                continue
            campos.append(fd)
        ws = wb.create_sheet(nome[:31])
        cab = []
        for fd in campos:
            cab.append(fd.GetAlternativeName() or fd.GetName())
            if fd.GetDomainName() in doms and fd.GetName().lower() not in ("lote",):
                cab.append(f"{fd.GetAlternativeName() or fd.GetName()} (descrição)")
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
            c.alignment = Alignment(wrap_text=True, vertical="center")
        n = 0
        lyr.ResetReading()
        for f in lyr:
            row = []
            for fd in campos:
                idx = f.GetFieldIndex(fd.GetName())
                v = f.GetField(idx) if f.IsFieldSetAndNotNull(idx) else None
                if v is not None and fd.GetType() == ogr.OFTDateTime:
                    v = _hora(v)
                row.append(v)
                if fd.GetDomainName() in doms and fd.GetName().lower() not in ("lote",):
                    tab = doms[fd.GetDomainName()]
                    row.append(tab.get(v, tab.get(str(v))) if v is not None else None)
            ws.append(row)
            n += 1
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, _ in enumerate(cab, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = 18
        resumo[nome] = n
    gdb = None
    os.makedirs(os.path.dirname(os.path.abspath(saida_xlsx)), exist_ok=True)
    wb.save(saida_xlsx)
    return {"success": True, "xlsx": saida_xlsx, "linhas_por_aba": resumo}


def _hora(v):
    """'2024/01/01 07:00:00' -> '07:00:00' (o Anexo G pede só o horário)."""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(v))
    if not m:
        return v
    return f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3) or '00'}"


def slu_gerar_programacao_trimestral(servico, lote, ano, trimestre, saida_xlsx):
    """Tabela .xlsx da programação trimestral dos serviços sob demanda (seção 7,
    Tabela 5): uma linha por dia do trimestre, agrupada por semana, com as colunas
    Semana, Dia, Região Administrativa, Setor, Endereços, Realizado (S/N) e
    Justificativa. RA com lista suspensa das RAs do lote."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    servico, lote = E.normaliza_servico(servico), E.normaliza_lote(lote)
    if servico not in E.SERVICOS_TRIMESTRAIS:
        raise ValueError(f"{servico} não é serviço sob demanda; programação trimestral só para "
                         f"{', '.join(E.SERVICOS_TRIMESTRAIS)}.")
    semanas = E.dias_do_trimestre(ano, trimestre)
    info = E.SERVICOS[servico]
    wb = Workbook()
    ws = wb.active
    ws.title = f"{E.TRIMESTRE_NOME[int(trimestre)]} Tri {ano}"[:31]
    titulo = (f"Serviço: {servico} - {info['nome']} - Lote {lote:02d} - "
              f"{E.TRIMESTRE_NOME[int(trimestre)]} Trimestre {ano}")
    cab = ["Semana", "Dia", "Região Administrativa", "Setor", "Endereços", "Realizado (S/N)",
           "Justificativa (Observação)"]
    ws.append([titulo])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(cab))
    ws.append(cab)
    fino = Side(style="thin", color="808080")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws["A1"].font = Font(bold=True, size=12)
    ws["A1"].alignment = centro
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = centro
        c.border = borda
    linha = 3
    for datas in semanas:
        ini = linha
        for d in datas:
            ws.cell(linha, 2, d.strftime("%d/%m/%y"))
            for col in range(1, len(cab) + 1):
                ws.cell(linha, col).border = borda
                ws.cell(linha, col).alignment = centro
            linha += 1
        ws.cell(ini, 1, E.rotulo_semana(datas))
        if linha - 1 > ini:
            ws.merge_cells(start_row=ini, start_column=1, end_row=linha - 1, end_column=1)
    ultima = linha - 1
    sn = DataValidation(type="list", formula1='"S,N"', allow_blank=True)
    ws.add_data_validation(sn)
    sn.add(f"F3:F{ultima}")
    ras = [E.RA[c] for c in sorted(E.RA_POR_LOTE[lote])]
    listas = wb.create_sheet("Listas")
    for i, nome in enumerate(ras, start=1):
        listas.cell(i, 1, nome)
    listas.sheet_state = "hidden"
    dv = DataValidation(type="list", formula1=f"Listas!$A$1:$A${len(ras)}", allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"C3:C{ultima}")
    for col, w in zip("ABCDEFG", (22, 11, 24, 20, 34, 12, 36)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A3"
    os.makedirs(os.path.dirname(os.path.abspath(saida_xlsx)), exist_ok=True)
    wb.save(saida_xlsx)
    return {"success": True, "xlsx": saida_xlsx, "dias": ultima - 2, "semanas": len(semanas)}


# ================================================================= .docx
def slu_gerar_docx(servico, lote, saida_docx, empresa=None, dados=None, gdb_path=None):
    """Texto .docx do Plano de Serviço (item 3.1.1) em Arial 12 / títulos 14
    (edital, item 7.8), com as seções exigidas. 'dados' preenche as seções
    ({título da seção: texto}); as vazias ficam com a orientação do edital para
    completar. Se 'gdb_path' for informado, inclui o quadro de circuitos."""
    servico, lote = E.normaliza_servico(servico), E.normaliza_lote(lote)
    info = E.SERVICOS[servico]
    dados = {_norm(k): v for k, v in (dados or {}).items()}
    corpo = []
    corpo.append(_p(f"Plano de Serviço — {servico} - {info['nome']}", "Title"))
    corpo.append(_p(f"Lote {lote:02d}" + (f" — {empresa}" if empresa else ""), "Subtitle"))
    corpo.append(_p("Elaborado conforme o Anexo G do Edital do Pregão Presencial nº 90005/2026 "
                    "(SLU-DF) — Roteiro de Elaboração dos Planos de Serviço."))
    arquivos = ["TEXTO (.docx) — este documento"]
    if info["grupo"] != "sem_gdb":
        arquivos.append(f"ARQUIVO VETORIAL File Geodatabase ({E.lote_codigo(servico, lote)}.gdb)")
    arquivos.append("TABELA (.xlsx) — " + ("programação trimestral" if servico in
                                           E.SERVICOS_TRIMESTRAIS else "tabela de atributos"))
    corpo.append(_p("Arquivos que compõem este Plano de Serviço", "Heading1"))
    for a in arquivos:
        corpo.append(_p("• " + a))
    for n, (titulo, orientacao) in enumerate(E.SECOES_DOCX, start=1):
        corpo.append(_p(f"{n}. {titulo}", "Heading1"))
        texto = dados.get(_norm(titulo))
        if texto:
            for par in str(texto).split("\n"):
                corpo.append(_p(par))
        else:
            corpo.append(_p(f"[Preencher: {orientacao}]", italico=True, cor="7F7F7F"))
    if gdb_path:
        corpo.append(_p("Quadro de circuitos", "Heading1"))
        corpo.append(_tabela_circuitos(gdb_path, servico, lote))
    _escreve_docx(saida_docx, "".join(corpo))
    pendentes = [t for t, _ in E.SECOES_DOCX if not dados.get(_norm(t))]
    return {"success": True, "docx": saida_docx, "secoes_a_preencher": pendentes}


def _p(texto, estilo=None, italico=False, cor=None):
    ppr = f'<w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>' if estilo else ""
    rpr = ""
    if italico or cor:
        rpr = "<w:rPr>" + ("<w:i/>" if italico else "") + \
              (f'<w:color w:val="{cor}"/>' if cor else "") + "</w:rPr>"
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{_xml(str(texto))}</w:t></w:r></w:p>'


def _tabela_circuitos(gdb_path, servico, lote):
    gdb = _Gdb(gdb_path)
    lyr = gdb.layer("lm_area_circuito_planejado")
    cab = ["Código", "Nome do Circuito", "Frequência", "Início", "Término", "Turno",
           "Equipamento"]
    linhas = []
    if lyr is not None:
        c = _Gdb.campos(lyr)
        lyr.ResetReading()
        for f in lyr:
            eq = _int(_val(f, c, "id_tipo_equipamento"))
            linhas.append([_val(f, c, "codigo_circuito"), _val(f, c, "nome_circuito"),
                           _val(f, c, "frequencia"),
                           _hora(_val(f, c, "horario_inicio") or ""),
                           _hora(_val(f, c, "horario_termino") or ""),
                           _val(f, c, "turno"), E.EQUIPAMENTOS.get(eq, eq)])
    gdb = None
    linhas.sort(key=lambda r: r[0] or 0)

    def cel(t, neg=False):
        r = "<w:rPr><w:b/><w:sz w:val=\"18\"/></w:rPr>" if neg else \
            "<w:rPr><w:sz w:val=\"18\"/></w:rPr>"
        return (f'<w:tc><w:p><w:r>{r}<w:t xml:space="preserve">'
                f'{_xml("" if t is None else str(t))}</w:t></w:r></w:p></w:tc>')
    borda = "".join(f'<w:{b} w:val="single" w:sz="4" w:color="808080"/>'
                    for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    xml = (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
           f'<w:tblBorders>{borda}</w:tblBorders></w:tblPr>')
    xml += "<w:tr>" + "".join(cel(h, True) for h in cab) + "</w:tr>"
    for r in linhas:
        xml += "<w:tr>" + "".join(cel(v) for v in r) + "</w:tr>"
    return xml + "</w:tbl><w:p/>"


def _escreve_docx(path, corpo_xml):
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}>'
                 f'<w:body>{corpo_xml}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                 '<w:pgMar w:top="1418" w:right="1134" w:bottom="1134" w:left="1701" '
                 'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    fonte = E.FONTE_DOCX
    corpo_sz, tit_sz = E.TAM_CORPO_PT * 2, E.TAM_TITULO_PT * 2
    rf = f'<w:rFonts w:ascii="{fonte}" w:hAnsi="{fonte}" w:cs="{fonte}" w:eastAsia="{fonte}"/>'
    estilos = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles {ns}>'
        f'<w:docDefaults><w:rPrDefault><w:rPr>{rf}<w:sz w:val="{corpo_sz}"/>'
        f'<w:szCs w:val="{corpo_sz}"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/>'
        '<w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="60"/></w:pPr>'
        f'<w:rPr><w:b/><w:sz w:val="{tit_sz + 4}"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>'
        f'<w:rPr><w:sz w:val="{tit_sz}"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/>'
        '<w:spacing w:before="240" w:after="120"/><w:jc w:val="left"/><w:outlineLvl w:val="0"/>'
        f'</w:pPr><w:rPr><w:b/><w:sz w:val="{tit_sz}"/><w:szCs w:val="{tit_sz}"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style>'
        '</w:styles>')
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", documento)
        z.writestr("word/styles.xml", estilos)
        z.writestr("word/_rels/document.xml.rels", doc_rels)


# ============================================================== shapefile
def slu_exportar_shapefile(gdb_path, pasta_saida, servico=None, lote=None):
    """Exporta as camadas do .gdb para shapefile (edital, item 7.8, pede mapas em
    .shp). Atenção: o shapefile corta nomes de campo em 10 caracteres; o mapa de
    nomes vai no retorno."""
    servico, lote = _servico_lote_de_gdb(gdb_path, servico, lote)
    codigo = E.lote_codigo(servico, lote)
    pasta = os.path.join(pasta_saida, f"{codigo}_shp")
    os.makedirs(pasta, exist_ok=True)
    gdb = _Gdb(gdb_path)
    saida = {}
    with _exc():
        for cam in E.esquema(servico, lote):
            lyr = gdb.layer(cam["nome"])
            if lyr is None:
                continue
            arq = os.path.join(pasta, f"{codigo}_{cam['nome']}.shp")
            gdal.VectorTranslate(arq, gdb.ds, layers=[lyr.GetName()], format="ESRI Shapefile",
                                 layerName=f"{codigo}_{cam['nome']}",
                                 options=["-lco", "ENCODING=UTF-8", "-overwrite"])
            sds = gdal.OpenEx(arq, gdal.OF_VECTOR)
            sl = sds.GetLayer(0)
            novos = [sl.GetLayerDefn().GetFieldDefn(i).GetName()
                     for i in range(sl.GetLayerDefn().GetFieldCount())]
            orig = [lyr.GetLayerDefn().GetFieldDefn(i).GetName()
                    for i in range(lyr.GetLayerDefn().GetFieldCount())]
            saida[cam["nome"]] = {"arquivo": arq, "feicoes": sl.GetFeatureCount(),
                                  "campos_renomeados": {o: n for o, n in zip(orig, novos)
                                                        if o != n}}
            sds = None
    gdb = None
    return {"success": True, "pasta": pasta, "camadas": saida}


# ===================================================== plano completo e info
def slu_gerar_plano(servico, lote, pasta_saida, ano=None, trimestre=None, gdb_existente=None,
                    empresa=None, dados_texto=None, limite_df=None, turnos=None,
                    numero_equipes=None, carregar=True):
    """Gera de uma vez os arquivos do Plano de Serviço exigidos no item 3.1:
    .gdb (vazio no padrão, ou usa 'gdb_existente'), .xlsx (tabela de atributos ou
    programação trimestral) e .docx. Pasta: <pasta_saida>/<Pn>_<sigla+lote>."""
    servico, lote = E.normaliza_servico(servico), E.normaliza_lote(lote)
    info = E.SERVICOS[servico]
    rotulo = E.lote_codigo(servico, lote) if info["sigla"] else f"Lote{lote:02d}"
    pasta = os.path.join(pasta_saida, f"{servico}_{rotulo}")
    os.makedirs(pasta, exist_ok=True)
    out = {"success": True, "pasta": pasta, "arquivos": {}}
    gdb = None
    if info["grupo"] != "sem_gdb":
        if gdb_existente:
            gdb = gdb_existente
            out["arquivos"]["gdb"] = gdb
        else:
            alvo = os.path.join(pasta, f"{rotulo}.gdb")
            if os.path.exists(alvo):
                gdb = alvo
                out["arquivos"]["gdb"] = alvo
                out["aviso"] = "Já havia um .gdb na pasta; foi mantido."
            else:
                r = slu_criar_gdb(servico, lote, pasta, carregar=carregar, limite_df=limite_df,
                                  turnos=turnos, numero_equipes=numero_equipes)
                gdb = r["gdb"]
                out["arquivos"]["gdb"] = gdb
    if servico in E.SERVICOS_TRIMESTRAIS:
        hoje = _dt.date.today()
        ano = int(ano or hoje.year)
        trimestre = int(trimestre or (hoje.month - 1) // 3 + 1)
        x = os.path.join(pasta, f"{rotulo}_programacao_{ano}_T{trimestre}.xlsx")
        slu_gerar_programacao_trimestral(servico, lote, ano, trimestre, x)
        out["arquivos"]["xlsx_programacao"] = x
    if gdb:
        x = os.path.join(pasta, f"{rotulo}_tabela_atributos.xlsx")
        slu_exportar_xlsx(gdb, x, servico, lote)
        out["arquivos"]["xlsx_atributos"] = x
    d = os.path.join(pasta, f"{servico}_{rotulo}_plano_de_servico.docx")
    r = slu_gerar_docx(servico, lote, d, empresa=empresa, dados=dados_texto,
                       gdb_path=gdb if gdb and info["grupo"] != "demanda" else None)
    out["arquivos"]["docx"] = d
    out["secoes_docx_a_preencher"] = r["secoes_a_preencher"]
    return out


def slu_info_edital(servico=None):
    """Resumo das regras do Anexo G: serviços, siglas, camadas, campos, códigos."""
    if servico:
        s = E.normaliza_servico(servico)
        info = dict(E.SERVICOS[s])
        info["servico"] = s
        info["camadas"] = [{"nome": c["nome"], "geometria": c["geometria"],
                            "campos": [(f["nome"], f["apelido"] or f["nome"], f["tipo"])
                                       for f in c["campos"]]}
                           for c in E.esquema(s, 1)]
        if info["grupo"] == "coleta":
            info["codigo_circuito"] = ("6 dígitos: lote + tipo de serviço "
                                       f"({info['tipos_servico']}) + sequência")
        elif info["grupo"] == "varricao":
            info["codigo_circuito"] = f"6 dígitos: lote + {info['codigo']} + sequência"
        elif info["grupo"] == "demanda":
            info["codigo_circuito"] = (f"5 dígitos: lote + {info['codigo']} + turno "
                                       "(01 Diurno, 02 Noturno)")
        info["programacao_trimestral"] = s in E.SERVICOS_TRIMESTRAIS
        return info
    return {
        "servicos": {k: {"nome": v["nome"], "sigla": v["sigla"], "grupo": v["grupo"]}
                     for k, v in E.SERVICOS.items()},
        "crs": f"EPSG:{E.EPSG} (SIRGAS 2000 / UTM 23S)",
        "arquivos_por_plano": ".docx (texto), .xlsx (atributos ou programação trimestral), "
                              ".gdb (exceto P9)",
        "nome_circuito": "Nome RA + código + lógica (D1 diário; S+SEG semanal; A+n+iniciais "
                         "alternado; M/Q + dia para mensal/quinzenal). Plano Piloto: 'Asa Norte' "
                         "ou 'Asa Sul'. Sob demanda: 'Lote 0N' + código + lógica",
        "linhas": "single-part, 50-130 m (coleta) ou 50-200 m (varrição)",
        "ra": E.RA, "ra_por_lote": {k: sorted(v) for k, v in E.RA_POR_LOTE.items()},
        "equipamentos_tabela4": E.EQUIPAMENTOS,
    }


TOOLS = {
    "slu_info_edital": slu_info_edital,
    "slu_criar_gdb": slu_criar_gdb,
    "slu_validar_gdb": slu_validar_gdb,
    "slu_preencher_atributos": slu_preencher_atributos,
    "slu_exportar_xlsx": slu_exportar_xlsx,
    "slu_gerar_programacao_trimestral": slu_gerar_programacao_trimestral,
    "slu_gerar_docx": slu_gerar_docx,
    "slu_exportar_shapefile": slu_exportar_shapefile,
    "slu_gerar_plano": slu_gerar_plano,
}
