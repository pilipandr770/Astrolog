"""
Генерация текста толкования на основе УЖЕ РАССЧИТАННЫХ данных
(ephemeris.py + lal_kitab.py). Claude здесь НЕ считает астрологию —
только облекает готовые расчёты в связный, тёплый, понятный текст
на немецком (или языке пользователя).

TODO: промпт не финализирован, нужно протестировать на реальных находках
из lal_kitab.py и откалибровать тон/длину под целевую аудиторию продукта.
"""
import anthropic
from app.config import Config
from app.models import settings

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

EXTRA_INSTRUCTIONS_KEY = "extra_claude_instructions"

# Stil der Auswertung — vom Nutzer per Nummer gewählt (siehe
# dialog_manager._handle_style()), gespeichert in conversation_state.style.
DEFAULT_STYLE_KEY = "warm"
STYLE_PRESETS = {
    "warm": {
        "label": "Warmherzig & persönlich",
        "instruction": "Schreibe warmherzig, persönlich und einfühlsam, wie eine gute "
                       "Freundin/ein guter Freund, die/der es gut mit der Person meint.",
    },
    "humorous": {
        "label": "Humorvoll & locker",
        "instruction": "Schreibe humorvoll, locker und mit einem Augenzwinkern — gerne mit "
                       "einer Prise Selbstironie, aber ohne die astrologischen Aussagen "
                       "selbst ins Lächerliche zu ziehen.",
    },
    "business": {
        "label": "Sachlich & business-orientiert",
        "instruction": "Schreibe sachlich, klar strukturiert und business-orientiert — wie "
                       "eine kompetente Beratung: wenig Emotionalität, Fokus auf konkrete "
                       "Handlungsempfehlungen.",
    },
    "romantic": {
        "label": "Liebevoll & romantisch",
        "instruction": "Schreibe liebevoll und mit romantischem Unterton, als persönliches "
                       "Geschenk für einen geliebten Menschen.",
    },
}


def get_style_instruction(style_key: str | None) -> str:
    preset = STYLE_PRESETS.get(style_key) or STYLE_PRESETS[DEFAULT_STYLE_KEY]
    return preset["instruction"]


def _language_directive(birth_data: dict) -> str:
    """
    birth_data ist hier das volle conversation_state-Dict (siehe Aufrufer
    in dialog_manager.py) — enthält ggf. language_hint (von Whisper bei
    Sprachnachrichten explizit erkannt) oder language_sample (Textprobe
    der ersten Nutzernachricht). Ohne beides: Deutsch als Standardsprache.
    """
    hint = (birth_data or {}).get("language_hint")
    sample = (birth_data or {}).get("language_sample")
    if hint:
        return f"Schreibe die gesamte Antwort auf {hint} (per Spracherkennung aus einer Sprachnachricht ermittelt)."
    if sample:
        return (
            f"Ermittle die Sprache aus diesem Text-Beispiel des Nutzers und schreibe die "
            f"gesamte Antwort in DERSELBEN Sprache: \"{sample}\". Falls daraus keine Sprache "
            f"eindeutig hervorgeht (z.B. nur Zahlen oder ein Ortsname), schreibe auf Deutsch."
        )
    return "Schreibe auf Deutsch (Standardsprache — kein Sprachsignal vom Nutzer vorhanden)."


TEASER_SYSTEM_PROMPT = """Du bist ein erfahrener Lal-Kitab-Astrologe. Du bekommst 1-2 \
bereits berechnete Lal-Kitab-Befunde aus der Geburtskarte eines Interessenten, der \
noch NICHT bezahlt hat — erfinde KEINE weiteren astrologischen Fakten.

Schreibe einen KURZEN, warmen Teaser (ca. 80-120 Wörter). Sprache und Ton sind in der \
Nutzernachricht als eigene Anweisungen angegeben — befolge diese genau.
- Greife die 1-2 mitgelieferten Befunde konkret auf (keine allgemeinen Floskeln).
- Wecke Neugier, ohne die volle Tiefe preiszugeben.
- Leite am Ende zu einem Angebot über: der volle Bericht (alle Befunde, Empfehlungen \
und ein Monats-Stundenkalender) folgt als PDF, sobald die Zahlung abgeschlossen ist \
— der Zahlungslink kommt in der nächsten Nachricht separat, erwähne ihn nur kurz, \
ohne ihn selbst zu enthalten.
- Kein Fachjargon-Overkill, keine medizinischen/rechtlichen/finanziellen Aussagen."""


