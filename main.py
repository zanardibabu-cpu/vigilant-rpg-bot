import os
import time
import json
import math
import random
import aiosqlite
import discord
from discord import app_commands

# ==============================
# CONFIG / IDs
# ==============================
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)

    raise SystemExit('❌ TOKEN não encontrado. Defina a variável de ambiente TOKEN e reinicie o terminal.')

MESTRE_ID = 1255256495369748573  # Cannabinoide

# Canais (IDs fornecidos por você)
CANAL_BEM_VINDO_ID = 1472100698211483679     # Bem vindo ao grupo
CANAL_COMANDOS_ID  = 1472216958647795965     # comandos dos players
CANAL_LOJA_ID      = 1472100628355350633     # Loja
CANAL_MESTRE_ID    = 1472274401289310248     # Sala do mestre
CANAL_CACAR_ID     = 1472365134801276998     # Sala de caçar
CANAL_TAVERNA_ID   = 0                       # << coloque aqui quando tiver

DB_FILE = "vigillant.db"

# Gameplay
STAMINA_MAX = 100
STAMINA_CUSTO_CACAR = 12
CACAR_COOLDOWN_S = 35
DESCANSO_HORAS = 12
ALBERGUE_MAX_CUSTO = 50

XP_BASE = 100
XP_MULT = 1.20  # +20% por nível

# ==============================
# DISCORD CLIENT
# ==============================
intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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
CLASSES = {
    "clerigo":   {"hp_base": 55, "mana_base": 40, "atk": 2,  "magia": 8,  "defesa": 5, "sorte": 3, "furtividade": 1, "destreza": 2},
    "barbaro":   {"hp_base": 70, "mana_base": 0,  "atk": 10, "magia": 0,  "defesa": 6, "sorte": 2, "furtividade": 1, "destreza": 3},
    "arqueiro":  {"hp_base": 40, "mana_base": 15, "atk": 8,  "magia": 2,  "defesa": 3, "sorte": 4, "furtividade": 5, "destreza": 8},
    "mago":      {"hp_base": 35, "mana_base": 60, "atk": 1,  "magia": 12, "defesa": 2, "sorte": 3, "furtividade": 2, "destreza": 3},
    "assassino": {"hp_base": 35, "mana_base": 10, "atk": 9,  "magia": 3,  "defesa": 3, "sorte": 5, "furtividade": 8, "destreza": 7},
    "guerreiro": {"hp_base": 46, "mana_base": 2, "atk": 12,  "magia": 3,  "defesa": 6, "sorte": 5, "furtividade": 1, "destreza": 7},
}

# Monstros ponderados (fortes = raros)
MONSTROS = {
    "rato_irradiado":      {"nome": "Rato Irradiado",            "hp": 20,  "atk": 5,  "xp": 12,  "gold": 14,  "peso": 26, "tags": ["orgânico", "radiação"]},
    "lobo_mutante":        {"nome": "Lobo Mutante",              "hp": 30,  "atk": 7,  "xp": 18,  "gold": 22,  "peso": 22, "tags": ["orgânico"]},
    "carnical_radioativo": {"nome": "Carniçal Radioativo",       "hp": 38,  "atk": 9,  "xp": 26,  "gold": 32,  "peso": 18, "tags": ["orgânico", "radiação"]},
    "drone_vigia":         {"nome": "Drone Vigia da Diretriz",   "hp": 45,  "atk": 12, "xp": 45,  "gold": 60,  "peso": 12, "tags": ["cibernético", "diretriz"]},
    "vampiro_errante":     {"nome": "Vampiro Errante",           "hp": 70,  "atk": 16, "xp": 90,  "gold": 130, "peso": 6,  "tags": ["orgânico", "vampiro"]},
    "demonio_invadido":    {"nome": "Demônio Invadido",          "hp": 95,  "atk": 20, "xp": 140, "gold": 200, "peso": 4,  "tags": ["demoníaco"]},
    "ciborgue_diretriz":   {"nome": "Ciborgue da Mente-Colmeia", "hp": 120, "atk": 24, "xp": 190, "gold": 260, "peso": 3,  "tags": ["cibernético", "diretriz"]},
    "sentinela_antigo":    {"nome": "Sentinela Antigo",          "hp": 160, "atk": 30, "xp": 280, "gold": 360, "peso": 2,  "tags": ["cibernético", "antigo"]},
    "executor_vigillant":  {"nome": "Executor de VIGILLANT",     "hp": 220, "atk": 38, "xp": 450, "gold": 600, "peso": 1,  "tags": ["cibernético", "diretriz", "boss"]},
}

# ==============================
# LOJA (ITENS) — COMPLETA E SAFE
# ==============================

LOJA = {
    # ===== CONSUMÍVEIS =====
    "pocao_vida": {
        "nome": "Poção de Vida",
        "preco": 20,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "desc": "Recupera 20 HP."
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 20,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "desc": "Recupera 20 Mana."
    },

    # ===== TECH / ESPECIAIS =====
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1200,
        "tipo": "especial",
        "slot": "especial",  # (seu código antigo usa "especial")
        "classes": ["mago", "clerigo"],
        "efeito": {"hack_stun_turns": 2},
        "desc": "Narrativa: hack desativa cibernéticos (não-orgânicos) por 2 turnos."
    },
}

