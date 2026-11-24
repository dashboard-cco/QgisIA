# -*- coding: utf-8 -*-
"""
Testes das regras do Anexo G e das ações de arquivo.

Rodar com o Python do QGIS (precisa de osgeo e openpyxl, não precisa do QGIS aberto):
    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_slu.py
"""
import os
import shutil
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(AQUI, "..", "src", "qgis_ia")
sys.path.insert(0, PLUGIN)
sys.path.insert(0, os.path.join(PLUGIN, "actions"))

import edital_slu as E  # noqa: E402
import slu  # noqa: E402
from osgeo import gdal, ogr  # noqa: E402

FALHAS = []


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


# ------------------------------------------------ exemplos do próprio Anexo G
SEG, TER, QUA, QUI, SEX, SAB, DOM = range(7)


def dias(*ativos):
    return [1 if i in ativos else 0 for i in range(7)]


def test_nomes_do_anexo():
    check(E.nome_circuito("P1", 102535, dias(TER, QUI), codigo_ra=18) == "Lago Norte 102535 A2TQ",
          "exemplo Lago Norte A2TQ")
    check(E.nome_circuito("P1", 256216, dias(*range(7)), codigo_ra=32)
          == "Sol Nascente/Pôr do Sol 256216 D1", "exemplo Sol Nascente D1")
    check(E.nome_circuito("P1", 380211, dias(SEG, QUA, SEX), codigo_ra=2) == "Gama 380211 A3SQS",
          "exemplo Gama A3SQS")
    check(E.nome_circuito("P5", 236666, dias(SEG), codigo_ra=12) == "Samambaia 236666 SSEG",
          "exemplo Samambaia SSEG")
    check(E.nome_circuito("P6", 145695, dias(SEG, QUA, SEX), codigo_ra=11)
          == "Cruzeiro 145695 A3SQS", "exemplo Cruzeiro A3SQS")
    check(E.nome_circuito("P5", 337524, dias(*range(6)), codigo_ra=2) == "Gama 337524 D1",
          "diário seg-sáb = D1")
    check(E.nome_circuito("P3", 11501, dias(*range(6)), lote=1) == "Lote 01 11501 D1",
          "exemplo sob demanda D1")
    check(E.nome_circuito("P4", 21602, dias(DOM), lote=2) == "Lote 02 21602 SDOM",
          "exemplo sob demanda SDOM")
    check(E.logica_circuito(dias(TER), ciclo=1) == "QTER", "quinzenal")
    check(E.logica_circuito(dias(SEG), ciclo=2) == "MSEG", "mensal")


def test_codigos():
    check(E.valida_codigo_circuito("P1", 1, 102535, 0) == [], "código coleta ok")
    check(E.valida_codigo_circuito("P1", 2, 102535, 0) != [], "lote errado detectado")
    check(E.valida_codigo_circuito("P2", 1, 102535) != [], "CS com dígito de CC detectado")
    check(E.valida_codigo_circuito("P1", 1, 10253) != [], "5 dígitos em coleta detectado")
    check(E.valida_codigo_circuito("P5", 2, 230001) == [], "varrição ok")
    check(E.valida_codigo_circuito("P6", 2, 230001) != [], "VE com dígito de VA detectado")
    for cod, s, l in ((11501, "P3", 1), (21602, "P4", 2), (31701, "P7", 3), (11802, "P8", 1),
                      (22001, "P10", 2), (32102, "P11", 3), (12201, "P12", 1)):
        check(E.valida_codigo_circuito(s, l, cod) == [], f"exemplo sob demanda {cod}")
    check(E.codigo_circuito_demanda("P4", 2, "Noturno") == 21602, "código demanda noturno")


def test_frequencia_e_trimestre():
    check(E.frequencia_texto(dias(SEG, QUA)) == "Segunda e Quarta", "freq 2 dias")
    check(E.frequencia_texto(dias(TER, QUI, SAB)) == "Terça, Quinta e Sábado", "freq 3 dias")
    sem = E.dias_do_trimestre(2025, 2)
    check(sum(len(s) for s in sem) == 91, "2º tri 2025 tem 91 dias")
    alvo = [s for s in sem if s[0].day == 2 and s[0].month == 6][0]
    check(E.rotulo_semana(alvo) == "2 a 8 de junho de 2025", "rótulo da Tabela 5")
    check(E.normaliza_servico("cc") == "P1" and E.normaliza_servico("10") == "P10"
          and E.normaliza_servico("VE02") == "P6", "normaliza serviço")


# ------------------------------------------------ ciclo completo em arquivo
def _feat(lyr, wkt, **attrs):
    f = ogr.Feature(lyr.GetLayerDefn())
    f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
    for k, v in attrs.items():
        f.SetField(k, v)
    lyr.CreateFeature(f)