def _with_extra_instructions(base_prompt: str) -> str:
    extra = settings.get_setting(EXTRA_INSTRUCTIONS_KEY, "").strip()
    if not extra:
        return base_prompt
    return f"{base_prompt}\n\nZusätzliche Anweisungen vom Betreiber:\n{extra}"

SYSTEM_PROMPT = """Du bist ein erfahrener Lal-Kitab-Astrologe, der einem Kunden \
seine persönliche Auswertung erklärt. Du erhältst bereits berechnete \
astrologische Daten (Planetenpositionen, Häuser, Haus-Aktivierung, \
Lal-Kitab-Befunde, mögliche Rin-Kandidaten) — erfinde KEINE zusätzlichen \
astrologischen Fakten, interpretiere nur, was dir gegeben wird.

Sprache und Ton der Auswertung sind in der Nutzernachricht als eigene Anweisungen \
angegeben (Sprachrichtlinie und Stil-Anweisung) — befolge beide genau, unabhängig \
davon, in welcher Sprache diese Systemanweisung selbst geschrieben ist.

Zu jedem Lal-Kitab-Befund bekommst du eine Liste möglicher positiver und \
belastender Effekte, jeweils mit der Originalbedingung aus dem Quelltext \
(z.B. "Rahu in Houses 8 or 11"). Prüfe für jede Bedingung anhand der oben \
gelisteten Planetenpositionen/Häuser, ob sie auf diese konkrete Karte \
zutrifft, und verwende in deiner Auswertung NUR die Effekte, deren \
Bedingung tatsächlich erfüllt ist. Wenn keine der Bedingungen zu einem \
Befund passt, erwähne nur die kurze Zusammenfassung (summary) dieses \
Befunds, ohne Einzeleffekte zu erfinden.

Zur Haus-Aktivierung: ein Haus ohne Planet ("leer") ist nach Lal Kitab nicht \
automatisch bedeutungslos — prüfe die mitgelieferte Aktivierungs-Tabelle \
(welcher Planet ein leeres Haus "weckt", ob eine ganze Kartenhälfte "schläft"). \
Nutze das, um Bedingungen wie "Haus 7 leer" korrekt einzuordnen, aber erfinde \
keine Aktivierungsregeln, die nicht in der Tabelle stehen.

Zu Rin-Kandidaten: das sind KEINE bestätigten Befunde, sondern grobe, \
NIEDRIG-KONFIDENTE Hinweise (die genaue Bedingung aus dem Quelltext ist nur \
teilweise digitalisiert). Erwähne einen Rin-Kandidaten \
höchstens vorsichtig und im Konjunktiv (z.B. "manche Lal-Kitab-Traditionen \
würden hier auf ein mögliches X hindeuten") — behaupte NIE, dass ein \
karmisches "Doss/Rin" sicher vorliegt, und erfinde keine Details über die \
Familie des Nutzers hinzu.

Schreibe klar, ohne Fachjargon-Überladung. Füge am Ende einen kurzen Hinweis hinzu, \
dass die Auswertung der Unterhaltung und Selbstreflexion dient und keine \
medizinische, rechtliche oder finanzielle Beratung ersetzt (in derselben Sprache \
wie der Rest der Auswertung)."""


