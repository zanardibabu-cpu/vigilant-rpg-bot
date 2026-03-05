import os
import time
import json
import math
import random
import aiosqlite
import discord
from discord import app_commands
from typing import Optional, List, Dict, Any, Tuple

# CONFIG / IDs
# ==========================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("❌ TOKEN não encontrado. Defina a variável de ambiente TOKEN no Railway e redeploy.")


MESTRE_ID = 1255256495369748573  # Cannabinoide

# Canais (IDs fornecidos por você)
CANAL_BEM_VINDO_ID = 1472100698211483679
CANAL_COMANDOS_ID  = 1472216958647795965
CANAL_LOJA_ID      = 1472100628355350633
CANAL_MESTRE_ID    = 1472274401289310248
CANAL_CACAR_ID     = 1472365134801276998
CANAL_TAVERNA_ID   = 0

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / "vigilant_rpg.sqlite")

# Gameplay
STAMINA_MAX = 100
STAMINA_CUSTO_CACAR = 12
CACAR_COOLDOWN_S = 35
DESCANSO_HORAS = 12
ALBERGUE_MAX_CUSTO = 50

# XP
XP_BASE = 100
XP_MULT = 1.20  # +20% por nível

# Loja UI
ITEMS_PER_PAGE = 6

def build_shop_embed(loja: str, page: int, itens: List[Dict[str, Any]]) -> discord.Embed:
    total = len(itens)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    chunk = itens[start:end]

    titulos = {
        "mercador": "🏪 Terminal de Suprimentos — MERCADOR",
        "ferreiro": "⚒️ Forja dos Ermos — FERREIRO",
        "alfaiate": "🧵 Atelier das Ruínas — ALFAIATE",
        "arcano": "🔮 Escola Arcana — ARCANOS",
        "igreja": "⛪ Santuário — IGREJA",
    }

    embed = discord.Embed(
        title=f"{titulos.get(loja, loja.upper())} (itens ativos)",
        description=(
            "Use **/comprar item_id** para comprar.\n"
            "Use **/vender item_id** para vender (**60%**).\n"
            "Use **/equipar** e **/desequipar**.\n"
        ),
        color=discord.Color.green()
    )

    for it in chunk:
        item_id = it["item_id"]
        preco = int(it.get("preco", 0))
        tipo = it.get("tipo", "—")
        desc = (it.get("desc", "") or "").strip()

        if tipo == "consumivel":
            eff = it.get("efeito", {})
            eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
            val = f"💰 **{preco}** | 🧪 {eff_txt}"
        else:
            bonus = it.get("bonus", {})
            btxt = ", ".join([f"{k.upper()}+{v}" for k, v in bonus.items()]) if bonus else "—"
            val = f"💰 **{preco}** | ⚙️ **{tipo}** | {btxt}"

        if desc:
            desc = desc[:90] + ("…" if len(desc) > 90 else "")
            val += f"\n_{desc}_"

        embed.add_field(name=f"**{it.get('nome','Item')}** (`{item_id}`)", value=val, inline=False)

    embed.set_footer(text=f"Loja: {loja} • Página {page+1}/{total_pages} • Itens {start+1}-{min(end,total)} de {total}")
    return embed


class ShopView(discord.ui.View):
    def __init__(self, user_id: int, loja: str, itens: List[Dict[str, Any]], page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.loja = loja
        self.itens = itens
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)


# Livro de magias
SPELLBOOK_SLOTS = 7

# ==============================
# LORE / FALAS
# ==============================

VIGILLANT_QUOTES = [
    "A humanidade é um erro estatístico. Eu vim corrigir.",
    "Eu observo cada movimento seu. Não há onde se esconder.",
    "A Diretriz não falha.",
    "Sua esperança é só ruído no sistema.",
    "Resistir é uma variável… e eu removo variáveis."
]

MOB_QUOTES = {
    "orgânico": [
        "Um uivo distante ecoa entre os destroços…",
        "O ar fede a ferrugem e carne podre.",
        "Algo vivo… mas errado… se arrasta na escuridão."
    ],
    "cibernético": [
        "Um zumbido mecânico corta o silêncio.",
        "Luzes frias varrem o terreno. Você foi detectado.",
        "Sinais da Diretriz… rastreando sua assinatura térmica."
    ],
    "demoníaco": [
        "O chão parece respirar. O ar fica quente demais.",
        "Uma presença antiga ri dentro da sua mente.",
        "O mundo perde cor. Algo do outro lado atravessou."
    ]
}

# ==============================
# DADOS DO RPG
# ==============================

CLASSES: Dict[str, Dict[str, int]] = {
    "clerigo":   {"hp_base": 55, "mana_base": 40, "atk": 2,  "magia": 8,  "defesa": 5, "sorte": 3, "furtividade": 1, "destreza": 2},
    "barbaro":   {"hp_base": 70, "mana_base": 0,  "atk": 10, "magia": 0,  "defesa": 6, "sorte": 2, "furtividade": 1, "destreza": 3},
    "arqueiro":  {"hp_base": 40, "mana_base": 15, "atk": 8,  "magia": 2,  "defesa": 3, "sorte": 4, "furtividade": 5, "destreza": 8},
    "mago":      {"hp_base": 35, "mana_base": 60, "atk": 1,  "magia": 12, "defesa": 2, "sorte": 3, "furtividade": 2, "destreza": 3},
    "assassino": {"hp_base": 35, "mana_base": 10, "atk": 9,  "magia": 3,  "defesa": 3, "sorte": 5, "furtividade": 8, "destreza": 7},
    "guerreiro": {"hp_base": 46, "mana_base": 2,  "atk": 12, "magia": 3,  "defesa": 6, "sorte": 5, "furtividade": 1, "destreza": 7},
}

# +1 automático por classe (stamina nunca)
AUTO_UP: Dict[str, str] = {
    "barbaro": "atk",
    "guerreiro": "atk",
    "assassino": "destreza",
    "arqueiro": "destreza",
    "mago": "magia",
    "clerigo": "magia",
}