def test_varricao_ponta_a_ponta(tmp):
    r = slu.slu_criar_gdb("P5", 1, tmp, carregar=False)
    gdb = r["gdb"]
    check(os.path.basename(gdb) == "VA01.gdb", "nome do arquivo VA01.gdb")
    ds = gdal.OpenEx(gdb, gdal.OF_VECTOR | gdal.OF_UPDATE)
    nomes = sorted(ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount()))
    check(nomes == ["lm_area_circuito_planejado", "st_circuito_inicio_fim",
                    "st_circuito_planejado", "st_quantificacao"], f"camadas VA: {nomes}")
    check("cod_ra" in (ds.GetFieldDomainNames() or []), "domínio cod_ra gravado")
    pol = ds.GetLayerByName("lm_area_circuito_planejado")
    check(pol.GetSpatialRef().GetAuthorityCode(None) == "31983", "CRS 31983")
    fd = pol.GetLayerDefn().GetFieldDefn(pol.GetLayerDefn().GetFieldIndex("codigo_ra"))
    check(fd.GetAlternativeName() == "Código RA" and fd.GetDomainName() == "cod_ra",
          "apelido e domínio do campo")

    x0, y0, cod = 190000, 8250000, 130001  # lote 1, varrição manual (3), Cruzeiro (RA 11)
    _feat(pol, f"MULTIPOLYGON((({x0-20} {y0-20},{x0+320} {y0-20},{x0+320} {y0+20},"
               f"{x0-20} {y0+20},{x0-20} {y0-20})))",
          codigo_circuito=cod, codigo_ra=11, enderecamento="SHCES Quadra 1",
          horario_inicio="2024/01/01 06:30:00", horario_termino="2024/01/01 14:50:00",
          segunda=1, quarta=1, sexta=1, id_tipo_equipamento=6,
          local_destinacao="Transbordo Sobradinho", turno="Diurno")
    lin = ds.GetLayerByName("st_circuito_planejado")
    for i in range(3):
        _feat(lin, f"MULTILINESTRING(({x0+100*i} {y0},{x0+100*(i+1)} {y0}))",
              codigo_circuito=cod, deslocamento=0)
    pts = ds.GetLayerByName("st_circuito_inicio_fim")
    _feat(pts, f"POINT({x0} {y0})", codigo_circuito=cod, endereco="SHCES Q1",
          horario="2024/01/01 06:30:00", turno="diurno", tipo=1)
    _feat(pts, f"POINT({x0+300} {y0})", codigo_circuito=cod, endereco="SHCES Q1",
          horario="2024/01/01 14:50:00", turno="Diurno", tipo=0)
    q = ds.GetLayerByName("st_quantificacao")
    _feat(q, f"MULTILINESTRING(({x0} {y0+5},{x0+300} {y0+5}))", codigo_circuito=cod)
    ds = None

    antes = slu.slu_validar_gdb(gdb)
    check(antes["erros"] > 0, "validação acusa campos vazios antes de preencher")

    p = slu.slu_preencher_atributos(gdb, backup=True)
    check(p["backup"] and os.path.isdir(p["backup"]), "backup criado")
    depois = slu.slu_validar_gdb(gdb, relatorio_xlsx=os.path.join(tmp, "rel.xlsx"))
    if depois["erros"]:
        for i in depois["itens"]:
            print("   ", i["nivel"], i["regra"], i["mensagem"])
    check(depois["erros"] == 0, f"sem erros depois de preencher (tem {depois['erros']})")
    check(os.path.exists(os.path.join(tmp, "rel.xlsx")), "relatório xlsx gravado")

    ds = gdal.OpenEx(gdb, gdal.OF_VECTOR)
    f = next(iter(ds.GetLayerByName("lm_area_circuito_planejado")))
    check(f.GetField("nome_circuito") == "Cruzeiro 130001 A3SQS",
          f"nome gerado: {f.GetField('nome_circuito')}")
    check(f.GetField("frequencia") == "Segunda, Quarta e Sexta", "frequência gerada")
    check(f.GetField("lote") == "VA01" and f.GetField("id_tipo_servico") == 3, "lote/tipo")
    qf = next(iter(ds.GetLayerByName("st_quantificacao")))
    check(abs(qf.GetField("extensao_sarjeta") - 300) < 0.01, "extensão da sarjeta")
    tf = [g.GetField("turno") for g in ds.GetLayerByName("st_circuito_inicio_fim")]
    check(tf == ["Diurno", "Diurno"], "turno capitalizado")
    ds = None

    # erros propositais: linha longa demais e nome errado
    ds = gdal.OpenEx(gdb, gdal.OF_VECTOR | gdal.OF_UPDATE)
    lin = ds.GetLayerByName("st_circuito_planejado")
    _feat(lin, f"MULTILINESTRING(({x0} {y0+10},{x0+250} {y0+10}))", lote="VA01",
          codigo_circuito=cod, codigo_ra=11, deslocamento=0)
    ds = None
    r2 = slu.slu_validar_gdb(gdb)
    check(r2["por_regra"].get("erro:comprimento") == 1, "linha > 200 m detectada")

    x = slu.slu_exportar_xlsx(gdb, os.path.join(tmp, "VA01.xlsx"))
    check(x["linhas_por_aba"]["st_circuito_planejado"] == 4, "xlsx com as 4 linhas")
    from openpyxl import load_workbook
    ws = load_workbook(x["xlsx"])["lm_area_circuito_planejado"]
    cab = [c.value for c in ws[1]]
    check("Horário Início" in cab, "cabeçalho com apelido")
    check(ws.cell(2, cab.index("Horário Início") + 1).value == "06:30:00", "hora HH:MM:SS")

    d = slu.slu_gerar_docx("P5", 1, os.path.join(tmp, "VA01.docx"), empresa="Empresa X",
                           dados={"Horários": "06h30 às 14h50"}, gdb_path=gdb)
    with zipfile.ZipFile(d["docx"]) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        est = z.read("word/styles.xml").decode("utf-8")
    check("Cruzeiro 130001 A3SQS" in doc and "06h30 às 14h50" in doc, "docx com conteúdo")
    check('w:ascii="Arial"' in est and 'w:val="24"' in est, "docx Arial 12")
    check("Horários" not in d["secoes_a_preencher"], "seção preenchida não fica pendente")

    s = slu.slu_exportar_shapefile(gdb, tmp)
    check(s["camadas"]["st_circuito_planejado"]["feicoes"] == 4, "shapefile exportado")


