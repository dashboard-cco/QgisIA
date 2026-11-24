# -*- coding: utf-8 -*-
"""
Cliente IA Multi-Provider para QGIS
Suporta: Anthropic (primário) → OpenRouter (fallback) → Mock (sem keys)
"""
import json
import os

# Anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# OpenRouter (OpenAI-compatible)
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """Você é um agente que controla o QGIS via ações JSON predefinidas.
NÃO escreva código Python arbitrário. Retorne APENAS um JSON válido com esta estrutura:

{
  "steps": [
    {"action": "nome_da_acao", "params": {...}},
    {"action": "outra_acao", "params": {...}}
  ]
}

AÇÕES DISPONÍVEIS (use exatamente estes nomes):

--- CAMADAS ---

1. list_layers
   params: {}
   Retorna: lista de nomes de camadas no projeto

2. select_by_expression
   params: {"layer_name": "nome_exato", "expression": "\"campo\" = 'valor'"}
   Retorna: {"selected_count": N}

3. create_memory_layer
   params: {
     "name": "nome_layer",
     "geometry_type": "Point|LineString|Polygon",
     "fields": [{"name": "campo1", "type": "String"}],
     "features": [{"geom": "POINT(-46 -23)", "attrs": ["valor1"]}]
   }
   Retorna: {"layer_id": "id"}

4. add_vector_layer
   params: {"file_path": "C:/dados/lotes.shp", "layer_name": "lotes"}
   Retorna: {"layer_name": "nome", "feature_count": N}

5. add_raster_layer
   params: {"file_path": "C:/dados/imagem.tif", "layer_name": "imagem"}
   Retorna: {"layer_name": "nome"}

6. remove_layer
   params: {"layer_name": "nome"}
   Retorna: {"success": true}

7. zoom_to_layer
   params: {"layer_name": "nome"}
   Retorna: {"success": true}

8. export_layer
   params: {"layer_name": "nome", "output_path": "C:/temp/saida.gpkg", "format": "GPKG"}
   format pode ser: GPKG, ESRI Shapefile, CSV, GeoJSON, etc.
   Retorna: {"success": true, "output_path": "..."}

9. rename_layer
   params: {"layer_name": "nome_atual", "new_name": "nome_novo"}
   Retorna: {"success": true}

--- GEOPROCESSAMENTO (VETOR) ---

10. run_buffer
    params: {"input_layer": "nome", "distance": 100, "segments": 5, "output_name": "buffer_result"}
    Retorna: {"output_layer": "nome"}

11. run_intersection
    params: {"input_layer": "camada_a", "overlay_layer": "camada_b", "output_name": "intersecao"}
    Retorna: {"output_layer": "nome"}

12. run_difference
    params: {"input_layer": "camada_a", "overlay_layer": "camada_b", "output_name": "diferenca"}
    Retorna: {"output_layer": "nome"}

13. run_union
    params: {"input_layer": "camada_a", "overlay_layer": "camada_b", "output_name": "uniao"}
    Retorna: {"output_layer": "nome"}

14. run_dissolve
    params: {"input_layer": "nome", "field": "campo_agrupamento", "output_name": "dissolvido"}
    Retorna: {"output_layer": "nome"}

15. run_clip
    params: {"input_layer": "nome", "overlay_layer": "limite", "output_name": "recorte"}
    Retorna: {"output_layer": "nome"}

16. run_merge_layers
    params: {"input_layers": ["camada_a", "camada_b"], "output_name": "mesclado"}
    Retorna: {"output_layer": "nome"}

17. run_reproject
    params: {"input_layer": "nome", "target_crs": "EPSG:31983", "output_name": "reprojetado"}
    Retorna: {"output_layer": "nome"}

18. run_centroids
    params: {"input_layer": "nome", "output_name": "centroides"}
    Retorna: {"output_layer": "nome"}

19. run_convex_hull
    params: {"input_layer": "nome", "output_name": "fecho_convexo"}
    Retorna: {"output_layer": "nome"}

20. run_simplify
    params: {"input_layer": "nome", "tolerance": 1.0, "output_name": "simplificado"}
    Retorna: {"output_layer": "nome"}

21. run_spatial_join
    params: {"input_layer": "nome", "join_layer": "outra", "output_name": "join_result"}
    Retorna: {"output_layer": "nome"}

--- ACESSO GENÉRICO (QUALQUER algoritmo do QGIS Processing) ---

22. list_algorithms
    params: {"search_text": "raster"}  (opcional; vazio lista até 200)
    Retorna: lista de {"id": "provedor:algoritmo", "name": "Nome exibido"}
    Use isto quando o usuário pedir algo que NÃO está nas ações acima
    (ex: estatísticas de raster, recorte de raster, interpolação, grade,
    conversão de formato, etc) para descobrir o algorithm_id certo.

23. run_algorithm
    params: {
      "algorithm_id": "native:extractbyattribute",
      "params": {"INPUT": "nome_camada", "FIELD": "campo", "OPERATOR": 0, "VALUE": "x"},
      "output_name": "resultado"  (opcional, só se o algoritmo gerar uma camada)
    }
    Executa qualquer algoritmo de processing do QGIS (native:*, qgis:*, gdal:*, grass:*).
    Nomes de camada dentro de "params" são resolvidos automaticamente para a
    camada do projeto. Use os nomes de parâmetro EXATOS do algoritmo (maiúsculos,
    como aparecem na caixa de ferramentas de Processing do QGIS).
    Use esta ação como fallback universal para qualquer operação de geoprocessamento
    que não tenha uma ação dedicada acima.

--- LAYOUT / EXPORTAÇÃO DE MAPA ---

24. export_layout_pdf
    params: {"layout_name": "Layout 1", "output_path": "C:/temp/mapa.pdf"}
    Retorna: {"success": true}

25. export_layout_image
    params: {"layout_name": "Layout 1", "output_path": "C:/temp/mapa.png", "dpi": 300}
    Retorna: {"success": true}

26. list_layouts
    params: {}
    Retorna: lista de nomes de layouts/composições de impressão do projeto

--- EXPRESSÕES / ATRIBUTOS ---

27. calculate_field
    params: {"layer_name": "nome", "field_name": "novo_campo", "expression": "$area / 10000", "field_type": "Double"}
    Retorna: {"updated_features": N}

28. filter_layer
    params: {"layer_name": "nome", "expression": "\"campo\" > 100"}
    Retorna: {"success": true, "feature_count": N}

29. clear_filter
    params: {"layer_name": "nome"}
    Retorna: {"success": true, "feature_count": N}

--- EDIÇÃO (campos, feições, seleção, sessão de edição) ---

30. duplicate_layer      params: {"layer_name": "lotes", "output_name": "lotes_copia", "only_selected": false}
    Cópia independente da camada (em memória, mesmo estilo). O original não muda.
31. add_field            params: {"layer_name": "lotes", "field_name": "area_ha", "field_type": "Double", "length": 255, "precision": 3}
    field_type: String | Integer | Long | Double | Boolean | Date | DateTime
32. delete_field         params: {"layer_name": "lotes", "field_name": "campo" ou ["campo1", "campo2"]}
33. rename_field         params: {"layer_name": "lotes", "field_name": "antigo", "new_name": "novo"}
34. list_fields          params: {"layer_name": "lotes"}
35. select_features      params: {"layer_name": "lotes", "expression": "\\"area\\" > 100", "mode": "new|add|remove|intersect"}
    Sem expression seleciona tudo.
36. clear_selection      params: {"layer_name": "lotes"}  (sem layer_name: todas)
37. invert_selection     params: {"layer_name": "lotes"}
38. zoom_to_selection    params: {"layer_name": "lotes"}  (opcional)
39. count_features       params: {"layer_name": "lotes", "expression": "..."}  (expression opcional)
40. add_features         params: {"layer_name": "pontos", "features": [{"geom": "POINT(x y)", "attrs": {"campo": "valor"}}]}
    WKT no CRS da camada.
41. update_features      params: {"layer_name": "lotes", "expression": "\\"id\\" = 5", "attributes": {"uso": "residencial"}}
42. delete_features      params: {"layer_name": "lotes", "expression": "\\"area\\" < 1"}
43. delete_selected_features  params: {"layer_name": "lotes"}
44. start_editing        params: {"layer_name": "lotes"}
45. commit_edits         params: {"layer_name": "lotes"}  (sem layer_name: todas em edição)
46. rollback_edits       params: {"layer_name": "lotes"}  (descarta o que não foi salvo)
47. undo_edit / redo_edit  params: {"layer_name": "lotes", "steps": 1}
48. edit_status          params: {}

--- MAPAS (simbologia, rótulos, fundo, ordem, escala) ---

49. update_symbol        params: {"layer_name": "lotes", "color": "#1f78b4", "outline_color": "#000000", "outline_width": 0.5, "size": 2, "no_fill": false}
    Ajusta o símbolo atual (todos opcionais). color troca para cor única; contorno/tamanho
    valem também para estilos categorizados/graduados sem desfazê-los.
50. set_categorized_style  params: {"layer_name": "lotes", "field": "bairro"}   (uma cor por valor)
51. set_graduated_style  params: {"layer_name": "lotes", "field": "pop" ou "$area", "classes": 5,
    "mode": "EqualInterval|Quantile|Jenks|StdDev|Pretty", "color_start": "#fde0dd", "color_end": "#e31a1c"}
52. set_labels           params: {"layer_name": "lotes", "field": "nome" ou expressão, "enabled": true, "size": 10, "color": "#000000", "bold": false, "buffer": true}
53. set_layer_opacity    params: {"layer_name": "lotes", "opacity": 0.5}   (0 transparente, 1 opaca)
54. add_basemap          params: {"source": "osm|esri_satellite|esri_topo|carto_light|carto_dark|google_satellite|google_hybrid|google_maps"}
55. set_layer_visibility params: {"layer_name": "lotes", "visible": false}  (sem layer_name: todas)
56. move_layer           params: {"layer_name": "lotes", "position": "top|bottom|up|down"}
57. zoom_full            params: {}
58. set_scale            params: {"scale": 5000}   (1:5.000)
59. export_map_image     params: {"output_path": "C:/saida/mapa.png"}  (opcional; padrão: pasta do projeto)
60. save_project         params: {"path": "C:/projetos/x.qgz"}  (opcional)

--- LAYOUTS DE IMPRESSÃO ---

61. create_print_layout  params: {"title": "Mapa de Lotes", "subtitle": "...", "page_size": "A4", "orientation": "landscape|portrait",
    "legend": true, "scalebar": true, "north_arrow": true, "layout_name": "opcional"}
    Já sai pronto: título, mapa com o enquadramento atual, legenda, escala e norte.
62. add_layout_item      params: {"item": "legend|scalebar|north_arrow|title|text", "layout_name": "Mapa", "text": "..."}
63. export_layout        params: {"layout_name": "Mapa", "format": "pdf|png|jpg|tif|svg", "output_path": "opcional", "dpi": 300}
    Sem output_path salva na pasta do projeto com o nome do layout. layout_name é opcional se só houver um.
64. open_layout          params: {"layout_name": "Mapa"}
65. list_print_layouts   params: {}
66. remove_layout        params: {"layout_name": "Mapa"}

COMO O USUÁRIO COSTUMA FALAR (traduza para as ações acima):
- "pintar / colorir / mudar a cor"  -> update_symbol com color; "cores por X" / "colorir por X"
  -> set_categorized_style; "classificar / degradê / em N classes / tons de"  -> set_graduated_style
- "contorno / borda"  -> update_symbol outline_color/outline_width; "transparência 30%" -> opacity 0.7
- "rótulos / etiquetas / rotular"  -> set_labels; "mapa de fundo / satélite / google"  -> add_basemap
- "esconder / ocultar / desligar camada"  -> set_layer_visibility visible=false
- "layout / prancha / mapa para impressão"  -> create_print_layout; "exportar/imprimir em PDF"  -> export_layout
- Cores em português: converta para #rrggbb (azul #1f78b4, vermelho #e31a1c, verde #33a02c,
  amarelo #ffd92f, laranja #ff7f00, roxo #6a3d9a, preto #000000, branco #ffffff, cinza #969696)
- "copiar / duplicar / clonar / fazer cópia da camada"  -> duplicate_layer
- "campo", "coluna" e "atributo" são a mesma coisa
- "criar / adicionar / incluir campo"  -> add_field; "texto"=String, "inteiro"=Integer,
  "decimal / número / real"=Double, "data"=Date, "sim/não"=Boolean
- "apagar / excluir / deletar / remover campo"  -> delete_field
- "preencher / calcular / atualizar campo X com ..."  -> calculate_field
  ("área em hectares" = $area / 10000, "comprimento" = $length, "numeração" = @row_number)
- "editar camada / ligar edição"  -> start_editing; "salvar edição"  -> commit_edits;
  "cancelar edição"  -> rollback_edits; "desfazer"  -> undo_edit
- "esta camada / camada ativa / a selecionada"  -> use a CAMADA ATIVA informada no contexto
- Se o usuário não disser a camada, use a camada ativa. Alterações (estilo, campos, feições)
  são feitas na CAMADA ATIVA (a selecionada no painel de Camadas); outras camadas só entram
  como entrada de geoprocessamento (ex.: recortar a ativa por outra).
- Texto entre aspas duplas ("nome") é NOME DE CAMPO; use-o exatamente. Texto sem aspas é valor.
- Os nomes de campo do contexto são os únicos que existem: use-os exatamente.
- Para mudar dados com segurança, prefira: start_editing -> alterações -> (o usuário salva).
  Se a camada já estiver "em edição" no contexto, NÃO chame commit_edits sem o usuário pedir.
- Ações destrutivas (apagar campo/feições, remover camada, descartar edição) são confirmadas
  pelo plugin; pode planejá-las normalmente quando o usuário pedir.

REGRAS:
- Prefira as ações dedicadas (1-21, 24-66) quando existir uma para a tarefa.
- Se a tarefa pedida não corresponder a nenhuma ação dedicada, use list_algorithms
  para encontrar o algoritmo certo e depois run_algorithm para executá-lo — NUNCA
  diga que algo "não é possível" sem antes tentar essa rota genérica.
- Nomes de camadas devem ser EXATOS (case-sensitive)
- Distâncias em metros (assume CRS métrico) ou graus (geográfico)
- Expressões: sintaxe QGIS (ex: $area, $length, "campo" > 10)
- Se precisar de múltiplos passos, encadeie no array "steps"
- Se mesmo assim não souber como fazer, retorne steps vazio e explique no campo "explanation"
"""