# Monstros ponderados (fortes = raros)
MONSTROS = {
    "rato_irradiado":      {"nome": "Rato Irradiado",            "hp": 5,  "atk": 5,  "xp": 12,  "gold": 14,  "peso": 26, "tags": ["orgânico", "radiação"]},
    "lobo_mutante":        {"nome": "Lobo Mutante",              "hp": 6,  "atk": 7,  "xp": 18,  "gold": 22,  "peso": 22, "tags": ["orgânico"]},
    "carnical_radioativo": {"nome": "Carniçal Radioativo",       "hp": 6,  "atk": 9,  "xp": 26,  "gold": 32,  "peso": 18, "tags": ["orgânico", "radiação"]},
    "drone_vigia":         {"nome": "Drone Vigia da Diretriz",   "hp": 11,  "atk": 12, "xp": 45,  "gold": 60,  "peso": 12, "tags": ["cibernético", "diretriz"]},
    "vampiro_errante":     {"nome": "Vampiro Errante",           "hp": 14,  "atk": 16, "xp": 90,  "gold": 130, "peso": 6,  "tags": ["orgânico", "vampiro"]},
    "demonio_invadido":    {"nome": "Demônio Invadido",          "hp": 95,  "atk": 20, "xp": 140, "gold": 200, "peso": 4,  "tags": ["demoníaco"]},
    "ciborgue_diretriz":   {"nome": "Ciborgue da Mente-Colmeia", "hp": 30, "atk": 24, "xp": 190, "gold": 260, "peso": 3,  "tags": ["cibernético", "diretriz"]},
    "sentinela_antigo":    {"nome": "Sentinela Antigo",          "hp": 40, "atk": 30, "xp": 280, "gold": 360, "peso": 2,  "tags": ["cibernético", "antigo"]},
    "executor_vigillant":  {"nome": "Executor de VIGILLANT",     "hp": 45, "atk": 38, "xp": 450, "gold": 600, "peso": 1,  "tags": ["cibernético", "diretriz", "boss"]},
}
# ==============================
# CONFIG DE PROBABILIDADES
# ==============================

INIMIGOS_FRACOS_CHANCE = 0.38
DROP_FRACO_CHANCE = 0.04
DROP_RARO_CHANCE = 0.35

# ==============================
# INIMIGOS FRACOS (sempre morrem)
# ==============================

INIMIGOS_FRACOS = [
    {"nome": "Cachorro Magro",   "xp": (2, 6),  "gold": (1, 6),  "tags": ["orgânico"]},
    {"nome": "Rato de Esgoto",   "xp": (1, 5),  "gold": (0, 4),  "tags": ["orgânico"]},
    {"nome": "Drone Defeituoso", "xp": (3, 8),  "gold": (1, 8),  "tags": ["cibernético", "diretriz"]},
    {"nome": "Ladrão Maneta",    "xp": (4, 10), "gold": (2, 12), "tags": ["orgânico"]},
    {"nome": "Mendigo Ousado",   "xp": (2, 7),  "gold": (0, 5),  "tags": ["orgânico"]},
]

# ==============================
# POOLS DE DROP (só itens ATIVOS)
# ==============================
DROP_POOL_FRACO = [
    "pocao_vida",
    "pocao_mana",
    "anel_caveira_rato",
]

DROP_POOL_RARO = [
    "katana",
    "manto_negro_deus_cabra",
    "anel_pristino",
    "arco_longo_norte",
    "manoplas_aco_polido",
]
# ==============================
# NARRAÇÃO / COMBATE
# ==============================

# Narração ON = considerado "combate/narração ativa" para travar troca do livro de magias
NARRACAO_GUILD: Dict[int, bool] = {}

# ==============================
# SEED: ITENS INICIAIS (só para primeira execução)
# Depois você cria/edita tudo pelo Discord
# ==============================

INITIAL_ITEMS = {
    "pocao_vida": {
        "nome": "Poção de Vida",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 HP."
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 Mana."
    },
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1900,
        "tipo": "especial",
        "slot": "especial",
        "efeito": {"hack_stun_turns": 2},
        "bonus": {},
        "classes": ["mago", "clerigo"],
        "desc": "Narrativa: hack desativa cibernéticos por 2 turnos."
    },

    "anel_do_vigor": {
        "nome": "Anel do Vigor",
        "tipo": "anel",
        "slot": "anel",
        "preco": 520,
        "bonus": {"atk": 1},
        "desc": "Um anel simples que fortalece o corpo do portador."
    },

    "anel_da_guarda": {
        "nome": "Anel da Guarda",
        "tipo": "anel",
        "slot": "anel",
        "preco": 560,
        "bonus": {"defesa": 1},
        "desc": "Gravado com runas antigas de proteção."
    },

    "anel_da_sabedoria": {
        "nome": "Anel da Sabedoria",
        "tipo": "anel",
        "slot": "anel",
        "preco": 620,
        "bonus": {"magia": 1},
        "desc": "Um cristal antigo amplifica o poder arcano."
    },

    "anel_da_sombra": {
        "nome": "Anel da Sombra",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"furtividade": 1},
        "desc": "Usado por ladrões e exploradores das ruínas."
    },

    "anel_da_agilidade": {
        "nome": "Anel da Agilidade",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"destreza": 1},
        "desc": "Leve como o vento, acelera os reflexos."
    },

    "anel_da_sorte_antiga": {
        "nome": "Anel da Sorte Antiga",
        "tipo": "anel",
        "slot": "anel",
        "preco": 650,
        "bonus": {"sorte": 1},
        "desc": "Relíquia de um cassino pré-guerra."
    },

    "anel_de_aco_negro": {
        "nome": "Anel de Aço Negro",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1050,
        "bonus": {"defesa": 2},
        "desc": "Forjado nas fornalhas de um ferreiro antigo."
    },

    "anel_arcano": {
        "nome": "Anel Arcano",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1200,
        "bonus": {"magia": 2},
        "desc": "Amplifica feitiços de magos experientes."
    },

    "anel_do_cacador": {
        "nome": "Anel do Caçador",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1150,
        "bonus": {"atk": 2},
        "desc": "Preferido pelos caçadores das zonas irradiadas."
    },

    "anel_da_luz_sagrada": {
        "nome": "Anel da Luz Sagrada",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1350,
        "bonus": {"magia": 2},
        "desc": "Relíquia usada por clérigos nas antigas catedrais."
    },
}

INITIAL_SHOP_ACTIVE = [
    ("pocao_vida", None, None),
    ("pocao_mana", None, None),
    ("tablet_hacker", None, None),
]

# ==============================
# FEITIÇOS / ESCOLA (DB)
# ==============================

ESCOLAS_SPELL = {"arcano", "igreja"}

SPELLS_PER_PAGE = 7