def test_coleta_e_demanda(tmp):
    r = slu.slu_criar_gdb("P2", 3, tmp, carregar=False)
    ds = gdal.OpenEx(r["gdb"], gdal.OF_VECTOR)
    nomes = sorted(ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount()))
    check(nomes == ["lm_area_circuito_planejado", "st_circuito_inicio_fim",
                    "st_circuito_planejado", "st_conteiner"], f"camadas CS: {nomes}")
    check(os.path.basename(r["gdb"]) == "CS03.gdb", "nome CS03.gdb")
    ds = None
    try:
        slu.slu_criar_gdb("P2", 3, tmp, carregar=False)
        check(False, "não deveria sobrescrever sem pedir")
    except FileExistsError:
        pass

    # limite do DF fictício em EPSG:4674 para testar a reprojeção
    lim = os.path.join(tmp, "df.geojson")
    with open(lim, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","crs":{"type":"name","properties":{"name":'
                 '"urn:ogc:def:crs:EPSG::4674"}},"features":[{"type":"Feature","properties":{},'
                 '"geometry":{"type":"Polygon","coordinates":[[[-48.2,-15.9],[-47.4,-15.9],'
                 '[-47.4,-15.6],[-48.2,-15.6],[-48.2,-15.9]]]}}]}')
    plano = slu.slu_gerar_plano("P10", 2, tmp, ano=2026, trimestre=1, limite_df=lim,
                                turnos=["Diurno", "Noturno"], numero_equipes=3, carregar=False)
    arqs = plano["arquivos"]
    check(set(arqs) == {"gdb", "xlsx_programacao", "xlsx_atributos", "docx"},
          f"arquivos do plano P10: {set(arqs)}")
    v = slu.slu_validar_gdb(arqs["gdb"])
    regras = set(v["por_regra"])
    check("erro:horario" in regras, "demanda sem horário acusa erro de horário")
    check(not any(k.startswith("erro:") and k not in ("erro:horario", "erro:equipamento")
                  for k in regras), f"demanda: só horário/equipamento pendentes ({regras})")
    ds = gdal.OpenEx(arqs["gdb"], gdal.OF_VECTOR)
    fs = list(ds.GetLayerByName("lm_area_circuito_planejado"))
    check([f.GetField("nome_circuito") for f in fs] == ["Lote 02 22001 D1", "Lote 02 22002 D1"],
          "nomes sob demanda")
    env = fs[0].GetGeometryRef().GetEnvelope()
    check(150000 < env[0] < 260000 and 8.2e6 < env[2] < 8.3e6, f"reprojetado p/ UTM: {env}")
    ds = None
    from openpyxl import load_workbook
    ws = load_workbook(arqs["xlsx_programacao"]).worksheets[0]
    check(ws.max_row == 2 + 90, f"programação 1º tri 2026 = 90 dias (linhas {ws.max_row})")
    check(ws["A1"].value.startswith("Serviço: P10 - Pintura"), "título da programação")

    p9 = slu.slu_gerar_plano("P9", 1, tmp, ano=2026, trimestre=2, carregar=False)
    check("gdb" not in p9["arquivos"] and "xlsx_programacao" in p9["arquivos"],
          "P9 sem .gdb, com programação")


if __name__ == "__main__":
    test_nomes_do_anexo()
    test_codigos()
    test_frequencia_e_trimestre()
    tmp = tempfile.mkdtemp(prefix="qgis_ia_slu_")
    try:
        test_varricao_ponta_a_ponta(tmp)
        test_coleta_e_demanda(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
    sys.exit(1 if FALHAS else 0)