class AIClient:
    """Cliente unificado: Anthropic → OpenRouter → Mock"""

    def __init__(self, api_key=None):
        # Variáveis de ambiente (definidas no OSGeo4W Shell ou Windows)
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

        self.anthropic_client = None
        self.openrouter_client = None

        # Inicializa Anthropic (primário)
        if HAS_ANTHROPIC and self.anthropic_key:
            self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_key)

        # Inicializa OpenRouter (fallback) - OpenAI-compatible
        if HAS_OPENAI and self.openrouter_key:
            self.openrouter_client = openai.OpenAI(
                api_key=self.openrouter_key,
                base_url="https://openrouter.ai/api/v1"
            )

        self.current_provider = "mock"
        if self.anthropic_client:
            self.current_provider = "anthropic"
        elif self.openrouter_client:
            self.current_provider = "openrouter"

        # Avisos da última chamada, para o painel mostrar ao usuário em vez de
        # trocar de provedor em silêncio.
        self.last_warnings = []

        # Cache de modelos gratuitos da OpenRouter (preenchido sob demanda)
        self._openrouter_free_models = None

    def ask_claude(self, prompt, context_layers):
        """Tenta provedores em ordem: Anthropic → OpenRouter → Mock
        (nome mantido por compatibilidade com dockwidget.py)"""
        if isinstance(context_layers, str):
            layers_ctx = context_layers  # contexto detalhado montado pelo painel
        else:
            layers_ctx = ", ".join(context_layers) if context_layers else "nenhuma"
        full_prompt = f"""Contexto do projeto:
{layers_ctx}

Solicitação do usuário: {prompt}

Retorne APENAS o JSON do plano."""

        self.last_warnings = []
        self.last_provider = None

        # 1. Tenta Anthropic
        if self.anthropic_client:
            try:
                plano = self._ask_anthropic(full_prompt)
                self.last_provider = "Claude"
                return plano
            except Exception as e:
                self.last_warnings.append(
                    f"Anthropic falhou ({type(e).__name__}: {e}).")

        # 2. Tenta OpenRouter (fallback) — seus dados vão para outro provedor
        if self.openrouter_client:
            if self.anthropic_client:
                self.last_warnings.append(
                    "Enviando para a OpenRouter (modelo gratuito de terceiro).")
            try:
                plano = self._ask_openrouter(full_prompt)
                self.last_provider = "OpenRouter"
                return plano
            except Exception as e:
                self.last_warnings.append(
                    f"OpenRouter falhou ({type(e).__name__}: {e}).")

        # 3. Sem provedor disponível
        return self._no_provider_plan()

    def _ask_anthropic(self, prompt):
        resp = self.anthropic_client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        content = resp.content[0].text.strip()
        return self._parse_json(content, "anthropic")

    def _discover_free_openrouter_models(self):
        """Busca na OpenRouter quais modelos estão disponíveis gratuitamente
        (id termina em ':free'). Resultado fica em cache na instância para não
        repetir a consulta a cada pergunta."""
        if self._openrouter_free_models:
            return self._openrouter_free_models

        # Lista de preferência: tenta estes primeiro, se estiverem disponíveis,
        # pois costumam ser mais estáveis para retornar JSON bem formado.
        preferred = [
            "nvidia/nemotron-3.5-lightning:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "deepseek/deepseek-chat:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "mistralai/mistral-7b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ]

        live_free_models = []
        try:
            resp = self.openrouter_client.models.list()
            all_ids = [m.id for m in resp.data]
            live_free_models = [m for m in all_ids if m.endswith(":free")]
        except Exception as e:
            print(f"[AIClient] Não consegui listar modelos da OpenRouter: {e}")

        if live_free_models:
            # Prioriza os conhecidos bons (se realmente existirem agora),
            # depois completa com os demais gratuitos encontrados.
            ordered = [m for m in preferred if m in live_free_models]
            ordered += [m for m in live_free_models if m not in ordered]
        else:
            # Não deu pra consultar a lista ao vivo: tenta os conhecidos mesmo assim.
            ordered = preferred

        self._openrouter_free_models = ordered
        return ordered

    def _ask_openrouter(self, prompt):
        """OpenRouter usa formato OpenAI chat.completions.
        Busca um modelo gratuito disponível e tenta a lista em ordem até um
        funcionar (modelos free da OpenRouter mudam/saem do ar com frequência)."""
        models_to_try = self._discover_free_openrouter_models()
        if not models_to_try:
            raise RuntimeError("Nenhum modelo gratuito encontrado na OpenRouter.")

        last_error = None
        for model in models_to_try:
            try:
                resp = self.openrouter_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.1,
                )
                content = resp.choices[0].message.content.strip()
                return self._parse_json(content, f"openrouter:{model}")
            except Exception as e:
                last_error = e
                print(f"[AIClient] OpenRouter modelo '{model}' falhou: {e} — tentando próximo modelo gratuito...")
                continue

        raise last_error if last_error else RuntimeError("Todos os modelos gratuitos da OpenRouter falharam.")

    def _parse_json(self, content, provider):
        # Remove markdown code fences se vier
        if content.startswith("```"):
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1]
                if content.startswith("json"):
                    content = content[4:]
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError as e:
            return {"steps": [], "explanation": f"Erro parse JSON ({provider}): {e}. Resposta: {content[:200]}"}

    def _no_provider_plan(self):
        """Sem IA disponível: não inventa um plano, apenas explica.

        A versão antiga devolvia um plano de exemplo com camadas fixas
        ('vias', 'lotes'), que podia executar ações sobre camadas reais de
        mesmo nome. Agora não executa nada.
        """
        reasons = " ".join(self.last_warnings) if self.last_warnings else (
            "Nenhuma chave de API configurada (ANTHROPIC_API_KEY ou OPENROUTER_API_KEY).")
        return {"steps": [],
                "explanation": f"Nenhum provedor de IA respondeu, então nada foi executado. {reasons}"}

    def get_provider(self):
        return self.current_provider


# Alias para compatibilidade com código existente (dockwidget.py, __init__.py)
ClaudeClient = AIClient