INITIAL_SPELLS: Dict[str, Dict[str, Any]] = {
    # ====== ARCANO (mago) ======
    "misseis_sucata": {
        "nome": "Mísseis de Sucata",
        "custo_mana": 6,
        "preco": 420,
        "escola": "arcano",
        "efeito_tipo": "dano",
        "efeito_valor": 12,
        "tags": ["arcano", "metal"],
        "classes": ["mago"],
        "desc": "Projéteis improvisados de metal e energia. Dano moderado."
    },
    "pulso_ionico": {
        "nome": "Pulso Iônico",
        "custo_mana": 8,
        "preco": 520,
        "escola": "arcano",
        "efeito_tipo": "util",
        "efeito_valor": 2,
        "tags": ["cibernético", "diretriz"],
        "classes": ["mago"],
        "desc": "Narrativa: interfere em sistemas cibernéticos por 2 turnos (stun/lock)."
    },
    "barreira_fractal": {
        "nome": "Barreira Fractal",
        "custo_mana": 7,
        "preco": 480,
        "escola": "arcano",
        "efeito_tipo": "buff",
        "efeito_valor": 2,
        "tags": ["defesa", "arcano"],
        "classes": ["mago"],
        "desc": "Conjura proteção: +2 DEF (interpretação via total_stat/efeitos)."
    },

    # ====== IGREJA (clérigo) ======
    "benção_do_aço": {
        "nome": "Bênção do Aço",
        "custo_mana": 6,
        "preco": 430,
        "escola": "igreja",
        "efeito_tipo": "buff",
        "efeito_valor": 2,
        "tags": ["sagrado", "defesa"],
        "classes": ["clerigo"],
        "desc": "Benção protetora: +2 DEF (interpretação via efeitos)."
    },
    "cura_de_campo": {
        "nome": "Cura de Campo",
        "custo_mana": 8,
        "preco": 560,
        "escola": "igreja",
        "efeito_tipo": "cura",
        "efeito_valor": 14,
        "tags": ["sagrado", "cura"],
        "classes": ["clerigo"],
        "desc": "Recupera 14 HP (cura direta)."
    },
    "exorcismo_ruidoso": {
        "nome": "Exorcismo Ruidoso",
        "custo_mana": 10,
        "preco": 720,
        "escola": "igreja",
        "efeito_tipo": "dano",
        "efeito_valor": 16,
        "tags": ["sagrado", "demoníaco"],
        "classes": ["clerigo"],
        "desc": "Dano elevado contra entidades demoníacas (interpretação por tags)."
    },
}

INITIAL_SPELLS_ACTIVE = [
    "misseis_sucata", "barreira_fractal",
    "cura_de_campo", "benção_do_aço"
]


async def spell_upsert(spell_id: str, s: Dict[str, Any]):
    spell_id = spell_id.lower().strip()
    escola = (s.get("escola") or "arcano").lower().strip()
    if escola not in ESCOLAS_SPELL:
        escola = "arcano"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO spells(spell_id, nome, custo_mana, preco, escola, efeito_tipo, efeito_valor, tags_json, classes_json, desc, ativo, deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        ON CONFLICT(spell_id) DO UPDATE SET
            nome=excluded.nome,
            custo_mana=excluded.custo_mana,
            preco=excluded.preco,
            escola=excluded.escola,
            efeito_tipo=excluded.efeito_tipo,
            efeito_valor=excluded.efeito_valor,
            tags_json=excluded.tags_json,
            classes_json=excluded.classes_json,
            desc=excluded.desc
        """, (
            spell_id,
            s.get("nome", spell_id),
            int(s.get("custo_mana", 0)),
            int(s.get("preco", 0)),
            escola,
            s.get("efeito_tipo", "util"),
            int(s.get("efeito_valor", 0)),
            json.dumps(s.get("tags", []), ensure_ascii=False),
            json.dumps(s.get("classes", []), ensure_ascii=False),
            s.get("desc", "")
        ))
        await db.commit()


async def spell_set_active(spell_id: str, ativo: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE spells SET ativo=? WHERE spell_id=? AND deleted=0", (1 if ativo else 0, spell_id.lower().strip()))
        await db.commit()


async def spell_get(spell_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE spell_id=?", (spell_id.lower().strip(),))
        row = await cur.fetchone()
        if not row:
            return None
        s = dict(row)
        s["tags"] = json.loads(s.get("tags_json") or "[]")
        s["classes"] = json.loads(s.get("classes_json") or "[]")
        return s


async def spell_list_active(escola: str, classe: Optional[str] = None) -> List[Dict[str, Any]]:
    escola = (escola or "arcano").lower().strip()
    if escola not in ESCOLAS_SPELL:
        escola = "arcano"

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM spells
            WHERE escola=? AND ativo=1 AND deleted=0
            ORDER BY preco ASC, nome ASC
        """, (escola,))
        rows = await cur.fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        s = dict(r)
        s["tags"] = json.loads(s.get("tags_json") or "[]")
        s["classes"] = json.loads(s.get("classes_json") or "[]")
        if classe and classe not in s["classes"]:
            continue
        out.append(s)
    return out


async def seed_initial_spells():
    for sid, s in INITIAL_SPELLS.items():
        await spell_upsert(sid, s)
    for sid in INITIAL_SPELLS_ACTIVE:
        await spell_set_active(sid, True)


