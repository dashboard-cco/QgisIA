# QGIS_IA

Plugin de IA para QGIS, com dois modos de uso:

1. **Servidor MCP** — o Claude Desktop, o Claude Code ou outro cliente MCP opera o
   projeto aberto no seu QGIS. É o modo principal, equivalente ao QGIS MCP.
2. **Painel de chat** — você descreve a tarefa e o plugin executa, usando sua própria
   chave de API (`ANTHROPIC_API_KEY`).

Versão 2.0.0. Antes chamava-se "Claude AI Assistant" (pasta `qgis_claude_ai`).

## Instalação

O plugin já está em `…/QGIS3/profiles/default/python/plugins/qgis_ia`.

1. Abra o QGIS.
2. Em `Complementos` → `Gerenciar e Instalar Complementos` → aba `Instalados`,
   **desmarque o antigo "Claude AI Assistant"** e **marque "QGIS_IA"**.
   Se o QGIS já estava aberto, feche e abra de novo para ele enxergar a pasta nova.

## Modo servidor MCP

**Não precisa de `uv`, nem de `pip`, nem de internet.** A ponte usa só a biblioteca
padrão do Python e roda com o Python que já vem no QGIS.

1. No QGIS, abra o painel **QGIS_IA** (menu `Complementos` → `QGIS_IA`, ou o ícone na
   barra de ferramentas).
2. Clique em **Iniciar servidor**.
3. Clique em **Copiar comando (Claude Code)** ou **Copiar JSON (Claude Desktop)**:
   - *Claude Code*: cole o comando no terminal e tecle Enter.
   - *Claude Desktop*: cole o JSON em `claude_desktop_config.json`
     (`%APPDATA%\Claude\claude_desktop_config.json`), depois feche e reabra o app.
4. Peça ao Claude para chamar a ferramenta `ping`. Resposta esperada: `{"pong": true}`.

Mantenha o QGIS aberto e o servidor iniciado enquanto usar.

### Como funciona

```
Claude  ⇄  mcp_server.py (stdio, fora do QGIS)  ⇄  socket 127.0.0.1  ⇄  plugin no QGIS  ⇄  PyQGIS
```

O servidor escuta **apenas em 127.0.0.1** (porta 9876, ou a próxima livre) e exige um
token aleatório, gerado a cada início e gravado em `~/.qgis_ia/server.json`. Ao parar
o servidor, o arquivo é apagado e o token deixa de valer.

### Segurança

- **Somente leitura** (caixa no painel): bloqueia tudo que grava arquivo, altera dados
  ou remove coisas — `remove_layer`, `export_layer`, `calculate_field`, `run_algorithm`,
  `export_layout_*`, `save_project`, `add_features`, `update_features`,
  `delete_features`, `add_field`, `delete_field`.
- **Permitir execução de código Python**: começa desligada e pede confirmação. Ligada,
  libera `execute_code`, que roda PyQGIS arbitrário — qualquer coisa que o QGIS faz,
  inclusive ler e apagar arquivos. Ligue só quando precisar e desligue depois.
- As ações rodam no thread principal do QGIS. Operações pesadas deixam a interface
  parada enquanto executam.

## As ferramentas (79)

**Inspeção** — `ping`, `get_project_info`, `get_layer_info`, `get_features`,
`get_field_statistics`, `get_unique_values`, `get_raster_stats`, `get_algorithm_help`,
`render_map`, `list_algorithms`

**Camadas** — `list_layers`, `add_vector_layer`, `add_raster_layer`, `add_basemap`,
`create_memory_layer`, `remove_layer`, `rename_layer`, `export_layer`,
`set_layer_visibility`, `zoom_to_layer`, `set_canvas_extent`, `save_project`

**Edição** — `add_features`, `update_features`, `delete_features`, `add_field`,
`delete_field`, `calculate_field`, `select_by_expression`, `filter_layer`, `clear_filter`