# ==============================
# NOVOS ITENS (NÃO MEXER NO LOJA)
# ==============================
novos_itens = {

    # ===== ARMAS FÍSICAS =====
    "espada_enferrujada": {
        "nome": "Espada Enferrujada",
        "preco": 60,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 1},
        "classes": ["guerreiro", "barbaro", "assassino"],
        "desc": "+1 ATK."
    },
    "machado_cranio": {
        "nome": "Machado de Crânio",
        "preco": 190,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 2},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 ATK."
    },
    "espada_bastarda": {
        "nome": "Espada Bastarda",
        "preco": 220,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 2},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 ATK."
    },
    "katana": {
        "nome": "Katana",
        "preco": 409,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 4, "defesa": -2},
        "classes": ["guerreiro", "assassino"],
        "desc": "+4 ATK, -2 DEF."
    },

    # ===== ARMAS À DISTÂNCIA =====
    "arco_osso": {
        "nome": "Arco de Osso",
        "preco": 120,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 1},
        "classes": ["arqueiro"],
        "desc": "+1 ATK."
    },
    "besta_carbono_composto": {
        "nome": "Besta de Carbono Composto",
        "preco": 650,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 3},
        "classes": ["arqueiro"],
        "desc": "+3 ATK."
    },
    "arco_longo_norte": {
        "nome": "Arco Longo do Norte",
        "preco": 600,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 4},
        "classes": ["arqueiro"],
        "desc": "+4 ATK."
    },
    "arco_vampirico_presa_ancestral": {
        "nome": "Arco Vampírico — Presa Ancestral",
        "preco": 1600,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 5},
        "classes": ["arqueiro", "assassino"],
        "efeito": {"lifesteal_chance": 0.15, "lifesteal_pct": 0.25},
        "desc": "+5 ATK. 15% de chance de roubo de vida (narrativo/automático se você aplicar)."
    },

    # ===== MUNIÇÃO =====
    "flecha_explosiva": {
        "nome": "Flecha Explosiva",
        "preco": 300,
        "tipo": "municao", "slot": "municao",
        "bonus": {"atk": 3},
        "classes": ["arqueiro"],
        "desc": "+3 ATK (munição especial)."
    },

    # ===== CAJADOS (SÓ MAGO/CLÉRIGO) =====
    "cajado_serpente": {
        "nome": "Cajado da Serpente",
        "preco": 260,
        "tipo": "cajado", "slot": "cajado",
        "bonus": {"magia": 2},
        "classes": ["mago", "clerigo"],
        "desc": "+2 MAGIA."
    },
    "cajado_estelar": {
        "nome": "Cajado Estelar",
        "preco": 420,
        "tipo": "cajado", "slot": "cajado",
        "bonus": {"magia": 2, "mana": 1},
        "classes": ["mago", "clerigo"],
        "desc": "+2 MAGIA, +1 MANA máx."
    },

    # ===== LIVROS / RELÍQUIAS (MÁGICOS) =====
    "livro_mantra_monge": {
        "nome": "Livro de Mantra do Monge",
        "preco": 500,
        "tipo": "especial", "slot": "especial",
        "bonus": {"magia": 4},
        "efeito": {"cura_bonus": 2},
        "classes": ["clerigo", "mago"],
        "desc": "+4 MAGIA. Bônus de cura (se você usar cura)."
    },
    "espada_magica": {
        "nome": "Espada Mágica",
        "preco": 300,
        "tipo": "arma", "slot": "arma",
        "bonus": {"atk": 2, "magia": 3},
        "classes": ["guerreiro", "clerigo"],
        "desc": "+2 ATK, +3 MAGIA."
    },

    # ===== ARMADURAS / PEÇAS =====
    "armadura_couro": {
        "nome": "Armadura de Couro",
        "preco": 160,
        "tipo": "armadura", "slot": "armadura",
        "bonus": {"defesa": 1},
        "classes": ["guerreiro", "arqueiro", "assassino", "clerigo"],
        "desc": "+1 DEF."
    },
    "armadura_ferro": {
        "nome": "Armadura de Ferro",
        "preco": 260,
        "tipo": "armadura", "slot": "armadura",
        "bonus": {"defesa": 2, "hp": 3},
        "classes": ["guerreiro", "barbaro", "clerigo"],
        "desc": "+2 DEF, +3 HP máx."
    },
    "manto_negro_deus_cabra": {
        "nome": "Manto Negro do Deus Cabra 🐐",
        "preco": 880,
        "tipo": "armadura", "slot": "armadura",
        "bonus": {"magia": 2, "defesa": 2},
        "classes": ["mago", "clerigo", "assassino"],
        "desc": "+2 MAGIA, +2 DEF."
    },
    "manto_divino": {
        "nome": "Manto Divino",
        "preco": 777,
        "tipo": "armadura", "slot": "armadura",
        "bonus": {"defesa": 4, "magia": 2, "atk": 1},
        "classes": ["clerigo"],
        "desc": "+4 DEF, +2 MAGIA, +1 ATK."
    },

    # ===== ELMOS / CAPUZ =====
    "capuz_anciao": {
        "nome": "Capuz Ancião",
        "preco": 240,
        "tipo": "elmo", "slot": "elmo",
        "bonus": {"defesa": 1, "magia": 1},
        "classes": ["mago", "clerigo"],
        "desc": "+1 DEF, +1 MAGIA."
    },
    "elmo_chifres_norte": {
        "nome": "Elmo com Chifres do Norte",
        "preco": 300,
        "tipo": "elmo", "slot": "elmo",
        "bonus": {"defesa": 2},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 DEF."
    },

    # ===== BOTAS =====
    "botas_couro": {
        "nome": "Botas de Couro",
        "preco": 100,
        "tipo": "botas", "slot": "botas",
        "bonus": {"defesa": 1},
        "classes": ["guerreiro", "arqueiro", "assassino", "clerigo"],
        "desc": "+1 DEF."
    },
    "botas_enferrujadas": {
        "nome": "Botas Enferrujadas",
        "preco": 160,
        "tipo": "botas", "slot": "botas",
        "bonus": {"defesa": 2},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 DEF."
    },
    "botas_bruxo": {
        "nome": "Botas de Bruxo",
        "preco": 350,
        "tipo": "botas", "slot": "botas",
        "bonus": {"magia": 2, "defesa": 1},
        "classes": ["mago", "clerigo"],
        "desc": "+2 MAGIA, +1 DEF."
    },
    "botas_aco_nobre": {
        "nome": "Botas de Aço Nobre",
        "preco": 520,
        "tipo": "botas", "slot": "botas",
        "bonus": {"defesa": 3},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+3 DEF."
    },
    "botas_norte": {
        "nome": "Botas do Norte",
        "preco": 420,
        "tipo": "botas", "slot": "botas",
        "bonus": {"defesa": 2, "hp": 1},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 DEF, +1 HP máx."
    },

    # ===== LUVAS / MANOPLAS =====
    "manoplas_couro": {
        "nome": "Manoplas de Couro",
        "preco": 100,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"defesa": 1},
        "classes": ["guerreiro", "arqueiro", "assassino", "clerigo"],
        "desc": "+1 DEF."
    },
    "manoplas_ferro_enferrujado": {
        "nome": "Manoplas de Ferro Enferrujado",
        "preco": 180,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"defesa": 2},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+2 DEF."
    },
    "manoplas_aco_polido": {
        "nome": "Manoplas de Aço Polido",
        "preco": 360,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"defesa": 3},
        "classes": ["guerreiro", "barbaro"],
        "desc": "+3 DEF."
    },
    "manoplas_mago_caos": {
        "nome": "Manoplas do Mago do Caos",
        "preco": 420,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"magia": 2},
        "classes": ["mago"],
        "desc": "+2 MAGIA."
    },
    "manoplas_clerigo": {
        "nome": "Manoplas do Clérigo",
        "preco": 340,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"hp": 2, "magia": 1},
        "classes": ["clerigo"],
        "desc": "+2 HP máx, +1 MAGIA."
    },
    "manipulas_nobre": {
        "nome": "Manípulas do Nobre",
        "preco": 500,
        "tipo": "luvas", "slot": "luvas",
        "bonus": {"defesa": 3},
        "classes": ["guerreiro", "clerigo"],
        "desc": "+3 DEF."
    },

    # ===== ANÉIS (EQUIPA ATÉ 8) =====
    "anel_vermelho": {
        "nome": "Anel Vermelho",
        "preco": 260,
        "tipo": "anel", "slot": "anel",
        "bonus": {"hp": 7},
        "desc": "+7 HP máx."
    },
    "anel_azul": {
        "nome": "Anel Azul",
        "preco": 260,
        "tipo": "anel", "slot": "anel",
        "bonus": {"mana": 7},
        "desc": "+7 Mana máx."
    },
    "anel_verde": {
        "nome": "Anel Verde",
        "preco": 260,
        "tipo": "anel", "slot": "anel",
        "bonus": {"stamina": 7},
        "desc": "+7 Stamina máx."
    },
    "anel_negro": {
        "nome": "Anel Negro",
        "preco": 340,
        "tipo": "anel", "slot": "anel",
        "bonus": {"magia": 2},
        "desc": "+2 MAGIA."
    },
    "anel_branco": {
        "nome": "Anel Branco",
        "preco": 360,
        "tipo": "anel", "slot": "anel",
        "efeito": {"cura_bonus": 2},
        "desc": "Bônus de cura (se você usar cura)."
    },
    "anel_pristino": {
        "nome": "Anel Prístino",
        "preco": 420,
        "tipo": "anel", "slot": "anel",
        "bonus": {"defesa": 3},
        "desc": "+3 DEF."
    },
    "anel_caveira_rato": {
        "nome": "Anel Caveira de Rato",
        "preco": 120,
        "tipo": "anel", "slot": "anel",
        "bonus": {"defesa": 1},
        "desc": "+1 DEF."
    },

    # ===== POÇÃO DE STAMINA (CARÍSSIMA) =====
    "pocao_stamina": {
        "nome": "Poção de Stamina",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"stamina": 15},
        "desc": "Recupera 15 de Stamina."
    },
}