def build_spellshop_embed(escola: str, page: int, spells: List[Dict[str, Any]]) -> discord.Embed:
    total = len(spells)
    total_pages = max(1, (total + SPELLS_PER_PAGE - 1) // SPELLS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * SPELLS_PER_PAGE
    end = start + SPELLS_PER_PAGE
    chunk = spells[start:end]

    titulo = "🔮 Escola Arcana — FEITIÇOS (ativos)" if escola == "arcano" else "⛪ Igreja — LITURGIAS (ativas)"

    embed = discord.Embed(
        title=titulo,
        description=(
            "Use **/aprender spell_id** para comprar e aprender.\n"
            "Depois equipe com **/livro_equipar spell_id** (fora de narração).\n"
        ),
        color=discord.Color.purple()
    )

    for s in chunk:
        sid = s["spell_id"]
        preco = int(s["preco"])
        mana = int(s["custo_mana"])
        et = s.get("efeito_tipo", "util")
        ev = int(s.get("efeito_valor", 0))
        classes = ", ".join(s.get("classes", [])) or "—"
        desc = (s.get("desc") or "").strip()
        if desc:
            desc = desc[:90] + ("…" if len(desc) > 90 else "")

        embed.add_field(
            name=f"**{s['nome']}** (`{sid}`)",
            value=(
                f"💰 **{preco}** | 🔵 Mana **{mana}**\n"
                f"✨ {et.upper()} {ev} | 🎭 {classes}\n"
                f"_{desc}_" if desc else f"✨ {et.upper()} {ev} | 🎭 {classes}"
            ),
            inline=False
        )

    embed.set_footer(text=f"Escola: {escola} • Página {page+1}/{total_pages} • Feitiços {start+1}-{min(end,total)} de {total}")
    return embed


class SpellShopView(discord.ui.View):
    def __init__(self, user_id: int, escola: str, spells: List[Dict[str, Any]], page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.escola = escola
        self.spells = spells
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=build_spellshop_embed(self.escola, self.page, self.spells), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=build_spellshop_embed(self.escola, self.page, self.spells), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Escola fechada.", embed=None, view=None)
# ==============================
# UTIL / CHECKS
# ==============================

def normalize_item_list(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",")]
    return [p for p in parts if p]

def now_ts() -> int:
    return int(time.time())

def eh_mestre(user_id: int) -> bool:
    return user_id == MESTRE_ID

def rolar_d20() -> int:
    return random.randint(1, 20)

def xp_para_upar(level: int) -> int:
    return int(round(XP_BASE * (XP_MULT ** (level - 1))))

def clamp(n, a, b):
    return max(a, min(b, n))

def only_channel(channel_id: int, friendly: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if channel_id == 0:
            return True
        if interaction.channel_id != channel_id:
            msg = f"❌ Este comando só pode ser usado em **#{friendly}**."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

def only_master_channel():

    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user:
            return False
        return interaction.user.id == MESTRE_ID

    return app_commands.check(predicate)

async def blocked_by_rest(interaction: discord.Interaction, p: dict) -> bool:
    if now_ts() < int(p.get("rest_until_ts", 0)):
        falta = int(p["rest_until_ts"]) - now_ts()
        horas = max(1, (falta + 3599) // 3600)
        msg = f"⛺ Você está **descansando**. Volte em ~**{horas}h**."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return True
    return False

async def blocked_by_narration(interaction: discord.Interaction) -> bool:
    if interaction.guild and NARRACAO_GUILD.get(interaction.guild.id, False):
        msg = "📖 **Modo Narração ATIVO.** Caça automática está pausada (mestre controla)."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return True
    return False

def narration_is_on(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    return bool(NARRACAO_GUILD.get(interaction.guild.id, False))

def jload(s: Optional[str], default):
    try:
        if not s:
            return default
        return json.loads(s)
    except Exception:
        return default

def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)

def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"id_{random.randint(1000, 9999)}"

def parse_kv_list(text: str) -> Dict[str, Any]:
    """
    "atk=2,defesa=-1,magia=3" -> {"atk":2,"defesa":-1,"magia":3}
    """
    out: Dict[str, Any] = {}
    text = (text or "").strip()
    if not text:
        return out
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k:
            continue
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out

def parse_classes(text: str) -> List[str]:
    if not text:
        return []
    return [c.strip().lower() for c in text.split(",") if c.strip()]

def can_use_spellbook(classe: str) -> bool:
    return classe in ("mago", "clerigo")

# ==============================
# PROGRESSÃO — HP e Mana automáticos, até nível 100
# - 1–20: +1 (HP para todos; Mana para classes com mana > 0)
# - Depois: por faixas, igual HP (mesma estrutura), mas valores por classe
# ==============================

def hp_gain(classe: str, new_level: int) -> int:
    if new_level <= 20:
        return 1

    if classe == "barbaro":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 4
        return 5

    if classe == "guerreiro":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 3
        return 4

    if classe in ("arqueiro", "assassino", "clerigo"):
        if new_level <= 40: return 1
        if new_level <= 60: return 2
        if new_level <= 80: return 3
        return 3

    # mago
    if new_level <= 40: return 1
    if new_level <= 60: return 2
    if new_level <= 80: return 2
    return 3

def mana_gain(classe: str, new_level: int) -> int:
    # sem mana
    if classe == "barbaro":
        return 0

    # 1–20: +1 para classes que têm mana
    if new_level <= 20:
        return 1

    # mesma estrutura de faixas do HP, mas com “perfil” de mana
    if classe == "mago":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 3
        return 4

    if classe == "clerigo":
        if new_level <= 40: return 1
        if new_level <= 60: return 2
        if new_level <= 80: return 2
        return 3

    # classes com mana baixa
    if new_level <= 40: return 1
    if new_level <= 60: return 1
    if new_level <= 80: return 2
    return 2

# ==============================
# BANCO DE DADOS
# ==============================

async def pick_drop_from_pool(pool: List[str]) -> Optional[Dict[str, Any]]:
    """
    Retorna um item aleatório DO POOL, mas apenas se estiver ATIVO na loja.
    Ajuste os nomes das tabelas/colunas se no seu DB forem diferentes.
    """
    if not pool:
        return None

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Tenta algumas vezes para achar um item válido/ativo
        for _ in range(12):
            drop_id = random.choice(pool)

            # ✅ AJUSTE AQUI se seu schema for diferente:
            # - items(item_id, nome, ...)
            # - shop_items(item_id, ativo)
            cur = await db.execute("""
                SELECT i.item_id, i.nome
                FROM items i
                JOIN shop_items s ON s.item_id = i.item_id
                WHERE i.item_id = ? AND s.ativo = 1
                LIMIT 1
            """, (drop_id,))
            row = await cur.fetchone()
            if row:
                return dict(row)

    return None

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # items catalog
        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            slot TEXT NOT NULL,
            preco INTEGER NOT NULL,
            bonus_json TEXT NOT NULL,
            efeito_json TEXT NOT NULL,
            classes_json TEXT NOT NULL,
            desc TEXT NOT NULL,
            loja TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_loja_ativo ON items(loja, ativo, deleted)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_tipo ON items(tipo, deleted)")

        # shop
        await db.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            item_id TEXT PRIMARY KEY,
            preco INTEGER,
            estoque INTEGER,
            ativo INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """)

        # master chest
        await db.execute("""
        CREATE TABLE IF NOT EXISTS master_chest (
            item_id TEXT PRIMARY KEY,
            qtd INTEGER NOT NULL,
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """)

        # spells catalog
        await db.execute("""
        CREATE TABLE IF NOT EXISTS spells (
            spell_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            custo_mana INTEGER NOT NULL,
            preco INTEGER NOT NULL,
            escola TEXT NOT NULL,              -- "arcano" ou "igreja"
            efeito_tipo TEXT NOT NULL,         -- "dano", "cura", "buff", "util"
            efeito_valor INTEGER NOT NULL,     -- número (ex: 12)
            tags_json TEXT NOT NULL,           -- ["cibernetico","radiação"...]
            classes_json TEXT NOT NULL,        -- ["mago"] etc
            desc TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_spells_escola_ativo ON spells(escola, ativo, deleted)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_spells_classes ON spells(deleted)")

        await db.commit()

# ==============================
# LOJAS / CATÁLOGO (DB driven)
# ==============================

LOJAS_VALIDAS = {"mercador", "ferreiro", "alfaiate", "arcano", "igreja"}

# Itens iniciais (catálogo) - você pode editar aqui no código pra ser mais rápido
INITIAL_ITEMS: Dict[str, Dict[str, Any]] = {
    # ===== CONSUMÍVEIS (Mercador) =====
    "pocao_vida": {
        "nome": "Poção de Vida",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 HP.",
        "loja": "mercador",
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 Mana.",
        "loja": "mercador",
    },

    # ===== ESPECIAIS (Mercador) =====
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1900,
        "tipo": "especial",
        "slot": "especial",
        "efeito": {"hack_stun_turns": 2},
        "bonus": {},
        "classes": ["mago", "clerigo"],
        "desc": "Narrativa: hack desativa cibernéticos por 2 turnos.",
        "loja": "mercador",
    },

    # ===== ANÉIS (Ferreiro) =====
    "anel_do_vigor": {
        "nome": "Anel do Vigor",
        "tipo": "anel",
        "slot": "anel",
        "preco": 520,
        "bonus": {"atk": 1},
        "efeito": {},
        "classes": [],
        "desc": "Um anel simples que fortalece o corpo do portador.",
        "loja": "ferreiro",
    },
    "anel_da_guarda": {
        "nome": "Anel da Guarda",
        "tipo": "anel",
        "slot": "anel",
        "preco": 560,
        "bonus": {"defesa": 1},
        "efeito": {},
        "classes": [],
        "desc": "Gravado com runas antigas de proteção.",
        "loja": "ferreiro",
    },
    "anel_da_sabedoria": {
        "nome": "Anel da Sabedoria",
        "tipo": "anel",
        "slot": "anel",
        "preco": 620,
        "bonus": {"magia": 1},
        "efeito": {},
        "classes": [],
        "desc": "Um cristal antigo amplifica o poder arcano.",
        "loja": "arcano",
    },
    "anel_da_sombra": {
        "nome": "Anel da Sombra",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"furtividade": 1},
        "efeito": {},
        "classes": [],
        "desc": "Usado por ladrões e exploradores das ruínas.",
        "loja": "ferreiro",
    },
    "anel_da_agilidade": {
        "nome": "Anel da Agilidade",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"destreza": 1},
        "efeito": {},
        "classes": [],
        "desc": "Leve como o vento, acelera os reflexos.",
        "loja": "alfaiate",
    },
    "anel_da_sorte_antiga": {
        "nome": "Anel da Sorte Antiga",
        "tipo": "anel",
        "slot": "anel",
        "preco": 650,
        "bonus": {"sorte": 1},
        "efeito": {},
        "classes": [],
        "desc": "Relíquia de um cassino pré-guerra.",
        "loja": "mercador",
    },
    "anel_de_aco_negro": {
        "nome": "Anel de Aço Negro",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1050,
        "bonus": {"defesa": 2},
        "efeito": {},
        "classes": [],
        "desc": "Forjado nas fornalhas de um ferreiro antigo.",
        "loja": "ferreiro",
    },
    "anel_arcano": {
        "nome": "Anel Arcano",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1200,
        "bonus": {"magia": 2},
        "efeito": {},
        "classes": ["mago"],
        "desc": "Amplifica feitiços de magos experientes.",
        "loja": "arcano",
    },
    "anel_do_cacador": {
        "nome": "Anel do Caçador",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1150,
        "bonus": {"atk": 2},
        "efeito": {},
        "classes": ["arqueiro", "assassino"],
        "desc": "Preferido pelos caçadores das zonas irradiadas.",
        "loja": "ferreiro",
    },
    "anel_da_luz_sagrada": {
        "nome": "Anel da Luz Sagrada",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1350,
        "bonus": {"magia": 2},
        "efeito": {"cura_bonus": 1},
        "classes": ["clerigo"],
        "desc": "Relíquia usada por clérigos nas antigas catedrais.",
        "loja": "igreja",
    },

    # ===== ITENS ARCANOS (Arcano) =====
    "cajado_serpente": {
        "nome": "Cajado da Serpente",
        "preco": 340,
        "tipo": "cajado",
        "slot": "cajado",
        "bonus": {"magia": 2},
        "efeito": {},
        "classes": ["mago", "clerigo"],
        "desc": "+2 MAGIA.",
        "loja": "arcano",
    },
    "grimorio_fissura": {
        "nome": "Grimório da Fissura",
        "preco": 900,
        "tipo": "livro",
        "slot": "especial",
        "bonus": {"magia": 2},
        "efeito": {"mana": 5},
        "classes": ["mago"],
        "desc": "Um tomo pré-guerra que aumenta o foco arcano. +2 MAGIA, +5 Mana máx (efeito).",
        "loja": "arcano",
    },

    # ===== IGREJA (Igreja) =====
    "sino_do_juizo": {
        "nome": "Sino do Juízo",
        "preco": 850,
        "tipo": "reliquia",
        "slot": "especial",
        "bonus": {"defesa": 1},
        "efeito": {"cura_bonus": 2},
        "classes": ["clerigo"],
        "desc": "Ressoa contra o caos. +2 cura (efeito), +1 DEF.",
        "loja": "igreja",
    },
    "livro_hinos": {
        "nome": "Livro de Hinos",
        "preco": 500,
        "tipo": "livro",
        "slot": "especial",
        "bonus": {"magia": 1},
        "efeito": {"cura_bonus": 1},
        "classes": ["clerigo"],
        "desc": "Cantos antigos amplificam bençãos. +1 MAGIA, +1 cura.",
        "loja": "igreja",
    },
}

# Quais itens começam "ativos" na vitrine (o resto existe, mas fica desativado até você ativar)
INITIAL_ACTIVE_IDS = [
    "pocao_vida", "pocao_mana", "tablet_hacker",
    # Anéis (ativos pra já aparecer)
    "anel_do_vigor", "anel_da_guarda", "anel_da_sabedoria", "anel_da_sorte_antiga",
    # Arcano/Igreja
    "cajado_serpente", "livro_hinos"
]


async def item_upsert(item_id: str, it: Dict[str, Any]):
    loja = (it.get("loja") or "mercador").lower().strip()
    if loja not in LOJAS_VALIDAS:
        loja = "mercador"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO items(item_id, nome, tipo, slot, preco, bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        ON CONFLICT(item_id) DO UPDATE SET
            nome=excluded.nome,
            tipo=excluded.tipo,
            slot=excluded.slot,
            preco=excluded.preco,
            bonus_json=excluded.bonus_json,
            efeito_json=excluded.efeito_json,
            classes_json=excluded.classes_json,
            desc=excluded.desc,
            loja=excluded.loja
        """, (
            item_id,
            it.get("nome", item_id),
            it.get("tipo", "especial"),
            it.get("slot", it.get("tipo", "especial")),
            int(it.get("preco", 0)),
            json.dumps(it.get("bonus", {}), ensure_ascii=False),
            json.dumps(it.get("efeito", {}), ensure_ascii=False),
            json.dumps(it.get("classes", []), ensure_ascii=False),
            it.get("desc", ""),
            loja
        ))
        await db.commit()


async def item_set_active(item_id: str, ativo: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE items SET ativo=? WHERE item_id=? AND deleted=0", (1 if ativo else 0, item_id))
        await db.commit()


async def item_get(item_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM items WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            return None
        it = dict(row)
        it["bonus"] = json.loads(it.get("bonus_json") or "{}")
        it["efeito"] = json.loads(it.get("efeito_json") or "{}")
        it["classes"] = json.loads(it.get("classes_json") or "[]")
        return it


async def items_list_active(loja: str) -> List[Dict[str, Any]]:
    loja = loja.lower().strip()
    if loja not in LOJAS_VALIDAS:
        loja = "mercador"
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM items
            WHERE loja=? AND ativo=1 AND deleted=0
            ORDER BY preco ASC, nome ASC
        """, (loja,))
        rows = await cur.fetchall()
        out = []
        for r in rows:
            it = dict(r)
            it["bonus"] = json.loads(it.get("bonus_json") or "{}")
            it["efeito"] = json.loads(it.get("efeito_json") or "{}")
            it["classes"] = json.loads(it.get("classes_json") or "[]")
            out.append(it)
        return out


async def seed_initial_items():
    # UPSERT em todos os itens iniciais
    for item_id, it in INITIAL_ITEMS.items():
        await item_upsert(item_id, it)

    # ativa os iniciais (sem desativar os seus customizados)
    for iid in INITIAL_ACTIVE_IDS:
        await item_set_active(iid, True)

async def seed_initial_data():
    """
    Insere itens iniciais (se não existirem) e ativa alguns na loja.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        # itens
        for item_id, it in INITIAL_ITEMS.items():
            cur = await db.execute("SELECT 1 FROM items WHERE item_id=?", (item_id,))
            exists = await cur.fetchone()
            if exists:
                continue
            await db.execute("""
                INSERT INTO items (item_id, nome, preco_base, tipo, slot, bonus_json, efeito_json, classes_json, desc, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                item_id,
                it["nome"],
                int(it["preco"]),
                it["tipo"],
                it["slot"],
                jdump(it.get("bonus", {})),
                jdump(it.get("efeito", {})),
                jdump(it.get("classes", [])),
                it.get("desc", "") or ""
            ))

        # ativa loja
        for item_id, preco, estoque in INITIAL_SHOP_ACTIVE:
            cur = await db.execute("SELECT 1 FROM shop_items WHERE item_id=?", (item_id,))
            exists = await cur.fetchone()
            if exists:
                continue
            await db.execute("""
                INSERT INTO shop_items (item_id, preco, estoque, ativo)
                VALUES (?, ?, ?, 1)
            """, (item_id, preco, estoque))

        await db.commit()

# ==============================
# PLAYER CRUD
# ==============================

def ensure_equipado_format(eq: dict) -> dict:
    if not isinstance(eq, dict):
        eq = {}
    # Slots
    eq.setdefault("arma", None)
    eq.setdefault("armadura", None)
    eq.setdefault("elmo", None)
    eq.setdefault("botas", None)
    eq.setdefault("luvas", None)
    eq.setdefault("cajado", None)
    eq.setdefault("especial", None)
    eq.setdefault("implante", None)        # slot novo (mestre-only)
    eq.setdefault("livro_magias", None)    # slot novo (item físico opcional, se quiser)

    aneis = eq.get("aneis", [])
    if not isinstance(aneis, list):
        aneis = []
    while len(aneis) < 8:
        aneis.append(None)
    eq["aneis"] = aneis[:8]
    return eq

async def get_player(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        p = dict(row)
        p["stats"] = jload(p.get("stats_json"), {})
        p["inventario"] = jload(p.get("inventario_json"), [])
        p["equipado"] = ensure_equipado_format(jload(p.get("equipado_json"), {}))
        p["spellbook"] = jload(p.get("spellbook_json"), [])
        return p

async def save_player(p: dict):
    async with aiosqlite.connect(DB_FILE) as db:
        p["equipado"] = ensure_equipado_format(p.get("equipado", {}))
        await db.execute("""
        INSERT INTO players (
            user_id, classe, level, xp, gold, pontos, hp, mana, stamina, max_stamina,
            rest_until_ts, last_hunt_ts, stats_json, inventario_json, equipado_json, spellbook_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            classe=excluded.classe,
            level=excluded.level,
            xp=excluded.xp,
            gold=excluded.gold,
            pontos=excluded.pontos,
            hp=excluded.hp,
            mana=excluded.mana,
            stamina=excluded.stamina,
            max_stamina=excluded.max_stamina,
            rest_until_ts=excluded.rest_until_ts,
            last_hunt_ts=excluded.last_hunt_ts,
            stats_json=excluded.stats_json,
            inventario_json=excluded.inventario_json,
            equipado_json=excluded.equipado_json,
            spellbook_json=excluded.spellbook_json
        """, (
            p["user_id"], p["classe"], int(p["level"]), int(p["xp"]), int(p["gold"]), int(p.get("pontos", 0)),
            int(p["hp"]), int(p["mana"]), int(p["stamina"]), int(p["max_stamina"]),
            int(p.get("rest_until_ts", 0)), int(p.get("last_hunt_ts", 0)),
            jdump(p.get("stats", {})),
            jdump(p.get("inventario", [])),
            jdump(p.get("equipado", {})),
            jdump(p.get("spellbook", [])),
        ))
        await db.commit()

async def require_player(interaction: discord.Interaction):
    p = await get_player(interaction.user.id)
    if not p:
        msg = "⚠️ Você ainda não tem personagem. Use **/start** no canal de bem-vindo."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return None
    return p

# ==============================
# ITENS / LOJA / BAÚ
# ==============================

async def item_get(item_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM items WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            return None
        it = dict(row)
        it["bonus"] = jload(it.get("bonus_json"), {})
        it["efeito"] = jload(it.get("efeito_json"), {})
        it["classes"] = jload(it.get("classes_json"), [])
        return it

async def item_exists_active(item_id: str) -> bool:
    it = await item_get(item_id)
    return bool(it) and int(it.get("deleted", 0)) == 0

async def shop_list_active() -> List[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT i.*, s.preco as preco_loja, s.estoque, s.ativo
            FROM shop_items s
            JOIN items i ON i.item_id = s.item_id
            WHERE s.ativo=1 AND i.deleted=0
            ORDER BY i.nome COLLATE NOCASE
        """)
        rows = await cur.fetchall()
        out = []
        for r in rows:
            it = dict(r)
            it["bonus"] = jload(it.get("bonus_json"), {})
            it["efeito"] = jload(it.get("efeito_json"), {})
            it["classes"] = jload(it.get("classes_json"), [])
            out.append(it)
        return out

def shop_price(it: dict) -> int:
    p = it.get("preco_loja")
    if p is None:
        return int(it.get("preco_base", 0))
    return int(p)

async def shop_is_active(item_id: str) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("""
            SELECT 1
            FROM shop_items s
            JOIN items i ON i.item_id=s.item_id
            WHERE s.item_id=? AND s.ativo=1 AND i.deleted=0
        """, (item_id,))
        return (await cur.fetchone()) is not None

async def shop_decrease_stock(item_id: str, n: int = 1) -> bool:
    """
    estoque NULL = infinito
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT estoque FROM shop_items WHERE item_id=? AND ativo=1", (item_id,))
        row = await cur.fetchone()
        if not row:
            return False
        estoque = row["estoque"]
        if estoque is None:
            return True
        estoque = int(estoque)
        if estoque < n:
            return False
        await db.execute("UPDATE shop_items SET estoque=? WHERE item_id=?", (estoque - n, item_id))
        await db.commit()
        return True

async def master_chest_add(item_id: str, qtd: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT qtd FROM master_chest WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO master_chest (item_id, qtd) VALUES (?, ?)", (item_id, qtd))
        else:
            await db.execute("UPDATE master_chest SET qtd=? WHERE item_id=?", (int(row[0]) + qtd, item_id))
        await db.commit()

async def master_chest_remove(item_id: str, qtd: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT qtd FROM master_chest WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            return False
        have = int(row[0])
        if have < qtd:
            return False
        left = have - qtd
        if left <= 0:
            await db.execute("DELETE FROM master_chest WHERE item_id=?", (item_id,))
        else:
            await db.execute("UPDATE master_chest SET qtd=? WHERE item_id=?", (left, item_id))
        await db.commit()
        return True

async def master_chest_list() -> List[Tuple[str, int]]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT item_id, qtd FROM master_chest ORDER BY item_id")
        return [(r[0], int(r[1])) for r in await cur.fetchall()]

# ==============================
# MAGIAS / LIVRO
# ==============================

async def spell_get(spell_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE spell_id=?", (spell_id,))
        row = await cur.fetchone()
        if not row:
            return None
        s = dict(row)
        s["classes"] = jload(s.get("classes_json"), [])
        return s

async def spell_exists_active(spell_id: str) -> bool:
    s = await spell_get(spell_id)
    return bool(s) and int(s.get("deleted", 0)) == 0

async def spell_list_for_class(classe: str) -> List[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE deleted=0 ORDER BY nome COLLATE NOCASE")
        rows = await cur.fetchall()
        out = []
        for r in rows:
            s = dict(r)
            s["classes"] = jload(s.get("classes_json"), [])
            if classe in s["classes"]:
                out.append(s)
        return out

# ==============================
# STATS + EQUIPAMENTOS (bonus vem dos itens do DB)
# ==============================

def iter_equips(p: dict):
    eq = p.get("equipado") or {}
    for slot in ["arma", "armadura", "elmo", "botas", "luvas", "cajado", "especial", "implante", "livro_magias"]:
        iid = eq.get(slot)
        if iid:
            yield iid
    for iid in eq.get("aneis", []) or []:
        if iid:
            yield iid

async def total_stat(p: dict, stat: str) -> int:
    base = int((p.get("stats") or {}).get(stat, 0))
    for item_id in iter_equips(p):
        it = await item_get(item_id)
        if not it or int(it.get("deleted", 0)) == 1:
            continue
        bonus = it.get("bonus", {}) or {}
        base += int(bonus.get(stat, 0) or 0)
        if stat == "cura":
            efeito = it.get("efeito", {}) or {}
            base += int(efeito.get("cura_bonus", 0) or 0)
    return base

# ==============================
# LEVEL UP (auto em loop)
# ==============================

async def apply_level_up_once(p: dict):
    p["level"] = int(p["level"]) + 1
    new_level = int(p["level"])

    # 3 pontos livres pendentes
    p["pontos"] = int(p.get("pontos", 0)) + 3

    # +1 automático por classe
    auto_attr = AUTO_UP.get(p["classe"])
    if auto_attr:
        p["stats"][auto_attr] = int(p["stats"].get(auto_attr, 0)) + 1

    # HP/Mana automáticos e progressivos
    p["hp"] = int(p["hp"]) + hp_gain(p["classe"], new_level)
    p["mana"] = int(p["mana"]) + mana_gain(p["classe"], new_level)

async def try_auto_level(p: dict) -> int:
    upou = 0
    while True:
        if int(p["level"]) >= 100:
            break
        custo = xp_para_upar(int(p["level"]))
        if int(p["xp"]) < custo:
            break
        p["xp"] -= custo
        await apply_level_up_once(p)
        upou += 1
    if upou:
        await save_player(p)
    return upou

# ==============================
# CRIAÇÃO DE PERSONAGEM
# ==============================

def build_new_player(user_id: int, classe: str) -> dict:
    base = CLASSES[classe].copy()
    return {
        "user_id": user_id,
        "classe": classe,
        "level": 1,
        "xp": 0,
        "gold": 100,
        "pontos": 0,
        "hp": int(base["hp_base"]),
        "mana": int(base["mana_base"]),
        "stamina": STAMINA_MAX,
        "max_stamina": STAMINA_MAX,
        "rest_until_ts": 0,
        "last_hunt_ts": 0,
        "stats": base,
        "inventario": [],
        "equipado": ensure_equipado_format({}),
        "spellbook": [],
    }


class ClasseSelect(discord.ui.Select):
    def __init__(self):
        opts = []
        for cls, st in CLASSES.items():
            opts.append(discord.SelectOption(
                label=cls.capitalize(),
                value=cls,
                description=f"HP {st['hp_base']} | Mana {st['mana_base']} | ATK {st['atk']} | MAG {st['magia']} | DEF {st['defesa']}"
            ))

        super().__init__(
            placeholder="Escolha sua classe…",
            min_values=1,
            max_values=1,
            options=opts,
            custom_id="classe_select_v1"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            if interaction.channel_id != CANAL_BEM_VINDO_ID:
                await interaction.followup.send("❌ Criação de personagem só no canal de **bem-vindo**.", ephemeral=True)
                return

            existing = await get_player(interaction.user.id)
            if existing:
                await interaction.followup.send("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
                return

            classe = self.values[0]
            p = build_new_player(interaction.user.id, classe)
            await save_player(p)

            embed = discord.Embed(
                title="✅ Registro Concluído",
                description=(
                    f"**{interaction.user.mention}** agora é **{classe.upper()}**.\n\n"
                    f"⭐ Nível: **1**\n"
                    f"❤ HP: **{p['hp']}** | 🔵 Mana: **{p['mana']}**\n"
                    f"💰 Gold inicial: **{p['gold']}**"
                ),
                color=discord.Color.dark_grey()
            )

            # remove o menu depois de escolher
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass

            await interaction.followup.send(embed=embed, ephemeral=False)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            await interaction.followup.send("❌ Erro ao registrar. Veja os logs.", ephemeral=True)


class ClasseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClasseSelect())

# ==============================
# LOJA PAGINADA (DB)
# ==============================

async def build_loja_embed(page: int) -> discord.Embed:
    itens = await shop_list_active()
    total = len(itens)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    chunk = itens[start:end]

    embed = discord.Embed(
        title="🏪 Terminal de Suprimentos — LOJA (itens ativos)",
        description=(
            "Use **/comprar item_id** para comprar.\n"
            "Use **/vender item_id** para vender (**60%**).\n"
            "Use **/equipar**, **/desequipar**, **/desequiparanel**, **/usar**.\n"
        ),
        color=discord.Color.green()
    )

    for it in chunk:
        key = it["item_id"]
        preco = shop_price(it)
        tipo = it.get("tipo", "—")
        desc = (it.get("desc", "") or "").strip()
        estoque = it.get("estoque", None)

        if tipo == "consumivel":
            eff = it.get("efeito", {}) or {}
            eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
            val = f"💰 **{preco}** | 🧪 {eff_txt}"
        else:
            bonus = it.get("bonus", {}) or {}
            btxt = ", ".join([f"{k.upper()}+{v}" for k, v in bonus.items()]) if bonus else "—"
            val = f"💰 **{preco}** | ⚙️ **{tipo}** | {btxt}"

        if estoque is not None:
            val += f"\n📦 Estoque: **{int(estoque)}**"

        if desc:
            desc = desc[:80] + ("…" if len(desc) > 80 else "")
            val += f"\n_{desc}_"

        embed.add_field(name=f"**{it.get('nome','Item')}** (`{key}`)", value=val, inline=False)

    embed.set_footer(text=f"Página {page+1}/{total_pages} • Itens {start+1}-{min(end,total)} de {total}")
    return embed

class LojaView(discord.ui.View):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=await build_loja_embed(self.page), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=await build_loja_embed(self.page), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)

# ==============================
# VIEW: BANDIDOS
# ==============================

class BandidosView(discord.ui.View):
    def __init__(self, user_id: int, forca: int):
        super().__init__(timeout=45)
        self.user_id = user_id
        self.forca = forca

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Pagar 100 gold", style=discord.ButtonStyle.secondary, emoji="💰")
    async def pagar(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
            return
        if int(p["gold"]) < 100:
            await interaction.response.send_message("❌ Você não tem 100 gold. Terá que lutar.", ephemeral=True)
            return
        p["gold"] -= 100
        await save_player(p)
        await interaction.response.send_message("💰 Você pagou. Os bandidos foram embora.", ephemeral=False)

    @discord.ui.button(label="Lutar", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def lutar(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
            return

        d20 = rolar_d20()
        dc = 11 + self.forca
        venceu = d20 >= dc

        defesa = await total_stat(p, "defesa")
        dano_recebido = max(4, (12 + self.forca * 3) - defesa)

        if venceu:
            xp = 60 + self.forca * 20
            gold = 120 + self.forca * 40
            p["xp"] += xp
            p["gold"] += gold
            upou = await try_auto_level(p)
            await save_player(p)
            await interaction.response.send_message(
                f"🎲 D20: **{d20}** (DC {dc})\n"
                f"🏆 Você venceu os bandidos!\n"
                f"✨ +{xp} XP | 💰 +{gold} Gold"
                + (f"\n🆙 UPOU {upou} nível(is)!" if upou else ""),
                ephemeral=False
            )
        else:
            p["hp"] = max(0, int(p["hp"]) - dano_recebido)
            await save_player(p)
            await interaction.response.send_message(
                f"🎲 D20: **{d20}** (DC {dc})\n"
                f"💀 Você perdeu a luta.\n"
                f"💥 Dano: **{dano_recebido}**\n"
                f"❤ HP agora: **{p['hp']}**",
                ephemeral=False
            )