**Geoprocessamento** — `run_buffer`, `run_intersection`, `run_difference`, `run_union`,
`run_dissolve`, `run_clip`, `run_merge_layers`, `run_reproject`, `run_centroids`,
`run_convex_hull`, `run_simplify`, `run_spatial_join`, `run_algorithm`

`run_algorithm` alcança **qualquer** algoritmo do Processing (native, qgis, gdal, grass).
Use `list_algorithms` para achar o id e `get_algorithm_help` para os nomes dos parâmetros.

**Simbologia e mapas** — `set_layer_style`, `update_symbol`, `set_categorized_style`,
`set_graduated_style`, `set_labels`, `set_layer_opacity`, `add_basemap` (inclui Google
satélite/híbrido), `move_layer`, `zoom_full`, `set_scale`, `export_map_image`

**Layouts** — `create_print_layout` (título, legenda, escala e norte prontos),
`add_layout_item`, `export_layout` (pdf/png/jpg/tif/svg, caminho automático),
`open_layout`, `list_print_layouts`, `remove_layout`, `export_layout_pdf`, `export_layout_image`

### Comandos simples de mapas (no chat, sem IA)

| Assunto | Exemplos |
|---|---|
| Cor | `pintar lotes de azul` · `mudar a cor de vias para vermelho escuro` · `deixar lotes sem preenchimento` |
| Contorno e tamanho | `contorno preto de 0.5 em lotes` · `sem contorno` · `espessura 1.5 em vias` · `tamanho dos pontos 4` |
| Transparência | `transparência 30% em lotes` · `deixar lotes semitransparente` · `opacidade 80%` |
| Cores por campo | `cores por bairro em lotes` · `classificar lotes por pop em 5 classes em tons de vermelho` · `graduar lotes por area do amarelo ao vermelho` |
| Rótulos | `rótulos com nome em lotes` · `rotular vias por nome tamanho 12 negrito` · `tirar rótulos` |
| Mapa de fundo | `mapa de fundo satélite` · `colocar imagem de satélite do google` · `fundo claro` |
| Mapa | `zoom total` · `escala 1:5000` · `trazer lotes para frente` · `esconder camada vias` · `salvar projeto` |
| Layout | `criar layout A3 retrato com título "Coleta 2026"` · `criar layout sem legenda` · `adicionar texto "Fonte: SLU" no layout` |
| Exportar | `exportar layout em pdf` · `exportar layout Mapa em png com 150 dpi para C:\saida` · `salvar mapa em pdf` (cria o layout se não houver) · `salvar imagem do mapa` |

**Avançado** — `execute_code` (desligada por padrão)

## Painel de chat

Precisa de `ANTHROPIC_API_KEY` nas variáveis de ambiente do Windows (cobra por uso,
à parte da assinatura). Sem chave nenhuma, o plugin avisa e não executa nada.

Se houver também `OPENROUTER_API_KEY`, ela é usada como reserva quando a Anthropic
falha — e o painel avisa no chat, porque seus dados passam a ir para outro provedor.

## Arquivos

| Arquivo | Função |
|---|---|
| `__init__.py` | Entrada do plugin: menu, barra e ciclo de vida |
| `dockwidget.py` | Painel: chat e controles do servidor |
| `mcp_socket.py` | Servidor socket dentro do QGIS |
| `mcp_server.py` | Ponte MCP (stdio), rodada pelo cliente, sem dependências |
| `protocol.py` | Formato das mensagens, token e travas de segurança |
| `tool_specs.py` | Nome, descrição e schema de cada ferramenta |
| `executor.py` | Executa o plano JSON vindo do chat |
| `ai_client.py` | Cliente da API para o modo chat |
| `actions/` | As funções que mexem no QGIS |

## Próxima etapa

Rotas ainda não estão implementadas. Quando for a hora: definir origem dos dados
(rede viária própria, OSM ou serviço externo), tipo de roteamento (ponto a ponto,
várias paradas, área de alcance) e então acrescentar as ferramentas em
`actions/routing.py`.