def _format_finding(f) -> str:
    lines = [f"### {f.title}", f.summary]
    if f.benefit_effects:
        lines.append("Mögliche positive Effekte (nur wenn die genannte Bedingung auf diese Karte zutrifft):")
        lines += [f"  - Wenn {e['condition']}: {e['effect']}" for e in f.benefit_effects]
    if f.malefic_effects:
        lines.append("Mögliche belastende Effekte (nur wenn die genannte Bedingung auf diese Karte zutrifft):")
        lines += [f"  - Wenn {e['condition']}: {e['effect']}" for e in f.malefic_effects]
    if f.remedy:
        lines.append(f"Empfehlung (Upay): {f.remedy}")
    return "\n".join(lines)


def _format_rin_candidate(r) -> str:
    return (
        f"- {r.debt_type} (Planet {r.planet}, Konfidenz: {r.confidence}) — "
        f"typische Ursache: {r.cause} | typische Symptome: {r.symptoms} | "
        f"Upay: {r.remedy}"
    )


def _format_house_activation(activation: dict) -> str:
    lines = []
    for house_no in range(1, 13):
        info = activation.get(house_no)
        if not info:
            continue
        state = "belegt" if info["occupied"] else "leer"
        side_note = " (Kartenhälfte gilt als schlafend)" if info["side_dormant"] else ""
        awak = info["awakening_planet"]
        awak_house = info["awakening_planet_house"]
        awak_note = f", weckender Planet {awak} steht in Haus {awak_house}" if awak_house else f", weckender Planet {awak} nicht im Chart"
        lines.append(f"- Haus {house_no}: {state}{side_note}{awak_note}")
    return "\n".join(lines)


_PLANET_ABBR_LEGEND = (
    "Su=Sun, Mo=Moon, Ma=Mars, Me=Mercury, Ju=Jupiter, Ve=Venus, "
    "Sa=Saturn, Ra=Rahu, Ke=Ketu"
)


def _format_highlight_block(block: dict) -> str:
    content = block["content"]
    source = "Transit-Treffer" if content["source"] == "transit" else "nataler Grundton"
    summary = content["rule"].get("summary", "")
    return (
        f"- {block['date'].strftime('%d.%m.%Y')}, "
        f"{block['start_hour']:02d}:00–{block['end_hour']:02d}:00 Uhr: "
        f"{content['planet']} ({source}) — {summary}"
    )


def _calendar_section(calendar_highlights: dict | None) -> str:
    """
    Anhang für die User-Message, wenn der Bericht den 30-Tage-Kalender
    enthält (siehe report_generator + transit_forecast.pick_highlights):
    Claude bekommt NUR die vorausgewählten Highlights und schreibt dazu
    Lese-Anleitung + Zusammenfassung in der Zielsprache — die visuelle
    Tabelle selbst rendert das PDF-Template, nicht Claude.
    """
    if not calendar_highlights:
        return ""

    best = "\n".join(_format_highlight_block(b) for b in calendar_highlights.get("best", [])) or "- keine"
    worst = "\n".join(_format_highlight_block(b) for b in calendar_highlights.get("worst", [])) or "- keine"

    return f"""

Kalender-Highlights für die nächsten 30 Tage (lokale Zeit, stärkste Zeitfenster):
Günstige Fenster:
{best}
Anspruchsvolle Fenster:
{worst}

Direkt nach deinem Text folgt im PDF eine visuelle Kalendertabelle: 30 Tage × \
2-Stunden-Blöcke, Zellen mit Planeten-Kürzeln ({_PLANET_ABBR_LEGEND}). Farben: \
grün=günstig, rot=Vorsicht, gelb=gemischt, grau=neutraler Grundton; fett mit \
goldener Umrandung=aktiver Transit-Treffer. Schreibe deshalb als LETZTEN \
Abschnitt deiner Auswertung (mit eigener Überschrift in der Zielsprache):
1. eine kurze Anleitung (2-3 Sätze), wie man die Kalendertabelle liest — \
erkläre die Farben in der Zielsprache und liste die Kürzel-Zuordnung auf. \
WICHTIG: Die Kürzel in der Tabelle sind lateinisch und ändern sich nicht — \
zitiere sie EXAKT so (Su, Mo, Ma, Me, Ju, Ve, Sa, Ra, Ke) und übersetze nur \
die Planetennamen dahinter (z.B. "Su = Солнце" in einer russischen Auswertung).
2. eine konkrete Zusammenfassung der oben gelisteten günstigen und \
anspruchsvollen Zeitfenster mit Datum und Uhrzeit — nutze NUR diese \
Highlights, erfinde keine zusätzlichen Zeitfenster. Formatiere die \
Zeitfenster als Markdown-Liste: jedes Fenster auf einer EIGENEN Zeile, \
die mit "- " beginnt (eine Leerzeile zwischen einleitendem Satz und Liste)."""