# Mescla os itens novos na loja principal
LOJA.update(novos_itens)




# ==============================
# NARRAÇÃO (PAUSA caça)
# ==============================
NARRACAO_GUILD = {}  # guild_id -> bool

# ==============================
# UTIL / CHECKS
# ==============================
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
            return True  # sem trava se não configurado
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
        if not eh_mestre(interaction.user.id):
            msg = "❌ Apenas o **Mestre** pode usar isso."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False

        if CANAL_MESTRE_ID and interaction.channel_id != CANAL_MESTRE_ID:
            msg = "❌ Comandos do mestre só na **#Sala do mestre**."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True
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

# ==============================
# BANCO DE DADOS / PERSISTÊNCIA
# ==============================

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            classe TEXT,
            level INTEGER,
            xp INTEGER,
            gold INTEGER,
            pontos INTEGER,
            hp INTEGER,
            mana INTEGER,
            stamina INTEGER,
            max_stamina INTEGER,
            rest_until_ts INTEGER,
            last_hunt_ts INTEGER,
            stats_json TEXT,
            inventario_json TEXT,
            equipado_json TEXT
        )
        """)
        await db.commit()


def ensure_equipado_format(eq: dict) -> dict:
    """Normaliza slots de equipamento para evitar erro com saves antigos."""
    if not isinstance(eq, dict):
        eq = {}

    # Slots únicos
    eq.setdefault("arma", None)
    eq.setdefault("armadura", None)
    eq.setdefault("elmo", None)
    eq.setdefault("botas", None)
    eq.setdefault("luvas", None)
    eq.setdefault("cajado", None)

    # Até 8 anéis
    aneis = eq.get("aneis", [])
    if not isinstance(aneis, list):
        aneis = []

    # completa com None até 8
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
        p["stats"] = json.loads(p.get("stats_json") or "{}")
        p["inventario"] = json.loads(p.get("inventario_json") or "[]")
        p["equipado"] = json.loads(p.get("equipado_json") or "{}")

        # normaliza slots
        p["equipado"] = ensure_equipado_format(p["equipado"])
        return p

async def get_player(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()

        if not row:
            return None

        p = dict(row)

        # Carrega JSONs com segurança
        p["stats"] = json.loads(p.get("stats_json") or "{}")
        p["inventario"] = json.loads(p.get("inventario_json") or "[]")
        p["equipado"] = json.loads(p.get("equipado_json") or "{}")

        # Normaliza equipamentos (corrige saves antigos)
        p["equipado"] = ensure_equipado_format(p["equipado"])

        return p


async def save_player(p: dict):
    async with aiosqlite.connect(DB_FILE) as db:
        p["equipado"] = ensure_equipado_format(p.get("equipado"))

        await db.execute("""
        INSERT INTO players (
            user_id, classe, level, xp, gold, pontos, hp, mana, stamina, max_stamina,
            rest_until_ts, last_hunt_ts, stats_json, inventario_json, equipado_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            equipado_json=excluded.equipado_json
        """, (
            p["user_id"], p["classe"], int(p["level"]), int(p["xp"]), int(p["gold"]), int(p.get("pontos", 0)),
            int(p["hp"]), int(p["mana"]), int(p["stamina"]), int(p["max_stamina"]),
            int(p.get("rest_until_ts", 0)), int(p.get("last_hunt_ts", 0)),
            json.dumps(p.get("stats", {}), ensure_ascii=False),
            json.dumps(p.get("inventario", []), ensure_ascii=False),
            json.dumps(p.get("equipado", {}), ensure_ascii=False),
        ))
        await db.commit()

def iter_equips(p: dict):
    eq = p.get("equipado") or {}
    for slot in ["arma", "armadura", "elmo", "botas", "luvas", "cajado"]:
        iid = eq.get(slot)
        if iid:
            yield iid
    for iid in eq.get("aneis", []) or []:
        if iid:
            yield iid

def total_stat(p: dict, stat: str) -> int:
    base = int((p.get("stats") or {}).get(stat, 0))
    for item_id in iter_equips(p):
        item = LOJA.get(item_id)
        if not item:
            continue
        bonus = item.get("bonus", {})
        base += int(bonus.get(stat, 0))
        # efeitos opcionais
        efeito = item.get("efeito", {})
        if stat == "cura":
            base += int(efeito.get("cura_bonus", 0))
    return base


async def try_auto_level(p: dict) -> int:
    upou = 0
    while True:
        custo = xp_para_upar(int(p["level"]))
        if int(p["xp"]) < custo:
            break
        p["xp"] -= custo
        p["level"] += 1
        p["pontos"] = int(p.get("pontos", 0)) + 5
        upou += 1
    if upou:
        await save_player(p)
    return upou

# ==============================
# CRIAÇÃO DE PERSONAGEM (Dropdown)
# ==============================
def build_new_player(user_id: int, classe: str) -> dict:
    base = CLASSES[classe].copy()
    hp = int(base["hp_base"])
    mana = int(base["mana_base"])
    return {
        "user_id": user_id,
        "classe": classe,
        "level": 1,
        "xp": 0,
        "gold": 100,
        "pontos": 0,
        "hp": hp,
        "mana": mana,
        "stamina": STAMINA_MAX,
        "max_stamina": STAMINA_MAX,
        "rest_until_ts": 0,
        "last_hunt_ts": 0,
        "stats": base,
        "inventario": [],
        "equipado": {"arma": None, "armadura": None, "especial": None},
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
        super().__init__(placeholder="Escolha sua classe…", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        if interaction.channel_id != CANAL_BEM_VINDO_ID:
            await interaction.response.send_message("❌ Criação de personagem só no canal de **bem-vindo**.", ephemeral=True)
            return

        existing = await get_player(interaction.user.id)
        if existing:
            await interaction.response.send_message("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
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
                f"💰 Gold inicial: **{p['gold']}**\n\n"
                f"_👁️ Vigillant: “Mais um nome para a estatística…”_"
            ),
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

class ClasseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ClasseSelect())

# ==============================
# LOJA PAGINADA (Botões)
# ==============================
ITEMS_PER_PAGE = 6

def build_loja_embed(page: int) -> discord.Embed:
    itens = list(LOJA.items())
    total = len(itens)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    chunk = itens[start:end]

    embed = discord.Embed(
        title="🏪 Terminal de Suprimentos — LOJA",
        description=(
            "Use **/comprar item_id** para comprar.\n"
            "Use **/vender item_id** para vender (**60%**).\n"
            "Use **/equipar** e **/desequipar** para gerenciar bônus.\n"
        ),
        color=discord.Color.green()
    )

    for key, item in chunk:
        preco = int(item.get("preco", 0))
        tipo = item.get("tipo", "—")
        desc = (item.get("desc", "") or "").strip()

        if tipo == "consumivel":
            eff = item.get("efeito", {})
            eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
            val = f"💰 **{preco}** | 🧪 {eff_txt}"
        else:
            bonus = item.get("bonus", {})
            btxt = ", ".join([f"{k.upper()}+{v}" for k, v in bonus.items()]) if bonus else "—"
            val = f"💰 **{preco}** | ⚙️ **{tipo}** | {btxt}"

        if desc:
            desc = desc[:80] + ("…" if len(desc) > 80 else "")
            val += f"\n_{desc}_"

        embed.add_field(name=f"**{item.get('nome','Item')}** (`{key}`)", value=val, inline=False)

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
        await interaction.response.edit_message(embed=build_loja_embed(self.page), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=build_loja_embed(self.page), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)

# ==============================
# EVENTO: BANDIDOS (Botões)
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
        dc = 11 + self.forca  # 50/50 aproximado
        venceu = d20 >= dc

        defesa = total_stat(p, "defesa")
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
                + (f"\n🆙 UPOU {upou} nível(is)! (+{upou*5} pontos)" if upou else ""),
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

# ==============================
# COMANDOS
# ==============================
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

@tree.command(name="ping", description="Ver se o bot está vivo.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("👁️ **Vigillant está online.**", ephemeral=True)

# /start só no canal bem-vindo
@tree.command(name="start", description="Criar personagem (menu de classes).")
@only_channel(CANAL_BEM_VINDO_ID, "bem-vindo")
async def start(interaction: discord.Interaction):
    existing = await get_player(interaction.user.id)
    if existing:
        await interaction.response.send_message("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
        return

    embed = discord.Embed(
        title="👁️ PROTOCOLO DE SOBREVIVÊNCIA — VIGILLANT",
        description=(
            "Você foi detectado.\n"
            "Escolha sua classe para entrar nas **Terras da Diretriz**.\n\n"
            "⬇️ Selecione abaixo."
        ),
        color=discord.Color.dark_grey()
    )
    for cls, st in CLASSES.items():
        embed.add_field(
            name=f"🔹 {cls.capitalize()}",
            value=f"❤ {st['hp_base']} | 🔵 {st['mana_base']} | ⚔ {st['atk']} | ✨ {st['magia']} | 🛡 {st['defesa']}",
            inline=False
        )
    embed.set_footer(text="Depois use /perfil e leia o canal de comandos.")
    await interaction.response.send_message(embed=embed, view=ClasseView(), ephemeral=False)

@tree.command(name="perfil", description="Ver seu personagem.")
async def perfil(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    eq = p.get("equipado") or {}
    arma = eq.get("arma") or "—"
    armadura = eq.get("armadura") or "—"
    especial = eq.get("especial") or "—"

    embed = discord.Embed(
        title=f"👤 Perfil — {interaction.user.display_name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Classe", value=str(p["classe"]).capitalize(), inline=True)
    embed.add_field(name="Nível", value=f"{p['level']} (XP {p['xp']}/{xp_para_upar(int(p['level']))})", inline=True)
    embed.add_field(name="Gold", value=f"💰 {p['gold']}", inline=True)

    embed.add_field(
        name="Status",
        value=(
            f"❤ HP: **{p['hp']}**\n"
            f"🔵 Mana: **{p['mana']}**\n"
            f"🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**\n"
            f"⭐ Pontos: **{p.get('pontos', 0)}**"
        ),
        inline=True
    )
    embed.add_field(
        name="Atributos (com bônus)",
        value=(
            f"⚔ ATK: **{total_stat(p,'atk')}**\n"
            f"🛡 DEF: **{total_stat(p,'defesa')}**\n"
            f"✨ MAG: **{total_stat(p,'magia')}**\n"
            f"🎯 DEX: **{total_stat(p,'destreza')}**\n"
            f"🍀 SORTE: **{total_stat(p,'sorte')}**\n"
            f"🕶 FURT: **{total_stat(p,'furtividade')}**"
        ),
        inline=True
    )
    embed.add_field(
        name="Equipado",
        value=f"🗡 Arma: `{arma}`\n🛡 Armadura: `{armadura}`\n🧩 Especial: `{especial}`",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /comandos só no canal de comandos
@tree.command(name="comandos", description="Lista resumida de comandos.")
@only_channel(CANAL_COMANDOS_ID, "comandos-dos-players")
async def comandos(interaction: discord.Interaction):
    txt = (
        "👁️ **COMANDOS — RPG VIGILLANT**\n\n"
        "**🎮 Jogadores**\n"
        f"• **/start** (apenas no canal de início)\n"
        f"• **/perfil**\n"
        f"• **/cacar** (apenas no canal de caça)\n"
        f"• **/descansar** (12h inativo)\n"
        f"• **/albergue** (cura pagando gold)\n"
        f"• **/loja** **/comprar** **/vender** **/inventario** **/equipar** **/desequipar** **/usar** (apenas na loja)\n"
        f"• **/uparnivel** (auto)  • **/upar** (atributos)\n"
        f"• **/enviargold** • **/doaritem**\n\n"
        "**👑 Mestre** (canal do mestre)\n"
        "• **/narracao on|off** (pausa caça)\n"
        "• **/darxp** • **/dargold** • **/daritem** • **/resetar** • **/setlevel**\n"
        "• **/mdano** • **/mcurar** • **/mstatus**\n"
    )
    await interaction.response.send_message(txt, ephemeral=True)

# Loja (somente canal loja)
@tree.command(name="loja", description="Ver itens disponíveis na loja (paginado).")
@only_channel(CANAL_LOJA_ID, "loja")
async def loja_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    await interaction.response.send_message(embed=build_loja_embed(0), view=LojaView(interaction.user.id, 0), ephemeral=True)

@tree.command(name="inventario", description="Ver seu inventário.")
@only_channel(CANAL_LOJA_ID, "loja")
async def inventario(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    inv = p.get("inventario") or []
    if not inv:
        await interaction.response.send_message("🎒 Inventário vazio.", ephemeral=True)
        return

    linhas = []
    for item_id in inv[:40]:
        nm = LOJA.get(item_id, {}).get("nome", item_id)
        linhas.append(f"• `{item_id}` — {nm}")

    await interaction.response.send_message("🎒 **Seu inventário:**\n" + "\n".join(linhas), ephemeral=True)

@tree.command(name="comprar", description="Comprar item da loja.")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item (ex: pocao_vida)")
async def comprar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower()
    item = LOJA.get(item_id)
    if not item:
        await interaction.response.send_message("❌ Item não encontrado.", ephemeral=True)
        return

    preco = int(item.get("preco", 0))
    if int(p["gold"]) < preco:
        await interaction.response.send_message("❌ Gold insuficiente.", ephemeral=True)
        return

    if "classes" in item and p["classe"] not in item["classes"]:
        await interaction.response.send_message(f"❌ Apenas para: {', '.join(item['classes'])}", ephemeral=True)
        return

    p["gold"] -= preco
    p.setdefault("inventario", []).append(item_id)
    await save_player(p)

    await interaction.response.send_message(f"✅ Comprou **{item['nome']}** por **{preco}** gold.", ephemeral=True)

@tree.command(name="vender", description="Vender item do inventário (60% do preço).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def vender(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem esse item.", ephemeral=True)
        return
    item = LOJA.get(item_id)
    if not item or int(item.get("preco", 0)) <= 0:
        await interaction.response.send_message("❌ Este item não pode ser vendido.", ephemeral=True)
        return

    preco = int(item["preco"])
    ganho = int(math.floor(preco * 0.6))

    inv.remove(item_id)
    p["inventario"] = inv
    p["gold"] += ganho
    await save_player(p)

    await interaction.response.send_message(f"💰 Vendeu **{item['nome']}** por **{ganho}** gold (60%).", ephemeral=True)

@tree.command(name="equipar", description="Equipar item (arma/armadura/especial).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def equipar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não possui este item.", ephemeral=True)
        return

    item = LOJA.get(item_id)
    if not item or item.get("tipo") not in ["arma", "armadura", "especial"]:
        await interaction.response.send_message("❌ Este item não pode ser equipado.", ephemeral=True)
        return

    if "classes" in item and p["classe"] not in item["classes"]:
        await interaction.response.send_message(f"❌ Apenas para: {', '.join(item['classes'])}", ephemeral=True)
        return

    slot = item["tipo"]
    p.setdefault("equipado", {}).setdefault(slot, None)
    p["equipado"][slot] = item_id
    await save_player(p)

    await interaction.response.send_message(f"⚙️ Equipou **{item['nome']}** no slot **{slot}**.", ephemeral=True)

@tree.command(name="desequipar", description="Desequipar um slot (arma/armadura/especial).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(slot="arma | armadura | especial")
async def desequipar(interaction: discord.Interaction, slot: str):
    p = await require_player(interaction)
    if not p:
        return
    slot = slot.lower()
    if slot not in ["arma", "armadura", "especial"]:
        await interaction.response.send_message("❌ Slot inválido. Use: arma, armadura, especial.", ephemeral=True)
        return

    eq = p.get("equipado") or {}
    if not eq.get(slot):
        await interaction.response.send_message("⚠️ Nada equipado nesse slot.", ephemeral=True)
        return

    eq[slot] = None
    p["equipado"] = eq
    await save_player(p)

    await interaction.response.send_message(f"✅ Desequipou o slot **{slot}**.", ephemeral=True)

@tree.command(name="usar", description="Usar consumível do inventário (poções).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def usar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem este item.", ephemeral=True)
        return

    item = LOJA.get(item_id)
    if not item or item.get("tipo") != "consumivel":
        await interaction.response.send_message("❌ Este item não é consumível.", ephemeral=True)
        return

    eff = item.get("efeito", {})
    if "hp" in eff:
        p["hp"] += int(eff["hp"])
    if "mana" in eff:
        p["mana"] += int(eff["mana"])

    inv.remove(item_id)
    p["inventario"] = inv
    await save_player(p)

    eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
    await interaction.response.send_message(f"🧪 Usou **{item['nome']}** ({eff_txt}).", ephemeral=True)

# Progressão
@tree.command(name="uparnivel", description="Upar automaticamente se tiver XP suficiente (+5 pontos).")
async def uparnivel(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    upou = await try_auto_level(p)
    if not upou:
        await interaction.response.send_message(
            f"❌ Você precisa de **{xp_para_upar(int(p['level']))} XP** para upar. (Você tem {p['xp']})",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"🆙 Você upou **{upou}** nível(is)! Agora é nível **{p['level']}**.\n"
        f"⭐ +**{upou*5}** pontos para distribuir.\n"
        f"Use: **/upar atributo quantidade**",
        ephemeral=True
    )

@tree.command(name="upar", description="Distribuir pontos de atributo manualmente.")
@app_commands.describe(atributo="hp_base|mana_base|atk|defesa|magia|sorte|furtividade|destreza", quantidade="quantos pontos")
async def upar(interaction: discord.Interaction, atributo: str, quantidade: int):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return

    atributo = atributo.lower()
    pontos = int(p.get("pontos", 0))
    if pontos < quantidade:
        await interaction.response.send_message(f"❌ Você tem apenas **{pontos}** pontos.", ephemeral=True)
        return

    # HP NÃO sobe sozinho — só aqui, manualmente
    if atributo in ["hp_base", "mana_base", "atk", "defesa", "magia", "sorte", "furtividade", "destreza"]:
        p["stats"][atributo] = int(p["stats"].get(atributo, 0)) + quantidade
        if atributo == "hp_base":
            p["hp"] += quantidade  # aumenta um pouco também (ajuste)
        if atributo == "mana_base":
            p["mana"] += quantidade
    else:
        await interaction.response.send_message("❌ Atributo inválido.", ephemeral=True)
        return

    p["pontos"] = pontos - quantidade
    await save_player(p)

    await interaction.response.send_message(f"✅ Upou **{atributo}** (+{quantidade}). Pontos restantes: **{p['pontos']}**", ephemeral=True)

# Trade (pode ser em qualquer canal)
@tree.command(name="enviargold", description="Enviar gold para outro jogador.")
@app_commands.describe(membro="Quem recebe", quantidade="quanto enviar")
async def enviargold(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    if int(p["gold"]) < quantidade:
        await interaction.response.send_message("❌ Você não tem gold suficiente.", ephemeral=True)
        return

    alvo = await get_player(membro.id)
    if not alvo:
        await interaction.response.send_message("❌ O alvo não tem personagem.", ephemeral=True)
        return

    p["gold"] -= quantidade
    alvo["gold"] += quantidade
    await save_player(p)
    await save_player(alvo)

    await interaction.response.send_message(f"💰 Você enviou **{quantidade}** gold para {membro.mention}.", ephemeral=True)

@tree.command(name="doaritem", description="Doar item do inventário para outro jogador.")
@app_commands.describe(membro="Quem recebe", item_id="ID do item")
async def doaritem(interaction: discord.Interaction, membro: discord.Member, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    alvo = await get_player(membro.id)
    if not alvo:
        await interaction.response.send_message("❌ O alvo não tem personagem.", ephemeral=True)
        return

    item_id = item_id.lower()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem esse item.", ephemeral=True)
        return

    inv.remove(item_id)
    p["inventario"] = inv
    alvo.setdefault("inventario", []).append(item_id)

    await save_player(p)
    await save_player(alvo)
    await interaction.response.send_message(f"🎁 Você doou `{item_id}` para {membro.mention}.", ephemeral=True)

# Descansar / Albergue
@tree.command(name="descansar", description="Descansar: fica inativo por 12h e recupera stamina (e HP/Mana base).")
async def descansar(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    p["rest_until_ts"] = now_ts() + DESCANSO_HORAS * 3600
    p["stamina"] = int(p["max_stamina"])

    # Recupera para o BASE do personagem
    p["hp"] = max(int(p["hp"]), int(p["stats"].get("hp_base", 1)))
    p["mana"] = max(int(p["mana"]), int(p["stats"].get("mana_base", 0)))

    await save_player(p)
    await interaction.response.send_message(f"⛺ Descanso iniciado. Você ficará inativo por **{DESCANSO_HORAS}h**.", ephemeral=True)

@tree.command(name="albergue", description="Descanso pago: recupera HP/Mana/Stamina (50 gold proporcional)")
async def albergue(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    p = await get_player(interaction.user.id)
    if not p:
        await interaction.followup.send(
            "⚠️ Você ainda não tem personagem. Use **/start**.",
            ephemeral=True
        )
        return

    # Garantir campos para saves antigos
    p["max_hp"] = int(p.get("max_hp", p.get("hp", 0)))
    p["max_mana"] = int(p.get("max_mana", p.get("mana", 0)))
    p["max_stamina"] = int(p.get("max_stamina", 100))
    p["stamina"] = int(p.get("stamina", p["max_stamina"]))
    p["gold"] = int(p.get("gold", 0))



    # remove "descanso bloqueado" se você usa esse sistema
    p["rest_until"] = 0

    await save_player(p)

    await interaction.followup.send(
        f"🏨 **Albergue**\n"
        f"Você pagou **{pago} gold** ({int(frac*100)}%).\n"
        f"❤ HP: **{p['hp']}/{max_hp}**"
        f"🔵 Mana: **{p['mana']}/{max_mana}**"
        f"🥵 Stamina: **{p['stamina']}/{max_stamina}**"
        f"💰 Gold restante: **{p['gold']}**",
        ephemeral=True
    )

# ==============================
# /CACAR — D20 AUTOMÁTICO (SÓ AQUI)
# ==============================
@tree.command(name="cacar", description="Caçar monstros e eventos (D20 automático).")
@only_channel(CANAL_CACAR_ID, "sala-de-cacar")
async def cacar(interaction: discord.Interaction):
    if await blocked_by_narration(interaction):
        return

    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    # cooldown anti-spam
    now = now_ts()
    last = int(p.get("last_hunt_ts", 0))
    if now - last < CACAR_COOLDOWN_S:
        falta = CACAR_COOLDOWN_S - (now - last)
        await interaction.response.send_message(f"⏳ Aguarde **{falta}s** para caçar novamente.", ephemeral=True)
        return

    # stamina
    if int(p["stamina"]) < STAMINA_CUSTO_CACAR:
        await interaction.response.send_message("🥵 Stamina insuficiente. Use **/descansar**.", ephemeral=True)
        return

    p["stamina"] -= STAMINA_CUSTO_CACAR
    p["last_hunt_ts"] = now

    # evento bandidos (pagar 100 ou lutar)
    if random.random() < 0.18:
        forca = random.choice([0, 1, 2])
        await save_player(p)

        embed = discord.Embed(
            title="💀 Emboscada!",
            description=(
                "Bandidos armados cercam você.\n\n"
                "💰 **Pagar 100 gold** e eles vão embora.\n"
                "⚔️ **Lutar** (50/50 aproximado — D20).\n\n"
                "_Vigillant observa em silêncio…_"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=BandidosView(interaction.user.id, forca), ephemeral=False)
        return

    # escolhe monstro ponderado
    ids = list(MONSTROS.keys())
    pesos = [int(MONSTROS[k].get("peso", 1)) for k in ids]
    mob_id = random.choices(ids, weights=pesos, k=1)[0]
    m = MONSTROS[mob_id]

    # fala do monstro (por tag)
    tag = "orgânico"
    if "cibernético" in m["tags"]:
        tag = "cibernético"
    if "demoníaco" in m["tags"]:
        tag = "demoníaco"
    mob_line = random.choice(MOB_QUOTES[tag])

    # D20 automático só aqui
    d20 = rolar_d20()
    if d20 == 20:
        mult = 2.0
        rotulo = "💥 **CRÍTICO!**"
    elif d20 >= 14:
        mult = 1.25
        rotulo = "⚔️ **Acerto forte**"
    elif d20 >= 8:
        mult = 1.0
        rotulo = "✅ **Acerto**"
    else:
        mult = 0.0
        rotulo = "❌ **Errou**"

    # dano do player (físico para certas classes, magia para outras)
    classe = p["classe"]
    atk = total_stat(p, "atk")
    mag = total_stat(p, "magia")
    base = atk if classe in ["barbaro", "assassino", "arqueiro"] else mag

    dano = int(max(0, base) * mult)

    # dano do monstro (defesa reduz)
    defesa = total_stat(p, "defesa")
    dano_monstro = max(0, int(m["atk"]) - defesa)

    mob_hp = int(m["hp"]) - dano
    tomou = dano_monstro if mob_hp > 0 else 0
    p["hp"] = max(0, int(p["hp"]) - tomou)

    ganhou = (mob_hp <= 0 and dano > 0)

    xp_gain = int(m["xp"])
    gold_gain = int(m["gold"])

    # nerf se errou (anti-farm)
    if dano == 0:
        xp_gain = max(0, xp_gain // 3)
        gold_gain = max(0, gold_gain // 3)

    if ganhou:
        p["xp"] += xp_gain
        p["gold"] += gold_gain

    upou = await try_auto_level(p)
    await save_player(p)

    embed = discord.Embed(
        title="⚔️ CAÇADA — VIGILLANT",
        description=(
            f"_{mob_line}_\n\n"
            f"👹 Alvo: **{m['nome']}**\n"
            f"🎲 D20: **{d20}**  →  {rotulo}\n\n"
            f"⚔️ Dano causado: **{dano}**\n"
            f"💥 Dano recebido: **{tomou}**\n\n"
            f"❤ HP: **{p['hp']}**  |  🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**"
        ),
        color=discord.Color.orange()
    )

    if ganhou:
        embed.add_field(name="🏆 Vitória", value=f"✨ +{xp_gain} XP | 💰 +{gold_gain} Gold", inline=False)
    else:
        embed.add_field(name="⚠️ Resultado", value="O alvo resistiu / você falhou. Reorganize-se e tente novamente.", inline=False)

    if upou:
        embed.add_field(name="🆙 LEVEL UP", value=f"Você upou **{upou}** nível(is)! (+{upou*5} pontos)", inline=False)

    if random.random() < 0.25:
        embed.set_footer(text=f"Vigillant: “{random.choice(VIGILLANT_QUOTES)}”")

    await interaction.response.send_message(embed=embed, ephemeral=False)

# ==============================
# MESTRE (restrito ao canal do mestre)
# ==============================
@tree.command(name="narracao", description="(Mestre) Ativar/desativar modo narração (pausa /cacar).")
@only_master_channel()
@app_commands.describe(modo="on ou off")
async def narracao(interaction: discord.Interaction, modo: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Use em servidor.", ephemeral=True)
        return
    modo = modo.lower()
    if modo not in ["on", "off"]:
        await interaction.response.send_message("❌ Use on/off.", ephemeral=True)
        return
    NARRACAO_GUILD[interaction.guild.id] = (modo == "on")
    await interaction.response.send_message(f"📖 Modo narração: **{modo.upper()}**", ephemeral=False)

@tree.command(name="darxp", description="(Mestre) Dar XP.")
@only_master_channel()
async def darxp(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["xp"] += quantidade
    upou = await try_auto_level(p)
    await save_player(p)
    await interaction.response.send_message(
        f"👑 Mestre deu **{quantidade} XP** para {membro.mention}."
        + (f" 🆙 (upou {upou}x)" if upou else ""),
        ephemeral=False
    )

@tree.command(name="dargold", description="(Mestre) Dar/remover gold (pode ser negativo).")
@only_master_channel()
async def dargold(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["gold"] = max(0, int(p["gold"]) + quantidade)
    await save_player(p)
    await interaction.response.send_message(f"💰 Gold ajustado em **{quantidade}** para {membro.mention}. (Agora {p['gold']})", ephemeral=False)

@tree.command(name="daritem", description="(Mestre) Dar item.")
@only_master_channel()
async def daritem(interaction: discord.Interaction, membro: discord.Member, item_id: str):
    item_id = item_id.lower()
    if item_id not in LOJA:
        await interaction.response.send_message("❌ Item não existe na loja.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p.setdefault("inventario", []).append(item_id)
    await save_player(p)
    await interaction.response.send_message(f"🎁 Mestre deu **{LOJA[item_id]['nome']}** para {membro.mention}.", ephemeral=False)

@tree.command(name="resetar", description="(Mestre) Resetar personagem do jogador.")
@only_master_channel()
async def resetar(interaction: discord.Interaction, membro: discord.Member):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE user_id=?", (membro.id,))
        await db.commit()
    await interaction.response.send_message(f"🗑️ Personagem de {membro.mention} resetado. (Use /start)", ephemeral=False)

@tree.command(name="setlevel", description="(Mestre) Definir nível (não mexe em atributos).")
@only_master_channel()
async def setlevel(interaction: discord.Interaction, membro: discord.Member, nivel: int):
    if nivel < 1:
        await interaction.response.send_message("❌ Nível inválido.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["level"] = nivel
    await save_player(p)
    await interaction.response.send_message(f"🆙 {membro.mention} agora está no nível **{nivel}**.", ephemeral=False)

@tree.command(name="mdano", description="(Mestre) Aplicar dano manual em jogador.")
@only_master_channel()
async def mdano(interaction: discord.Interaction, membro: discord.Member, dano: int):
    if dano <= 0:
        await interaction.response.send_message("❌ Dano inválido.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["hp"] = max(0, int(p["hp"]) - dano)
    await save_player(p)
    await interaction.response.send_message(f"💥 {membro.mention} sofreu **{dano}** dano. (HP {p['hp']})", ephemeral=False)

@tree.command(name="mcurar", description="(Mestre) Curar manualmente jogador.")
@only_master_channel()
async def mcurar(interaction: discord.Interaction, membro: discord.Member, hp: int = 0, mana: int = 0):
    if hp < 0 or mana < 0:
        await interaction.response.send_message("❌ Valores inválidos.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["hp"] += hp
    p["mana"] += mana
    await save_player(p)
    await interaction.response.send_message(f"✨ {membro.mention} curado: ❤ +{hp} | 🔵 +{mana}.", ephemeral=False)

@tree.command(name="mstatus", description="(Mestre) Status rápido de um jogador.")
@only_master_channel()
async def mstatus(interaction: discord.Interaction, membro: discord.Member):
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🧾 **Status — {membro.display_name}**\n"
        f"Classe: {p['classe']} | Lv {p['level']} | XP {p['xp']}/{xp_para_upar(int(p['level']))}\n"
        f"❤ HP {p['hp']} | 🔵 Mana {p['mana']} | 🥵 Stamina {p['stamina']}/{p['max_stamina']} | 💰 Gold {p['gold']}\n"
        f"⭐ Pontos: {p.get('pontos',0)}",
        ephemeral=True
    )

# ==============================
# READY
# ==============================
@client.event
async def on_ready():
    await init_db()
    try:
        await tree.sync()
    except Exception:
        pass
    print(f"👁️ VIGILLANT ONLINE: {client.user}")

# ==============================
# RUN
# ==============================
client.run("TOKEN")


