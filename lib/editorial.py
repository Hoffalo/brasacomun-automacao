"""
BRASA Briefing Bot — Linha editorial, prefixos e paletas
Fonte: documentação do projeto + Manual de ID Visual seção 1.3
"""

# ── Prefixos ────────────────────────────────────────────────────────────────
# Mapeia prefixo do nome da task → (tipo de conteúdo, tipo de plataforma)

PREFIXES = {
    "CAM":           ("campanha",      "post"),
    "Corp":          ("corp",          "post"),
    "Stories":       ("stories",       "story"),
    "Reels":         ("campanha",      "reels"),
    "INN":           ("conferencia",   "post"),
    "POST Inn":      ("conferencia",   "post"),
    "EDU":           ("educativo",     "post"),
    "REDE":          ("rede",          "post"),
    "Institucional": ("institucional", "post"),
    "Newsletter":    ("newsletter",    "newsletter"),
    "Takeover":      ("institucional", "story"),
    "VÍDEO":         ("producao",      "video_horizontal"),
}


def identify_prefix(task_name: str) -> tuple[str, str]:
    """
    Identifica o tipo de conteúdo e plataforma pelo prefixo da task.
    Retorna ("desconhecido", "desconhecido") se não reconhecer.
    """
    name_upper = task_name.upper()
    for prefix, types in PREFIXES.items():
        if name_upper.startswith(prefix.upper()):
            return types
    return ("desconhecido", "desconhecido")


# ── Linha editorial ──────────────────────────────────────────────────────────
# weekday: 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom

EDITORIAL = {
    "@gobrasa": {
        0: "corp",
        1: "institucional",
        2: "rede",
        3: "educativo",
        4: "produto",
        5: "produto",
        6: "produto",
    },
    "LinkedIn & Newsletter": {
        0: "corp",
        1: "produto",
        2: "institucional",
        3: "produto",
        4: "educativo",
    },
    "TikTok": {
        0: "institucional",
        1: "romantizacao",
        2: "rede",
        3: "campanha",
        4: "campanha",
        5: "campanha",
        6: "campanha",
    },
    # Listas de conferência seguem linha própria (produto/campanha todos os dias)
    "IG Summit Innovation": {i: "conferencia" for i in range(7)},
    "IG Summit Americas":   {i: "conferencia" for i in range(7)},
    "IG Summit Europa":     {i: "conferencia" for i in range(7)},
    "IG BeC":               {i: "campanha" for i in range(7)},
}

# Dia correto por tipo de conteúdo no @gobrasa
CONTENT_TYPE_DAY = {
    "corp": 0,
    "institucional": 1,
    "rede": 2,
    "educativo": 3,
}

DAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def validate_date(due_date_ms: int | None, content_type: str, list_name: str) -> str | None:
    """
    Valida se a data de entrega está no dia correto para o tipo de conteúdo.
    Retorna string de alerta ou None se tudo ok.
    """
    if not due_date_ms or content_type in ("producao", "conferencia", "desconhecido"):
        return None

    from datetime import datetime
    due_dt = datetime.fromtimestamp(int(due_date_ms) / 1000)
    weekday = due_dt.weekday()

    editorial = EDITORIAL.get(list_name, EDITORIAL.get("@gobrasa", {}))
    expected_type = editorial.get(weekday)

    if expected_type and expected_type != content_type:
        correct_day = CONTENT_TYPE_DAY.get(content_type)
        suggestion = DAY_NAMES[correct_day] if correct_day is not None else "verificar linha editorial"
        return (
            f"⚠ Data {due_dt.strftime('%d/%m')} ({DAY_NAMES[weekday]}) "
            f"não é o dia correto para conteúdo '{content_type}'. "
            f"Sugestão: {suggestion}"
        )
    return None


# ── Paletas por produto (Manual de ID Visual — seção 1.3) ───────────────────

PALETA_POR_PRODUTO = {
    "passaporte": (
        "Azul escuro #1A2B77 · Azul vívido #065FD8 · Azul claro · "
        "Amarelo #FFCC02 · Laranja #FB8C0A"
    ),
    "pdb": (
        "Verde escuro #03571A · Verde folha #00863D · "
        "Verde vívido #4BBF4B · Verde claro #009F00 · Branco #FFFFFF"
    ),
    "bec": (
        "Laranja #FB8C0A · Amarelo #FFCC02 · Amarelo claro #F5D566 · "
        "Verde folha #00863D · Verde vívido #4BBF4B"
    ),
    "innovation": (
        "Azul escuro #1A2B77 · Azul vívido #065FD8 · Azul claro · "
        "Laranja #FB8C0A"
    ),
    "summit am": (
        "Azul escuro #1A2B77 · Azul médio #3B5ECC · Azul vívido #065FD8 · "
        "Amarelo claro #F5D566"
    ),
    "summit eu": (
        "Verde escuro #03571A · Verde folha #00863D · "
        "Verde vívido #4BBF4B · Amarelo #FFCC02"
    ),
    "mentoria": (
        "Preto #252726 · Azul escuro #1A2B77 · Azul vívido #065FD8 · "
        "Amarelo claro #F5D566 · Amarelo #FFCC02"
    ),
    "brasa next": (
        "Preto #252726 · Verde escuro #03571A · Verde folha #00863D · "
        "Verde vívido #4BBF4B · Verde claro #009F00"
    ),
    "default": (
        "Verde escuro #03571A · Azul vívido #065FD8 · Amarelo #FFCC02 · "
        "Laranja #FB8C0A (paleta principal BRASA)"
    ),
}