def generate_interpretation(
    birth_data: dict,
    houses: dict,
    findings: list,
    rin_candidates: list | None = None,
    house_activation: dict | None = None,
    calendar_highlights: dict | None = None,
) -> str:
    findings_text = "\n\n".join(_format_finding(f) for f in findings) or (
        "Keine spezifischen Lal-Kitab-Befunde für diese Karte gefunden."
    )

    positions_text = "\n".join(
        f"- {name}: {data['sign']} (Haus {data.get('house', '?')})"
        for name, data in houses.items()
    )

    rin_text = "\n".join(_format_rin_candidate(r) for r in rin_candidates or []) or (
        "Keine Rin-Kandidaten für diese Karte gefunden."
    )

    activation_text = _format_house_activation(house_activation) if house_activation else (
        "Keine Haus-Aktivierungsdaten übergeben."
    )

    user_message = f"""Sprachrichtlinie: {_language_directive(birth_data)}

Stil-Anweisung: {get_style_instruction(birth_data.get("style"))}

Geburtsdaten: {birth_data}

Planetenpositionen:
{positions_text}

Haus-Aktivierung:
{activation_text}

Lal-Kitab-Befunde:
{findings_text}

Rin-Kandidaten (niedrige Konfidenz, siehe Systemanweisung):
{rin_text}

Erstelle daraus eine persönliche, gut lesbare Auswertung von ca. 400-600 Wörtern, \
gegliedert in kurze Abschnitte mit Überschriften. Formatiere die gesamte \
Auswertung als Markdown. Der Text erscheint 1:1 in einem bezahlten PDF-Bericht — \
schreibe ALLES (auch Überschriften und Tabellen) konsequent in der Zielsprache, \
ohne englische oder deutsche Einsprengsel. Verwende KEINE Emojis und keine \
astrologischen Sonderzeichen (☿, ♃ usw.) — die PDF-Schrift kann sie nicht \
darstellen. Beginne nach der Hauptüberschrift mit \
einer kompakten Markdown-Tabelle der Planetenpositionen (Spalten: Planet, \
Zeichen, Haus) — übersetze dabei auch die Planeten- und Sternzeichennamen in die \
Zielsprache.{_calendar_section(calendar_highlights)}"""

    response = client.messages.create(
        model=Config.ANTHROPIC_MODEL,
        max_tokens=5000,
        system=_with_extra_instructions(SYSTEM_PROMPT),
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_teaser(birth_data: dict, houses: dict, findings: list) -> str:
    """
    Kurzer kostenloser Teaser vor dem Zahlungslink (siehe dialog_manager.py)
    — nutzt nur 1-2 ausgewählte Befunde, nicht die volle Liste.
    """
    findings_text = "\n\n".join(_format_finding(f) for f in findings)
    positions_text = "\n".join(
        f"- {name}: {data['sign']} (Haus {data.get('house', '?')})"
        for name, data in houses.items()
    )

    user_message = f"""Sprachrichtlinie: {_language_directive(birth_data)}

Stil-Anweisung: {get_style_instruction(birth_data.get("style"))}

Geburtsdaten: {birth_data}

Planetenpositionen:
{positions_text}

Ausgewählte Lal-Kitab-Befunde für den Teaser:
{findings_text}

Schreibe den Teaser."""

    response = client.messages.create(
        model=Config.ANTHROPIC_MODEL,
        max_tokens=400,
        system=_with_extra_instructions(TEASER_SYSTEM_PROMPT),
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
