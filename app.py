"""
Meu Financeiro - painel de gestão financeira pessoal (Streamlit + Supabase).

Organização do arquivo:
  1. Configuração, constantes e conexão com o banco (Supabase)
  2. Utilitários (formatação, datas, cotações de mercado)
  3. Design system (CSS)
  4. Autenticação (login, sessão persistente por cookie)
  5. Regras de negócio (cartão, devedores, caixinhas, carteira)
  6. Barra lateral e navegação
  7. Páginas (uma função por tela) e despacho de rotas
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import html
import time
import urllib.request
import urllib.parse
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

# ==============================================================================
# IDENTIDADE DO PRODUTO (white-label: troque aqui para renomear o sistema todo)
# ==============================================================================
APP_NOME = "Meu Financeiro"
APP_SLOGAN = "Gestão patrimonial segura, simples e inteligente"

# Link de checkout para quem ainda não é cliente
LINK_COMPRA = "https://pay.kiwify.com.br/z9ynIE5"

# Foto de apresentação do sistema (mostrada na tela de login).
# Salve a imagem com UM destes nomes na mesma pasta do app.py (ou dentro de /assets).
IMAGENS_APRESENTACAO = [
    "foto_sistema.png", "foto_sistema.jpg", "foto_sistema.jpeg", "foto_sistema.webp",
    "assets/foto_sistema.png", "assets/foto_sistema.jpg", "assets/foto_sistema.jpeg", "assets/foto_sistema.webp",
]

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA (precisa ser o primeiro comando do Streamlit)
# ==============================================================================
st.set_page_config(
    page_title=APP_NOME,
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CONEXÃO COM O BANCO DE DADOS NAS NUVENS (SUPABASE)
# ==============================================================================
try:
    from supabase import create_client, Client
except ImportError:
    st.error("A biblioteca do Supabase não está instalada! Rode no terminal: pip install supabase")
    st.stop()

SUPABASE_URL = "https://pthlykliquenulrgntvt.supabase.co"

# Puxa a chave de forma segura do painel do Streamlit Cloud (ou do computador)
try:
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_KEY:
    st.error(
        "Configuração pendente: a chave de acesso ao banco de dados não foi encontrada. "
        "Defina SUPABASE_KEY em Settings > Secrets (Streamlit Cloud) ou como variável de ambiente."
    )
    st.stop()

def iniciar_supabase() -> "Client":
    """Um cliente por sessão do navegador. Com um cliente global compartilhado, o login de um
    usuário poderia vazar para outro que estivesse usando o app ao mesmo tempo."""
    if "_sb_client" not in st.session_state:
        st.session_state["_sb_client"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state["_sb_client"]

supabase: Client = iniciar_supabase()

if "auth_session" in st.session_state and st.session_state["auth_session"]:
    try:
        _r = supabase.auth.set_session(
            st.session_state["auth_session"].access_token,
            st.session_state["auth_session"].refresh_token
        )
        _nova = getattr(_r, "session", None)
        if _nova is not None and getattr(_nova, "access_token", None):
            st.session_state["auth_session"] = _nova
    except Exception:
        pass

# ==============================================================================
# CONFIGURAÇÃO NATIVA DE TEMA CLARO
# ==============================================================================
try:
    os.makedirs(".streamlit", exist_ok=True)
    cfg_file = os.path.join(".streamlit", "config.toml")
    cfg_content = '[theme]\nbase="light"\nprimaryColor="#0F766E"\nbackgroundColor="#F4F6FA"\nsecondaryBackgroundColor="#FFFFFF"\ntextColor="#0B1220"\n'
    if not os.path.exists(cfg_file) or open(cfg_file, "r", encoding="utf-8").read() != cfg_content:
        with open(cfg_file, "w", encoding="utf-8") as f:
            f.write(cfg_content)
except Exception:
    pass

# ==============================================================================
# ESTRUTURA PADRÃO DE DADOS
# ==============================================================================
def estrutura_inicial_dados():
    return {
        "ativos": [],
        "vendas": [],
        "proventos": [],
        "devedores": [],
        "cartao_compras": [],
        "transacoes_debito": [],
        "caixinhas": [],
        "caixinhas_mov": [],
        "contas_fixas": [],
        "faturas_pagas": [],
        "config": {"brapi_token": "", "caixinha_fluxo_id": None, "smtp_email": "", "smtp_pass": ""},
        "metas": {"patrimonio": 100000.0, "renda_mensal": 1000.0}
    }

CLASSES_INVEST = ["Ações", "FIIs", "Renda Fixa", "Internacional", "Cripto", "Dólar"]
CLASSES_BOLSA_FORM = ["Ações", "FIIs", "Renda Fixa", "Internacional"]
CLASSES_ALT = ["Cripto", "Dólar"]
CORES_CLASSE = {
    "Ações": "#2563EB",
    "FIIs": "#7C3AED",
    "Renda Fixa": "#059669",
    "Caixinhas": "#DB2777",
    "Internacional": "#D97706",
    "Cripto": "#EA580C",
    "Dólar": "#0891B2"
}

CRIPTO_NOMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP",
    "LTC": "Litecoin", "DOGE": "Dogecoin", "USDT": "Tether", "USDC": "USD Coin",
    "ADA": "Cardano", "BNB": "BNB"
}

MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
# Regras do cartão de crédito
DIA_FECHAMENTO_CARTAO = 15   # compras a partir deste dia entram na fatura do mês seguinte
DIA_VENCIMENTO_CARTAO = 22   # vencimento da fatura

DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

LISTA_CARTOES = ["Nubank", "C6 Bank", "Banco Inter", "Itaú", "Bradesco", "Santander", "Outro"]
LISTA_CATEGORIAS_CARTAO = ["Lazer", "Empréstimo", "Curso", "Streaming / Assinatura", "Tecnologia", "Vestuário", "Viagem", "Mercado", "Alimentação", "Saúde", "Outros"]
LISTA_CATEGORIAS_DEBITO = [
    "Salário", "Vale da Empresa", "Comissão", "Compra no Débito", "Pagamento de Empréstimo",
    "Transferência PIX", "Alimentação / Restaurante", "Supermercado", "Contas de Casa (Luz, Água, Net)",
    "Transporte / Combustível", "Lazer", "Saúde", "Educação", "Outros"
]
LISTA_CATEGORIAS_CONTAS = [
    "Moradia (Aluguel, Condomínio)", "Contas de Casa (Luz, Água, Gás)", "Internet & Telefonia",
    "Educação / Cursos", "Saúde / Plano", "Assinaturas / Streaming", "Transporte / Garagem", "Outros"
]

# --- Visual dos gráficos (Plotly) ---
LAYOUT_GRAFICO = {
    "separators": ",.",
    "margin": dict(l=10, r=10, t=20, b=10),
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, sans-serif", "color": "#334155", "size": 12},
    "hoverlabel": dict(bgcolor="#0B1220", font_size=12, font_family="Inter, sans-serif", font_color="#FFFFFF"),
}
GRADE_GRAFICO = "#EEF1F6"
CONFIG_PLOTLY = {"displayModeBar": False}

# ==============================================================================
# FUNÇÕES GERAIS E AUXILIARES
# ==============================================================================
def md(texto):
    st.markdown(texto, unsafe_allow_html=True)

def hero(titulo, sub):
    d = agora_br()
    data_txt = f"{DIAS_PT[d.weekday()]}, {d.day} de {MESES_PT[d.month-1].lower()}"
    md(f"""<div class="hero-box">
      <div class="hero-text"><div class="hero-eyebrow">{APP_NOME} &nbsp;/&nbsp; Painel</div><div class="hero-title">{titulo}</div><div class="hero-sub">{sub}</div></div>
      <div class="hero-date">{data_txt}</div>
    </div>""")

def secao(titulo, sub=None):
    s = f"<div class='sec-sub'>{sub}</div>" if sub else ""
    md(f"<div class='sec'><div class='sec-t'>{titulo}</div>{s}</div>")

def vazio(msg, icone=None):
    md(f"<div class='empty'>{msg}</div>")

def kpi(valor, label, cor="#0B1220", tamanho="1.55rem"):
    return f"<div class='kpi'><div class='kpi-l'>{label}</div><div class='kpi-n' style='color:{cor};font-size:{tamanho}'>{valor}</div></div>"

def fmt_moeda(val, casas=2):
    if val is None or pd.isna(val):
        val = 0.0
    return f"R$ {val:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_dolar(val, casas=2):
    if val is None or pd.isna(val):
        val = 0.0
    return f"US$ {val:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_num(val, casas=2):
    if val is None or pd.isna(val):
        val = 0.0
    return f"{val:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_num_limpo(val, max_casas=8):
    s = f"{float(val):.{max_casas}f}".rstrip("0").rstrip(".")
    if s == "":
        s = "0"
    return s.replace(".", ",")

def fmt_pct(val):
    if val is None or pd.isna(val):
        return "0,00%"
    sinal = "+" if val > 0 else ""
    return f"{sinal}{val:.2f}%".replace(".", ",")

def parse_valor_moeda(val_str, default=0.0):
    try:
        if isinstance(val_str, (int, float)):
            return float(val_str)
        s = str(val_str).replace("R$", "").replace("US$", "").replace(" ", "").strip()
        if not s:
            return default
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return default

def novo_id():
    return int(time.time() * 1_000_000)

def agora_br():
    try:
        if ZoneInfo:
            return datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        pass
    return datetime.now()

def hoje_br():
    """Data de hoje no horário de Brasília (o servidor do Streamlit Cloud roda em UTC)."""
    return agora_br().date()

def chip_classe(classe):
    mapa = {
        "Ações": "chip-acoes",
        "FIIs": "chip-fiis",
        "Renda Fixa": "chip-rendafixa",
        "Caixinhas": "chip-caixinhas",
        "Internacional": "chip-internacional",
        "Cripto": "chip-cripto",
        "Dólar": "chip-dolar"
    }
    css = mapa.get(classe, "chip-acoes")
    return f"<span class='chip {css}'>{classe}</span>"

# ------------------------------------------------------------------------------
# COTAÇÕES EM TEMPO REAL
# ------------------------------------------------------------------------------
@st.cache_resource
def _store_cache():
    return {}

CACHE = _store_cache()
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")

def _get_json(url, timeout=4):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def _cached(chave, ttl, fn):
    agora = time.time()
    item = CACHE.get(chave)
    if item and agora - item[0] < ttl:
        return item[1]
    try:
        val = fn()
    except Exception:
        val = None
    if val is not None:
        CACHE[chave] = (agora, val)
        return val
    return item[1] if item else None

def _tentar_fontes(fontes):
    """Tenta cada fonte em ordem; devolve a primeira que responder com preço válido."""
    for fonte in fontes:
        try:
            r = fonte()
            if r and r.get("preco") and float(r["preco"]) > 0:
                return r
        except Exception:
            continue
    return None

def _yahoo_quote(simbolo):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(simbolo)}?interval=1m&range=1d"
    meta = _get_json(url, timeout=5)["chart"]["result"][0]["meta"]
    preco = float(meta["regularMarketPrice"])
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    pct = ((preco - float(prev)) / float(prev) * 100) if prev else None
    return {"preco": preco, "pct": pct}

def _awesome_quote(par):
    chave = par.replace("-", "")
    d = _get_json(f"https://economia.awesomeapi.com.br/last/{par}", timeout=5)[chave]
    return {"preco": float(d["bid"]), "pct": float(d.get("pctChange", 0.0))}

def _binance_quote(simbolo):
    # data-api.binance.vision funciona também em servidores nos EUA (Streamlit Cloud)
    d = _get_json(f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={simbolo}", timeout=5)
    return {"preco": float(d["lastPrice"]), "pct": float(d["priceChangePercent"])}

def cotacao_dolar():
    def f():
        return _tentar_fontes([
            lambda: _awesome_quote("USD-BRL"),
            lambda: _yahoo_quote("BRL=X"),
            lambda: _binance_quote("USDTBRL"),
            lambda: {"preco": float(_get_json("https://api.coinbase.com/v2/exchange-rates?currency=USD", timeout=5)["data"]["rates"]["BRL"]), "pct": None},
        ])
    return _cached("USD-BRL", 20, f)

def cotacao_cripto(simbolo):
    s = simbolo.strip().upper()
    def f():
        return _tentar_fontes([
            lambda: _awesome_quote(f"{s}-BRL"),
            lambda: _yahoo_quote(f"{s}-BRL"),
            lambda: _binance_quote(f"{s}BRL"),
            lambda: {"preco": float(_get_json(f"https://api.coinbase.com/v2/prices/{s}-BRL/spot", timeout=5)["data"]["amount"]), "pct": None},
        ])
    return _cached(f"CRIPTO-{s}", 20, f)

def _url_brapi(caminho):
    url = f"https://brapi.dev/api/{caminho}"
    if BRAPI_TOKEN:
        url += ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(BRAPI_TOKEN)
    return url

def cotacao_acao(ticker):
    t = ticker.strip().upper()
    def f():
        data = _get_json(_url_brapi(f"quote/{urllib.parse.quote(t)}"))
        if data.get("results"):
            r = data["results"][0]
            p = r.get("regularMarketPrice")
            if p:
                return {"preco": float(p), "pct": r.get("regularMarketChangePercent")}
        return None
    return _cached(f"B3-{t}", 45, f)

def cotacao_ibov():
    def f():
        try:
            data = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range=1d", timeout=3)
            meta = data["chart"]["result"][0]["meta"]
            preco = meta["regularMarketPrice"]
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            pct = ((preco - prev) / prev * 100) if prev else 0.0
            return {"preco": float(preco), "pct": float(pct)}
        except Exception:
            pass
        try:
            return cotacao_acao("^BVSP")
        except Exception:
            pass
        return None
    return _cached("IBOV", 60, f)

def buscar_proventos_mercado(ticker):
    try:
        t = ticker.strip().upper()
        data = _get_json(_url_brapi(f"quote/{urllib.parse.quote(t)}?dividends=true"), timeout=4)
        if data.get("results") and len(data["results"]) > 0:
            res = data["results"][0]
            divs = res.get("dividendsData", {}).get("cashDividends", [])
            return divs, res.get("regularMarketPrice", 0.0)
    except Exception:
        pass
    return [], 0.0

def preco_por_chave(classe, ticker):
    try:
        if classe == "Dólar":
            q = cotacao_dolar()
        elif classe == "Cripto":
            q = cotacao_cripto(ticker)
        elif classe in ("Ações", "FIIs", "Internacional"):
            q = cotacao_acao(ticker)
        else:
            q = None
        return float(q["preco"]) if q and q.get("preco") else None
    except Exception:
        return None

def atualizar_precos(dados):
    alvos = [a for a in dados.get("ativos", []) if a.get("classe") != "Renda Fixa"]
    chaves = sorted({(a["classe"], a["ticker"].strip().upper()) for a in alvos})
    if not chaves:
        return 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        resultados = list(ex.map(lambda k: preco_por_chave(k[0], k[1]), chaves))
    mapa = dict(zip(chaves, resultados))
    mudou = 0
    for a in alvos:
        p = mapa.get((a["classe"], a["ticker"].strip().upper()))
        if p and abs(p - float(a.get("preco_atual", 0.0))) > 1e-9:
            a["preco_atual"] = float(p)
            mudou += 1
    if mudou:
        salvar_dados(dados)
    return mudou

# ==============================================================================
# DESIGN SYSTEM (CSS)
# ==============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --bg: #F4F6FA;
  --paper: #FFFFFF;
  --ink: #0B1220;
  --ink-2: #334155;
  --ink-3: #64748B;
  --ink-4: #94A3B8;
  --line: #E5E9F0;
  --line-2: #EEF1F6;
  --brand: #0F766E;
  --brand-2: #14B8A6;
  --brand-soft: #E6F6F4;
  --navy: #0A1628;
  --navy-2: #0F2238;
  --pos: #047857;
  --neg: #B91C1C;
  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
  --r-xl: 22px;
  --sh-xs: 0 1px 2px rgba(11,18,32,.04);
  --sh-sm: 0 1px 3px rgba(11,18,32,.06), 0 1px 2px rgba(11,18,32,.04);
  --sh-md: 0 10px 28px -10px rgba(11,18,32,.16);
}

/* ---------- Base ---------- */
html, body, .stApp, .stMarkdown, p, label, button, input, textarea, select, h1, h2, h3, h4 {
  font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
}
.stApp { background: var(--bg) !important; color: var(--ink) !important; }
.block-container { max-width: 1320px !important; padding: 1.6rem 2.2rem 5rem !important; }
h1, h2, h3, h4 { color: var(--ink) !important; letter-spacing: -.02em; font-weight: 800 !important; }
::selection { background: rgba(20,184,166,.25); }

/* Esconde a marca padrão do Streamlit (SEM esconder o botão de abrir/fechar a sidebar) */
#MainMenu, footer, [data-testid="stDecoration"], .stDeployButton,
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stToolbarActions"] { display: none !important; }
[data-testid="stHeader"] {
  background: transparent !important; visibility: visible !important;
  z-index: 999990 !important; pointer-events: none !important;
}
[data-testid="stHeader"] > * { pointer-events: auto !important; }
[data-testid="stToolbar"] { visibility: visible !important; background: transparent !important; }

/* ---------- Botão de ABRIR a sidebar: sempre visível e fixo na tela ---------- */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"] {
  display: flex !important; visibility: visible !important; opacity: 1 !important;
  position: fixed !important; top: 0.8rem !important; left: 0.8rem !important;
  z-index: 999999 !important; pointer-events: auto !important;
  width: auto !important; height: auto !important; transform: none !important;
}
[data-testid="collapsedControl"] button, [data-testid="stSidebarCollapsedControl"] button,
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] button {
  display: flex !important; visibility: visible !important; opacity: 1 !important;
  background-color: var(--navy) !important; border: 1.5px solid var(--brand-2) !important;
  color: #FFFFFF !important; border-radius: 10px !important; box-shadow: 0 4px 14px rgba(0,0,0,.25) !important;
  pointer-events: auto !important;
}
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stExpandSidebarButton"] svg, [data-testid="stExpandSidebarButton"] span {
  fill: #FFFFFF !important; color: #FFFFFF !important;
}
/* Botão de recolher dentro da sidebar também sempre visível */
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] button {
  visibility: visible !important; opacity: 1 !important; pointer-events: auto !important;
}
[data-testid="stSidebarCollapseButton"] svg { fill: #FFFFFF !important; color: #FFFFFF !important; }

/* ---------- Hero ---------- */
.hero-box {
  position: relative; overflow: hidden;
  background: linear-gradient(120deg, #0A1628 0%, #0E3447 52%, #0F766E 130%);
  border-radius: var(--r-xl); padding: 1.7rem 2rem; margin-bottom: 1.6rem;
  display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 14px;
  box-shadow: var(--sh-md);
}
.hero-box::before {
  content: ""; position: absolute; right: -80px; top: -120px; width: 340px; height: 340px; border-radius: 50%;
  background: radial-gradient(circle, rgba(20,184,166,.35), rgba(20,184,166,0) 70%);
}
.hero-box::after {
  content: ""; position: absolute; left: 38%; bottom: -160px; width: 300px; height: 300px; border-radius: 50%;
  background: radial-gradient(circle, rgba(56,189,248,.16), rgba(56,189,248,0) 70%);
}
.hero-text { position: relative; z-index: 1; }
.hero-eyebrow { font-size: .7rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #5EEAD4; margin-bottom: .45rem; }
.hero-title { font-size: 1.9rem; font-weight: 800; color: #FFFFFF; letter-spacing: -.03em; line-height: 1.15; }
.hero-sub { color: #AFC0D2; font-size: .93rem; margin-top: .45rem; max-width: 680px; line-height: 1.5; }
.hero-date {
  position: relative; z-index: 1; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.18);
  backdrop-filter: blur(6px); border-radius: 999px; color: #E2E8F0; font-weight: 600; font-size: .8rem;
  padding: .45rem 1rem; text-transform: capitalize;
}

/* ---------- Títulos de seção ---------- */
.sec { margin: 1.9rem 0 .9rem; }
.sec-t { font-size: 1.12rem; font-weight: 800; color: var(--ink); letter-spacing: -.02em; display: flex; align-items: center; gap: 10px; }
.sec-t::before { content: ""; width: 4px; height: 18px; border-radius: 4px; background: linear-gradient(180deg, var(--brand-2), var(--brand)); }
.sec-sub { font-size: .85rem; color: var(--ink-3); margin: 4px 0 0 14px; }

/* ---------- Cards de números ---------- */
.stats { display: grid !important; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)) !important; gap: 16px; margin-bottom: 1.5rem; }
.stat {
  position: relative; overflow: hidden; background: var(--paper); border: 1px solid var(--line);
  border-radius: var(--r-lg); padding: 1.1rem 1.3rem 1.1rem 1.5rem; box-shadow: var(--sh-sm);
  display: flex; flex-direction: column-reverse; gap: 6px; transition: transform .18s ease, box-shadow .18s ease;
}
.stat::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: linear-gradient(180deg, var(--brand-2), var(--brand)); }
.stat:hover { transform: translateY(-2px); box-shadow: var(--sh-md); }
.stat-n { font-size: 1.6rem; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -.025em; line-height: 1.15; }
.stat-l { color: var(--ink-3); font-size: .8rem; font-weight: 600; }

.kpi { padding: 2px 2px 6px; }
.kpi-l { color: var(--ink-3); font-size: .78rem; font-weight: 600; margin-bottom: 4px; }
.kpi-n { font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -.025em; line-height: 1.15; }

/* ---------- Banner de status do mês ---------- */
.banner {
  border: 1px solid var(--line); border-left: 6px solid var(--accent, #10B981); border-radius: var(--r-lg);
  padding: 1.4rem 1.8rem; margin-bottom: 1.4rem; box-shadow: var(--sh-sm);
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;
}
.banner-t { font-size: .74rem; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.banner-d { font-size: .9rem; color: var(--ink-2); margin-top: 6px; line-height: 1.6; }
.banner-v { font-size: 2.4rem; font-weight: 900; letter-spacing: -.035em; font-variant-numeric: tabular-nums; text-align: right; }
.banner-vl { font-size: .8rem; font-weight: 700; color: var(--ink-3); text-align: right; }

/* ---------- Cotações ao vivo ---------- */
.ticker { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 1.4rem; }
.tk { background: var(--paper); border: 1px solid var(--line); border-radius: var(--r-lg); padding: .8rem 1.15rem; min-width: 170px; flex: 1; box-shadow: var(--sh-sm); }
.tk-n { font-size: .74rem; color: var(--ink-3); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.tk-v { font-size: 1.3rem; font-weight: 800; color: var(--ink); font-variant-numeric: tabular-nums; margin-top: 3px; letter-spacing: -.02em; }
.tk-p { font-size: .76rem; font-weight: 700; margin-top: 1px; }
.tk-up { color: var(--pos); } .tk-down { color: var(--neg); } .tk-flat { color: var(--ink-3); }
.tk-live { background: linear-gradient(135deg, #0A1628, #0F2238); border-radius: var(--r-lg); padding: .8rem 1.15rem; min-width: 150px; display: flex; flex-direction: column; justify-content: center; color: #fff; }
.tk-live b { font-size: .78rem; color: #fff; letter-spacing: .04em; }
.tk-live span { color: #94A3B8; font-size: .72rem; margin-top: 2px; }
.live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22C55E; margin-right: 6px; animation: pulse 1.8s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(34,197,94,.7);} 70% { box-shadow: 0 0 0 8px rgba(34,197,94,0);} 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0);} }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0A1628 0%, #0C1D33 100%) !important; border-right: 1px solid rgba(255,255,255,.06); }
section[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] div[role="radiogroup"] label { border-radius: 10px !important; padding: .62rem .85rem !important; margin: 1px 0 !important; transition: background .15s ease; cursor: pointer; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: rgba(255,255,255,.06) !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) { background: linear-gradient(90deg, rgba(20,184,166,.22), rgba(20,184,166,.06)) !important; box-shadow: inset 3px 0 0 #14B8A6; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p { color: #FFFFFF !important; font-weight: 700 !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none !important; }
section[data-testid="stSidebar"] button { background: linear-gradient(135deg, #14B8A6, #0F9488) !important; border-radius: 10px !important; border: none !important; box-shadow: 0 4px 14px rgba(20,184,166,.3) !important; }
section[data-testid="stSidebar"] button p { color: #042F2E !important; font-weight: 700 !important; }
section[data-testid="stSidebar"] input { background: rgba(255,255,255,.07) !important; color: #FFFFFF !important; border: 1px solid rgba(255,255,255,.14) !important; border-radius: 10px !important; }
section[data-testid="stSidebar"] [data-baseweb="input"], section[data-testid="stSidebar"] [data-baseweb="base-input"] { background: transparent !important; border-radius: 10px !important; }
/* Botão de recolher da sidebar: estilo discreto (não herda o verde dos botões) */
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button {
  background: rgba(255,255,255,.08) !important; border: 1px solid rgba(255,255,255,.18) !important; box-shadow: none !important;
}
/* Textos da sidebar bem legíveis (prioridade maior que a regra global de rótulos) */
section[data-testid="stSidebar"] label p,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] div[role="radiogroup"] label p {
  color: #E2E8F0 !important; font-weight: 500 !important; font-size: .92rem !important; opacity: 1 !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover p { color: #FFFFFF !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p { color: #FFFFFF !important; font-weight: 700 !important; }
section[data-testid="stSidebar"] input::placeholder { color: #8FA3BC !important; opacity: 1 !important; }
section[data-testid="stSidebar"] [data-baseweb="radio"] > div { background-color: transparent !important; border-color: #5F7391 !important; }
section[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) > div { border-color: #14B8A6 !important; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"], section[data-testid="stSidebar"] small { color: #94A3B8 !important; }
.brand { display: flex; align-items: center; gap: 12px; padding: .2rem 0 1.2rem; margin-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,.09); }
.brand-mark { width: 42px; height: 42px; border-radius: 12px; background: linear-gradient(135deg, #14B8A6, #0F766E); display: grid; place-items: center; font-weight: 800; color: #fff !important; font-size: .95rem; box-shadow: 0 6px 16px rgba(20,184,166,.35); flex-shrink: 0; }
.brand-name { font-size: 1rem; font-weight: 700; color: #fff !important; line-height: 1.2; }
.brand-sub { font-size: .74rem; color: #7C8FA6 !important; }
.side-label { font-size: .68rem; color: #5F7391 !important; margin: 1.3rem 0 .4rem; text-transform: uppercase; font-weight: 700; letter-spacing: .12em; }
.side-user { font-size: .76rem; color: #94A3B8 !important; line-height: 1.55; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07); border-radius: 12px; padding: .75rem .9rem; margin-bottom: .8rem; word-break: break-all; }
.side-user b { color: #fff !important; font-weight: 600; }

/* ---------- Chips & badges ---------- */
.chip { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; vertical-align: middle; }
.chip-acoes { background: #DBEAFE; color: #1D4ED8; }
.chip-fiis { background: #EDE9FE; color: #6D28D9; }
.chip-rendafixa { background: #D1FAE5; color: #047857; }
.chip-caixinhas { background: #FCE7F3; color: #BE185D; }
.chip-internacional { background: #FEF3C7; color: #B45309; }
.chip-cripto { background: #FFEDD5; color: #C2410C; }
.chip-dolar { background: #CFFAFE; color: #0E7490; }
.chip-cartao { background: #E0E7FF; color: #3730A3; }
.chip-pix { background: #FEF3C7; color: #92400E; }
.chip-entrada { background: #DCFCE7; color: #166534; }
.chip-saida { background: #FEE2E2; color: #991B1B; }
.badge-status { display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; border-radius: 999px; font-size: .74rem; font-weight: 700; white-space: nowrap; }
.badge-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-alta { background: #DCFCE7; color: #15803D; }
.status-baixa { background: #FEE2E2; color: #B91C1C; }
.status-atraso { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }
.status-alerta { background: #FEF3C7; color: #B45309; }
.status-neutro { background: #F1F5F9; color: #475569; }

/* ---------- Ativos ---------- */
.asset { display: flex; align-items: center; gap: 12px; }
.avatar { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-weight: 800; font-size: .78rem; flex-shrink: 0; letter-spacing: .02em; }
.asset-tk { font-size: 1.05rem; font-weight: 800; color: var(--ink); letter-spacing: -.01em; }
.asset-sub { font-size: .76rem; color: var(--ink-3); margin-top: 1px; }
.cell-l { font-size: .74rem; color: var(--ink-3); font-weight: 600; }
.cell-v { font-size: .98rem; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.cell-big { font-size: 1.1rem; font-weight: 800; color: var(--ink); font-variant-numeric: tabular-nums; letter-spacing: -.01em; }

/* ---------- Cards genéricos ---------- */
.card-pro { background: var(--paper); border: 1px solid var(--line); border-radius: var(--r-xl); padding: 1.5rem 1.8rem; margin-bottom: 1.2rem; box-shadow: var(--sh-sm); }
.tip { background: var(--paper); border: 1px solid var(--line); border-left: 4px solid var(--brand); border-radius: var(--r-md); padding: .9rem 1.2rem; margin-bottom: 10px; color: var(--ink); box-shadow: var(--sh-xs); font-size: .92rem; line-height: 1.55; }
.person { background: var(--paper); border: 1px solid var(--line); border-radius: var(--r-lg); padding: .95rem 1.3rem; margin: 18px 0 8px; box-shadow: var(--sh-sm); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.empty { text-align: center; padding: 2.8rem 1.5rem; border: 1.5px dashed #CBD5E1; border-radius: var(--r-lg); color: var(--ink-3); background: rgba(255,255,255,.6); margin: 1rem 0; font-size: .92rem; }
.empty-i { font-size: 1.8rem; margin-bottom: .4rem; opacity: .85; }
.prog-wrap { background: #E2E8F0; border-radius: 999px; height: 14px; overflow: hidden; }
.prog-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #14B8A6, #0F766E); }

/* ---------- Calendário ---------- */
/* minmax(0,1fr): impede que o texto das etiquetas alargue as colunas e distorça o calendário no celular */
.cal-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; margin: 12px 0 22px 0; width: 100%; max-width: 100%; }
.cal-head { text-align: center; font-weight: 700; font-size: .74rem; padding: 9px 4px; background: var(--navy); border-radius: 10px; color: #CBD5E1; letter-spacing: .08em; text-transform: uppercase; min-width: 0; overflow: hidden; }
.cal-cell { background: var(--paper); border: 1px solid var(--line); border-radius: 12px; min-height: 92px; padding: 7px; display: flex; flex-direction: column; box-shadow: var(--sh-xs); min-width: 0; overflow: hidden; }
.cal-cell-empty { background: transparent; border: 1px dashed var(--line); min-height: 92px; border-radius: 12px; min-width: 0; }
.cal-day-num { font-size: .8rem; font-weight: 700; color: var(--ink-3); margin-bottom: 5px; }
.cal-day-hoje { background: #F0FDFA !important; border: 2px solid var(--brand) !important; }
.cal-day-hoje .cal-day-num { color: var(--brand); }
.cal-tag { font-size: .66rem; padding: 3px 5px; border-radius: 5px; margin-bottom: 3px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; line-height: 1.25; max-width: 100%; min-width: 0; box-sizing: border-box; }
.tag-pago { background: #DCFCE7; color: #15803D; border-left: 3px solid #16A34A; }
.tag-atraso { background: #FEE2E2; color: #B91C1C; border-left: 3px solid #DC2626; }
.tag-hoje { background: #FEF3C7; color: #B45309; border-left: 3px solid #F59E0B; }
.tag-avencer { background: #E0F2FE; color: #0369A1; border-left: 3px solid #0284C7; }

/* ---------- Componentes nativos do Streamlit ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: var(--r-lg) !important; border-color: var(--line) !important; background: var(--paper) !important;
  box-shadow: var(--sh-sm) !important; transition: box-shadow .18s ease, border-color .18s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover { box-shadow: var(--sh-md) !important; border-color: #D3DAE6 !important; }
.block-container > [data-testid="stVerticalBlockBorderWrapper"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: transparent !important; box-shadow: none !important; border-color: transparent !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] { box-shadow: none !important; background: #FAFBFD !important; }

.stTextInput div[data-baseweb="input"], .stNumberInput div[data-baseweb="input"], .stDateInput div[data-baseweb="input"],
.stSelectbox div[data-baseweb="select"] > div, .stTextArea div[data-baseweb="textarea"] {
  border-radius: 10px !important; border-color: var(--line) !important; background: #FFFFFF !important;
}
.stTextInput div[data-baseweb="input"]:focus-within, .stNumberInput div[data-baseweb="input"]:focus-within,
.stDateInput div[data-baseweb="input"]:focus-within, .stSelectbox div[data-baseweb="select"] > div:focus-within {
  border-color: var(--brand-2) !important; box-shadow: 0 0 0 3px rgba(20,184,166,.15) !important;
}
.stApp label p, [data-testid="stWidgetLabel"] p { font-weight: 600 !important; color: var(--ink-2) !important; font-size: .84rem !important; }

.stButton > button, .stFormSubmitButton > button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stBaseButton-primaryFormSubmit"] {
  border-radius: 10px !important; font-weight: 600 !important; transition: all .15s ease !important; box-shadow: var(--sh-xs);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(135deg, #14B8A6, #0F766E) !important; border: none !important; color: #FFFFFF !important;
  box-shadow: 0 4px 14px rgba(15,118,110,.28) !important;
}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  filter: brightness(1.06); transform: translateY(-1px); box-shadow: 0 8px 20px rgba(15,118,110,.32) !important;
}
.stButton > button[kind="secondary"], [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
  background: #FFFFFF !important; border: 1px solid var(--line) !important; color: var(--ink) !important;
}
.stButton > button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover { border-color: var(--brand-2) !important; color: var(--brand) !important; }
section[data-testid="stSidebar"] .stButton > button[kind="secondary"], section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] { background: rgba(255,255,255,.08) !important; border: 1px solid rgba(255,255,255,.14) !important; box-shadow: none !important; }
[data-testid="stBaseLinkButton-secondary"], [data-testid="stBaseLinkButton-primary"] { border-radius: 10px !important; font-weight: 600 !important; }
[data-testid="stBaseLinkButton-secondary"] { border: 1px solid var(--line) !important; background: #fff !important; }
[data-testid="stBaseLinkButton-primary"] { background: linear-gradient(135deg, #14B8A6, #0F766E) !important; border: none !important; color: #FFFFFF !important; box-shadow: 0 4px 14px rgba(15,118,110,.28) !important; }
[data-testid="stBaseLinkButton-primary"] p { color: #FFFFFF !important; }

.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] { height: 44px; padding: 0 16px; border-radius: 10px 10px 0 0; font-weight: 600; color: var(--ink-3); }
.stTabs [aria-selected="true"] { color: var(--brand) !important; font-weight: 700; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--brand) !important; height: 3px; border-radius: 3px; }
.stTabs [data-baseweb="tab-border"] { display: none; }

[data-testid="stExpander"] { border: 1px solid var(--line) !important; border-radius: var(--r-lg) !important; background: var(--paper); box-shadow: var(--sh-xs); overflow: hidden; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { border: none !important; }
[data-testid="stExpander"] summary p { font-weight: 700 !important; color: var(--ink) !important; font-size: .92rem !important; }

/* Expander dentro da sidebar (alterar senha): visual escuro, integrado ao menu */
section[data-testid="stSidebar"] [data-testid="stExpander"] { background: rgba(255,255,255,.04) !important; border: 1px solid rgba(255,255,255,.1) !important; box-shadow: none !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p { color: #E2E8F0 !important; }
section[data-testid="stSidebar"] [data-testid="stForm"] { background: transparent !important; border: none !important; padding: .2rem 0 0 !important; box-shadow: none !important; }

[data-testid="stForm"] { border: 1px solid var(--line) !important; border-radius: var(--r-lg) !important; background: var(--paper); padding: 1.3rem !important; box-shadow: var(--sh-xs); }
[data-testid="stAlert"] { border-radius: var(--r-md) !important; }
[data-testid="stPopover"] > div > button, div[data-testid="stPopover"] button { border-radius: 10px !important; }
hr { border-color: var(--line) !important; }
[data-testid="stPlotlyChart"] { background: var(--paper); border: 1px solid var(--line); border-radius: var(--r-lg); padding: .6rem; box-shadow: var(--sh-sm); }
[data-testid="stToast"] { border-radius: 12px !important; }

@media (max-width: 768px) {
  .block-container { padding: 1rem 1rem 4rem !important; }
  .hero-title { font-size: 1.45rem; }
  .hero-box { padding: 1.3rem 1.2rem; }
  .banner-v { font-size: 1.8rem; text-align: left; }
  .cal-cell, .cal-cell-empty { min-height: 60px; }
  .cal-tag { font-size: .58rem; }
}

/* ---------- Acabamento profissional ---------- */
.stApp { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
*:focus-visible { outline: 2px solid var(--brand-2) !important; outline-offset: 2px; border-radius: 6px; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 10px; border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
[data-testid="stStatusWidget"] { display: none !important; }
.app-footer { text-align: center; color: var(--ink-4); font-size: .76rem; margin: 3rem 0 0; padding-top: 1.2rem; border-top: 1px solid var(--line); }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }

/* --- Correções para Celular / Responsividade (calendário e cards) --- */
@media (max-width: 768px) {
  .block-container { padding-left: .6rem !important; padding-right: .6rem !important; }
  .cal-grid {
    gap: 3px !important;
    margin: 8px 0 16px 0 !important;
  }
  .cal-cell {
    min-height: 55px !important;
    padding: 3px !important;
    border-radius: 8px !important;
  }
  .cal-cell-empty {
    min-height: 55px !important;
    border-radius: 8px !important;
  }
  .cal-day-num {
    font-size: 0.7rem !important;
    margin-bottom: 2px !important;
  }
  .cal-tag {
    font-size: 0.5rem !important;
    padding: 1px 3px !important;
    margin-bottom: 1px !important;
    border-left-width: 2px !important;
  }
  .cal-head {
    font-size: 0.6rem !important;
    padding: 6px 2px !important;
    letter-spacing: 0 !important;
    border-radius: 6px !important;
  }
  .stats { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)) !important; gap: 10px !important; }
  .stat-n { font-size: 1.25rem !important; }
}

/* ============================================================================
   POLIMENTO PROFISSIONAL (v2)
   ============================================================================ */
:root {
  --r-sm: 6px; --r-md: 8px; --r-lg: 12px; --r-xl: 14px;
  --sh-xs: 0 1px 1px rgba(15,23,42,.04);
  --sh-sm: 0 1px 2px rgba(15,23,42,.06);
  --sh-md: 0 6px 20px -8px rgba(15,23,42,.18);
}
.block-container { max-width: 1240px !important; padding-top: 1.4rem !important; }
html { font-size: 15px; }
h1, h2, h3, h4 { letter-spacing: -.015em; }

/* Cabeçalho da página */
.hero-box {
  padding: 1.15rem 1.5rem; border-radius: var(--r-xl); margin-bottom: 1.3rem; align-items: center;
  background: linear-gradient(115deg, #0B1B30 0%, #0F2A44 62%, #115E59 170%); box-shadow: var(--sh-md);
}
.hero-box::before, .hero-box::after { display: none; }
.hero-eyebrow { font-size: .66rem; letter-spacing: .12em; margin-bottom: .3rem; color: #7DD3C8; }
.hero-title { font-size: 1.4rem; letter-spacing: -.02em; }
.hero-sub { font-size: .86rem; margin-top: .3rem; color: #B6C4D4; max-width: 760px; }
.hero-date { border-radius: 8px; background: rgba(255,255,255,.07); border-color: rgba(255,255,255,.14); font-size: .76rem; padding: .4rem .8rem; backdrop-filter: none; }

/* Seções */
.sec { margin: 1.7rem 0 .8rem; padding-bottom: .5rem; border-bottom: 1px solid var(--line); }
.sec-t { font-size: .98rem; font-weight: 700; }
.sec-t::before { width: 3px; height: 15px; }
.sec-sub { margin-left: 13px; font-size: .82rem; }

/* Cards de números */
.stats { gap: 14px; }
.stat { border-radius: var(--r-lg); padding: .95rem 1.15rem .95rem 1.3rem; box-shadow: var(--sh-sm); }
.stat::before { width: 3px; }
.stat:hover { transform: none; box-shadow: var(--sh-md); }
.stat-n { font-size: 1.4rem; font-weight: 800; }
.stat-l { font-size: .76rem; text-transform: none; letter-spacing: 0; }
.kpi-l { font-size: .74rem; }
.banner { border-radius: var(--r-lg); padding: 1.15rem 1.5rem; }
.banner-v { font-size: 2rem; }

/* Linhas das listas (ativos, contas, devedores...) */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--r-lg) !important; box-shadow: var(--sh-xs) !important; }
[data-testid="stVerticalBlockBorderWrapper"]:hover { box-shadow: var(--sh-sm) !important; border-color: #CFD8E3 !important; }
.asset-tk { font-size: 1rem; font-weight: 700; }
.cell-l { text-transform: uppercase; letter-spacing: .04em; font-size: .66rem; font-weight: 700; color: var(--ink-4); }
.cell-v { font-size: .95rem; font-weight: 600; }
.cell-big { font-size: 1.05rem; font-weight: 700; }

/* Etiquetas e status: formato retangular discreto */
.chip { border-radius: 5px; padding: 1px 7px; font-size: .66rem; letter-spacing: .02em; }
.badge-status { border-radius: 6px; padding: 2px 9px; font-size: .72rem; }
.avatar { border-radius: 9px; width: 38px; height: 38px; }
.person { border-radius: var(--r-lg); padding: .8rem 1.15rem; box-shadow: var(--sh-xs); background: #F8FAFC; }
.empty { border-radius: var(--r-lg); padding: 2.2rem 1.2rem; font-size: .9rem; background: #FAFBFD; }

/* Botões e campos */
.stButton > button, .stFormSubmitButton > button, [data-testid="stBaseLinkButton-secondary"], [data-testid="stBaseLinkButton-primary"],
[data-testid="stPopover"] button { min-height: 2.35rem; border-radius: var(--r-md) !important; font-size: .86rem; }
.stTextInput div[data-baseweb="input"], .stNumberInput div[data-baseweb="input"], .stDateInput div[data-baseweb="input"],
.stSelectbox div[data-baseweb="select"] > div, .stTextArea div[data-baseweb="textarea"] { border-radius: var(--r-md) !important; }
[data-testid="stExpander"], [data-testid="stForm"] { border-radius: var(--r-lg) !important; }
.stTabs [data-baseweb="tab"] { font-size: .9rem; }

/* Menu lateral */
section[data-testid="stSidebar"] div[role="radiogroup"] label { border-radius: var(--r-md) !important; padding: .55rem .8rem !important; }
.brand-mark { border-radius: 10px; }

/* Calendário */
.cal-head { border-radius: 6px; font-size: .7rem; padding: 8px 4px; }
.cal-cell, .cal-cell-empty { border-radius: 8px; }
.cal-tag { border-radius: 4px; }

/* Cotações */
.tk, .tk-live { border-radius: var(--r-lg); }
.tk-v { font-size: 1.2rem; }

@media (max-width: 768px) {
  html { font-size: 14px; }
  .hero-title { font-size: 1.2rem; }
  .hero-box { padding: 1rem 1.1rem; }
  .banner-v { font-size: 1.6rem; }
}

/* ============================================================================
   v3 - GRÁFICOS, INDICADORES E ACABAMENTO
   ============================================================================ */
.chart-h { margin: .2rem 0 .5rem; }
.chart-t { font-size: .92rem; font-weight: 700; color: var(--ink); letter-spacing: -.01em; }
.chart-s { font-size: .78rem; color: var(--ink-3); margin-top: 2px; }
[data-testid="stPlotlyChart"] { padding: .4rem .5rem; border-radius: var(--r-lg); box-shadow: var(--sh-sm); overflow: hidden; }
.js-plotly-plot .plotly .modebar { display: none !important; }

/* Legenda dos gráficos de rosca */
.leg { display: flex; flex-direction: column; gap: 2px; padding: .4rem .2rem; }
.leg-row { display: grid; grid-template-columns: 12px 1fr auto 52px; align-items: center; gap: 10px; padding: .5rem .6rem; border-radius: 8px; font-size: .84rem; }
.leg-row:hover { background: #F4F6FA; }
.leg-dot { width: 10px; height: 10px; border-radius: 3px; }
.leg-n { color: var(--ink-2); font-weight: 600; }
.leg-v { color: var(--ink); font-weight: 700; font-variant-numeric: tabular-nums; }
.leg-p { color: var(--ink-3); font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; font-size: .78rem; }

/* Indicadores */
.meter-box { background: var(--paper); border: 1px solid var(--line); border-radius: var(--r-lg); padding: 1.1rem 1.3rem; box-shadow: var(--sh-sm); margin-bottom: 1rem; }
.meter-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; margin-bottom: .7rem; }
.meter-l { font-size: .72rem; font-weight: 700; color: var(--ink-3); text-transform: uppercase; letter-spacing: .05em; }
.meter-v { font-size: 1.5rem; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.meter-f { display: flex; justify-content: space-between; margin-top: .55rem; font-size: .78rem; color: var(--ink-3); gap: 8px; flex-wrap: wrap; }
.prog-wrap { background: #E8EDF3; }
.legend-cal { display: flex; gap: 14px; flex-wrap: wrap; font-size: .76rem; color: var(--ink-3); margin: -.4rem 0 .6rem; }
.legend-cal span::before { content: ""; display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; background: var(--c); }

/* Painéis e cabeçalho */
.insight { display: flex; gap: 12px; align-items: flex-start; background: #F0FDFA; border: 1px solid #CCEFEA; border-radius: var(--r-lg); padding: .8rem 1.1rem; font-size: .86rem; color: #115E59; line-height: 1.5; margin: .4rem 0 1rem; }
.insight b { color: #0B4F4A; }
.tip { border-radius: var(--r-md); }
.hero-box { position: relative; }
.hero-box .hero-title { text-wrap: balance; }

/* Tabelas / listas */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] { gap: .8rem; }
.stTabs [data-baseweb="tab-list"] { gap: 2px; }
.stTabs [data-baseweb="tab"] { height: 42px; padding: 0 14px; font-weight: 600; font-size: .88rem; }

/* Navegação lateral */
section[data-testid="stSidebar"] .brand { padding-bottom: 1rem; }
section[data-testid="stSidebar"] div[role="radiogroup"] label p { font-size: .9rem !important; }

/* Scroll suave e seleção */
html { scroll-behavior: smooth; }
@media (max-width: 768px) {
  .leg-row { grid-template-columns: 12px 1fr auto 44px; gap: 8px; padding: .45rem .4rem; font-size: .8rem; }
  .meter-v { font-size: 1.25rem; }
  [data-testid="stPlotlyChart"] { padding: .2rem; }
}

/* Gráficos dentro de cartões: sem borda/sombra duplicada */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPlotlyChart"] { border: none; box-shadow: none; background: transparent; padding: 0; }
.chart-h { margin: .1rem 0 .3rem; min-height: 2.6rem; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# TELA DE LOGIN (ACESSO EXCLUSIVO PARA CLIENTES + BOTÃO DE COMPRA)
# Versão protegida: SEM cadastro público. Quem não é cliente vê o botão de compra.
# ==============================================================================
if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None
if "auth_nome" not in st.session_state:
    st.session_state["auth_nome"] = ""

def _caminho_foto_sistema():
    base = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    for nome in IMAGENS_APRESENTACAO:
        for raiz in (base, os.getcwd()):
            p = os.path.join(raiz, nome)
            if os.path.exists(p):
                return p
    return None

def render_tela_login():
    if st.session_state.pop("_apagar_cookie", False):
        apagar_cookie_sessao()
    # CSS exclusivo da tela de login (não afeta o painel depois que o cliente entra)
    st.markdown("""
    <style>
    .stApp { background: radial-gradient(1100px 600px at 8% 0%, #D9F3EF 0%, rgba(217,243,239,0) 60%),
                         radial-gradient(900px 500px at 100% 100%, #DCE8FB 0%, rgba(220,232,251,0) 60%), #F4F6FA !important; }
    .block-container { max-width: 1080px !important; padding-top: 2.2rem !important; }
    section[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
    [data-testid="stExpandSidebarButton"] { display: none !important; }
    .lg-top { text-align:center; margin-bottom: 1.2rem; }
    .lg-badge { display:inline-flex; align-items:center; gap:8px; background:#fff; border:1px solid #E5E9F0; border-radius:999px; padding:6px 14px; font-size:.76rem; font-weight:700; color:#0F766E; box-shadow:0 1px 3px rgba(11,18,32,.06); }
    .lg-h { font-size:2.5rem; font-weight:900; letter-spacing:-.04em; line-height:1.1; color:#0B1220; margin:1rem 0 .7rem; }
    .lg-h span { background:linear-gradient(120deg,#0F766E,#14B8A6); -webkit-background-clip:text; background-clip:text; color:transparent; }
    .lg-p { font-size:1.02rem; color:#475569; line-height:1.65; max-width:640px; margin:0 auto; }
    .lg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; margin: 1.6rem 0 1.8rem; }
    .lg-card { background:#fff; border:1px solid #E5E9F0; border-radius:16px; padding:1.1rem 1.2rem; box-shadow:0 1px 3px rgba(11,18,32,.06); }
    .lg-ic { width:38px; height:38px; border-radius:11px; background:#E6F6F4; display:grid; place-items:center; font-size:1.1rem; margin-bottom:.6rem; }
    .lg-ft { font-weight:800; color:#0B1220; font-size:.95rem; }
    .lg-fd { color:#64748B; font-size:.84rem; margin-top:3px; line-height:1.5; }
    .lg-logo { width:54px; height:54px; border-radius:16px; background:linear-gradient(135deg,#14B8A6,#0F766E); display:grid; place-items:center; font-size:1.15rem; font-weight:800; color:#FFFFFF; letter-spacing:.02em; margin:0 auto 12px; box-shadow:0 12px 26px -8px rgba(15,118,110,.5); }
    [data-testid="stImage"] img { border-radius: 20px; box-shadow: 0 24px 50px -20px rgba(11,18,32,.35); }
    @media (max-width: 768px) { .lg-h { font-size: 1.8rem; } }
    </style>
    """, unsafe_allow_html=True)

    # --- 1) FOTO DO SISTEMA NO COMEÇO ---
    foto = _caminho_foto_sistema()
    if foto:
        st.image(foto, use_container_width=True)
    else:
        md(f"""
        <div class="lg-top">
          <div class="lg-logo">MF</div>
          <div style="font-size:1.6rem;font-weight:900;color:#0B1220;letter-spacing:-.03em">{APP_NOME}</div>
        </div>
        """)

    # --- 2) IMPORTÂNCIA DA ORGANIZAÇÃO FINANCEIRA ---
    md(f"""
    <div class="lg-top">
      <div class="lg-badge">{APP_NOME}</div>
      <div class="lg-h">Organizar o dinheiro é o primeiro passo para <span>conquistar sua liberdade.</span></div>
      <div class="lg-p">{APP_SLOGAN}. Quem sabe exatamente quanto ganha, quanto deve e para onde o dinheiro vai toma decisões melhores, evita dívidas e constrói patrimônio com tranquilidade.</div>
    </div>
    <div class="lg-grid">
      <div class="lg-card"><div class="lg-ic">🎯</div><div class="lg-ft">Clareza para decidir</div><div class="lg-fd">Veja num só painel investimentos, cartão, contas, caixinhas e metas, sem planilhas espalhadas.</div></div>
      <div class="lg-card"><div class="lg-ic">🛡️</div><div class="lg-ft">Fim dos sustos</div><div class="lg-fd">Calendário de vencimentos e diagnóstico do mês mostram o que você pode gastar com segurança.</div></div>
      <div class="lg-card"><div class="lg-ic">📈</div><div class="lg-ft">Patrimônio crescendo</div><div class="lg-fd">Acompanhe ações, FIIs, cripto e dólar em tempo real e defina metas de patrimônio e renda.</div></div>
      <div class="lg-card"><div class="lg-ic">📱</div><div class="lg-ft">Em qualquer lugar</div><div class="lg-fd">Acesse do computador ou do celular, com seus dados protegidos e isolados na nuvem.</div></div>
    </div>
    """)

    # --- 3) LOGIN (SOMENTE CLIENTES) + BOTÃO DE COMPRA PARA QUEM NÃO É CLIENTE ---
    c_center = st.columns([1, 1.5, 1])[1]
    with c_center:
        md("""
        <div style="text-align:center;margin-bottom:1rem">
          <div style="font-size:1.35rem;font-weight:800;color:#0B1220;letter-spacing:-.02em">Acesso exclusivo para membros autorizados</div>
          <div style="font-size:.88rem;color:#64748B;margin-top:2px">Entre com sua conta ou adquira sua licença</div>
        </div>
        """)

        with st.container(border=True):
            st.markdown("#### Acessar minha conta")
            with st.form("form_login"):
                email_login = st.text_input("E-mail cadastrado", placeholder="seu.email@exemplo.com").strip().lower()
                senha_login = st.text_input("Sua senha", type="password", placeholder="Digite sua senha")
                btn_entrar = st.form_submit_button("Entrar no painel", use_container_width=True, type="primary")

                if btn_entrar:
                    if not email_login or not senha_login:
                        st.error("Preencha o e-mail e a senha.")
                    else:
                        try:
                            res = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                            if res.user and res.session:
                                st.session_state["auth_user"] = res.user
                                st.session_state["auth_session"] = res.session
                                st.session_state["_saiu"] = False
                                supabase.auth.set_session(res.session.access_token, res.session.refresh_token)
                                st.rerun()
                        except Exception:
                            st.error("E-mail ou senha incorretos, ou sua licença ainda não foi ativada.")

            st.divider()

            # Se alguém que não pagou receber o link, ele vê isto:
            st.markdown("<p style='text-align:center;font-size:0.88rem;color:#64748B;margin-bottom:8px'>Ainda não tem sua licença de acesso?</p>", unsafe_allow_html=True)
            st.link_button("Adquirir meu acesso", LINK_COMPRA, use_container_width=True, type="primary")

        st.markdown("<p style='text-align:center;font-size:0.75rem;color:#94A3B8;margin-top:1.2rem'>Ambiente seguro e protegido contra acessos não autorizados.</p>", unsafe_allow_html=True)

# --- Sessão persistente: o refresh token fica em um cookie do navegador, assim o
# --- F5 / recarregar a página não derruba o login. (Requer Streamlit >= 1.37)
COOKIE_SESSAO = "mf_rt"

def _ler_cookie_sessao():
    try:
        return st.context.cookies.get(COOKIE_SESSAO)
    except Exception:
        return None

def gravar_cookie_sessao(refresh_token):
    if not refresh_token:
        return
    tok = urllib.parse.quote(str(refresh_token), safe="")
    components.html(
        "<script>(function(){try{var p=window.parent;"
        "var sec=(p.location.protocol==='https:')?'; Secure':'';"
        f"p.document.cookie='{COOKIE_SESSAO}={tok}; path=/; max-age=2592000; SameSite=Lax'+sec;"
        "}catch(e){}})();</script>", height=0)

def apagar_cookie_sessao():
    components.html(
        "<script>(function(){try{var p=window.parent;"
        f"p.document.cookie='{COOKIE_SESSAO}=; path=/; max-age=0; SameSite=Lax';"
        "}catch(e){}})();</script>", height=0)

if st.session_state["auth_user"] is None and not st.session_state.get("_saiu"):
    _rt = _ler_cookie_sessao()
    if _rt:
        try:
            _res = supabase.auth.refresh_session(urllib.parse.unquote(_rt))
            if _res and _res.user and _res.session:
                st.session_state["auth_user"] = _res.user
                st.session_state["auth_session"] = _res.session
        except Exception:
            pass

if st.session_state["auth_user"] is None:
    render_tela_login()
    st.stop()

# ==============================================================================
# CARREGAMENTO E SINCRONIZAÇÃO
# ==============================================================================
user_logado = st.session_state["auth_user"]

def carregar_dados_usuario(user):
    try:
        resp = supabase.table("perfis_financeiros").select("dados, nome").eq("user_id", user.id).execute()
        if resp.data and len(resp.data) > 0:
            d = resp.data[0].get("dados") or {}
            d_init = estrutura_inicial_dados()
            for k, v in d_init.items():
                d.setdefault(k, v)
            nome_bd = resp.data[0].get("nome") or user.email.split("@")[0].title()
            return d, nome_bd
        else:
            d_novo = estrutura_inicial_dados()
            nome_meta = ""
            if hasattr(user, "user_metadata") and user.user_metadata:
                nome_meta = user.user_metadata.get("nome", "")
            nome_final = nome_meta if nome_meta else user.email.split("@")[0].title()

            supabase.table("perfis_financeiros").insert({
                "user_id": user.id,
                "nome": nome_final,
                "email": user.email,
                "dados": d_novo
            }).execute()
            return d_novo, nome_final
    except Exception:
        return estrutura_inicial_dados(), user.email.split("@")[0].title()

def salvar_dados_usuario(dados, user):
    try:
        supabase.table("perfis_financeiros").update({"dados": dados}).eq("user_id", user.id).execute()
    except Exception:
        st.toast("Não foi possível sincronizar com o servidor. Verifique sua conexão.", icon="⚠️")

if "db_invest" not in st.session_state or st.session_state.get("db_invest") is None or st.session_state.get("last_uid") != user_logado.id:
    dados_carregados, nome_usuario = carregar_dados_usuario(user_logado)
    st.session_state["db_invest"] = dados_carregados
    st.session_state["auth_nome"] = nome_usuario
    st.session_state["last_uid"] = user_logado.id

db = st.session_state["db_invest"]
NOME_USUARIO_LOGADO = st.session_state.get("auth_nome", "Usuário")
EMAIL_USUARIO_LOGADO = user_logado.email

def salvar_dados(dados):
    st.session_state["db_invest"] = dados
    salvar_dados_usuario(dados, user_logado)

def somar_ou_adicionar_ativo(novo):
    """Se o ativo (mesmo ticker e classe) já existe na carteira, soma a quantidade e
    recalcula o preço médio ponderado. Se não existe, cadastra como novo."""
    tk = str(novo["ticker"]).strip().upper()
    cl = novo["classe"]
    for a in db["ativos"]:
        if str(a.get("ticker", "")).strip().upper() == tk and a.get("classe") == cl:
            q_old, q_new = float(a["qtd"]), float(novo["qtd"])
            pm_old, pm_new = float(a["pm"]), float(novo["pm"])
            q_tot = round(q_old + q_new, 8)
            a["pm"] = float((q_old * pm_old + q_new * pm_new) / q_tot) if q_tot > 0 else pm_new
            a["qtd"] = q_tot if (cl in CLASSES_ALT or abs(q_tot - round(q_tot)) > 1e-9) else int(round(q_tot))
            a["preco_atual"] = float(novo.get("preco_atual", a.get("preco_atual", pm_new)))
            if novo.get("data_compra"):
                a["data_compra"] = novo["data_compra"]
            if novo.get("corretora"):
                a["corretora"] = novo["corretora"]
            st.toast(f"{tk} já estava na carteira: quantidade somada e preço médio atualizado!", icon="🔁")
            return True
    db["ativos"].append(novo)
    return False

def consolidar_ativos_duplicados():
    """Junta ativos repetidos (mesmo ticker e classe) em um só, somando as quantidades
    e recalculando o preço médio ponderado. Roda sozinho a cada carregamento."""
    grupos, unicos, mudou = {}, [], False
    for a in db.get("ativos", []):
        k = (str(a.get("ticker", "")).strip().upper(), a.get("classe"))
        if k in grupos:
            base = grupos[k]
            q1, q2 = float(base["qtd"]), float(a["qtd"])
            q_tot = round(q1 + q2, 8)
            if q_tot > 0:
                base["pm"] = float((q1 * float(base["pm"]) + q2 * float(a["pm"])) / q_tot)
            base["qtd"] = q_tot if (k[1] in CLASSES_ALT or abs(q_tot - round(q_tot)) > 1e-9) else int(round(q_tot))
            base["preco_atual"] = float(a.get("preco_atual", base.get("preco_atual", base["pm"])))
            if a.get("data_compra"):
                base["data_compra"] = a["data_compra"]
            if a.get("corretora") and not base.get("corretora"):
                base["corretora"] = a["corretora"]
            mudou = True
        else:
            grupos[k] = a
            unicos.append(a)
    if mudou:
        db["ativos"] = unicos
        salvar_dados(db)
        st.toast("Ativos repetidos foram juntados em um só, com preço médio atualizado.", icon="🔁")
    return mudou

consolidar_ativos_duplicados()

# Mantém o cookie de sessão sempre com o token mais recente
if st.session_state.get("auth_session"):
    gravar_cookie_sessao(getattr(st.session_state["auth_session"], "refresh_token", None))

# ------------------------------------------------------------------------------
# ACOMPANHAR A DATA: se o dia/mês virar com o site aberto, os filtros acompanham
# ------------------------------------------------------------------------------
CHAVES_FILTRO_MES = [
    "vg_mes", "vg_ano", "diag_mes", "diag_ano", "sel_m_contas", "sel_a_contas",
    "m_prov", "a_prov", "deb_mes", "deb_ano", "sel_mfat", "sel_afat",
]
_hoje_ref = hoje_br()
_ref_mes_anterior = st.session_state.get("_ref_mes")
if _ref_mes_anterior != (_hoje_ref.year, _hoje_ref.month):
    st.session_state["_ref_mes"] = (_hoje_ref.year, _hoje_ref.month)
    if _ref_mes_anterior is not None:  # o mês virou com a sessão aberta
        for _k in CHAVES_FILTRO_MES:
            st.session_state.pop(_k, None)
        st.session_state["fatura_mes_num"] = _hoje_ref.month
        st.session_state["fatura_ano_num"] = _hoje_ref.year
        st.toast("Novo mês: os painéis foram atualizados para " + MESES_PT[_hoje_ref.month - 1] + ".", icon="📅")
st.session_state["_ref_dia"] = _hoje_ref

def _vigia_data():
    # roda a cada 60s: se virou o dia (ou o mês), recarrega o painel sozinho
    if st.session_state.get("_ref_dia") != hoje_br():
        st.rerun()

if hasattr(st, "fragment"):
    st.fragment(run_every=60)(_vigia_data)()

iniciais = "".join([part[0] for part in NOME_USUARIO_LOGADO.split()[:2]]).upper() or "UF"

# ==============================================================================
# BOTÃO FLUTUANTE DE REABRIR A BARRA LATERAL (reforço contra a "setinha" sumir)
# Se a sidebar estiver recolhida e o botão nativo do Streamlit não estiver
# visível, cria um botão "☰" fixo no canto da tela que reabre o menu.
# ==============================================================================
components.html("""
<script>
(function () {
  var doc;
  try { doc = window.parent.document; } catch (e) { return; }
  if (!doc) return;
  if (window.parent.__mfSidebarFix) return;
  window.parent.__mfSidebarFix = true;

  function nativeBtn() {
    return doc.querySelector('[data-testid="stExpandSidebarButton"]')
        || doc.querySelector('[data-testid="stSidebarCollapsedControl"] button')
        || doc.querySelector('[data-testid="collapsedControl"] button');
  }
  function visivel(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    var cs = window.parent.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  }
  function sidebarRecolhida() {
    var sb = doc.querySelector('section[data-testid="stSidebar"]');
    if (!sb) return true;
    var exp = sb.getAttribute('aria-expanded');
    if (exp === 'false') return true;
    var r = sb.getBoundingClientRect();
    return r.width < 40;
  }
  function criar() {
    var b = doc.getElementById('mf-open-sidebar');
    if (b) return b;
    b = doc.createElement('button');
    b.id = 'mf-open-sidebar';
    b.type = 'button';
    b.title = 'Abrir menu';
    b.innerHTML = '&#9776;';
    b.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2147483000;width:42px;height:42px;' +
      'border-radius:12px;border:1.5px solid #14B8A6;background:#0A1628;color:#fff;font-size:20px;' +
      'cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.28);display:none;align-items:center;justify-content:center;';
    b.addEventListener('click', function () {
      var n = nativeBtn();
      if (n) { n.click(); }
    });
    doc.body.appendChild(b);
    return b;
  }
  function ciclo() {
    var b = criar();
    var n = nativeBtn();
    var precisa = sidebarRecolhida() && !visivel(n);
    b.style.display = (precisa && n) ? 'flex' : 'none';
  }
  ciclo();
  setInterval(ciclo, 600);
})();
</script>
""", height=0)

# ==============================================================================
# FUNÇÕES DE CÁLCULO FINANCEIRO
# ==============================================================================
def inicio_fatura_compra(c):
    if c.get("mes_inicio_fatura"):
        try:
            partes = c["mes_inicio_fatura"].split("-")
            return int(partes[0]), int(partes[1])
        except Exception:
            pass
    try:
        dt_compra = datetime.strptime(c["data_compra"], "%Y-%m-%d").date()
    except Exception:
        dt_compra = hoje_br()
    m = dt_compra.month + (1 if dt_compra.day >= DIA_FECHAMENTO_CARTAO else 0)
    a = dt_compra.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    return a, m

def calcular_fatura_cartao_mes(chave_mes):
    total = 0.0
    for c in db.get("cartao_compras", []):
        p_tot = max(int(c.get("parcelas_total", 1)), 1)
        v_parc = float(c.get("valor_parcela", float(c.get("valor_total", 0.0)) / p_tot))
        a_ini, m_ini = inicio_fatura_compra(c)
        for p_idx in range(1, p_tot + 1):
            m_calc = m_ini + (p_idx - 1)
            a_calc = a_ini + (m_calc - 1) // 12
            m_real = ((m_calc - 1) % 12) + 1
            if f"{a_calc:04d}-{m_real:02d}" == chave_mes:
                total += v_parc
    return total

def recebido_devedores_no_mes(chave_mes):
    return sum(r["valor"] for r in recebimentos_devedores_mes(chave_mes))

def obter_caixinha_fluxo():
    caixinhas = db.get("caixinhas", [])
    if not caixinhas:
        return None
    cfg_id = db.get("config", {}).get("caixinha_fluxo_id")
    if cfg_id:
        for c in caixinhas:
            if c.get("id") == cfg_id:
                return c
    for c in caixinhas:
        if "fluxo" in str(c.get("nome", "")).lower():
            return c
    return caixinhas[0]

def saldo_caixinha_no_mes(cx, chave_mes=None):
    if not cx:
        return 0.0
    return float(cx.get("saldo", 0.0))

def registrar_mov_caixinha(caixinha_id, tipo, valor, data_mov, obs=""):
    db.setdefault("caixinhas_mov", []).append({
        "id": novo_id(),
        "caixinha_id": caixinha_id,
        "tipo": tipo,
        "valor": float(valor),
        "data": data_mov,
        "obs": obs
    })

def _add_meses(d, n, dia=None):
    """Soma n meses a uma data, respeitando o último dia de cada mês."""
    m0 = d.month - 1 + n
    ano, mes = d.year + m0 // 12, m0 % 12 + 1
    dia = dia or d.day
    return date(ano, mes, min(int(dia), calendar.monthrange(ano, mes)[1]))

def _parcela_divida(dev):
    parc_tot = max(int(dev.get("parcelas_total", 1)), 1)
    v_tot = float(dev.get("valor_total", 0.0))
    v = float(dev.get("valor_parcela") or 0.0)
    return v if v > 0 else (v_tot / parc_tot)

def vencimentos_divida(dev):
    """Lista com a data de vencimento de cada parcela da dívida."""
    parc_tot = max(int(dev.get("parcelas_total", 1)), 1)
    base_str = dev.get("primeiro_vencimento") or dev.get("data_vencimento") or dev.get("data_emprestimo") or dev.get("data")
    try:
        base = datetime.strptime(str(base_str), "%Y-%m-%d").date()
    except Exception:
        base = hoje_br()
    dia = int(dev.get("dia_vencimento") or base.day)
    return [_add_meses(base, i, dia) for i in range(parc_tot)]

def calcular_atraso_real_divida(dev):
    """O atraso é calculado pela DATA DE VENCIMENTO de cada parcela:
    parcela vencida (data < hoje) e ainda não coberta pelos recebimentos = em atraso."""
    v_tot = float(dev.get("valor_total", 0.0))
    v_parc = _parcela_divida(dev)
    tot_pago = float(dev.get("total_pago_reais", 0.0))
    falta_tot = max(0.0, v_tot - tot_pago)
    hoje_atual = hoje_br()

    venc = vencimentos_divida(dev)
    n_vencidas = sum(1 for d in venc if d < hoje_atual)
    esperado = min(v_tot, n_vencidas * v_parc)
    val_atraso = max(0.0, min(falta_tot, esperado - tot_pago))

    parcelas_cobertas = int((tot_pago + 0.05) // v_parc) if v_parc > 0 else 0
    n_atrasadas = max(0, n_vencidas - parcelas_cobertas) if val_atraso > 0 else 0
    # Próximo vencimento = próxima data do calendário (>= hoje). Se há atraso, mostra a parcela vencida mais antiga em aberto.
    futuras = [d for d in venc if d >= hoje_atual]
    if val_atraso > 0 and n_vencidas > 0:
        proximo_venc = venc[min(parcelas_cobertas, n_vencidas - 1)]
    else:
        proximo_venc = futuras[0] if futuras else None

    is_quitado = falta_tot <= 0.05

    dias_atraso = 0
    if is_quitado:
        status_d = "quitado"
        badge = "<span class='badge-status status-alta'>Quitado</span>"
        msg_detalhe = "Dívida totalmente paga"
    elif val_atraso > 0:
        status_d = "atrasado"
        dias_atraso = max(0, (hoje_atual - proximo_venc).days) if proximo_venc else 0
        badge = f"<span class='badge-status status-atraso'>Em atraso · {fmt_moeda(val_atraso)}</span>"
        msg_detalhe = f"{n_atrasadas} parcela(s) vencida(s) · venceu em {proximo_venc.strftime('%d/%m/%Y')} ({dias_atraso} dia(s))" if proximo_venc else f"{n_atrasadas} parcela(s) vencida(s)"
    else:
        status_d = "em_dia"
        badge = "<span class='badge-status status-alta'>Em dia</span>"
        msg_detalhe = f"Próximo vencimento: {proximo_venc.strftime('%d/%m/%Y')}" if proximo_venc else "Parcelas em dia"

    return {
        "falta_total": falta_tot,
        "valor_atraso": val_atraso,
        "v_parc": v_parc,
        "total_pago": tot_pago,
        "total_contratado": v_tot,
        "status": status_d,
        "badge": badge,
        "msg_detalhe": msg_detalhe,
        "proximo_venc": proximo_venc,
        "dias_atraso": dias_atraso,
        "n_atrasadas": n_atrasadas,
        "parcelas_cobertas": parcelas_cobertas,
    }

def recebimentos_devedores_mes(chave_mes):
    """Cada recebimento (data + valor) registrado no mês, com o nome de quem pagou."""
    lista = []
    for d in db.get("devedores", []):
        for pg in d.get("pagamentos", []):
            if str(pg.get("data", "")).startswith(chave_mes):
                lista.append({"data": str(pg["data"]), "valor": float(pg.get("valor", 0.0)),
                              "nome": d.get("nome", ""), "descricao": d.get("descricao", "")})
    return sorted(lista, key=lambda x: x["data"])

def previsto_devedores_no_mes(chave_mes):
    """Soma das parcelas que vencem no mês (valor da parcela de cada devedor)."""
    total = 0.0
    for d in db.get("devedores", []):
        v = _parcela_divida(d)
        for dt in vencimentos_divida(d):
            if dt.strftime("%Y-%m") == chave_mes:
                total += v
    return total

def sincronizar_dividendos_carteira(mes, ano):
    adicionados = 0
    chave_mes = f"{ano:04d}-{mes:02d}"
    existentes = {(p["ticker"], p["data"]) for p in db.get("proventos", [])}
    for a in db.get("ativos", []):
        t = a.get("ticker", "").upper()
        cl = a.get("classe", "")
        if cl not in ("Ações", "FIIs", "Internacional"):
            continue
        divs, _ = buscar_proventos_mercado(t)
        for d in divs:
            dt = d.get("paymentDate") or d.get("approvedOn")
            if dt and str(dt).startswith(chave_mes):
                dt_s = str(dt)[:10]
                if (t, dt_s) not in existentes:
                    val_unit = float(d.get("rate", 0.0))
                    val_calc = val_unit * float(a.get("qtd", 1))
                    if val_calc > 0:
                        db.setdefault("proventos", []).append({
                            "id": novo_id(),
                            "data": dt_s,
                            "ticker": t,
                            "valor": val_calc,
                            "tipo": d.get("type", "Dividendo"),
                            "status": "previsto"
                        })
                        existentes.add((t, dt_s))
                        adicionados += 1
    if adicionados > 0:
        salvar_dados(db)
    return adicionados

# ==============================================================================
# SIDEBAR
# ==============================================================================
MENU_ITENS = [
    "Visão Geral",
    "Resumo",
    "Contas Fixas",
    "Minha Carteira",
    "Dividendos",
    "Cartão de Crédito",
    "Movimentações",
    "Devedores",
    "Metas"
]

with st.sidebar:
    md(f"""
    <div class="brand">
      <div class="brand-mark">{html.escape(iniciais)}</div>
      <div>
        <div class="brand-name">{html.escape(NOME_USUARIO_LOGADO)}</div>
        <div class="brand-sub">{APP_NOME}</div>
      </div>
    </div>
    <div class="side-label" style="margin-top:0">Menu</div>
    """)

    _SLUGS = {m: m.lower().replace(" & ", "-").replace(" ", "-").replace("ã", "a").replace("ç", "c").replace("é", "e").replace("í", "i").replace("ó", "o") for m in MENU_ITENS}
    try:
        _p_atual = st.query_params.get("p")
    except Exception:
        _p_atual = None
    _idx_menu = next((i for i, m in enumerate(MENU_ITENS) if _SLUGS[m] == _p_atual), 0)

    menu = st.radio(
        "Navegação",
        MENU_ITENS,
        index=_idx_menu,
        key="menu_nav",
        format_func=lambda x: x,
        label_visibility="collapsed"
    )
    try:
        if st.query_params.get("p") != _SLUGS[menu]:
            st.query_params["p"] = _SLUGS[menu]
    except Exception:
        pass

    md("<div class='side-label'>Mercado</div>")
    auto_tempo_real = st.toggle("Tempo real (atualiza a cada 30s)", value=True, help="Atualiza dólar, Bitcoin, ações e FIIs automaticamente.")

    if st.button("Atualizar cotações agora", type="primary", use_container_width=True):
        CACHE.clear()
        n_mudou = atualizar_precos(db)
        st.toast(f"{n_mudou} cotações atualizadas!" if n_mudou else "Cotações já estavam em dia.", icon="📈")
        st.rerun()

    md("<div class='side-label'>Token brapi.dev (opcional)</div>")
    tk_in = st.text_input("Token brapi", value=db.get("config", {}).get("brapi_token", ""), type="password", label_visibility="collapsed", placeholder="Cole aqui seu token")
    if tk_in.strip() != db.get("config", {}).get("brapi_token", ""):
        db.setdefault("config", {})["brapi_token"] = tk_in.strip()
        salvar_dados(db)
        st.rerun()

    st.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,.1);margin:1.5rem 0 1rem 0'>", unsafe_allow_html=True)
    st.markdown(f"<div class='side-user'>Conectado como<br><b>{html.escape(EMAIL_USUARIO_LOGADO)}</b><br><span style='color:#34D399 !important'>● Banco online sincronizado</span></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # ALTERAR MINHA SENHA (o cliente troca a própria senha pelo painel)
    # --------------------------------------------------------------------------
    with st.expander("Alterar minha senha"):
        with st.form("form_alt_senha", clear_on_submit=True):
            nova_senha = st.text_input("Nova senha (mínimo 6 caracteres)", type="password", placeholder="Digite a nova senha")
            conf_senha = st.text_input("Confirme a nova senha", type="password", placeholder="Repita a nova senha")
            btn_salvar_senha = st.form_submit_button("Atualizar senha", use_container_width=True)

            if btn_salvar_senha:
                if len(nova_senha) < 6:
                    st.error("A senha precisa ter pelo menos 6 caracteres.")
                elif nova_senha != conf_senha:
                    st.error("As senhas não coincidem.")
                else:
                    try:
                        # Garante que a sessão ativa do usuário está carregada antes de atualizar
                        sess = st.session_state.get("auth_session")
                        if sess:
                            supabase.auth.set_session(sess.access_token, sess.refresh_token)
                        # Atualiza a senha usando a sessão ativa do usuário no Supabase
                        supabase.auth.update_user({"password": nova_senha})
                        st.success("Senha alterada com sucesso! Use ela nos próximos logins.")
                    except Exception:
                        st.error("Erro ao alterar senha. Tente novamente ou saia e entre de novo na conta.")

    if st.button("Sair da conta", use_container_width=True):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state["auth_user"] = None
        st.session_state["auth_session"] = None
        st.session_state["db_invest"] = None
        st.session_state["_saiu"] = True
        st.session_state["_apagar_cookie"] = True
        st.rerun()

if auto_tempo_real:
    try:
        atualizar_precos(db)
    except Exception:
        pass

# ==============================================================================
# ENGENHARIA DE INVESTIMENTOS
# ==============================================================================
df_ativos = pd.DataFrame(db["ativos"])
if df_ativos.empty:
    df_ativos = pd.DataFrame(columns=["id", "ticker", "nome", "classe", "qtd", "pm", "preco_atual"])

if not df_ativos.empty:
    df_ativos["qtd"] = df_ativos["qtd"].astype(float)
    df_ativos["valor_investido"] = df_ativos["qtd"] * df_ativos["pm"]
    df_ativos["valor_atual"] = df_ativos["qtd"] * df_ativos["preco_atual"]
    df_ativos["lucro_reais"] = df_ativos["valor_atual"] - df_ativos["valor_investido"]
    df_ativos["rentabilidade_pct"] = (df_ativos["lucro_reais"] / df_ativos["valor_investido"].replace(0, float("nan"))) * 100
else:
    df_ativos["valor_investido"] = []
    df_ativos["valor_atual"] = []
    df_ativos["lucro_reais"] = []
    df_ativos["rentabilidade_pct"] = []

caixinhas_lista = db.get("caixinhas", [])
total_em_caixinhas = sum(float(c.get("saldo", 0.0)) for c in caixinhas_lista)
patrimonio_investido_bolsa = float(df_ativos["valor_atual"].sum()) if not df_ativos.empty else 0.0
patrimonio_total = patrimonio_investido_bolsa + total_em_caixinhas

# ==============================================================================
# BARRA DE COTAÇÕES AO VIVO
# ==============================================================================
def _card_cotacao(nome, q, tipo="moeda", casas=2):
    if not q:
        return ""
    if tipo == "dolar":
        v = f"US$ {q['preco']:,.4f}".replace(".", ",")
    elif tipo == "moeda":
        v = fmt_moeda(q["preco"], casas)
    else:
        v = fmt_num(q["preco"], 0) + " pts"
    pct = q.get("pct")
    if pct is None:
        p_html = "<div class='tk-p tk-flat'>— ao vivo</div>"
    else:
        pct = float(pct)
        cls = "tk-up" if pct > 0 else ("tk-down" if pct < 0 else "tk-flat")
        seta = "▲" if pct > 0 else ("▼" if pct < 0 else "■")
        p_html = f"<div class='tk-p {cls}'>{seta} {fmt_pct(pct)} hoje</div>"
    return f"<div class='tk'><div class='tk-n'>{nome}</div><div class='tk-v'>{v}</div>{p_html}</div>"

def render_barra_cotacoes():
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_usd = ex.submit(cotacao_dolar)
        f_btc = ex.submit(cotacao_cripto, "BTC")
        f_ibov = ex.submit(cotacao_ibov)
        usd, btc, ibov = f_usd.result(), f_btc.result(), f_ibov.result()

    hora = agora_br().strftime("%H:%M:%S")
    status = "AO VIVO · 30s" if auto_tempo_real else "MANUAL"

    cards_html = _card_cotacao("Dólar", usd, tipo="dolar", casas=4) + _card_cotacao("Bitcoin", btc, casas=0)
    if ibov:
        cards_html += _card_cotacao("Ibovespa", ibov, tipo="pts")

    md(
        "<div class='ticker'>"
        + cards_html
        + f"<div class='tk-live'><b><span class='live-dot'></span>{status}</b><span>Atualizado às {hora}</span></div>"
        + "</div>"
    )

def _barra_ao_vivo():
    render_barra_cotacoes()
    if auto_tempo_real:
        if atualizar_precos(db) > 0:
            st.rerun()

if auto_tempo_real and hasattr(st, "fragment"):
    st.fragment(run_every=30)(_barra_ao_vivo)()
else:
    _barra_ao_vivo()

def txt_qtd(row):
    cl = row["classe"]
    q = float(row["qtd"])
    if cl == "Dólar":
        return f"US$ {fmt_num(q, 2)}"
    if cl == "Cripto":
        return f"{fmt_num_limpo(q)} {row['ticker']}"
    return f"{int(q)} cotas"

def listar_ativos(df_view):
    for idx, row in df_view.iterrows():
        cl = row["classe"]
        frac = cl in CLASSES_ALT
        casas_preco = 4 if cl == "Dólar" else 2
        lucro_r = row["lucro_reais"]
        ret_pct = row["rentabilidade_pct"]

        badge_mercado = f"<span class='badge-status {'status-alta' if lucro_r >= 0 else 'status-baixa'}'>{'Valorizou' if lucro_r >= 0 else 'Caiu'} · {fmt_moeda(lucro_r)} ({fmt_pct(ret_pct)})</span>"

        if cl == "Dólar":
            rot_pm, rot_cot = "Dólar que paguei", "Dólar agora"
        elif cl == "Cripto":
            rot_pm, rot_cot = "Preço que paguei", "Preço agora"
        else:
            rot_pm, rot_cot = "Preço pago", "Cotação"

        cor_cl = CORES_CLASSE.get(cl, "#2563EB")

        extra = ""
        _corr = row.get("corretora")
        if isinstance(_corr, str) and _corr.strip():
            extra = f" · {html.escape(_corr.strip())}"
        _dt_c = row.get("data_compra")
        if isinstance(_dt_c, str) and _dt_c.strip():
            try:
                extra += " · " + datetime.strptime(_dt_c, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                pass

        with st.container(border=True):
            c_info, c_compra, c_atual, c_ret, c_act = st.columns([1.6, 1.3, 1.3, 1.4, 0.8], vertical_alignment="center")
            with c_info:
                md(f"""<div class="asset"><div class="avatar" style="background:{cor_cl}1A;color:{cor_cl}">{html.escape(str(row['ticker'])[:3])}</div>
                <div><div class="asset-tk">{html.escape(str(row['ticker']))} {chip_classe(cl)}</div>
                <div class="asset-sub">{html.escape(str(row['nome']))}{extra}</div></div></div>""")

            with c_compra:
                md(f"""<div><div class="cell-l">Você tem</div><div class="cell-v">{txt_qtd(row)}</div>
                <div class="cell-l" style="margin-top:4px">{rot_pm}: <b style="color:#0B1220">{fmt_moeda(row['pm'], casas_preco)}</b></div>
                <div class="cell-l">Investido: <b style="color:#0B1220">{fmt_moeda(row['valor_investido'])}</b></div></div>""")

            with c_atual:
                ao_vivo = " <span class='live-dot'></span>" if (auto_tempo_real and cl != "Renda Fixa") else ""
                md(f"""<div><div class="cell-l">{rot_cot}{ao_vivo}</div><div class="cell-v">{fmt_moeda(row['preco_atual'], casas_preco)}</div>
                <div class="cell-l" style="margin-top:4px">Saldo atual</div><div class="cell-big">{fmt_moeda(row['valor_atual'])}</div></div>""")

            with c_ret:
                md(f"<div>{badge_mercado}</div>")

            with c_act:
                col_vend, col_edit = st.columns(2)
                with col_vend:
                    with st.popover(":material/sell:", use_container_width=True, help="Vender"):
                        st.markdown(f"**Vender {row['ticker']}**")
                        if frac:
                            casas = 2 if cl == "Dólar" else 8
                            qtd_venda = st.number_input(
                                "Quantidade vendida", min_value=float(10 ** -casas), max_value=float(row["qtd"]),
                                value=float(row["qtd"]), step=float(10.0 if cl == "Dólar" else 0.001),
                                format=f"%.{casas}f", key=f"v_qtd_{row['id']}")
                        else:
                            qtd_venda = st.number_input("Cotas vendidas", min_value=1, max_value=int(row["qtd"]), value=int(row["qtd"]), step=1, key=f"v_qtd_{row['id']}")
                        p_venda = st.number_input("Valor da venda por unidade (R$)", min_value=0.0001, value=float(row["preco_atual"]), format="%.4f" if cl == "Dólar" else "%.2f", key=f"v_p_{row['id']}")
                        dt_venda = st.date_input("Data da venda", value=hoje_br(), format="DD/MM/YYYY", key=f"v_dt_{row['id']}")

                        if st.button("Confirmar Venda", key=f"btn_v_{row['id']}", type="primary", use_container_width=True):
                            db.setdefault("vendas", []).append({
                                "id": novo_id(), "ticker": row["ticker"], "classe": row["classe"], "qtd": float(qtd_venda) if frac else int(qtd_venda),
                                "pm_compra": float(row["pm"]), "preco_venda": float(p_venda), "total_recebido": float(qtd_venda * p_venda),
                                "lucro_reais": float((p_venda - row["pm"]) * qtd_venda),
                                "rentabilidade_pct": float(((p_venda - row["pm"]) / row["pm"]) * 100) if row["pm"] > 0 else 0.0,
                                "data": dt_venda.strftime("%Y-%m-%d")
                            })
                            for at in db["ativos"]:
                                if at["id"] == row["id"]:
                                    nova_q = round(float(at["qtd"]) - float(qtd_venda), 8)
                                    at["qtd"] = nova_q if frac else int(round(nova_q))
                            db["ativos"] = [a for a in db["ativos"] if float(a["qtd"]) > 1e-8]
                            salvar_dados(db)
                            st.toast("Venda registrada!", icon="💰")
                            st.rerun()

                with col_edit:
                    with st.popover(":material/settings:", use_container_width=True, help="Editar / Excluir"):
                        n_atual = st.number_input("Cotação Atual (R$)", value=float(row["preco_atual"]), format="%.4f" if cl == "Dólar" else "%.2f", key=f"cot_{row['id']}")
                        n_pm = st.number_input("Preço Médio / Pago (R$)", value=float(row["pm"]), format="%.4f" if cl == "Dólar" else "%.2f", key=f"pm_{row['id']}")
                        if frac:
                            n_qtd = st.number_input("Quantidade", min_value=0.00000001, value=float(row["qtd"]), format="%.8f" if cl == "Cripto" else "%.2f", key=f"qtd_{row['id']}")
                        else:
                            n_qtd = st.number_input("Cotas", min_value=1, value=int(row["qtd"]), step=1, key=f"qtd_{row['id']}")
                        if st.button("Salvar", key=f"up_{row['id']}", type="primary", use_container_width=True):
                            for at in db["ativos"]:
                                if at["id"] == row["id"]:
                                    at["preco_atual"] = float(n_atual)
                                    at["pm"] = float(n_pm)
                                    at["qtd"] = float(n_qtd) if frac else int(n_qtd)
                            salvar_dados(db)
                            st.toast("Atualizado!")
                            st.rerun()
                        if st.button("Excluir", key=f"del_{row['id']}", use_container_width=True):
                            db["ativos"] = [a for a in db["ativos"] if a["id"] != row["id"]]
                            salvar_dados(db)
                            st.rerun()

# ==============================================================================
# VISUALIZAÇÕES (gráficos e componentes visuais reutilizáveis)
# ==============================================================================
ALTURA_CARD = 340  # altura padrão dos gráficos que ficam lado a lado
COR_ENTRADA = "#059669"
COR_SAIDA = "#E11D48"
COR_BRAND = "#0F766E"
COR_AZUL = "#2563EB"
COR_NEUTRA = "#CBD5E1"
CORES_ORIGEM = {"Cartão": "#2563EB", "Contas fixas": "#E11D48", "Débito / PIX": "#F59E0B"}
SEQ_CORES = ["#0F766E", "#2563EB", "#7C3AED", "#D97706", "#E11D48", "#0891B2", "#059669", "#DB2777", "#64748B"]

def estilizar(fig, altura=320, legenda=True, **extra):
    """Aplica o visual padrão do sistema a qualquer gráfico Plotly."""
    layout = dict(LAYOUT_GRAFICO)
    layout.update(height=altura, showlegend=legenda)
    if legenda:
        layout["legend"] = dict(orientation="h", yanchor="top", y=-0.14, xanchor="center", x=0.5, font=dict(size=11), title=None)
    layout.update(extra)
    fig.update_layout(**layout)
    fig.update_xaxes(showgrid=False, linecolor="#E5E9F0", tickfont=dict(size=11, color="#64748B"), title=None)
    fig.update_yaxes(gridcolor=GRADE_GRAFICO, zeroline=False, tickfont=dict(size=11, color="#64748B"), title=None)
    return fig

def mostrar(fig):
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)

def titulo_grafico(titulo, sub=""):
    s_ = f"<div class='chart-s'>{sub}</div>" if sub else ""
    md(f"<div class='chart-h'><div class='chart-t'>{titulo}</div>{s_}</div>")

def rotulo_mes(a, m):
    return f"{MESES_PT[m - 1][:3]}/{str(a)[2:]}"

def meses_ate(ano, mes, n):
    """Lista de (ano, mês) dos n meses que terminam no mês informado."""
    out = []
    for i in range(n - 1, -1, -1):
        m0 = (ano * 12 + mes - 1) - i
        out.append((m0 // 12, m0 % 12 + 1))
    return out

def resumo_mes(chave):
    """Totais do mês usados nos gráficos (mesmas regras da Visão Geral)."""
    trans = db.get("transacoes_debito", [])
    ent = sum(float(t["valor"]) for t in trans if t["tipo"] == "Entrada (+)" and t["data"].startswith(chave))
    prov = sum(float(p["valor"]) for p in db.get("proventos", []) if p.get("status") == "recebido" and p["data"].startswith(chave))
    deb = sum(float(t["valor"]) for t in trans if t["tipo"] == "Saída (-)" and t["data"].startswith(chave))
    fat = calcular_fatura_cartao_mes(chave)
    cfx = sum(float(c["valor"]) for c in db.get("contas_fixas", []) if c["mes_ano"] == chave)
    return {"entradas": ent + prov, "fatura": fat, "contas": cfx, "debito": deb, "despesas": fat + cfx + deb}

def despesas_por_categoria(chave):
    """Despesas do mês por categoria e origem (cartão, contas fixas, débito/PIX)."""
    linhas = []
    for c in db.get("cartao_compras", []):
        p_tot = max(int(c.get("parcelas_total", 1)), 1)
        v_parc = float(c.get("valor_parcela", float(c.get("valor_total", 0.0)) / p_tot))
        a_ini, m_ini = inicio_fatura_compra(c)
        for p_idx in range(1, p_tot + 1):
            m_calc = m_ini + (p_idx - 1)
            a_calc = a_ini + (m_calc - 1) // 12
            m_real = ((m_calc - 1) % 12) + 1
            if f"{a_calc:04d}-{m_real:02d}" == chave:
                linhas.append(("Cartão", c.get("categoria", "Outros"), v_parc))
    for c in db.get("contas_fixas", []):
        if c["mes_ano"] == chave:
            linhas.append(("Contas fixas", c.get("categoria", "Outros"), float(c["valor"])))
    for t in db.get("transacoes_debito", []):
        if t["tipo"] == "Saída (-)" and t["data"].startswith(chave):
            linhas.append(("Débito / PIX", t.get("categoria", "Outros"), float(t["valor"])))
    return pd.DataFrame(linhas, columns=["origem", "categoria", "valor"])

def fig_fluxo_mes(entradas, caixinha, fatura, contas, debito, nome_caixinha="Caixinha"):
    """Cascata: de onde vem o dinheiro e para onde ele vai até chegar ao saldo livre."""
    saldo = entradas + caixinha - fatura - contas - debito
    rot = ["Entradas", "Caixinha", "Cartão", "Contas", "Débito/PIX", "Saldo livre"]
    val = [entradas, caixinha, -fatura, -contas, -debito, 0]
    txt = [fmt_moeda(entradas), fmt_moeda(caixinha), "-" + fmt_moeda(fatura), "-" + fmt_moeda(contas), "-" + fmt_moeda(debito), fmt_moeda(saldo)]
    fig = go.Figure(go.Waterfall(
        x=rot, y=val, measure=["relative"] * 5 + ["total"], text=txt, textposition="outside", cliponaxis=False,
        connector=dict(line=dict(color="#CBD5E1", width=1, dash="dot")),
        increasing=dict(marker=dict(color=COR_ENTRADA)), decreasing=dict(marker=dict(color=COR_SAIDA)),
        totals=dict(marker=dict(color=COR_BRAND if saldo >= 0 else "#991B1B")),
        hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>"))
    estilizar(fig, ALTURA_CARD, legenda=False, margin=dict(l=10, r=10, t=34, b=10))
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig

def fig_evolucao(lista_meses):
    """Entradas x despesas dos últimos meses, com a linha do saldo."""
    rot, ent, desp, saldo = [], [], [], []
    for a, m in lista_meses:
        r = resumo_mes(f"{a:04d}-{m:02d}")
        rot.append(rotulo_mes(a, m)); ent.append(r["entradas"]); desp.append(r["despesas"]); saldo.append(r["entradas"] - r["despesas"])
    fig = go.Figure()
    fig.add_bar(x=rot, y=ent, name="Entradas", marker=dict(color=COR_ENTRADA, cornerradius=5),
                hovertemplate="<b>%{x}</b><br>Entradas: R$ %{y:,.2f}<extra></extra>")
    fig.add_bar(x=rot, y=desp, name="Despesas", marker=dict(color=COR_SAIDA, cornerradius=5),
                hovertemplate="<b>%{x}</b><br>Despesas: R$ %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=rot, y=saldo, name="Saldo do mês", mode="lines+markers",
                    line=dict(color="#0B1220", width=2.5), marker=dict(size=8, color="#FFFFFF", line=dict(color="#0B1220", width=2)),
                    hovertemplate="<b>%{x}</b><br>Saldo: R$ %{y:,.2f}<extra></extra>")
    estilizar(fig, ALTURA_CARD, barmode="group", bargap=0.35, bargroupgap=0.08)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig

def rotulo_curto(txt, n=20):
    """Encurta nomes de categoria para caberem no gráfico sem distorcer."""
    t = str(txt).split(" (")[0].strip()
    if len(t) > n and " / " in t:
        t = t.split(" / ")[0].strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"

def fig_despesas_top(df, n=6):
    """Maiores categorias de despesa do mês (barras limpas, com valor e % ao lado)."""
    if df.empty:
        return None
    d = df.copy()
    d["rot"] = d["categoria"].map(rotulo_curto)
    g = d.groupby("rot")["valor"].sum().sort_values(ascending=False)
    top = g.head(n)
    resto = float(g.iloc[n:].sum())
    if resto > 0:
        top = pd.concat([top, pd.Series({"Outras": resto})])
    total = float(g.sum()) or 1.0
    cores = [COR_NEUTRA if r == "Outras" else "#F43F5E" for r in top.index]
    textos = [f"{fmt_moeda(v)}  ·  {v / total * 100:.0f}%" for v in top.values]
    fig = go.Figure(go.Bar(x=top.values, y=list(top.index), orientation="h", marker=dict(color=cores, cornerradius=6),
                           text=textos, textposition="outside", cliponaxis=False, textfont=dict(size=11, color="#334155"),
                           hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>"))
    estilizar(fig, ALTURA_CARD, legenda=False, margin=dict(l=10, r=125, t=10, b=10), bargap=0.42)
    fig.update_xaxes(showgrid=False, showticklabels=False, zeroline=False)
    fig.update_yaxes(showgrid=False, autorange="reversed", tickfont=dict(size=12, color="#334155"))
    return fig

def fig_categorias(df):
    """Barras empilhadas por categoria, coloridas pela origem do gasto."""
    if df.empty:
        return None
    ordem = df.groupby("categoria")["valor"].sum().sort_values().index.tolist()
    fig = px.bar(df.groupby(["categoria", "origem"], as_index=False)["valor"].sum(), x="valor", y="categoria", color="origem",
                 orientation="h", color_discrete_map=CORES_ORIGEM, category_orders={"categoria": ordem})
    fig.update_traces(marker=dict(cornerradius=4), hovertemplate="<b>%{y}</b><br>%{fullData.name}: R$ %{x:,.2f}<extra></extra>")
    estilizar(fig, max(280, 38 * len(ordem) + 100), bargap=0.3)
    fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", showgrid=True, gridcolor=GRADE_GRAFICO)
    fig.update_yaxes(showgrid=False)
    return fig

def fig_donut(rotulos, valores, cores, centro, altura=300, legenda=False):
    """Rosca. Com legenda=True a legenda fica dentro do próprio gráfico (altura previsível, alinha com outros cartões)."""
    fig = go.Figure(go.Pie(
        labels=rotulos, values=valores, hole=0.66, sort=False, direction="clockwise",
        textinfo="percent" if legenda else "none", textposition="inside", insidetextorientation="horizontal",
        textfont=dict(size=11, color="#FFFFFF"),
        marker=dict(colors=cores, line=dict(color="#FFFFFF", width=3)),
        hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f} (%{percent})<extra></extra>"))
    fig.add_annotation(text=centro, showarrow=False, align="center", font=dict(size=15, color="#0B1220"))
    estilizar(fig, altura, legenda=legenda, margin=dict(l=10, r=10, t=10, b=10), uniformtext=dict(minsize=10, mode="hide"))
    return fig

def legenda_html(rotulos, valores, cores):
    total = sum(valores) or 1.0
    linhas = "".join(
        f"<div class='leg-row'><span class='leg-dot' style='background:{c}'></span><span class='leg-n'>{html.escape(str(r))}</span>"
        f"<span class='leg-v'>{fmt_moeda(v)}</span><span class='leg-p'>{v / total * 100:.1f}%</span></div>"
        for r, v, c in zip(rotulos, valores, cores))
    return f"<div class='leg'>{linhas}</div>"

def fig_resultado_ativos(df):
    d = df.sort_values("lucro_reais")
    cores = [COR_ENTRADA if v >= 0 else COR_SAIDA for v in d["lucro_reais"]]
    textos = [f"{fmt_moeda(v)}  ·  {fmt_pct(p)}" for v, p in zip(d["lucro_reais"], d["rentabilidade_pct"])]
    fig = go.Figure(go.Bar(x=d["lucro_reais"], y=d["ticker"], orientation="h", marker=dict(color=cores, cornerradius=5),
                           text=textos, textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>"))
    estilizar(fig, max(ALTURA_CARD, 38 * len(d) + 90), legenda=False, margin=dict(l=10, r=135, t=10, b=10), bargap=0.4)
    fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", showgrid=True, gridcolor=GRADE_GRAFICO, zeroline=True, zerolinecolor="#94A3B8")
    fig.update_yaxes(showgrid=False)
    return fig

def fig_projecao_faturas(chaves, projecao, chave_sel):
    rot = [rotulo_mes(int(k[:4]), int(k[5:7])) for k in chaves]
    val = [projecao[k] for k in chaves]
    cores = [COR_BRAND if k == chave_sel else "#99D5CE" for k in chaves]
    fig = go.Figure(go.Bar(x=rot, y=val, marker=dict(color=cores, cornerradius=7), text=[fmt_moeda(v, 0) for v in val],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{x}</b><br>Fatura: R$ %{y:,.2f}<extra></extra>"))
    if val:
        media = sum(val) / len(val)
        fig.add_hline(y=media, line=dict(color="#94A3B8", width=1.5, dash="dash"),
                      annotation_text=f"média {fmt_moeda(media, 0)}", annotation_position="top left",
                      annotation_font=dict(size=11, color="#64748B"))
    estilizar(fig, 330, legenda=False, margin=dict(l=10, r=10, t=30, b=10), bargap=0.3)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig

def fig_divida_restante(chaves, projecao):
    """Quanto ainda falta pagar de parcelas, mês a mês."""
    rot = [rotulo_mes(int(k[:4]), int(k[5:7])) for k in chaves]
    rest = [sum(projecao[k] for k in chaves[i:]) for i in range(len(chaves))]
    fig = go.Figure(go.Scatter(x=rot, y=rest, mode="lines+markers", fill="tozeroy",
                               line=dict(color=COR_BRAND, width=3, shape="spline"), fillcolor="rgba(15,118,110,.12)",
                               marker=dict(size=7, color="#FFFFFF", line=dict(color=COR_BRAND, width=2)),
                               hovertemplate="<b>%{x}</b><br>Ainda a pagar: R$ %{y:,.2f}<extra></extra>"))
    estilizar(fig, 300, legenda=False)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", rangemode="tozero")
    return fig

def fig_barras_simples(rotulos, valores, cor=COR_AZUL, altura=280):
    fig = go.Figure(go.Bar(x=valores, y=rotulos, orientation="h", marker=dict(color=cor, cornerradius=5),
                           text=[fmt_moeda(v) for v in valores], textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>"))
    estilizar(fig, altura, legenda=False, margin=dict(l=10, r=90, t=10, b=10), bargap=0.4)
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig

def barra_progresso(pct, cor=None, altura=10):
    """Barra de progresso em HTML (pct de 0 a 100)."""
    pct = max(0.0, min(100.0, float(pct)))
    fundo = cor or "linear-gradient(90deg,#14B8A6,#0F766E)"
    return f"<div class='prog-wrap' style='height:{altura}px'><div class='prog-bar' style='width:{pct:.1f}%;background:{fundo}'></div></div>"

# ==============================================================================
# TELA: VISÃO GERAL
# ==============================================================================
def pagina_visao_geral() -> None:
    """Tela: Visão Geral."""
    hero(f"Visão Geral · {NOME_USUARIO_LOGADO}", "Painel consolidado e interativo: clique em “Ver detalhes” em cada card para ver exatamente o que compõe cada número.")

    hoje = hoje_br()

    c_m1, c_m2 = st.columns([2.5, 1])
    with c_m1:
        mes_vg_idx = st.selectbox("Mês de Análise", range(1, 13), index=hoje.month - 1, format_func=lambda x: MESES_PT[x-1], key="vg_mes")
    with c_m2:
        ano_vg = st.selectbox("Ano", [hoje.year - 1, hoje.year, hoje.year + 1], index=1, key="vg_ano")

    chave_mes_vg = f"{ano_vg:04d}-{mes_vg_idx:02d}"
    nome_mes_vg = MESES_PT[mes_vg_idx - 1]

    transacoes = db.get("transacoes_debito", [])
    trans_entradas_mes = [t for t in transacoes if t["tipo"] == "Entrada (+)" and t["data"].startswith(chave_mes_vg)]
    entradas_conta_mes = sum(float(t["valor"]) for t in trans_entradas_mes)

    proventos = db.get("proventos", [])
    prov_mes_lista = [p for p in proventos if p.get("status") == "recebido" and p["data"].startswith(chave_mes_vg)]
    proventos_mes = sum(float(p["valor"]) for p in prov_mes_lista)

    # Recebimentos de devedores NÃO entram na soma: já são lançados como entrada (PIX) em Conta & Débito.
    total_entradas_mes = entradas_conta_mes + proventos_mes

    contas_mes = [c for c in db.get("contas_fixas", []) if c["mes_ano"] == chave_mes_vg]
    total_contas_fixas_mes = sum(float(c["valor"]) for c in contas_mes)

    fatura_cartao_mes = calcular_fatura_cartao_mes(chave_mes_vg)

    trans_saidas_mes = [t for t in transacoes if t["tipo"] == "Saída (-)" and t["data"].startswith(chave_mes_vg)]
    saidas_debito_mes = sum(float(t["valor"]) for t in trans_saidas_mes)
    total_despesas_mes = fatura_cartao_mes + total_contas_fixas_mes + saidas_debito_mes

    cx_fluxo = obter_caixinha_fluxo()
    saldo_fluxo = saldo_caixinha_no_mes(cx_fluxo, chave_mes_vg)
    nome_cx_fluxo = cx_fluxo["nome"] if cx_fluxo else "Fluxo do Mês"

    total_recursos_disponiveis = total_entradas_mes + saldo_fluxo
    saldo_livre_consolidado = total_recursos_disponiveis - total_despesas_mes
    saldo_direto_receitas = total_entradas_mes - total_despesas_mes
    esta_positivo = saldo_livre_consolidado >= 0

    cor_borda = "#10B981" if esta_positivo else "#EF4444"
    cor_txt = "#047857" if esta_positivo else "#B91C1C"
    bg_banner = "linear-gradient(135deg,#ECFDF5 0%,#FFFFFF 70%)" if esta_positivo else "linear-gradient(135deg,#FEF2F2 0%,#FFFFFF 70%)"
    msg_titulo = f"Financeiro positivo · {nome_mes_vg}/{ano_vg}" if esta_positivo else f"Financeiro negativo · {nome_mes_vg}/{ano_vg}"

    md(f"""
    <div class="banner" style="--accent:{cor_borda};background:{bg_banner}">
      <div>
        <div class="banner-t" style="color:{cor_txt}">{msg_titulo}</div>
        <div class="banner-d">
          Total disponível: <b>{fmt_moeda(total_recursos_disponiveis)}</b> (entradas + caixinha {html.escape(nome_cx_fluxo)}) · Despesas: <b>{fmt_moeda(total_despesas_mes)}</b>
          <br>Sobra das receitas do mês: <b>{fmt_moeda(saldo_direto_receitas)}</b> (sem mexer na caixinha de reserva).
        </div>
      </div>
      <div>
        <div class="banner-v" style="color:{'#15803D' if esta_positivo else '#B91C1C'}">{fmt_moeda(saldo_livre_consolidado)}</div>
        <div class="banner-vl">Saldo livre</div>
      </div>
    </div>
    """)

    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)

    with col_c1:
        with st.container(border=True):
            md(kpi(f"+{fmt_moeda(total_entradas_mes)}", "Entradas no mês", "#15803D"))
            with st.popover("Ver detalhes", use_container_width=True):
                st.markdown(f"**Entradas em {nome_mes_vg}/{ano_vg}**")
                st.write(f"• Conta / Débito: **{fmt_moeda(entradas_conta_mes)}**")
                st.write(f"• Proventos/Dividendos: **{fmt_moeda(proventos_mes)}**")
                st.divider()
                st.caption("Extrato das entradas:")
                for te in trans_entradas_mes:
                    st.text(f"• {te['data'][8:10]}/{te['data'][5:7]}: {te['descricao']} (+{fmt_moeda(te['valor'])})")

    with col_c2:
        with st.container(border=True):
            md(kpi(f"+{fmt_moeda(saldo_fluxo)}", f"Caixinha ({html.escape(nome_cx_fluxo)})", "#0F766E"))
            with st.popover("Ver detalhes", use_container_width=True):
                st.markdown(f"**Caixinha {html.escape(nome_cx_fluxo)}**")
                st.write(f"• Saldo disponível: **{fmt_moeda(saldo_fluxo)}**")
                if cx_fluxo:
                    st.write(f"• Banco: **{cx_fluxo.get('banco', 'Nubank')}**")
                    st.write(f"• Rendimento acumulado: **{fmt_moeda(cx_fluxo.get('rendimento', 0.0))}**")

    with col_c3:
        with st.container(border=True):
            md(kpi(f"-{fmt_moeda(fatura_cartao_mes)}", "Fatura do cartão", "#2563EB"))
            with st.popover("Ver detalhes", use_container_width=True):
                st.markdown(f"**Compras na fatura de {nome_mes_vg}/{ano_vg}**")
                faturas_mes_itens = []
                for c in db.get("cartao_compras", []):
                    p_tot = max(int(c.get("parcelas_total", 1)), 1)
                    v_parc = float(c.get("valor_parcela", float(c["valor_total"]) / p_tot))
                    a_ini, m_ini = inicio_fatura_compra(c)
                    for p_idx in range(1, p_tot + 1):
                        m_calc = m_ini + (p_idx - 1)
                        a_calc = a_ini + (m_calc - 1) // 12
                        m_real = ((m_calc - 1) % 12) + 1
                        if f"{a_calc:04d}-{m_real:02d}" == chave_mes_vg:
                            faturas_mes_itens.append((c['descricao'], p_idx, p_tot, v_parc))
                if not faturas_mes_itens:
                    st.caption("Nenhuma compra parcelada nesta fatura.")
                else:
                    for nom_c, p_i, p_t, v_p in faturas_mes_itens:
                        st.write(f"• **{nom_c}** ({p_i}/{p_t}x): {fmt_moeda(v_p)}")

    with col_c4:
        with st.container(border=True):
            md(kpi(f"-{fmt_moeda(total_contas_fixas_mes)}", "Contas fixas", "#B91C1C"))
            with st.popover("Ver detalhes", use_container_width=True):
                st.markdown(f"**Contas Fixas em {nome_mes_vg}/{ano_vg}**")
                if not contas_mes:
                    st.caption("Nenhuma conta fixa cadastrada para este mês.")
                else:
                    for cf in contas_mes:
                        st_icon = "✅ PAGO" if cf.get("status") == "pago" else "⏳ A PAGAR"
                        st.write(f"• **{cf['nome']}** (Dia {cf['dia_vencimento']}): {fmt_moeda(cf['valor'])} — *{st_icon}*")

    with col_c5:
        with st.container(border=True):
            md(kpi(f"-{fmt_moeda(saidas_debito_mes)}", "Débito & PIX", "#EA580C"))
            with st.popover("Ver detalhes", use_container_width=True):
                st.markdown(f"**Saídas no Débito em {nome_mes_vg}/{ano_vg}**")
                if not trans_saidas_mes:
                    st.caption("Nenhuma saída no débito registrada.")
                else:
                    for ts in trans_saidas_mes:
                        st.write(f"• {ts['data'][8:10]}/{ts['data'][5:7]}: **{ts['descricao']}** (-{fmt_moeda(ts['valor'])})")

    # ---------------- Fluxo do mês ----------------
    secao(f"Fluxo de {nome_mes_vg}", "De onde veio o dinheiro, para onde foi e quanto sobrou.")
    col_f1, col_f2 = st.columns(2, gap="large")
    with col_f1:
        with st.container(border=True):
            titulo_grafico("Do dinheiro disponível ao saldo livre", "Entradas e caixinha menos as despesas")
            mostrar(fig_fluxo_mes(total_entradas_mes, saldo_fluxo, fatura_cartao_mes, total_contas_fixas_mes, saidas_debito_mes))
    with col_f2:
        with st.container(border=True):
            titulo_grafico("Despesas por categoria", "As maiores categorias do mês")
            _fig_desp = fig_despesas_top(despesas_por_categoria(chave_mes_vg))
            if _fig_desp is not None:
                mostrar(_fig_desp)
            else:
                vazio("Nenhuma despesa registrada neste mês.")

    # ---------------- Evolução ----------------
    secao("Evolução dos últimos 6 meses", "Entradas, despesas e o saldo de cada mês.")
    _meses_hist = meses_ate(ano_vg, mes_vg_idx, 6)
    _hist = [resumo_mes(f"{a:04d}-{m:02d}") for a, m in _meses_hist]
    with st.container(border=True):
        titulo_grafico("Entradas x despesas", "A linha mostra se sobrou ou faltou dinheiro em cada mês")
        mostrar(fig_evolucao(_meses_hist))
        if any(h["entradas"] > 0 or h["despesas"] > 0 for h in _hist):
            _me = sum(h["entradas"] for h in _hist) / len(_hist)
            _md = sum(h["despesas"] for h in _hist) / len(_hist)
            _tom = "sobrando" if _me >= _md else "faltando"
            md(f"<div class='insight' style='margin:.2rem 0 0'><div>Média dos últimos 6 meses: <b>{fmt_moeda(_me)}</b> de entradas e <b>{fmt_moeda(_md)}</b> de despesas. Em média está {_tom} <b>{fmt_moeda(abs(_me - _md))}</b> por mês.</div></div>")

    # ---------------- Patrimônio ----------------
    secao("Meu patrimônio", "Tudo o que você tem hoje: investimentos, moedas e caixinhas.")

    def _pat(cl):
        return float(df_ativos[df_ativos["classe"] == cl]["valor_atual"].sum()) if not df_ativos.empty else 0.0

    df_dolar = df_ativos[df_ativos["classe"] == "Dólar"]
    qtd_total_dolar = float(df_dolar["qtd"].sum()) if not df_dolar.empty else 0.0
    total_investido_ativos = float(df_ativos["valor_investido"].sum()) if not df_ativos.empty else 0.0
    resultado_ativos = patrimonio_investido_bolsa - total_investido_ativos
    cor_res = "#15803D" if resultado_ativos >= 0 else "#B91C1C"
    pct_geral_invest = (resultado_ativos / total_investido_ativos * 100) if total_investido_ativos > 0 else 0.0

    md(f"""
    <div class="stats">
      <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(patrimonio_total)}</div><div class="stat-l">Patrimônio total</div></div>
      <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(total_investido_ativos)}</div><div class="stat-l">Total investido em ativos</div></div>
      <div class="stat"><div class="stat-n" style="color:{cor_res}">{fmt_moeda(resultado_ativos)}</div><div class="stat-l">Lucro / prejuízo ({fmt_pct(pct_geral_invest)})</div></div>
      <div class="stat"><div class="stat-n" style="color:#DB2777">{fmt_moeda(total_em_caixinhas)}</div><div class="stat-l">Total nas caixinhas</div></div>
    </div>
    """)

    if not df_ativos.empty:
        col_a, col_b = st.columns(2, gap="large")
        with col_a:
            with st.container(border=True):
                titulo_grafico("Composição do patrimônio", "Distribuição por classe de ativo")
                _itens = []
                if total_em_caixinhas > 0:
                    _itens.append(("Caixinhas", total_em_caixinhas))
                for cl in CLASSES_INVEST:
                    v_cl = _pat(cl)
                    if v_cl > 0:
                        _itens.append((cl, v_cl))
                if _itens:
                    _rot = [i[0] for i in _itens]
                    _val = [i[1] for i in _itens]
                    _cor = [CORES_CLASSE.get(r, "#64748B") for r in _rot]
                    mostrar(fig_donut(_rot, _val, _cor, f"<b>{fmt_moeda(patrimonio_total, 0)}</b><br><span style='font-size:11px;color:#64748B'>patrimônio</span>", ALTURA_CARD, legenda=True))
                else:
                    vazio("Sem valores para exibir.")
        with col_b:
            with st.container(border=True):
                titulo_grafico("Resultado por ativo", "Lucro ou prejuízo e rentabilidade")
                mostrar(fig_resultado_ativos(df_ativos))

        _cls = "" if resultado_ativos >= 0 else "style='background:#FEF2F2;border-color:#FECACA;color:#991B1B'"
        _usd = f" Você também tem <b>{fmt_dolar(qtd_total_dolar)}</b> em dólar." if qtd_total_dolar > 0 else ""
        _txt = (f"Você investiu <b>{fmt_moeda(total_investido_ativos)}</b> e hoje a carteira vale <b>{fmt_moeda(patrimonio_investido_bolsa)}</b>. "
                f"Resultado consolidado: <b>{'+' if resultado_ativos >= 0 else ''}{fmt_moeda(resultado_ativos)} ({fmt_pct(pct_geral_invest)})</b>.{_usd}")
        md(f"<div class='insight' {_cls}><div>{_txt}</div></div>")
    else:
        vazio("Cadastre ativos em “Minha Carteira” para ver o desempenho dos seus investimentos.")

    secao("Devedores", "Informativo: os recebimentos de devedores não entram na soma do mês, pois já são lançados como entrada (PIX).")
    devedores = db.get("devedores", [])
    _infos_dev = [calcular_atraso_real_divida(d) for d in devedores]
    total_geral_receber = sum(i["falta_total"] for i in _infos_dev)
    total_atraso_devedores = sum(i["valor_atraso"] for i in _infos_dev)
    previsto_dev_mes = previsto_devedores_no_mes(chave_mes_vg)

    md(f"""
    <div class="stats">
      <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(total_geral_receber)}</div><div class="stat-l">Total a receber ({len(set(d['nome'].strip().title() for d in devedores))} pessoa(s))</div></div>
      <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(previsto_dev_mes)}</div><div class="stat-l">Parcelas que vencem em {nome_mes_vg}</div></div>
      <div class="stat"><div class="stat-n" style="color:#B91C1C">{fmt_moeda(total_atraso_devedores)}</div><div class="stat-l">Em atraso</div></div>
    </div>
    """)

# ==============================================================================
# TELA: RESUMO & DIAGNÓSTICO
# ==============================================================================
def pagina_resumo_diagnostico() -> None:
    """Tela: Resumo."""
    hero("Resumo", "Veja quanto você tem, o que não deve gastar no mês e quanto pode gastar com segurança.")

    hoje = hoje_br()
    c1, c2 = st.columns([2.5, 1])
    m_diag = c1.selectbox("Mês do Diagnóstico", range(1, 13), index=hoje.month - 1, format_func=lambda x: MESES_PT[x-1], key="diag_mes")
    a_diag = c2.selectbox("Ano", [hoje.year - 1, hoje.year, hoje.year + 1], index=1, key="diag_ano")
    ch_diag = f"{a_diag:04d}-{m_diag:02d}"

    trans = db.get("transacoes_debito", [])
    ent_m = sum(float(t["valor"]) for t in trans if t["tipo"] == "Entrada (+)" and t["data"].startswith(ch_diag))
    sai_deb = sum(float(t["valor"]) for t in trans if t["tipo"] == "Saída (-)" and t["data"].startswith(ch_diag))
    fat_card = calcular_fatura_cartao_mes(ch_diag)
    contas_m = [c for c in db.get("contas_fixas", []) if c["mes_ano"] == ch_diag]
    tot_cfix = sum(float(c["valor"]) for c in contas_m)

    cx_flx = obter_caixinha_fluxo()
    sal_flx = float(cx_flx.get("saldo", 0.0)) if cx_flx else 0.0
    tot_caixas = sum(float(c.get("saldo", 0.0)) for c in db.get("caixinhas", []))
    tot_invest = float(df_ativos["valor_atual"].sum()) if not df_ativos.empty else 0.0
    patrimonio_geral = tot_caixas + tot_invest

    nao_deve_gastar = fat_card + tot_cfix
    recursos_totais = ent_m + sal_flx
    pode_gastar_seguro = max(0.0, recursos_totais - (nao_deve_gastar + sai_deb))

    dicas = []
    if ent_m > 0 and (fat_card / ent_m) > 0.40:
        dicas.append(f"💳 <b>Atenção ao Cartão de Crédito:</b> Sua fatura consome {fat_card / ent_m * 100:.1f}% da sua renda mensal. O ideal é manter abaixo de 35% para não comprometer os próximos meses.")
    if pode_gastar_seguro > 300:
        dicas.append(f"💰 <b>Oportunidade de Investir:</b> Você tem {fmt_moeda(pode_gastar_seguro)} livres e seguros este mês. Considere colocar metade em Caixinha de Emergência e outra metade em FIIs de dividendos.")
    if tot_cfix > 0 and (tot_cfix / (ent_m if ent_m > 0 else 1)) > 0.50:
        dicas.append("🏠 <b>Contas Fixas Altas:</b> Suas despesas fixas pesam mais de 50% das suas entradas. Tente renegociar assinaturas, pacotes de internet e consumo.")
    if not dicas:
        dicas.append("🎉 <b>Parabéns!</b> Seu fluxo financeiro deste mês está equilibrado, seguro e pronto para continuar crescendo.")

    md(f"""
    <div class="stats">
      <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(patrimonio_geral)}</div><div class="stat-l">1. Quanto dinheiro tenho no total</div></div>
      <div class="stat"><div class="stat-n" style="color:#B91C1C">{fmt_moeda(nao_deve_gastar)}</div><div class="stat-l">2. O que NÃO devo gastar (cartão + contas)</div></div>
      <div class="stat"><div class="stat-n" style="color:#15803D">{fmt_moeda(pode_gastar_seguro)}</div><div class="stat-l">3. O que POSSO gastar com segurança</div></div>
    </div>
    """)

    secao("Como o dinheiro do mês está distribuído", "Quanto da sua renda já está comprometido e quanto ainda está livre.")
    _comprometido = fat_card + tot_cfix + sai_deb
    _pct_comp = (_comprometido / ent_m * 100) if ent_m > 0 else (100.0 if _comprometido > 0 else 0.0)
    _cor_m = "linear-gradient(90deg,#34D399,#059669)" if _pct_comp < 60 else ("linear-gradient(90deg,#FBBF24,#D97706)" if _pct_comp < 85 else "linear-gradient(90deg,#F87171,#DC2626)")
    _txt_m = "Saudável" if _pct_comp < 60 else ("Atenção" if _pct_comp < 85 else "Crítico")
    col_r1, col_r2 = st.columns([1, 1], gap="large")
    with col_r1:
        titulo_grafico("Distribuição da renda do mês", "Cartão, contas fixas, débito/PIX e o que sobra")
        if ent_m > 0 or _comprometido > 0:
            _rot = ["Fatura do cartão", "Contas fixas", "Débito / PIX", "Livre"]
            _val = [fat_card, tot_cfix, sai_deb, max(0.0, ent_m - _comprometido)]
            _cor = ["#2563EB", "#E11D48", "#F59E0B", "#059669"]
            mostrar(fig_donut(_rot, _val, _cor, f"<b>{fmt_moeda(ent_m, 0)}</b><br><span style='font-size:11px;color:#64748B'>entradas</span>", 260))
            md(legenda_html(_rot, _val, _cor))
        else:
            vazio("Sem entradas nem despesas neste mês.")
    with col_r2:
        titulo_grafico("Comprometimento da renda", "Quanto das entradas já está destinado a despesas")
        md(f"""
        <div class="meter-box">
          <div class="meter-top">
            <div><div class="meter-l">Comprometido</div><div class="meter-v">{_pct_comp:.1f}%</div></div>
            <div style="text-align:right"><div class="meter-l">Situação</div><div class="meter-v" style="font-size:1.1rem">{_txt_m}</div></div>
          </div>
          {barra_progresso(_pct_comp, _cor_m, 12)}
          <div class="meter-f"><span>Despesas: <b>{fmt_moeda(_comprometido)}</b></span><span>Entradas: <b>{fmt_moeda(ent_m)}</b></span></div>
        </div>
        """)
        titulo_grafico("Despesas por categoria")
        _fc = fig_categorias(despesas_por_categoria(ch_diag))
        if _fc is not None:
            mostrar(_fc)

    secao("Onde posso melhorar financeiramente?")
    for d in dicas:
        md(f"<div class='tip'>{d}</div>")

# ==============================================================================
# TELA: CONTAS FIXAS
# ==============================================================================
def pagina_contas_fixas() -> None:
    """Tela: Contas Fixas."""
    hero("Contas Fixas", f"Cadastre, edite e acompanhe os vencimentos do mês. A fatura do cartão entra automaticamente no dia {DIA_VENCIMENTO_CARTAO}.")

    hoje = hoje_br()

    c_m1, c_m2 = st.columns([2.5, 1])
    with c_m1:
        mes_contas_idx = st.selectbox("Mês de Vencimento", range(1, 13), index=hoje.month - 1, format_func=lambda x: MESES_PT[x-1], key="sel_m_contas")
    with c_m2:
        ano_contas = st.selectbox("Ano", [hoje.year - 1, hoje.year, hoje.year + 1], index=1, key="sel_a_contas")

    chave_mes_contas = f"{ano_contas:04d}-{mes_contas_idx:02d}"
    nome_mes_contas = MESES_PT[mes_contas_idx - 1]

    with st.expander("Cadastrar nova conta fixa", expanded=False):
        with st.form("form_nova_conta_fixa", clear_on_submit=True):
            f_col1, f_col2, f_col3 = st.columns(3)
            nome_cf = f_col1.text_input("Nome da Conta", placeholder="Ex: Aluguel, Luz, Internet, Netflix, Academia").strip()
            cat_cf = f_col2.selectbox("Categoria", LISTA_CATEGORIAS_CONTAS)
            valor_cf = f_col3.number_input("Valor da Conta (R$)", min_value=0.01, value=150.00, step=10.00)

            f_col4, f_col5 = st.columns(2)
            dia_venc_cf = f_col4.number_input("Dia do Vencimento", min_value=1, max_value=31, value=10, step=1)
            repetir_meses = f_col5.slider("Repetir para os próximos meses?", min_value=1, max_value=12, value=12,
                                          help="Gera automaticamente essa conta para os próximos meses para você não precisar digitar todo mês!")

            if st.form_submit_button("Salvar conta fixa", use_container_width=True, type="primary"):
                if nome_cf:
                    for i in range(repetir_meses):
                        m_calc = mes_contas_idx + i
                        a_calc = ano_contas + (m_calc - 1) // 12
                        m_real = ((m_calc - 1) % 12) + 1
                        _, max_dia_m = calendar.monthrange(a_calc, m_real)
                        dia_real = min(int(dia_venc_cf), max_dia_m)

                        db.setdefault("contas_fixas", []).append({
                            "id": novo_id() + i, "nome": nome_cf.title(), "categoria": cat_cf,
                            "valor": float(valor_cf), "dia_vencimento": dia_real,
                            "mes_ano": f"{a_calc:04d}-{m_real:02d}", "status": "pendente", "data_pagamento": None
                        })
                    salvar_dados(db)
                    st.toast(f"Conta '{nome_cf.title()}' cadastrada!", icon="📑")
                    st.rerun()

    contas_todas = db.get("contas_fixas", [])
    contas_do_mes = [c for c in contas_todas if c["mes_ano"] == chave_mes_contas]

    fatura_cartao_dinamica = calcular_fatura_cartao_mes(chave_mes_contas)
    faturas_pagas_lista = db.get("faturas_pagas", [])
    cartao_pago_neste_mes = chave_mes_contas in faturas_pagas_lista

    total_mes_contas = sum(float(c["valor"]) for c in contas_do_mes) + fatura_cartao_dinamica
    pago_contas = sum(float(c["valor"]) for c in contas_do_mes if c.get("status") == "pago") + (fatura_cartao_dinamica if cartao_pago_neste_mes else 0.0)
    pendente_contas = total_mes_contas - pago_contas

    contas_atrasadas = [c for c in contas_do_mes if c.get("status") != "pago" and date(ano_contas, mes_contas_idx, int(c["dia_vencimento"])) < hoje]
    if (not cartao_pago_neste_mes) and date(ano_contas, mes_contas_idx, DIA_VENCIMENTO_CARTAO) < hoje and fatura_cartao_dinamica > 0:
        qtd_atrasadas = len(contas_atrasadas) + 1
        tot_atrasado = sum(float(c["valor"]) for c in contas_atrasadas) + fatura_cartao_dinamica
    else:
        qtd_atrasadas = len(contas_atrasadas)
        tot_atrasado = sum(float(c["valor"]) for c in contas_atrasadas)

    md(f"""
    <div class="stats">
      <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(total_mes_contas)}</div><div class="stat-l">Total de obrigações em {nome_mes_contas}</div></div>
      <div class="stat"><div class="stat-n" style="color:#15803D">{fmt_moeda(pago_contas)}</div><div class="stat-l">Já pago no mês</div></div>
      <div class="stat"><div class="stat-n" style="color:#3B82F6">{fmt_moeda(pendente_contas)}</div><div class="stat-l">Pendente a pagar</div></div>
      <div class="stat"><div class="stat-n" style="color:#B91C1C">{fmt_moeda(tot_atrasado)}</div><div class="stat-l">Em atraso ({qtd_atrasadas})</div></div>
    </div>
    """)

    _pct_pago = (pago_contas / total_mes_contas * 100) if total_mes_contas > 0 else 0.0
    md(f"""
    <div class="meter-box">
      <div class="meter-top">
        <div><div class="meter-l">Contas pagas em {nome_mes_contas}</div><div class="meter-v">{_pct_pago:.0f}%</div></div>
        <div style="text-align:right"><div class="meter-l">Falta pagar</div><div class="meter-v" style="color:#B91C1C;font-size:1.2rem">{fmt_moeda(pendente_contas)}</div></div>
      </div>
      {barra_progresso(_pct_pago, None, 10)}
    </div>
    """)

    # CALENDÁRIO VISUAL
    secao(f"Vencimentos de {nome_mes_contas}/{ano_contas}")
    md("<div class='legend-cal'><span style='--c:#16A34A'>Pago</span><span style='--c:#DC2626'>Em atraso</span><span style='--c:#F59E0B'>Vence hoje</span><span style='--c:#0284C7'>A vencer</span></div>")

    cal_obj = calendar.Calendar(firstweekday=0)
    semanas = cal_obj.monthdayscalendar(ano_contas, mes_contas_idx)

    mapa_dias = {}
    for c in contas_do_mes:
        d = int(c["dia_vencimento"])
        mapa_dias.setdefault(d, []).append(c)

    if fatura_cartao_dinamica > 0:
        mapa_dias.setdefault(DIA_VENCIMENTO_CARTAO, []).append({
            "id": "fatura_cartao_auto", "nome": "💳 Fatura Cartão", "categoria": "Cartão de Crédito",
            "valor": fatura_cartao_dinamica, "status": "pago" if cartao_pago_neste_mes else "pendente", "dia_vencimento": DIA_VENCIMENTO_CARTAO
        })

    dias_semana_lbl = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    grid_html = "<div class='cal-grid'>"
    for d_lbl in dias_semana_lbl:
        grid_html += f"<div class='cal-head'>{d_lbl}</div>"

    for semana in semanas:
        for dia in semana:
            if dia == 0:
                grid_html += "<div class='cal-cell-empty'></div>"
            else:
                dt_atual = date(ano_contas, mes_contas_idx, dia)
                eh_hoje = dt_atual == hoje
                cls_hoje = " cal-day-hoje" if eh_hoje else ""
                grid_html += f"<div class='cal-cell{cls_hoje}'>"
                grid_html += f"<div class='cal-day-num'>{dia}</div>"

                contas_dia = mapa_dias.get(dia, [])
                for ct in contas_dia:
                    st_pago = ct.get("status") == "pago"
                    if st_pago:
                        cls_tag = "tag-pago"
                        icone_st = "✓"
                    elif dt_atual < hoje:
                        cls_tag = "tag-atraso"
                        icone_st = "!"
                    elif dt_atual == hoje:
                        cls_tag = "tag-hoje"
                        icone_st = "●"
                    else:
                        cls_tag = "tag-avencer"
                        icone_st = "○"

                    nome_cut = html.escape(ct["nome"][:12])
                    grid_html += f"<span class='cal-tag {cls_tag}' title='{html.escape(ct['nome'])}: {fmt_moeda(ct['valor'])}'>{icone_st} {nome_cut} ({fmt_moeda(ct['valor'], 0)})</span>"

                grid_html += "</div>"

    grid_html += "</div>"
    md(grid_html)

    # LISTAGEM
    secao(f"Contas de {nome_mes_contas}/{ano_contas}")

    if fatura_cartao_dinamica > 0:
        dt_venc_c = date(ano_contas, mes_contas_idx, DIA_VENCIMENTO_CARTAO)
        atrasada_c = (not cartao_pago_neste_mes) and (dt_venc_c < hoje)
        with st.container(border=True):
            c_d, c_i, c_v, c_ac, _ = st.columns([1.1, 2.3, 1.3, 1.4, 0.4], vertical_alignment="center")
            c_d.markdown(f"<div class='cell-big'>Dia {DIA_VENCIMENTO_CARTAO}</div><div class='cell-l'>{dt_venc_c.strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
            c_i.markdown(f"<div class='asset-tk'>💳 Fatura do cartão de crédito <span class='chip chip-cartao'>Automático</span></div><div class='asset-sub'>Valor calculado a partir das compras de {nome_mes_contas}</div>", unsafe_allow_html=True)
            cor_v_c = "#15803D" if cartao_pago_neste_mes else ("#B91C1C" if atrasada_c else "#0F766E")
            st_badge = "<span class='badge-status status-alta'>Fatura paga</span>" if cartao_pago_neste_mes else ("<span class='badge-status status-atraso'>Fatura atrasada</span>" if atrasada_c else "<span class='badge-status status-neutro'>A vencer</span>")
            c_v.markdown(f"<span style='font-size:1.15rem;font-weight:900;color:{cor_v_c}'>{fmt_moeda(fatura_cartao_dinamica)}</span><br>{st_badge}", unsafe_allow_html=True)

            with c_ac:
                if cartao_pago_neste_mes:
                    if st.button("Reabrir fatura", key="reab_fat_card"):
                        db["faturas_pagas"] = [x for x in db["faturas_pagas"] if x != chave_mes_contas]
                        salvar_dados(db)
                        st.toast("Fatura reaberta!")
                        st.rerun()
                else:
                    if st.button("Marcar fatura como paga", key="pag_fat_card", type="primary"):
                        db.setdefault("faturas_pagas", []).append(chave_mes_contas)
                        salvar_dados(db)
                        st.toast("Fatura marcada como Paga!", icon="✅")
                        st.rerun()

    for c in contas_do_mes:
        pago = c.get("status") == "pago"
        dt_venc = date(ano_contas, mes_contas_idx, int(c["dia_vencimento"]))
        atrasada = (not pago) and (dt_venc < hoje)
        vence_hoje = (not pago) and (dt_venc == hoje)

        if pago:
            badge_st = "<span class='badge-status status-alta'>Pago</span>"
        elif atrasada:
            badge_st = "<span class='badge-status status-atraso'>Atrasada</span>"
        elif vence_hoje:
            badge_st = "<span class='badge-status status-alerta'>Vence hoje</span>"
        else:
            badge_st = "<span class='badge-status status-neutro'>A vencer</span>"

        with st.container(border=True):
            col_dia, col_info, col_val, col_acao, col_edit, col_del = st.columns([1.0, 2.2, 1.3, 1.4, 0.45, 0.45], vertical_alignment="center")
            with col_dia:
                md(f"""<div><div class='cell-big'>Dia {c['dia_vencimento']}</div>
                <div class='cell-l'>{dt_venc.strftime('%d/%m/%Y')}</div></div>""")

            with col_info:
                md(f"""<div><div class='asset-tk'>{html.escape(c['nome'])}</div>
                <div class='asset-sub'>{html.escape(c['categoria'])}</div></div>""")

            with col_val:
                cor_v = "#15803D" if pago else ("#B91C1C" if atrasada else "#0B1220")
                md(f"""<div><div style='font-size:1.1rem;font-weight:800;color:{cor_v};font-variant-numeric:tabular-nums'>{fmt_moeda(c['valor'])}</div>
                <div>{badge_st}</div></div>""")

            with col_acao:
                if pago:
                    if st.button("Reabrir", key=f"reab_{c['id']}", use_container_width=True):
                        c["status"] = "pendente"
                        c["data_pagamento"] = None
                        salvar_dados(db)
                        st.toast(f"{c['nome']} reaberta.")
                        st.rerun()
                else:
                    if st.button("Marcar como paga", key=f"pag_{c['id']}", type="primary", use_container_width=True):
                        c["status"] = "pago"
                        c["data_pagamento"] = hoje.strftime("%Y-%m-%d")
                        salvar_dados(db)
                        st.toast(f"{c['nome']} marcada como paga.", icon="✅")
                        st.rerun()

            with col_edit:
                with st.popover(":material/edit:", use_container_width=True, help="Editar conta"):
                    st.markdown("**Editar conta fixa**")
                    e_nome = st.text_input("Nome da conta", value=c["nome"], key=f"cf_n_{c['id']}")
                    _idx_cat_cf = LISTA_CATEGORIAS_CONTAS.index(c["categoria"]) if c.get("categoria") in LISTA_CATEGORIAS_CONTAS else 0
                    e_cat = st.selectbox("Categoria", LISTA_CATEGORIAS_CONTAS, index=_idx_cat_cf, key=f"cf_c_{c['id']}")
                    e_val = st.number_input("Valor (R$)", min_value=0.01, value=float(c["valor"]), step=10.0, key=f"cf_v_{c['id']}")
                    e_dia = st.number_input("Dia do vencimento", min_value=1, max_value=31, value=int(c["dia_vencimento"]), step=1, key=f"cf_d_{c['id']}")
                    e_prox = st.checkbox("Aplicar também aos meses seguintes", value=True, key=f"cf_p_{c['id']}",
                                         help="Atualiza as contas com o mesmo nome dos próximos meses.")
                    if st.button("Salvar alterações", key=f"cf_s_{c['id']}", type="primary", use_container_width=True):
                        nome_antigo, mes_ref = c["nome"], c["mes_ano"]
                        novo_nome = e_nome.strip().title() or nome_antigo
                        for x in db["contas_fixas"]:
                            alvo = x["id"] == c["id"] or (e_prox and x["nome"] == nome_antigo and x["mes_ano"] > mes_ref)
                            if alvo:
                                a_x, m_x = int(x["mes_ano"][:4]), int(x["mes_ano"][5:7])
                                x["nome"] = novo_nome
                                x["categoria"] = e_cat
                                x["valor"] = float(e_val)
                                x["dia_vencimento"] = min(int(e_dia), calendar.monthrange(a_x, m_x)[1])
                        salvar_dados(db)
                        st.toast("Conta atualizada.", icon="✅")
                        st.rerun()

            with col_del:
                with st.popover(":material/delete:", use_container_width=True, help="Excluir conta"):
                    st.markdown("**Excluir esta conta?**")
                    ex_prox = st.checkbox("Excluir também dos meses seguintes", value=False, key=f"cf_xp_{c['id']}")
                    if st.button("Sim, excluir", key=f"del_cfix_{c['id']}", type="primary", use_container_width=True):
                        nome_x, mes_x = c["nome"], c["mes_ano"]
                        db["contas_fixas"] = [x for x in db["contas_fixas"]
                                              if not (x["id"] == c["id"] or (ex_prox and x["nome"] == nome_x and x["mes_ano"] > mes_x))]
                        salvar_dados(db)
                        st.rerun()

# ==============================================================================
# TELA: MINHA CARTEIRA
# ==============================================================================
def pagina_carteira() -> None:
    """Tela: Minha Carteira."""
    hero("Minha Carteira", "Ações, FIIs, Cripto, Dólar e Caixinhas — com cotações em tempo real e Radar de Aportes da Bolsa.")

    aba_invest, aba_radar, aba_alt, aba_caixinhas, aba_vendas = st.tabs([
        "Ações, FIIs e Renda Fixa",
        "Radar da Bolsa",
        "Cripto & Dólar",
        "Caixinhas",
        "Histórico de Vendas"
    ])

    with aba_invest:
        df_t1 = df_ativos[~df_ativos["classe"].isin(CLASSES_ALT)]

        with st.expander("Adicionar ação, FII ou renda fixa", expanded=df_t1.empty):
            with st.form("form_novo_ativo", clear_on_submit=True):
                f1, f2, f3 = st.columns(3)
                ticker_in = f1.text_input("Código do Ativo (Ticker)", placeholder="Ex: PETR4, MXRF11, HGLG11").strip().upper()
                nome_in = f2.text_input("Nome da Empresa ou Fundo", placeholder="Ex: Petrobras, Maxi Renda").strip()
                classe_in = f3.selectbox("Classe do Investimento", CLASSES_BOLSA_FORM)

                f4, f5, f6 = st.columns(3)
                qtd_in = f4.number_input("Quantidade de Cotas que comprei", min_value=1, value=10, step=1)
                pm_in = f5.number_input("Preço que paguei por cota (R$)", min_value=0.01, value=10.00, step=0.50)
                atual_in = f6.number_input("Cotação Atual de Mercado (R$)", min_value=0.01, value=10.50, step=0.50)

                if st.form_submit_button("Salvar investimento", use_container_width=True, type="primary"):
                    if ticker_in:
                        preco_final = float(atual_in)
                        live = preco_por_chave(classe_in, ticker_in)
                        if live:
                            preco_final = live
                        somar_ou_adicionar_ativo({
                            "id": novo_id(), "ticker": ticker_in.upper(), "nome": nome_in if nome_in else ticker_in.upper(),
                            "classe": classe_in, "qtd": int(qtd_in), "pm": float(pm_in), "preco_atual": preco_final
                        })
                        salvar_dados(db)
                        st.toast(f"{ticker_in.upper()} salvo com sucesso!", icon="✅")
                        st.rerun()

        if df_t1.empty:
            vazio("Nenhum ativo cadastrado nesta classe. Use o botão acima para cadastrar.", "📈")
        else:
            _inv1 = float(df_t1["valor_investido"].sum())
            _atu1 = float(df_t1["valor_atual"].sum())
            _res1 = _atu1 - _inv1
            _pct1 = (_res1 / _inv1 * 100) if _inv1 > 0 else 0.0
            _cor1 = "#15803D" if _res1 >= 0 else "#B91C1C"
            col_s1, col_s2 = st.columns([1.1, 1], gap="large")
            with col_s1:
                md(f"""
                <div class="stats" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr)) !important">
                  <div class="stat"><div class="stat-n">{fmt_moeda(_inv1)}</div><div class="stat-l">Total investido</div></div>
                  <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(_atu1)}</div><div class="stat-l">Valor atual</div></div>
                  <div class="stat"><div class="stat-n" style="color:{_cor1}">{fmt_moeda(_res1)}</div><div class="stat-l">Resultado ({fmt_pct(_pct1)})</div></div>
                </div>
                """)
            with col_s2:
                _g = df_t1.groupby("classe")["valor_atual"].sum()
                _g = _g[_g > 0].sort_values(ascending=False)
                _rotg, _valg = list(_g.index), [float(v) for v in _g.values]
                _corg = [CORES_CLASSE.get(r, "#64748B") for r in _rotg]
                mostrar(fig_donut(_rotg, _valg, _corg, f"<b>{fmt_moeda(_atu1, 0)}</b>", 210))
            listar_ativos(df_t1)

    with aba_radar:
        secao("Radar de oportunidades de compra", "Acompanhe o que está barato e valendo a pena comprar hoje, nos ativos que você já possui e nas maiores oportunidades do mercado.")

        df_radar = df_ativos[df_ativos["classe"].isin(["Ações", "FIIs", "Internacional"])].copy()
        if not df_radar.empty:
            md("#### Na sua carteira: onde vale a pena baixar o preço médio?")
            df_radar["diff_pct"] = ((df_radar["preco_atual"] - df_radar["pm"]) / df_radar["pm"]) * 100
            df_radar = df_radar.sort_values(by="diff_pct", ascending=True)

            for _, row in df_radar.iterrows():
                diff = row["diff_pct"]
                pm = row["pm"]
                atual = row["preco_atual"]
                ticker = row["ticker"]
                nome = row["nome"]
                cl = row["classe"]

                if diff < -2.0:
                    badge_radar = f"<span class='badge-status status-alta'>Bom valor para comprar ({fmt_pct(diff)})</span>"
                    msg_radar = f"A cotação está <b>{fmt_pct(abs(diff))} mais barata</b> que o seu Preço Médio. Ótima oportunidade de comprar mais cotas e <b>baixar seu preço médio</b>!"
                    cor_borda = "#86EFAC"
                    bg_card = "#F0FDF4"
                elif -2.0 <= diff <= 3.0:
                    badge_radar = f"<span class='badge-status status-alerta'>Preço em linha ({fmt_pct(diff)})</span>"
                    msg_radar = "A cotação está praticamente idêntica ao que você pagou. Bom para aportes regulares."
                    cor_borda = "#FCD34D"
                    bg_card = "#FFFBEB"
                else:
                    badge_radar = f"<span class='badge-status status-neutro' style='background:#DBEAFE;color:#1E40AF'>Valorizado ({fmt_pct(diff)})</span>"
                    msg_radar = f"O ativo já valorizou <b>{fmt_pct(diff)}</b> em relação ao que você pagou. Se quiser comprar mais, priorize ativos com desconto na carteira."
                    cor_borda = "#93C5FD"
                    bg_card = "#EFF6FF"

                with st.container():
                    md(f"""
                    <div style="background:{bg_card};border:1px solid {cor_borda};border-radius:16px;padding:16px 20px;margin-bottom:12px;box-shadow:0 1px 3px rgba(11,18,32,.05)">
                      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
                        <div>
                          <span style="font-size:1.15rem;font-weight:800;color:#0B1220">{ticker}</span>
                          <span style="font-size:.85rem;color:#475569;margin-left:6px">· {nome}</span>
                          {chip_classe(cl)}
                        </div>
                        <div>{badge_radar}</div>
                      </div>
                      <div style="display:flex;gap:34px;margin-top:12px;flex-wrap:wrap">
                        <div><span class="cell-l">SEU PREÇO MÉDIO</span><br><b style="font-size:1.05rem;color:#0B1220">{fmt_moeda(pm)}</b></div>
                        <div><span class="cell-l">COTAÇÃO AGORA (BOLSA)</span><br><b style="font-size:1.05rem;color:#2563EB">{fmt_moeda(atual)}</b></div>
                        <div><span class="cell-l">VOCÊ TEM</span><br><b style="font-size:1.05rem;color:#0B1220">{int(row['qtd'])} cotas</b></div>
                      </div>
                      <div style="font-size:.86rem;color:#334155;margin-top:12px;padding-top:10px;border-top:1px dashed #CBD5E1;line-height:1.5">
                        💡 {msg_radar}
                      </div>
                    </div>
                    """)

        st.divider()
        secao("Oportunidades do mercado aberto", "Ativos monitorados pelo mercado com preços atraentes ou altos pagamentos de dividendos.")

        aba_m1, aba_m2, aba_m3, aba_m4 = st.tabs(["Fundos Imobiliários", "Ações da B3", "Dólar & Exterior", "Criptoativos"])

        fii_mercado = [
            {"ticker": "MXRF11", "nome": "Maxi Renda FII", "classe": "FIIs", "preco_ref": 10.15, "motivo": "Maior número de cotistas da B3. Dividendos mensais consistentes (Yield ~11.5% a.a.).", "destaque": "💎 Queridinho dos Dividendos"},
            {"ticker": "HGLG11", "nome": "CSHG Logística", "classe": "FIIs", "preco_ref": 160.50, "motivo": "Líder em galpões logísticos de alto padrão (AAA). Inquilinos de grande porte e vacância muito baixa.", "destaque": "🏢 Tijolo / Logística Premium"},
            {"ticker": "XPML11", "nome": "XP Malls FII", "classe": "FIIs", "preco_ref": 112.00, "motivo": "Portfólio com os melhores shoppings do Brasil (Catarina Fashion, Cidade Jardim, etc.). Alta resiliência.", "destaque": "🛍️ Shoppings Consolidados"},
            {"ticker": "BTLG11", "nome": "BTG Pactual Logística", "classe": "FIIs", "preco_ref": 100.80, "motivo": "Excelente gestão ativa e galpões próximos dos maiores centros de consumo de SP.", "destaque": "📦 Galpões Estratégicos"},
            {"ticker": "KNCR11", "nome": "Kinea Rendimentos", "classe": "FIIs", "preco_ref": 103.50, "motivo": "Fundo de papel indexado 100% ao CDI. Protege seu capital e paga dividendos altos quando os juros estão altos.", "destaque": "🛡️ Proteção Indexada ao CDI"}
        ]

        acoes_mercado = [
            {"ticker": "BBAS3", "nome": "Banco do Brasil", "classe": "Ações", "preco_ref": 27.50, "motivo": "Bancão muito lucrativo negociando com múltiplos baixos (P/L e P/VP com desconto histórico). Dividendos elevados.", "destaque": "💰 Bancão Barato / Dividendos"},
            {"ticker": "PETR4", "nome": "Petrobras PN", "classe": "Ações", "preco_ref": 36.80, "motivo": "Geração de caixa massiva no pré-sal e distribuição frequente de dividendos expressivos.", "destaque": "⛽ Dividendos Massivos"},
            {"ticker": "VALE3", "nome": "Vale", "classe": "Ações", "preco_ref": 62.00, "motivo": "Líder global em minério de ferro. Negociando em patamares atrativos de entrada com receita forte em dólar.", "destaque": "⛏️ Exportadora Global"},
            {"ticker": "ITUB4", "nome": "Itaú Unibanco", "classe": "Ações", "preco_ref": 34.00, "motivo": "Maior banco privado da América Latina. Crescimento contínuo de lucro e rentabilidade (ROE) impecável.", "destaque": "🏛️ Máxima Solidez e Lucro"},
            {"ticker": "TAEE11", "nome": "Taesa Transmissão", "classe": "Ações", "preco_ref": 35.50, "motivo": "Receita previsível corrigida por inflação (IPCA/IGP-M). Modelo de negócios seguro para quem busca renda passiva.", "destaque": "⚡ Energia Perene / Renda Passiva"}
        ]

        moedas_mercado = [
            {"ticker": "USD", "nome": "Dólar Comercial", "classe": "Dólar", "preco_ref": 5.45, "motivo": "Moeda de reserva mundial. Comprar dólar fracionado para conta Nomad protege seu patrimônio contra a desvalorização do Real.", "destaque": "💵 Proteção Cambial Nomad"},
            {"ticker": "IVVB11", "nome": "iShares S&P 500", "classe": "Internacional", "preco_ref": 320.00, "motivo": "ETF negociado na B3 que investe nas 500 maiores empresas dos Estados Unidos (Apple, Microsoft, Google, etc.).", "destaque": "🌐 Top 500 Empresas dos EUA"}
        ]

        criptos_mercado = [
            {"ticker": "BTC", "nome": "Bitcoin", "classe": "Cripto", "preco_ref": 380000.0, "motivo": "Ativo mais escasso do mundo com limite de 21 milhões de moedas. Excelente para aportes mensais de longo prazo.", "destaque": "₿ Reserva de Valor Digital"},
            {"ticker": "SOL", "nome": "Solana", "classe": "Cripto", "preco_ref": 950.0, "motivo": "Blockchain ultrarrápida com crescimento exponencial em finanças descentralizadas e aplicações.", "destaque": "⚡ Alta Velocidade e Adoção"},
            {"ticker": "ETH", "nome": "Ethereum", "classe": "Cripto", "preco_ref": 15000.0, "motivo": "A maior plataforma de contratos inteligentes e tokenização do mercado cripto.", "destaque": "🌐 Líder em Contratos Inteligentes"}
        ]

        def _render_lista_radar(itens):
            for op in itens:
                live_p = preco_por_chave(op["classe"], op["ticker"])
                preco_exibir = live_p if live_p else op["preco_ref"]
                casas_p = 4 if op["classe"] == "Dólar" else 2
                cor_op = CORES_CLASSE.get(op["classe"], "#2563EB")

                with st.container(border=True):
                    c_r1, c_r2, c_r3 = st.columns([2.5, 1.2, 1], vertical_alignment="center")
                    with c_r1:
                        md(f"""<div class="asset" style="align-items:flex-start"><div class="avatar" style="background:{cor_op}1A;color:{cor_op}">{op['ticker'][:3]}</div>
                        <div><div class="asset-tk">{op['ticker']} <span style='font-size:.85rem;color:#475569;font-weight:500'>· {op['nome']}</span> <span class='badge-status status-alta'>{op['destaque']}</span></div>
                        <div style='font-size:.83rem;color:#475569;margin-top:4px;line-height:1.5'>{op['motivo']}</div></div></div>""")

                    with c_r2:
                        md(f"<div><span class='cell-l'>COTAÇÃO ESTIMADA</span><br><b style='font-size:1.15rem;color:#2563EB;font-variant-numeric:tabular-nums'>{fmt_moeda(preco_exibir, casas_p)}</b></div>")

                    with c_r3:
                        with st.popover("Adicionar", use_container_width=True):
                            st.markdown(f"**Registrar {op['ticker']}**")
                            q_add = st.number_input("Quantidade comprada", min_value=0.0001, value=10.0 if op["classe"] in ("Ações", "FIIs") else 1.0, key=f"q_rd_{op['ticker']}")
                            p_add = st.number_input("Preço pago (R$)", min_value=0.01, value=float(preco_exibir), key=f"p_rd_{op['ticker']}")
                            if st.button("Confirmar Compra", key=f"btn_rd_{op['ticker']}", type="primary", use_container_width=True):
                                somar_ou_adicionar_ativo({
                                    "id": novo_id(), "ticker": op["ticker"], "nome": op["nome"], "classe": op["classe"],
                                    "qtd": float(q_add), "pm": float(p_add), "preco_atual": float(preco_exibir),
                                    "data_compra": hoje_br().strftime("%Y-%m-%d")
                                })
                                salvar_dados(db)
                                st.toast(f"{op['ticker']} adicionado à sua carteira com sucesso!", icon="✅")
                                st.rerun()

        with aba_m1:
            _render_lista_radar(fii_mercado)
        with aba_m2:
            _render_lista_radar(acoes_mercado)
        with aba_m3:
            _render_lista_radar(moedas_mercado)
        with aba_m4:
            _render_lista_radar(criptos_mercado)

    with aba_alt:
        df_alt = df_ativos[df_ativos["classe"].isin(CLASSES_ALT)]

        inv_alt = float(df_alt["valor_investido"].sum()) if not df_alt.empty else 0.0
        atu_alt = float(df_alt["valor_atual"].sum()) if not df_alt.empty else 0.0
        luc_alt = atu_alt - inv_alt
        pct_alt = (luc_alt / inv_alt * 100) if inv_alt > 0 else 0.0
        cor_alt = "#15803D" if luc_alt >= 0 else "#B91C1C"

        md(f"""
        <div class="stats">
          <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(inv_alt)}</div><div class="stat-l">Total que investi (Cripto + Dólar)</div></div>
          <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(atu_alt)}</div><div class="stat-l">Valor hoje (tempo real)</div></div>
          <div class="stat"><div class="stat-n" style="color:{cor_alt}">{fmt_moeda(luc_alt)}</div><div class="stat-l">Lucro / prejuízo</div></div>
          <div class="stat"><div class="stat-n" style="color:{cor_alt}">{fmt_pct(pct_alt)}</div><div class="stat-l">Rentabilidade</div></div>
        </div>
        """)

        df_usd = df_ativos[df_ativos["classe"] == "Dólar"]
        if not df_usd.empty:
            usd_total = float(df_usd["qtd"].sum())
            inv_usd = float(df_usd["valor_investido"].sum())
            cot_media = inv_usd / usd_total if usd_total > 0 else 0.0
            q_usd = cotacao_dolar()
            cot_agora = float(q_usd["preco"]) if q_usd else float(df_usd["preco_atual"].iloc[0])
            res_usd = usd_total * cot_agora - inv_usd
            cor_usd = "#15803D" if res_usd >= 0 else "#B91C1C"
            md(f"""
            <div style="background:linear-gradient(135deg,#ECFEFF,#FFFFFF 70%);border:1px solid #A5F3FC;border-radius:18px;padding:18px 24px;margin-bottom:1.3rem;box-shadow:0 1px 3px rgba(11,18,32,.05)">
              <div style="font-size:.76rem;font-weight:800;color:#0E7490;margin-bottom:12px;letter-spacing:.1em;text-transform:uppercase">💵 Meus dólares (Nomad)</div>
              <div style="display:flex;gap:40px;flex-wrap:wrap">
                <div><div style="font-size:1.45rem;font-weight:800;color:#0B1220;letter-spacing:-.02em">US$ {fmt_num(usd_total)}</div><div class="stat-l">Total em dólar</div></div>
                <div><div style="font-size:1.45rem;font-weight:800;color:#0B1220;letter-spacing:-.02em">{fmt_moeda(cot_media, 4)}</div><div class="stat-l">Cotação média que paguei</div></div>
                <div><div style="font-size:1.45rem;font-weight:800;color:#0891B2;letter-spacing:-.02em"><span class="live-dot"></span>{fmt_moeda(cot_agora, 4)}</div><div class="stat-l">Dólar agora</div></div>
                <div><div style="font-size:1.45rem;font-weight:800;color:{cor_usd};letter-spacing:-.02em">{fmt_moeda(res_usd)}</div><div class="stat-l">Ganho / perda no câmbio</div></div>
              </div>
            </div>
            """)

        with st.expander("Registrar compra de criptomoeda (Bitcoin, Solana...)", expanded=df_alt.empty):
            with st.form("form_nova_cripto", clear_on_submit=True):
                k1, k2, k3 = st.columns(3)
                moeda_sel = k1.selectbox("Criptomoeda", ["BTC", "SOL", "XRP", "LTC", "DOGE", "USDT", "USDC", "ADA", "BNB", "Outra"])
                outra_moeda = k2.text_input("Se escolheu 'Outra', digite o código", placeholder="Ex: AVAX").strip().upper()
                qtd_cripto = k3.number_input("Quantidade comprada", min_value=0.00000001, value=0.00100000, step=0.0001, format="%.8f")

                k4, k5, k6 = st.columns(3)
                total_pago_cripto = k4.number_input("Total pago na compra (R$)", min_value=0.0, value=500.0, step=50.0)
                preco_un_cripto = k5.number_input("OU preço por unidade (R$)", min_value=0.0, value=0.0, step=1000.0)
                data_cripto = k6.date_input("Data da compra", value=hoje_br(), format="DD/MM/YYYY", key="dt_cripto")

                corretora_cripto = st.text_input("Corretora / Exchange", placeholder="Ex: Binance, Mercado Bitcoin, Nomad").strip()

                if st.form_submit_button("Salvar criptomoeda", use_container_width=True, type="primary"):
                    tick_c = outra_moeda if moeda_sel == "Outra" else moeda_sel
                    if not tick_c:
                        st.error("Informe o código da criptomoeda.")
                    else:
                        pm_c = float(preco_un_cripto) if preco_un_cripto > 0 else (float(total_pago_cripto) / float(qtd_cripto) if total_pago_cripto > 0 else 0.0)
                        if pm_c <= 0:
                            st.error("Informe o total pago ou o preço por unidade.")
                        else:
                            live = preco_por_chave("Cripto", tick_c)
                            somar_ou_adicionar_ativo({
                                "id": novo_id(), "ticker": tick_c, "nome": CRIPTO_NOMES.get(tick_c, tick_c),
                                "classe": "Cripto", "qtd": float(qtd_cripto), "pm": float(pm_c),
                                "preco_atual": float(live) if live else float(pm_c),
                                "data_compra": data_cripto.strftime("%Y-%m-%d"),
                                "corretora": corretora_cripto
                            })
                            salvar_dados(db)
                            st.toast(f"{tick_c} registrado!", icon="🪙")
                            st.rerun()

        cot_inicial = cotacao_dolar()
        cot_default = float(cot_inicial["preco"]) if cot_inicial else 5.00
        with st.expander("Registrar compra de dólar (Nomad)", expanded=False):
            with st.form("form_novo_dolar", clear_on_submit=True):
                u1, u2, u3 = st.columns(3)
                usd_comprado = u1.number_input("Quantos dólares comprei (US$)", min_value=0.01, value=100.00, step=10.0)
                cot_compra = u2.number_input("Cotação do dólar na compra (R$)", min_value=0.01, value=round(cot_default, 4), step=0.01, format="%.4f")
                taxas_usd = u3.number_input("Taxas / IOF pagos (R$)", min_value=0.0, value=0.0, step=1.0)

                u4, u5 = st.columns(2)
                data_usd = u4.date_input("Data da compra", value=hoje_br(), format="DD/MM/YYYY", key="dt_usd")
                corretora_usd = u5.text_input("Onde comprou", value="Nomad").strip()

                if st.form_submit_button("Salvar compra de dólar", use_container_width=True, type="primary"):
                    pm_usd = (float(usd_comprado) * float(cot_compra) + float(taxas_usd)) / float(usd_comprado)
                    live = cotacao_dolar()
                    somar_ou_adicionar_ativo({
                        "id": novo_id(), "ticker": "USD", "nome": "Dólar Americano",
                        "classe": "Dólar", "qtd": float(usd_comprado), "pm": float(pm_usd),
                        "preco_atual": float(live["preco"]) if live else float(cot_compra),
                        "data_compra": data_usd.strftime("%Y-%m-%d"),
                        "corretora": corretora_usd
                    })
                    salvar_dados(db)
                    st.toast("Compra de dólar registrada!", icon="💵")
                    st.rerun()

        if df_alt.empty:
            vazio("Nenhuma cripto ou dólar registrado.", "₿")
        else:
            listar_ativos(df_alt)

    with aba_caixinhas:
        hoje = hoje_br()
        movs_todas = db.get("caixinhas_mov", [])

        md(f"""
        <div class="card-pro" style="background:linear-gradient(135deg,#0A1628,#0E3447 70%,#0F766E 150%);border:none;color:#fff;position:relative;overflow:hidden">
          <div style="font-size:.74rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#5EEAD4">Total guardado em caixinhas</div>
          <div style="font-size:2.4rem;font-weight:900;color:#fff;margin:6px 0;letter-spacing:-.035em">{fmt_moeda(total_em_caixinhas)}</div>
          <div style="font-size:.88rem;color:#AFC0D2">Dinheiro seguro guardado para suas metas, reservas e planos pessoais.</div>
        </div>
        """)

        with st.expander("Criar nova caixinha"):
            with st.form("form_nova_caixinha", clear_on_submit=True):
                cx1, cx2 = st.columns(2)
                nome_cx = cx1.text_input("Nome da Caixinha", placeholder="Ex: Fluxo do Mês, Reserva de Emergência, Viagem").strip()
                banco_cx = cx2.text_input("Banco ou onde está guardado", placeholder="Ex: Nubank, Banco Inter, C6 Bank").strip()

                cx3, cx4 = st.columns(2)
                saldo_inicial_cx = cx3.number_input("Valor que guardou inicialmente (R$)", min_value=0.01, value=500.0, step=50.0)
                rendimento_cx = cx4.number_input("Rendimento acumulado até hoje (R$)", min_value=0.0, value=0.0, step=10.0)

                if st.form_submit_button("Criar caixinha", use_container_width=True, type="primary"):
                    if nome_cx:
                        novo_cx_id = novo_id()
                        hoje_s = hoje_br().strftime("%Y-%m-%d")
                        db.setdefault("caixinhas", []).append({
                            "id": novo_cx_id, "nome": nome_cx.title(), "banco": banco_cx.title() if banco_cx else "Nubank",
                            "saldo": float(saldo_inicial_cx) + float(rendimento_cx), "guardado_inicial": float(saldo_inicial_cx),
                            "rendimento": float(rendimento_cx), "data_criacao": hoje_s
                        })
                        registrar_mov_caixinha(novo_cx_id, "entrada", saldo_inicial_cx, hoje_s, "Valor inicial")
                        if rendimento_cx > 0:
                            registrar_mov_caixinha(novo_cx_id, "rendimento", rendimento_cx, hoje_s, "Rendimento acumulado")
                        salvar_dados(db)
                        st.toast(f"Caixinha '{nome_cx.title()}' criada com sucesso!", icon="📦")
                        st.rerun()

        if not caixinhas_lista:
            vazio("Nenhuma caixinha criada ainda. Crie sua primeira caixinha no botão acima!", "📦")
        else:
            for cx in caixinhas_lista:
                saldo_cx = float(cx.get("saldo", 0.0))
                m_cx = [m for m in movs_todas if m["caixinha_id"] == cx["id"]]
                tot_g = sum(float(m["valor"]) for m in m_cx if m["tipo"] == "entrada")
                tot_r = sum(float(m["valor"]) for m in m_cx if m["tipo"] == "saida")
                tot_rend = sum(float(m["valor"]) for m in m_cx if m["tipo"] == "rendimento")

                with st.container(border=True):
                    col_card, col_acoes_cx = st.columns([3.4, 2.2], vertical_alignment="center")

                    with col_card:
                        md(f"""
                        <div>
                          <div class="asset-tk">📦 {html.escape(cx['nome'])} <span class="chip chip-caixinhas">{html.escape(cx.get('banco', 'Banco'))}</span></div>
                          <div style="font-size:1.7rem;font-weight:900;color:#15803D;margin:4px 0;letter-spacing:-.03em;font-variant-numeric:tabular-nums">{fmt_moeda(saldo_cx)}</div>
                          <div style="display:flex;gap:18px;font-size:.8rem;color:#64748B;flex-wrap:wrap">
                            <span>⬆️ Guardei: <b>{fmt_moeda(tot_g)}</b></span>
                            <span>⬇️ Retirei: <b>{fmt_moeda(tot_r)}</b></span>
                            <span>📈 Rendimento: <b>{fmt_moeda(tot_rend)}</b></span>
                          </div>
                        </div>
                        """)

                    with col_acoes_cx:
                        c_guardar, c_retirar, c_editar_cx, c_del_cx = st.columns(4)

                        with c_guardar:
                            with st.popover(":material/add:", use_container_width=True, help="Guardar dinheiro"):
                                st.markdown(f"**Guardar na caixinha {cx['nome']}**")
                                tipo_g = st.radio("Tipo", ["Depósito", "Rendimento"], horizontal=True, key=f"tipo_g_{cx['id']}")
                                val_guardar = st.number_input("Valor (R$)", min_value=0.01, value=100.0, step=50.0, key=f"g_cx_{cx['id']}")
                                dt_g = st.date_input("Data", value=hoje_br(), format="DD/MM/YYYY", key=f"dt_g_{cx['id']}")
                                obs_g = st.text_input("Observação (opcional)", key=f"obs_g_{cx['id']}")
                                if st.button("Confirmar Entrada", key=f"btn_g_cx_{cx['id']}", type="primary", use_container_width=True):
                                    cx["saldo"] = float(cx.get("saldo", 0.0)) + float(val_guardar)
                                    if tipo_g == "Rendimento":
                                        cx["rendimento"] = float(cx.get("rendimento", 0.0)) + float(val_guardar)
                                    registrar_mov_caixinha(cx["id"], "rendimento" if tipo_g == "Rendimento" else "entrada", val_guardar, dt_g.strftime("%Y-%m-%d"), obs_g.strip())
                                    salvar_dados(db)
                                    st.toast(f"{fmt_moeda(val_guardar)} guardados em {cx['nome']}!", icon="💰")
                                    st.rerun()

                        with c_retirar:
                            with st.popover(":material/remove:", use_container_width=True, help="Retirar dinheiro"):
                                st.markdown(f"**Retirar da caixinha {cx['nome']}**")
                                val_retirar = st.number_input("Valor (R$)", min_value=0.01, max_value=max(0.01, saldo_cx), value=min(100.0, max(0.01, saldo_cx)), step=50.0, key=f"r_cx_{cx['id']}")
                                dt_r = st.date_input("Data", value=hoje_br(), format="DD/MM/YYYY", key=f"dt_r_{cx['id']}")
                                obs_r = st.text_input("Motivo (opcional)", key=f"obs_r_{cx['id']}")
                                if st.button("Confirmar Saída", key=f"btn_r_cx_{cx['id']}", type="primary", use_container_width=True):
                                    cx["saldo"] = max(0.0, float(cx.get("saldo", 0.0)) - float(val_retirar))
                                    registrar_mov_caixinha(cx["id"], "saida", val_retirar, dt_r.strftime("%Y-%m-%d"), obs_r.strip())
                                    salvar_dados(db)
                                    st.toast(f"{fmt_moeda(val_retirar)} retirados de {cx['nome']}!", icon="💸")
                                    st.rerun()

                        with c_editar_cx:
                            with st.popover(":material/edit:", use_container_width=True, help="Editar"):
                                ed_nom_cx = st.text_input("Nome da Caixinha", value=cx["nome"], key=f"ed_nom_cx_{cx['id']}")
                                ed_bco_cx = st.text_input("Banco", value=cx.get("banco", "Nubank"), key=f"ed_bco_cx_{cx['id']}")
                                ed_sal_cx = st.number_input("Saldo atual (R$)", value=float(cx.get("saldo", 0.0)), key=f"ed_sal_cx_{cx['id']}")
                                if st.button("Salvar Edição", key=f"btn_e_cx_{cx['id']}", type="primary", use_container_width=True):
                                    diff = float(ed_sal_cx) - float(cx.get("saldo", 0.0))
                                    if abs(diff) > 0.005:
                                        registrar_mov_caixinha(cx["id"], "entrada" if diff > 0 else "saida", abs(diff), hoje_br().strftime("%Y-%m-%d"), "Ajuste manual")
                                    cx["nome"] = ed_nom_cx.title()
                                    cx["banco"] = ed_bco_cx.title()
                                    cx["saldo"] = float(ed_sal_cx)
                                    salvar_dados(db)
                                    st.toast("Caixinha atualizada!")
                                    st.rerun()

                        with c_del_cx:
                            if st.button(":material/delete:", key=f"del_cx_{cx['id']}", help="Excluir caixinha"):
                                db["caixinhas"] = [x for x in db["caixinhas"] if x["id"] != cx["id"]]
                                db["caixinhas_mov"] = [m for m in db["caixinhas_mov"] if m["caixinha_id"] != cx["id"]]
                                salvar_dados(db)
                                st.rerun()

    with aba_vendas:
        lista_vendas = db.get("vendas", [])
        if not lista_vendas:
            vazio("Nenhuma venda de ativos registrada ainda.", "💸")
        else:
            for v in reversed(lista_vendas):
                lucro_v = v["lucro_reais"]
                tag_v = f"<span class='badge-status {'status-alta' if lucro_v>=0 else 'status-baixa'}'>{'Lucro' if lucro_v>=0 else 'Prejuízo'} · {fmt_moeda(lucro_v)}</span>"
                with st.container(border=True):
                    cv1, cv2, cv3, cv4 = st.columns([1.5, 1.2, 1.3, 0.4], vertical_alignment="center")
                    cv1.markdown(f"<div class='asset-tk'>{v['ticker']}</div><div class='asset-sub'>{fmt_num_limpo(v['qtd'])} un. · Venda em {datetime.strptime(v['data'], '%Y-%m-%d').strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
                    cv2.markdown(f"<div class='cell-l'>Total recebido</div><div class='cell-big'>{fmt_moeda(v['total_recebido'])}</div>", unsafe_allow_html=True)
                    cv3.markdown(tag_v, unsafe_allow_html=True)
                    if cv4.button(":material/delete:", key=f"del_v_{v['id']}"):
                        db["vendas"] = [x for x in db["vendas"] if x["id"] != v["id"]]
                        salvar_dados(db)
                        st.rerun()

# ==============================================================================
# TELA: AGENDA DE DIVIDENDOS
# ==============================================================================
def pagina_dividendos() -> None:
    """Tela: Dividendos."""
    hero("Agenda de Dividendos & Proventos", "Controle de proventos com cálculo automático e confirmação de recebimento.")

    hoje = hoje_br()
    c1, c2 = st.columns([2.5, 1])
    m_p = c1.selectbox("Mês", range(1, 13), index=hoje.month - 1, format_func=lambda x: MESES_PT[x-1], key="m_prov")
    a_p = c2.selectbox("Ano", [hoje.year - 1, hoje.year, hoje.year + 1], index=1, key="a_prov")
    chave_prv = f"{a_p:04d}-{m_p:02d}"

    col_auto, col_man = st.columns([2, 1], vertical_alignment="center")
    with col_auto:
        if st.button("Sincronizar dividendos da minha carteira", type="primary", use_container_width=True):
            qtd_adicionados = sincronizar_dividendos_carteira(m_p, a_p)
            if qtd_adicionados > 0:
                st.toast(f"{qtd_adicionados} provento(s) adicionados para {MESES_PT[m_p-1]}!", icon="📈")
            else:
                st.toast("Os proventos dos seus ativos já estão cadastrados para este mês!", icon="ℹ️")
            st.rerun()

    with col_man:
        with st.popover("Lançar manualmente", use_container_width=True):
            with st.form("form_novo_prov_man", clear_on_submit=True):
                dt_pagamento = st.date_input("Data de Pagamento", value=hoje_br(), format="DD/MM/YYYY")
                lista_tickers = [a["ticker"] for a in db["ativos"] if a["classe"] in ("Ações", "FIIs", "Renda Fixa", "Internacional")] or ["Outro"]
                tick_p = st.selectbox("Ativo", lista_tickers)
                tipo_p = st.selectbox("Tipo de Provento", ["Rendimento FII", "Dividendo / JCP", "Juros Renda Fixa", "Outro"])
                val_total = st.number_input("Valor a Receber (R$)", min_value=0.01, value=50.0, step=1.0)
                status_p = st.selectbox("Status", ["⏳ Previsto (A Receber)", "✅ Já Caiu na Conta"])

                if st.form_submit_button("Salvar provento", use_container_width=True, type="primary"):
                    db["proventos"].append({
                        "id": int(datetime.now().timestamp() * 1000), "data": dt_pagamento.strftime("%Y-%m-%d"),
                        "ticker": tick_p, "valor": float(val_total), "tipo": tipo_p,
                        "status": "recebido" if "Já Caiu" in status_p else "previsto"
                    })
                    salvar_dados(db)
                    st.toast("Provento registrado!", icon="💰")
                    st.rerun()

    prov_mes = [p for p in db.get("proventos", []) if p["data"].startswith(chave_prv)]
    tot_previsto = sum(float(p["valor"]) for p in prov_mes if p.get("status") == "previsto")
    tot_recebido = sum(float(p["valor"]) for p in prov_mes if p.get("status") == "recebido")

    md(f"""
    <div class="stats" style="margin-top:1.2rem">
      <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(tot_previsto + tot_recebido)}</div><div class="stat-l">Total previsto em {MESES_PT[m_p-1]}</div></div>
      <div class="stat"><div class="stat-n" style="color:#D97706">{fmt_moeda(tot_previsto)}</div><div class="stat-l">A receber no mês</div></div>
      <div class="stat"><div class="stat-n" style="color:#15803D">{fmt_moeda(tot_recebido)}</div><div class="stat-l">Já recebido na conta</div></div>
    </div>
    """)

    secao(f"Proventos em {a_p}", "Recebidos e previstos mês a mês. O mês selecionado fica destacado.")
    _rec_m, _prev_m = [], []
    for _m in range(1, 13):
        _ch = f"{a_p:04d}-{_m:02d}"
        _rec_m.append(sum(float(p["valor"]) for p in db.get("proventos", []) if p["data"].startswith(_ch) and p.get("status") == "recebido"))
        _prev_m.append(sum(float(p["valor"]) for p in db.get("proventos", []) if p["data"].startswith(_ch) and p.get("status") == "previsto"))
    _rot_m = [MESES_PT[i][:3] for i in range(12)]
    fig_prov = go.Figure()
    fig_prov.add_bar(x=_rot_m, y=_rec_m, name="Recebido", marker=dict(color=[COR_ENTRADA if i == m_p - 1 else "#6EE7B7" for i in range(12)], cornerradius=5),
                     hovertemplate="<b>%{x}</b><br>Recebido: R$ %{y:,.2f}<extra></extra>")
    fig_prov.add_bar(x=_rot_m, y=_prev_m, name="Previsto", marker=dict(color=[COR_AZUL if i == m_p - 1 else "#93C5FD" for i in range(12)], cornerradius=5),
                     hovertemplate="<b>%{x}</b><br>Previsto: R$ %{y:,.2f}<extra></extra>")
    estilizar(fig_prov, 300, barmode="stack", bargap=0.3)
    fig_prov.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    mostrar(fig_prov)
    md(f"<div class='insight'><div>Total de proventos em {a_p}: <b>{fmt_moeda(sum(_rec_m))}</b> recebidos e <b>{fmt_moeda(sum(_prev_m))}</b> previstos.</div></div>")

    secao(f"Proventos de {MESES_PT[m_p-1]}/{a_p}")
    if not prov_mes:
        vazio(f"Nenhum dividendo agendado para {MESES_PT[m_p-1]}/{a_p}. Clique no botão acima para sincronizar!", "💰")
    else:
        for r in prov_mes:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1.4, 1.3, 0.4], vertical_alignment="center")
                c1.markdown(f"<div class='asset-tk'>{r['ticker']}</div><div class='asset-sub'>🗓️ {datetime.strptime(r['data'], '%Y-%m-%d').strftime('%d/%m/%Y')} · {r['tipo']}</div>", unsafe_allow_html=True)
                c2.markdown(f"<span style='font-size:1.2rem;font-weight:800;color:#0B1220;font-variant-numeric:tabular-nums'>{fmt_moeda(r['valor'])}</span>", unsafe_allow_html=True)

                with c3:
                    if r["status"] == "recebido":
                        md("<span class='badge-status status-alta'>Já caiu na conta</span>")
                    else:
                        if st.button("Confirmar recebimento", key=f"conf_{r['id']}", use_container_width=True):
                            r["status"] = "recebido"
                            salvar_dados(db)
                            st.toast("Recebimento confirmado!", icon="💰")
                            st.rerun()

                with c4:
                    if st.button(":material/delete:", key=f"del_prv_{r['id']}"):
                        db["proventos"] = [p for p in db["proventos"] if p["id"] != r["id"]]
                        salvar_dados(db)
                        st.rerun()

# ==============================================================================
# TELA: CARTÃO DE CRÉDITO
# ==============================================================================
def pagina_cartao() -> None:
    """Tela: Cartão de Crédito."""
    hero("Faturas & Cartão de Crédito", f"Fechamento dia {DIA_FECHAMENTO_CARTAO} e vencimento dia {DIA_VENCIMENTO_CARTAO}. Selecione o mês para ver a fatura.")

    hoje = hoje_br()

    if "fatura_mes_num" not in st.session_state:
        st.session_state["fatura_mes_num"] = hoje.month
    if "fatura_ano_num" not in st.session_state:
        st.session_state["fatura_ano_num"] = hoje.year

    def _ir_para_fatura(mes_k, ano_k):
        # Atualiza direto as chaves dos seletores (antes de serem desenhados),
        # senão o selectbox ignora o novo valor e volta para o mês antigo.
        st.session_state["sel_mfat"] = mes_k
        st.session_state["sel_afat"] = ano_k
        st.session_state["fatura_mes_num"] = mes_k
        st.session_state["fatura_ano_num"] = ano_k

    c_f1, c_f2 = st.columns([2.5, 1])
    with c_f1:
        mes_fat_idx = st.selectbox("Mês da fatura", range(1, 13), index=st.session_state["fatura_mes_num"] - 1, format_func=lambda x: MESES_PT[x-1], key="sel_mfat")
        st.session_state["fatura_mes_num"] = mes_fat_idx
    with c_f2:
        anos_opcoes = [hoje.year - 1, hoje.year, hoje.year + 1, hoje.year + 2]
        idx_ano = anos_opcoes.index(st.session_state["fatura_ano_num"]) if st.session_state["fatura_ano_num"] in anos_opcoes else 1
        ano_fat = st.selectbox("Ano da fatura", anos_opcoes, index=idx_ano, key="sel_afat")
        st.session_state["fatura_ano_num"] = ano_fat

    mes_sel = st.session_state["fatura_mes_num"]
    ano_sel = st.session_state["fatura_ano_num"]
    fatura_chave_sel = f"{ano_sel:04d}-{mes_sel:02d}"
    mes_fat_nome = MESES_PT[mes_sel - 1]

    with st.expander("Lançar nova compra no cartão de crédito"):
        with st.form("form_compra_cartao", clear_on_submit=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            desc_compra = f_c1.text_input("Nome da Compra / Loja", placeholder="Ex: Celular, Zara, Curso").strip()
            cartao_nome = f_c2.selectbox("Cartão Utilizado", LISTA_CARTOES)
            categoria_compra = f_c3.selectbox("Categoria", LISTA_CATEGORIAS_CARTAO)

            f_c4, f_c5, f_c6, f_c7 = st.columns(4)
            val_total_compra = f_c4.number_input("Valor Total (R$)", min_value=0.50, value=20.90, step=10.0)
            parc_total_compra = f_c5.number_input("Número de Parcelas", min_value=1, max_value=60, value=1, step=1)
            val_parc_compra = f_c6.number_input("Valor de cada Parcela (R$)", min_value=0.0, value=0.0, step=10.0)
            cashback_compra = f_c7.number_input("Cashback Ganho (R$)", min_value=0.0, value=0.0, step=0.50)

            f_c8, f_c9, f_c10 = st.columns([1.2, 1.4, 1.4])
            dt_compra = f_c8.date_input("Data da Compra", value=hoje_br(), format="DD/MM/YYYY")

            mes_sug = dt_compra.month + (1 if dt_compra.day >= DIA_FECHAMENTO_CARTAO else 0)
            ano_sug = dt_compra.year + (1 if mes_sug > 12 else 0)
            mes_sug = 1 if mes_sug > 12 else mes_sug

            mes_cobranca_idx = f_c9.selectbox("Fatura da 1ª Parcela (Mês):", range(1, 13), index=mes_sug - 1, format_func=lambda x: MESES_PT[x-1])
            ano_cobranca = f_c10.selectbox("Ano da Fatura:", [ano_sug, ano_sug + 1], index=0)

            if st.form_submit_button("Lançar compra no cartão", use_container_width=True, type="primary"):
                if desc_compra:
                    p_calc = float(val_parc_compra) if val_parc_compra > 0 else (float(val_total_compra) / int(parc_total_compra))
                    db.setdefault("cartao_compras", []).append({
                        "id": int(datetime.now().timestamp() * 1000), "descricao": desc_compra, "cartao": cartao_nome,
                        "categoria": categoria_compra, "valor_total": float(val_total_compra), "parcelas_total": int(parc_total_compra),
                        "valor_parcela": float(p_calc), "cashback_reais": float(cashback_compra), "data_compra": dt_compra.strftime("%Y-%m-%d"),
                        "mes_inicio_fatura": f"{ano_cobranca:04d}-{mes_cobranca_idx:02d}"
                    })
                    salvar_dados(db)
                    st.toast("Compra cadastrada!", icon="💳")
                    st.rerun()

    compras_cartao = db.get("cartao_compras", [])
    total_fatura_mes_sel = 0.0
    total_cashback_mes_sel = 0.0
    total_divida_futura_restante = 0.0
    compras_do_mes = []
    projecao_meses = {}

    fatura_atual_real_chave = f"{hoje.year:04d}-{hoje.month:02d}"

    for c in compras_cartao:
        v_tot = float(c["valor_total"])
        p_tot = int(c["parcelas_total"])
        v_parc = float(c.get("valor_parcela", v_tot / max(p_tot, 1)))
        try:
            dt_compra_obj = datetime.strptime(c["data_compra"], "%Y-%m-%d").date()
        except Exception:
            dt_compra_obj = hoje
        mes_compra_chave = f"{dt_compra_obj.year:04d}-{dt_compra_obj.month:02d}"

        if mes_compra_chave == fatura_chave_sel:
            total_cashback_mes_sel += float(c.get("cashback_reais", 0.0))

        ano_ini, mes_ini = inicio_fatura_compra(c)

        for p_idx in range(1, p_tot + 1):
            mes_num = mes_ini + (p_idx - 1)
            ano_num = ano_ini + (mes_num - 1) // 12
            mes_real = ((mes_num - 1) % 12) + 1
            fat_chave = f"{ano_num:04d}-{mes_real:02d}"

            projecao_meses[fat_chave] = projecao_meses.get(fat_chave, 0.0) + v_parc

            if fat_chave >= fatura_atual_real_chave:
                total_divida_futura_restante += v_parc

            if fat_chave == fatura_chave_sel:
                parc_restantes_depois = max(0, p_tot - p_idx)
                saldo_devedor_depois = parc_restantes_depois * v_parc
                total_fatura_mes_sel += v_parc

                compras_do_mes.append({
                    "id": c["id"], "descricao": c["descricao"], "cartao": c["cartao"], "categoria": c["categoria"],
                    "valor_total": v_tot, "parcela_atual": p_idx, "parcelas_total": p_tot, "valor_parcela": v_parc,
                    "parcelas_restantes": parc_restantes_depois, "saldo_restante": saldo_devedor_depois,
                    "cashback": float(c.get("cashback_reais", 0.0)) if mes_compra_chave == fatura_chave_sel else 0.0,
                    "data_compra": c["data_compra"], "ano_inicio": ano_ini, "mes_inicio": mes_ini
                })

    md(f"""
    <div class="stats" style="margin-top:1.2rem">
      <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(total_fatura_mes_sel)}</div><div class="stat-l">Fatura em {mes_fat_nome}/{ano_sel}</div></div>
      <div class="stat"><div class="stat-n" style="color:#15803D">+{fmt_moeda(total_cashback_mes_sel)}</div><div class="stat-l">Cashback no mês</div></div>
      <div class="stat"><div class="stat-n" style="color:#B91C1C">{fmt_moeda(total_divida_futura_restante)}</div><div class="stat-l">Dívida total parcelada restante</div></div>
      <div class="stat"><div class="stat-n">{len(compras_do_mes)}</div><div class="stat-l">Compras nesta fatura</div></div>
    </div>
    """)

    if projecao_meses:
        chaves_futuras = sorted(k for k in projecao_meses.keys() if k >= fatura_atual_real_chave)
        chaves_proj = chaves_futuras[:12]

        secao("Visão das faturas", "Quanto você paga em cada fatura e como a dívida parcelada vai diminuindo.")
        col_p1, col_p2 = st.columns([1.5, 1], gap="large")
        with col_p1:
            titulo_grafico("Projeção das próximas faturas", f"Mês selecionado em destaque: {mes_fat_nome}/{ano_sel}")
            mostrar(fig_projecao_faturas(chaves_proj, projecao_meses, fatura_chave_sel))
        with col_p2:
            titulo_grafico(f"Fatura de {mes_fat_nome} por categoria", "Para onde foi o dinheiro do cartão")
            if compras_do_mes:
                _cat = {}
                for it in compras_do_mes:
                    _cat[it["categoria"]] = _cat.get(it["categoria"], 0.0) + it["valor_parcela"]
                _cat_ord = sorted(_cat.items(), key=lambda kv: kv[1], reverse=True)
                _rot = [k for k, _ in _cat_ord]
                _val = [v for _, v in _cat_ord]
                _cor = [SEQ_CORES[i % len(SEQ_CORES)] for i in range(len(_rot))]
                mostrar(fig_donut(_rot, _val, _cor, f"<b>{fmt_moeda(total_fatura_mes_sel, 0)}</b><br><span style='font-size:11px;color:#64748B'>fatura</span>", 250))
                md(legenda_html(_rot, _val, _cor))
            else:
                vazio("Nenhuma compra nesta fatura.")

        col_p3, col_p4 = st.columns([1.5, 1], gap="large")
        with col_p3:
            titulo_grafico("Dívida parcelada a pagar", "Quanto ainda falta pagar, a partir de cada mês")
            if len(chaves_futuras) >= 1:
                mostrar(fig_divida_restante(chaves_futuras[:18], projecao_meses))
        with col_p4:
            titulo_grafico(f"Por cartão em {mes_fat_nome}", "Quanto cada cartão pesa nesta fatura")
            if compras_do_mes:
                _cartao = {}
                for it in compras_do_mes:
                    _cartao[it["cartao"]] = _cartao.get(it["cartao"], 0.0) + it["valor_parcela"]
                _cs = sorted(_cartao.items(), key=lambda kv: kv[1], reverse=True)
                mostrar(fig_barras_simples([k for k, _ in _cs], [v for _, v in _cs], COR_AZUL, max(200, 56 * len(_cs) + 60)))
            else:
                vazio("Nenhuma compra nesta fatura.")

        secao("Abrir outra fatura", "Selecione o mês para ver todas as compras e parcelas dele.")
        chaves_botoes = [k for k in chaves_futuras if int(k.split("-")[0]) in anos_opcoes][:12]
        for i in range(0, len(chaves_botoes), 6):
            linha = chaves_botoes[i:i + 6]
            cols_botoes = st.columns(6)
            for col_btn, k_chave in zip(cols_botoes, linha):
                ano_k = int(k_chave.split("-")[0])
                mes_k = int(k_chave.split("-")[1])
                rotulo = f"{MESES_PT[mes_k - 1][:3]}/{str(ano_k)[2:]}\n{fmt_moeda(projecao_meses[k_chave])}"
                eh_sel = (mes_k == mes_sel and ano_k == ano_sel)
                col_btn.button(
                    rotulo, key=f"btn_p_{k_chave}", use_container_width=True,
                    type="primary" if eh_sel else "secondary",
                    on_click=_ir_para_fatura, args=(mes_k, ano_k)
                )

    secao(f"Compras e parcelas na fatura de {mes_fat_nome}/{ano_sel}")
    if not compras_do_mes:
        vazio(f"Nenhuma compra cai na fatura de {mes_fat_nome}/{ano_sel}.", "💳")
    else:
        for item in compras_do_mes:
            with st.container(border=True):
                c_nom, c_parc, c_sal, c_cash, c_ed, c_del = st.columns([1.6, 1.4, 1.3, 1.1, 0.4, 0.4], vertical_alignment="center")
                c_nom.markdown(f"<div class='asset-tk'>{html.escape(item['descricao'])} <span class='chip chip-cartao'>{html.escape(item['cartao'])}</span></div><div class='asset-sub'>{html.escape(item['categoria'])} · {datetime.strptime(item['data_compra'], '%Y-%m-%d').strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
                c_parc.markdown(f"<div class='cell-l'>Parcela {item['parcela_atual']} de {item['parcelas_total']}</div><div class='cell-big'>{fmt_moeda(item['valor_parcela'])}</div>", unsafe_allow_html=True)
                c_sal.markdown(f"<div style='color:#B91C1C;font-weight:700;font-size:.92rem'>Falta: {fmt_moeda(item['saldo_restante'])}</div><div class='asset-sub'>Restam {item['parcelas_restantes']} parcelas</div>", unsafe_allow_html=True)
                c_cash.markdown(f"<span class='badge-status status-alta'>+{fmt_moeda(item['cashback'])}</span>" if item["cashback"] > 0 else "<span style='font-size:.78rem;color:#94A3B8'>Sem cashback</span>", unsafe_allow_html=True)

                with c_ed:
                    with st.popover(":material/edit:", use_container_width=True):
                        e_desc = st.text_input("Descrição", value=item["descricao"], key=f"ed_d_{item['id']}")
                        idx_cat_c = LISTA_CATEGORIAS_CARTAO.index(item["categoria"]) if item["categoria"] in LISTA_CATEGORIAS_CARTAO else 0
                        e_cat = st.selectbox("Categoria", LISTA_CATEGORIAS_CARTAO, index=idx_cat_c, key=f"ed_cat_{item['id']}")
                        e_tot = st.number_input("Total (R$)", value=float(item["valor_total"]), key=f"ed_tot_{item['id']}")
                        e_parc = st.number_input("Parcelas", min_value=1, value=int(item["parcelas_total"]), key=f"ed_parc_{item['id']}")
                        e_vparc = st.number_input("Valor Parcela (R$)", value=float(item["valor_parcela"]), key=f"ed_vp_{item['id']}")
                        e_cash = st.number_input("Cashback (R$)", value=float(item["cashback"]), key=f"ed_cb_{item['id']}")
                        if st.button("Salvar Edição", key=f"btn_e_{item['id']}", type="primary"):
                            for cp in db["cartao_compras"]:
                                if cp["id"] == item["id"]:
                                    cp["descricao"] = e_desc
                                    cp["categoria"] = e_cat
                                    cp["valor_total"] = float(e_tot)
                                    cp["parcelas_total"] = int(e_parc)
                                    cp["valor_parcela"] = float(e_vparc)
                                    cp["cashback_reais"] = float(e_cash)
                            salvar_dados(db)
                            st.toast("Atualizado!")
                            st.rerun()

                with c_del:
                    if st.button(":material/delete:", key=f"del_cp_{item['id']}"):
                        db["cartao_compras"] = [x for x in db["cartao_compras"] if x["id"] != item["id"]]
                        salvar_dados(db)
                        st.rerun()

# ==============================================================================
# TELA: CONTA & DÉBITO
# ==============================================================================
def pagina_conta_debito() -> None:
    """Tela: Movimentações."""
    hero("Movimentações", "Controle tudo o que entra e sai da sua conta à vista: salário, vale, PIX e débito.")

    hoje = hoje_br()
    c1, c2 = st.columns([2.5, 1])
    mes_deb = c1.selectbox("Mês do Extrato", range(1, 13), index=hoje.month - 1, format_func=lambda x: MESES_PT[x-1], key="deb_mes")
    ano_deb = c2.selectbox("Ano", [hoje.year - 1, hoje.year, hoje.year + 1], index=1, key="deb_ano")
    chave_deb_sel = f"{ano_deb:04d}-{mes_deb:02d}"
    nome_mes_deb = MESES_PT[mes_deb - 1]

    with st.expander("Lançar nova movimentação (entrada ou saída)"):
        with st.form("form_nova_transacao", clear_on_submit=True):
            t1, t2 = st.columns(2)
            tipo_transacao = t1.radio("Tipo:", ["Entrada (+)", "Saída (-)"], horizontal=True)
            desc_transacao = t2.text_input("Descrição / O que foi", placeholder="Ex: Salário, Vale, Compra no Débito...").strip()

            t3, t4, t5 = st.columns(3)
            val_transacao = t3.number_input("Valor (R$)", min_value=0.01, value=150.0, step=10.0)
            cat_transacao = t4.selectbox("Categoria", LISTA_CATEGORIAS_DEBITO)
            dt_transacao = t5.date_input("Data da Operação", value=hoje_br(), format="DD/MM/YYYY")

            if st.form_submit_button("Lançar na conta", use_container_width=True, type="primary"):
                if desc_transacao:
                    db.setdefault("transacoes_debito", []).append({
                        "id": int(datetime.now().timestamp() * 1000), "tipo": tipo_transacao,
                        "descricao": desc_transacao, "categoria": cat_transacao, "valor": float(val_transacao),
                        "data": dt_transacao.strftime("%Y-%m-%d")
                    })
                    salvar_dados(db)
                    st.toast(f"{tipo_transacao} registrada!", icon="💸")
                    st.rerun()

    transacoes_todas = db.get("transacoes_debito", [])
    transacoes_mes = [t for t in transacoes_todas if t["data"].startswith(chave_deb_sel)]

    total_ent = sum(float(t["valor"]) for t in transacoes_mes if t["tipo"] == "Entrada (+)")
    total_sai = sum(float(t["valor"]) for t in transacoes_mes if t["tipo"] == "Saída (-)")
    saldo_conta_mes = total_ent - total_sai

    md(f"""
    <div class="stats" style="margin-top:1.2rem">
      <div class="stat"><div class="stat-n" style="color:#15803D">+{fmt_moeda(total_ent)}</div><div class="stat-l">Total de entradas em {nome_mes_deb}</div></div>
      <div class="stat"><div class="stat-n" style="color:#B91C1C">-{fmt_moeda(total_sai)}</div><div class="stat-l">Total de saídas no débito/PIX em {nome_mes_deb}</div></div>
      <div class="stat"><div class="stat-n" style="color:{'#15803D' if saldo_conta_mes >= 0 else '#B91C1C'}">{fmt_moeda(saldo_conta_mes)}</div><div class="stat-l">Saldo da conta em {nome_mes_deb}</div></div>
    </div>
    """)

    if transacoes_mes:
        col_m1, col_m2 = st.columns([1.2, 1], gap="large")
        with col_m1:
            titulo_grafico("Saldo acumulado no mês", "Como o saldo da conta evoluiu a cada movimentação")
            _acum, _xs, _ys = 0.0, [], []
            for _t in sorted(transacoes_mes, key=lambda t: (t["data"], t["id"])):
                _acum += float(_t["valor"]) if _t["tipo"] == "Entrada (+)" else -float(_t["valor"])
                _xs.append(datetime.strptime(_t["data"], "%Y-%m-%d")); _ys.append(_acum)
            fig_acum = go.Figure(go.Scatter(x=_xs, y=_ys, mode="lines+markers", line=dict(color=COR_BRAND, width=3, shape="hv"),
                                            fill="tozeroy", fillcolor="rgba(15,118,110,.10)",
                                            marker=dict(size=7, color="#FFFFFF", line=dict(color=COR_BRAND, width=2)),
                                            hovertemplate="<b>%{x|%d/%m}</b><br>Saldo: R$ %{y:,.2f}<extra></extra>"))
            estilizar(fig_acum, 290, legenda=False)
            fig_acum.update_xaxes(tickformat="%d/%m")
            fig_acum.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
            mostrar(fig_acum)
        with col_m2:
            titulo_grafico("Saídas por categoria", "Onde o dinheiro da conta foi parar")
            _sc = {}
            for _t in transacoes_mes:
                if _t["tipo"] == "Saída (-)":
                    _sc[_t["categoria"]] = _sc.get(_t["categoria"], 0.0) + float(_t["valor"])
            if _sc:
                _so = sorted(_sc.items(), key=lambda kv: kv[1], reverse=True)
                mostrar(fig_barras_simples([k for k, _ in _so], [v for _, v in _so], COR_SAIDA, max(200, 46 * len(_so) + 60)))
            else:
                vazio("Nenhuma saída neste mês.")

    secao(f"Extrato de movimentações — {nome_mes_deb}/{ano_deb}")
    if not transacoes_mes:
        vazio(f"Nenhuma movimentação lançada em {nome_mes_deb}/{ano_deb}.", "🏦")
    else:
        for t in reversed(transacoes_mes):
            eh_ent = t["tipo"] == "Entrada (+)"
            cor_val = "#15803D" if eh_ent else "#B91C1C"
            sinal = "+" if eh_ent else "-"
            chip_t = "chip-entrada" if eh_ent else "chip-saida"

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.6, 1.2, 1.2, 0.4], vertical_alignment="center")
                c1.markdown(f"<div class='asset-tk'>{html.escape(t['descricao'])} <span class='chip {chip_t}'>{t['tipo']}</span></div><div class='asset-sub'>{html.escape(t['categoria'])} · {datetime.strptime(t['data'], '%Y-%m-%d').strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
                c2.markdown(f"<span style='font-size:1.15rem;font-weight:800;color:{cor_val};font-variant-numeric:tabular-nums'>{sinal} {fmt_moeda(t['valor'])}</span>", unsafe_allow_html=True)

                with c3:
                    with st.popover(":material/edit:", use_container_width=True):
                        e_tipo = st.selectbox("Tipo", ["Entrada (+)", "Saída (-)"], index=0 if t["tipo"] == "Entrada (+)" else 1, key=f"e_tip_{t['id']}")
                        e_desc = st.text_input("Descrição", value=t["descricao"], key=f"e_d_deb_{t['id']}")
                        e_val = st.number_input("Valor (R$)", value=float(t["valor"]), key=f"e_v_deb_{t['id']}")
                        idx_cat_deb = LISTA_CATEGORIAS_DEBITO.index(t.get("categoria", "Outros")) if t.get("categoria") in LISTA_CATEGORIAS_DEBITO else 0
                        e_cat = st.selectbox("Categoria", LISTA_CATEGORIAS_DEBITO, index=idx_cat_deb, key=f"e_c_deb_{t['id']}")

                        if st.button("Salvar Edição", key=f"btn_e_deb_{t['id']}", type="primary"):
                            t["tipo"] = e_tipo
                            t["descricao"] = e_desc
                            t["valor"] = float(e_val)
                            t["categoria"] = e_cat
                            salvar_dados(db)
                            st.toast("Atualizado!")
                            st.rerun()

                with c4:
                    if st.button(":material/delete:", key=f"del_deb_{t['id']}"):
                        db["transacoes_debito"] = [x for x in db["transacoes_debito"] if x["id"] != t["id"]]
                        salvar_dados(db)
                        st.rerun()

# ==============================================================================
# TELA: DEVEDORES
# ==============================================================================
def pagina_devedores() -> None:
    """Tela: Devedores."""
    hero("Devedores", "Valores a receber, vencimentos de cada parcela e recebimentos registrados. O atraso é calculado pela data de vencimento.")

    hoje = hoje_br()
    nomes_cadastrados = sorted(list(set(d["nome"].strip().title() for d in db.get("devedores", []))))

    with st.expander("Adicionar nova cobrança", expanded=not db.get("devedores", [])):
        with st.form("form_novo_devedor", clear_on_submit=True):
            c1_nome, c2_nome = st.columns(2)
            nome_escolhido = c1_nome.selectbox("Pessoa já cadastrada", ["-- Nenhuma (digitar ao lado) --"] + nomes_cadastrados if nomes_cadastrados else ["Nenhuma cadastrada"])
            nome_digitado = c2_nome.text_input("Ou digite o nome de uma nova pessoa", placeholder="Ex: Rafael, Julia").strip()

            d1, d2 = st.columns(2)
            desc_p = d1.text_input("Descrição do que foi", placeholder="Ex: Óculos, Celular, Camisa").strip()
            forma_p = d2.selectbox("Forma do empréstimo", ["💳 Cartão de Crédito", "💸 PIX / Dinheiro"])

            d3, d4, d5, d6 = st.columns(4)
            val_p = d3.number_input("Valor total (R$)", min_value=1.0, value=100.0, step=50.0)
            parc_total = d4.number_input("Número de parcelas", min_value=1, max_value=60, value=1, step=1)
            val_parc_manual = d5.number_input("Valor de cada parcela (R$)", min_value=0.0, value=0.0, step=10.0, help="Deixe 0,00 para dividir o total igualmente pelas parcelas.")
            valor_ja_pago_inicial = d6.number_input("Já recebido até hoje (R$)", min_value=0.0, value=0.0, step=50.0)

            d7, d8 = st.columns(2)
            data_emp = d7.date_input("Data da compra / empréstimo", value=hoje, format="DD/MM/YYYY")
            prim_venc = d8.date_input("Vencimento da 1ª parcela", value=_add_meses(hoje, 1), format="DD/MM/YYYY",
                                      help="As demais parcelas vencem no mesmo dia dos meses seguintes.")

            if st.form_submit_button("Cadastrar cobrança", use_container_width=True, type="primary"):
                nome_final = nome_digitado.title() if nome_digitado else (nome_escolhido.strip().title() if nome_escolhido not in ["-- Nenhuma (digitar ao lado) --", "Nenhuma cadastrada"] else None)
                if not nome_final:
                    st.error("Informe o nome da pessoa.")
                else:
                    parc_calc = float(val_parc_manual) if val_parc_manual > 0 else (float(val_p) / int(parc_total))
                    db.setdefault("devedores", []).append({
                        "id": int(datetime.now().timestamp() * 1000), "nome": nome_final,
                        "descricao": desc_p if desc_p else "Empréstimo", "forma": forma_p,
                        "valor_total": float(val_p), "parcelas_total": int(parc_total),
                        "valor_parcela": float(parc_calc), "total_pago_reais": float(valor_ja_pago_inicial),
                        "parcelas_pagas": int(float(valor_ja_pago_inicial) / parc_calc) if parc_calc > 0 else 0,
                        "data_emprestimo": data_emp.strftime("%Y-%m-%d"),
                        "primeiro_vencimento": prim_venc.strftime("%Y-%m-%d"),
                        "data_vencimento": prim_venc.strftime("%Y-%m-%d"),
                        "dia_vencimento": int(prim_venc.day),
                        "pagamentos": [], "status": "quitado" if float(valor_ja_pago_inicial) >= float(val_p) - 0.05 else "pendente"
                    })
                    salvar_dados(db)
                    st.toast("Cobrança cadastrada.", icon="✅")
                    st.rerun()

    devedores_lista = db.get("devedores", [])
    if not devedores_lista:
        vazio("Ninguém está te devendo no momento.")
    else:
        # ---- resumo geral ----
        infos_all = [calcular_atraso_real_divida(d) for d in devedores_lista]
        tot_receber = sum(i["falta_total"] for i in infos_all)
        tot_atrasado = sum(i["valor_atraso"] for i in infos_all)
        chave_hoje = hoje.strftime("%Y-%m")
        md(f"""
        <div class="stats">
          <div class="stat"><div class="stat-n" style="color:#0B1220">{fmt_moeda(tot_receber)}</div><div class="stat-l">Total a receber</div></div>
          <div class="stat"><div class="stat-n" style="color:#B91C1C">{fmt_moeda(tot_atrasado)}</div><div class="stat-l">Em atraso (parcelas vencidas)</div></div>
          <div class="stat"><div class="stat-n" style="color:#2563EB">{fmt_moeda(previsto_devedores_no_mes(chave_hoje))}</div><div class="stat-l">Parcelas que vencem em {MESES_PT[hoje.month-1]}</div></div>
          <div class="stat"><div class="stat-n" style="color:#15803D">{fmt_moeda(recebido_devedores_no_mes(chave_hoje))}</div><div class="stat-l">Recebido em {MESES_PT[hoje.month-1]}</div></div>
        </div>
        """)

        pessoas_agrupadas = {}
        for d in devedores_lista:
            pessoas_agrupadas.setdefault(d["nome"].strip().title(), []).append(d)

        for nome_pessoa, dividas in sorted(pessoas_agrupadas.items()):
            tot_falta = sum(calcular_atraso_real_divida(it)["falta_total"] for it in dividas)
            tot_atraso = sum(calcular_atraso_real_divida(it)["valor_atraso"] for it in dividas)
            cor_topo = "#B91C1C" if tot_atraso > 0 else ("#2563EB" if tot_falta > 0 else "#15803D")
            md(f"""
            <div class="person">
              <div style="display:flex;align-items:center;gap:12px">
                <div class="avatar" style="background:#E6F6F4;color:#0F766E">{html.escape(nome_pessoa[:2].upper())}</div>
                <div style="font-size:1.05rem;font-weight:800;color:#0B1220;letter-spacing:-.01em">{html.escape(nome_pessoa)}</div>
              </div>
              <div style="font-size:.88rem;font-weight:600;color:#64748B">Total que deve: <b style="color:{cor_topo};font-size:1.02rem">{fmt_moeda(tot_falta)}</b></div>
            </div>
            """)

            for dev in dividas:
                info = calcular_atraso_real_divida(dev)
                forma_tag = dev.get("forma", "💳 Cartão de Crédito")
                forma_txt = "Cartão" if "Cartão" in forma_tag else "PIX / Dinheiro"
                forma_class = "chip-cartao" if "Cartão" in forma_tag else "chip-pix"
                dt_emp_str = dev.get("data_emprestimo", dev.get("data", "2026-01-01"))
                pagamentos = dev.get("pagamentos", [])
                soma_pgtos = sum(float(p.get("valor", 0.0)) for p in pagamentos)
                valor_inicial = max(0.0, info["total_pago"] - soma_pgtos)

                with st.container(border=True):
                    c_desc, c_parc, c_val, c_abater, c_acoes = st.columns([1.8, 1.3, 1.5, 1.1, 0.7], vertical_alignment="center")
                    with c_desc:
                        md(f"""
                        <div>
                          <div class="asset-tk">{html.escape(dev['descricao'])} <span class="chip {forma_class}">{forma_txt}</span></div>
                          <div style="margin-top:5px">{info['badge']}</div>
                          <div class="asset-sub" style="margin-top:4px">Início {datetime.strptime(dt_emp_str, '%Y-%m-%d').strftime('%d/%m/%Y')} · {info['msg_detalhe']}</div>
                          <div style="margin-top:8px;max-width:340px">{barra_progresso((info['total_pago'] / info['total_contratado'] * 100) if info['total_contratado'] > 0 else 0, None, 6)}</div>
                        </div>
                        """)

                    with c_parc:
                        if info["status"] == "quitado":
                            md(f"<div class='cell-l'>Total recebido</div><div class='cell-big' style='color:#15803D'>{fmt_moeda(info['total_pago'])}</div>")
                        else:
                            md(f"""
                            <div>
                              <div class="cell-l">{dev['parcelas_total']}x de</div>
                              <div class="cell-big">{fmt_moeda(info['v_parc'])}</div>
                              <div class="cell-l" style="margin-top:3px">Recebido: <b style="color:#15803D">{fmt_moeda(info['total_pago'])}</b></div>
                            </div>
                            """)

                    with c_val:
                        if info["status"] == "quitado":
                            md("<div class='cell-l'>Situação</div><div class='cell-big' style='color:#15803D'>Quitado</div>")
                        elif info["valor_atraso"] > 0:
                            md(f"""
                            <div>
                              <div class="cell-l">Em atraso</div>
                              <div class="cell-big" style="color:#B91C1C">{fmt_moeda(info['valor_atraso'])}</div>
                              <div class="cell-l" style="margin-top:3px">Falta no total: <b style="color:#0B1220">{fmt_moeda(info['falta_total'])}</b></div>
                            </div>
                            """)
                        else:
                            md(f"""
                            <div>
                              <div class="cell-l">Próxima parcela</div>
                              <div class="cell-big">{fmt_moeda(min(info['v_parc'], info['falta_total']))}</div>
                              <div class="cell-l" style="margin-top:3px">Vence em <b style="color:#0B1220">{info['proximo_venc'].strftime('%d/%m/%Y') if info['proximo_venc'] else '—'}</b></div>
                            </div>
                            """)

                    with c_abater:
                        if info["status"] != "quitado":
                            with st.popover("Registrar recebimento", use_container_width=True):
                                st.markdown("**Registrar recebimento**")
                                st.caption(f"Parcela: {fmt_moeda(info['v_parc'])} · Falta no total: {fmt_moeda(info['falta_total'])}")
                                v_abt = st.number_input(
                                    "Valor recebido (R$)", min_value=0.01, max_value=float(max(0.01, info["falta_total"])),
                                    value=float(max(0.01, min(info["v_parc"], info["falta_total"]))), step=10.0, key=f"abt_{dev['id']}")
                                dt_abt = st.date_input("Data do recebimento", value=hoje, format="DD/MM/YYYY", key=f"dt_abt_{dev['id']}")
                                if st.button("Confirmar recebimento", key=f"btn_abt_{dev['id']}", type="primary", use_container_width=True):
                                    novo_p = info["total_pago"] + float(v_abt)
                                    dev["total_pago_reais"] = round(float(novo_p), 2)
                                    dev.setdefault("pagamentos", []).append({"data": dt_abt.strftime("%Y-%m-%d"), "valor": float(v_abt)})
                                    dev["parcelas_pagas"] = int(novo_p / info["v_parc"]) if info["v_parc"] > 0 else 0
                                    dev["status"] = "quitado" if novo_p >= info["total_contratado"] - 0.05 else "pendente"
                                    salvar_dados(db)
                                    st.toast("Recebimento registrado.", icon="✅")
                                    st.rerun()

                    with c_acoes:
                        col_ed, col_dl = st.columns(2)
                        with col_ed:
                            with st.popover(":material/edit:", use_container_width=True, help="Editar cobrança"):
                                st.markdown("**Editar cobrança**")
                                ed_n = st.text_input("Nome", value=dev["nome"], key=f"ed_n_{dev['id']}")
                                ed_d = st.text_input("Descrição", value=dev["descricao"], key=f"ed_d_{dev['id']}")
                                ed_v = st.number_input("Valor total (R$)", min_value=1.0, value=float(dev["valor_total"]), key=f"ed_v_{dev['id']}")
                                ed_np = st.number_input("Nº de parcelas", min_value=1, max_value=60, value=int(dev["parcelas_total"]), key=f"ed_np_{dev['id']}")
                                ed_vp = st.number_input("Valor da parcela (R$)", min_value=0.01, value=float(info["v_parc"]), key=f"ed_vp_{dev['id']}")
                                try:
                                    _pv = datetime.strptime(str(dev.get("primeiro_vencimento") or dev.get("data_vencimento") or dt_emp_str), "%Y-%m-%d").date()
                                except Exception:
                                    _pv = hoje
                                ed_pv = st.date_input("Vencimento da 1ª parcela", value=_pv, format="DD/MM/YYYY", key=f"ed_pv_{dev['id']}")
                                ed_ini = st.number_input("Recebido antes do cadastro (R$)", min_value=0.0, value=float(valor_inicial), key=f"ed_ini_{dev['id']}",
                                                         help="Valor já recebido antes de começar a registrar aqui. Os recebimentos com data ficam no histórico.")
                                if st.button("Salvar alterações", key=f"btn_e_dev_{dev['id']}", type="primary", use_container_width=True):
                                    dev["nome"] = ed_n.strip().title()
                                    dev["descricao"] = ed_d
                                    dev["valor_total"] = float(ed_v)
                                    dev["parcelas_total"] = int(ed_np)
                                    dev["valor_parcela"] = float(ed_vp)
                                    dev["primeiro_vencimento"] = ed_pv.strftime("%Y-%m-%d")
                                    dev["data_vencimento"] = ed_pv.strftime("%Y-%m-%d")
                                    dev["dia_vencimento"] = int(ed_pv.day)
                                    dev["total_pago_reais"] = round(float(ed_ini) + soma_pgtos, 2)
                                    dev["parcelas_pagas"] = int(dev["total_pago_reais"] / float(ed_vp)) if float(ed_vp) > 0 else 0
                                    dev["status"] = "quitado" if dev["total_pago_reais"] >= float(ed_v) - 0.05 else "pendente"
                                    salvar_dados(db)
                                    st.toast("Cobrança atualizada.", icon="✅")
                                    st.rerun()
                        with col_dl:
                            with st.popover(":material/delete:", use_container_width=True, help="Excluir cobrança"):
                                st.markdown("**Excluir esta cobrança?**")
                                st.caption("Os recebimentos registrados nela também serão removidos.")
                                if st.button("Sim, excluir", key=f"del_dev_{dev['id']}", type="primary", use_container_width=True):
                                    db["devedores"] = [x for x in db["devedores"] if x["id"] != dev["id"]]
                                    salvar_dados(db)
                                    st.rerun()

                    # ---- histórico de recebimentos (data + valor), com ajuste/remoção ----
                    if pagamentos or valor_inicial > 0:
                        with st.expander(f"Histórico de recebimentos ({len(pagamentos)})"):
                            if valor_inicial > 0:
                                st.caption(f"Recebido antes do cadastro: {fmt_moeda(valor_inicial)}")
                            for pi, pg in sorted(enumerate(pagamentos), key=lambda t: str(t[1].get("data", ""))):
                                try:
                                    dt_pg_txt = datetime.strptime(str(pg["data"]), "%Y-%m-%d").strftime("%d/%m/%Y")
                                except Exception:
                                    dt_pg_txt = str(pg.get("data", ""))
                                h1, h2, h3, h4 = st.columns([1.2, 1.2, 0.6, 0.6], vertical_alignment="center")
                                h1.markdown(f"<div class='cell-l'>Data</div><div class='cell-v'>{dt_pg_txt}</div>", unsafe_allow_html=True)
                                h2.markdown(f"<div class='cell-l'>Valor</div><div class='cell-v' style='color:#15803D'>{fmt_moeda(pg['valor'])}</div>", unsafe_allow_html=True)
                                with h3:
                                    with st.popover(":material/edit:", use_container_width=True, help="Ajustar data / valor"):
                                        st.markdown("**Ajustar recebimento**")
                                        try:
                                            _dpg = datetime.strptime(str(pg["data"]), "%Y-%m-%d").date()
                                        except Exception:
                                            _dpg = hoje
                                        n_dt = st.date_input("Data", value=_dpg, format="DD/MM/YYYY", key=f"pg_dt_{dev['id']}_{pi}")
                                        n_vl = st.number_input("Valor (R$)", min_value=0.01, value=float(pg["valor"]), step=10.0, key=f"pg_vl_{dev['id']}_{pi}")
                                        if st.button("Salvar", key=f"pg_sv_{dev['id']}_{pi}", type="primary", use_container_width=True):
                                            delta = float(n_vl) - float(pg["valor"])
                                            pg["valor"] = float(n_vl)
                                            pg["data"] = n_dt.strftime("%Y-%m-%d")
                                            dev["total_pago_reais"] = round(max(0.0, float(dev.get("total_pago_reais", 0.0)) + delta), 2)
                                            dev["status"] = "quitado" if dev["total_pago_reais"] >= float(dev["valor_total"]) - 0.05 else "pendente"
                                            salvar_dados(db)
                                            st.toast("Recebimento ajustado.", icon="✅")
                                            st.rerun()
                                with h4:
                                    if st.button(":material/delete:", key=f"pg_del_{dev['id']}_{pi}", help="Remover este recebimento", use_container_width=True):
                                        dev["total_pago_reais"] = round(max(0.0, float(dev.get("total_pago_reais", 0.0)) - float(pg["valor"])), 2)
                                        dev["pagamentos"] = [x for j, x in enumerate(dev["pagamentos"]) if j != pi]
                                        dev["status"] = "quitado" if dev["total_pago_reais"] >= float(dev["valor_total"]) - 0.05 else "pendente"
                                        salvar_dados(db)
                                        st.toast("Recebimento removido.", icon="🗑️")
                                        st.rerun()

# ==============================================================================
# TELA: METAS
# ==============================================================================
def pagina_metas() -> None:
    """Tela: Metas."""
    meta_p = float(db.get("metas", {}).get("patrimonio", 100000.0))
    meta_r = float(db.get("metas", {}).get("renda_mensal", 1000.0))
    hero("Metas de Independência Financeira", "Defina seus objetivos patrimoniais e de renda passiva.")

    with st.form("form_metas"):
        c1, c2 = st.columns(2)
        n_patrimonio_str = c1.text_input("Meta de Patrimônio (R$)", value=fmt_num(meta_p, 2), help="Pode digitar com vírgula ou ponto (ex: 100.000,00 ou 100000,50)")
        n_renda_str = c2.text_input("Meta de Renda Mensal Desejada (R$)", value=fmt_num(meta_r, 2), help="Pode digitar com vírgula ou ponto (ex: 1.000,00 ou 1000,00)")

        if st.form_submit_button("Salvar novas metas", use_container_width=True, type="primary"):
            val_p_calc = parse_valor_moeda(n_patrimonio_str, meta_p)
            val_r_calc = parse_valor_moeda(n_renda_str, meta_r)
            if val_p_calc <= 0:
                st.error("Informe um valor válido para a meta de patrimônio.")
            else:
                db["metas"] = {"patrimonio": float(val_p_calc), "renda_mensal": float(val_r_calc)}
                salvar_dados(db)
                st.toast("Metas salvas com sucesso!", icon="🎯")
                st.rerun()

    pct = int((patrimonio_total / meta_p * 100)) if meta_p > 0 else 0
    falta_meta = max(0.0, meta_p - patrimonio_total)
    largura_barra = min(max(pct, 0), 100)

    secao("Progresso da meta de patrimônio")
    md(f"""
    <div class="card-pro">
      <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-bottom:14px">
        <div>
          <div class="cell-l">Patrimônio atual</div>
          <div style="font-size:2rem;font-weight:900;color:#0B1220;letter-spacing:-.03em">{fmt_moeda(patrimonio_total)}</div>
        </div>
        <div style="text-align:right">
          <div class="cell-l">Meta</div>
          <div style="font-size:1.3rem;font-weight:800;color:#0F766E">{fmt_moeda(meta_p)}</div>
        </div>
      </div>
      <div class="prog-wrap"><div class="prog-bar" style="width:{largura_barra}%"></div></div>
      <div style="display:flex;justify-content:space-between;margin-top:10px;font-size:.86rem;color:#64748B;flex-wrap:wrap;gap:6px">
        <span><b style="color:#0F766E">{pct}%</b> atingido</span>
        <span>Faltam <b style="color:#0B1220">{fmt_moeda(falta_meta)}</b></span>
      </div>
    </div>
    """)

    secao("Visão das metas", "Onde você está em relação ao que definiu.")
    col_g1, col_g2 = st.columns([1, 1], gap="large")
    with col_g1:
        titulo_grafico("Meta de patrimônio", "Patrimônio atual em relação à meta")
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number", value=patrimonio_total, number=dict(prefix="R$ ", valueformat=",.0f", font=dict(size=30, color="#0B1220")),
            gauge=dict(axis=dict(range=[0, max(meta_p, patrimonio_total)], tickformat=",.0f", tickfont=dict(size=10, color="#64748B")),
                       bar=dict(color=COR_BRAND, thickness=0.28), bgcolor="#EEF1F6", borderwidth=0,
                       threshold=dict(line=dict(color="#0B1220", width=3), thickness=0.8, value=meta_p))))
        estilizar(fig_g, 280, legenda=False, margin=dict(l=30, r=30, t=30, b=10))
        mostrar(fig_g)
    with col_g2:
        titulo_grafico("Meta de renda mensal", "Média mensal de proventos recebidos nos últimos 12 meses")
        _meses12 = meses_ate(hoje_br().year, hoje_br().month, 12)
        _rec12 = sum(float(p["valor"]) for p in db.get("proventos", []) if p.get("status") == "recebido" and p["data"][:7] in {f"{a:04d}-{m:02d}" for a, m in _meses12})
        _media12 = _rec12 / 12
        _pct_renda = (_media12 / meta_r * 100) if meta_r > 0 else 0.0
        md(f"""
        <div class="meter-box">
          <div class="meter-top">
            <div><div class="meter-l">Renda passiva média</div><div class="meter-v">{fmt_moeda(_media12)}</div></div>
            <div style="text-align:right"><div class="meter-l">Meta mensal</div><div class="meter-v" style="color:#0F766E;font-size:1.2rem">{fmt_moeda(meta_r)}</div></div>
          </div>
          {barra_progresso(_pct_renda, None, 12)}
          <div class="meter-f"><span><b>{min(_pct_renda, 999):.0f}%</b> da meta</span><span>Faltam <b>{fmt_moeda(max(0.0, meta_r - _media12))}</b> por mês</span></div>
        </div>
        """)
        md("<div class='insight'><div>A renda passiva é calculada com os proventos marcados como <b>recebidos</b> na aba Dividendos.</div></div>")

# ==============================================================================
# ROTAS: nome do menu -> função da página
# ==============================================================================
PAGINAS = {
    "Visão Geral": pagina_visao_geral,
    "Resumo": pagina_resumo_diagnostico,
    "Contas Fixas": pagina_contas_fixas,
    "Minha Carteira": pagina_carteira,
    "Dividendos": pagina_dividendos,
    "Cartão de Crédito": pagina_cartao,
    "Movimentações": pagina_conta_debito,
    "Devedores": pagina_devedores,
    "Metas": pagina_metas,
}
PAGINAS[menu]()

# ==============================================================================
# RODAPÉ INSTITUCIONAL
# ==============================================================================
md(f"<div class='app-footer'>{APP_NOME} · {APP_SLOGAN}</div>")