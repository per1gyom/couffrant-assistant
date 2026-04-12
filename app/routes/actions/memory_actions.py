"""
Gestion des actions memoire (LEARN, INSIGHT, FORGET, SYNTH, RESTART_ONBOARDING, ASK_CHOICE).
5D-2d : support tenant cible dans LEARN.
7-ACT : log d'activite pour LEARN et INSIGHT.
"""
import json
import re
import threading
from app.memory_loader import MEMORY_OK, save_rule, save_insight, delete_rule, synthesize_session
from app.activity_log import log_activity

_ASK_CHOICE_PREFIX = "__CHOICE__:"


def _extract_tenant_target(raw_rule: str) -> tuple:
    """
    5D-2d : extrait le tenant cible optionnel du texte de la regle.
    Format :
      "regle simple"                       -> ("regle simple", None)
      "regle avec tenant|couffrant_solar"  -> ("regle avec tenant", "couffrant_solar")
      "regle perso|_user"                  -> ("regle perso", "_user")
    """
    last_pipe = raw_rule.rfind('|')
    if last_pipe == -1:
        return raw_rule, None
    candidate = raw_rule[last_pipe + 1:].strip()
    if candidate and len(candidate) <= 50 and re.match(r'^_?[a-z][a-z0-9_]*$', candidate):
        return raw_rule[:last_pipe].strip(), candidate
    return raw_rule, None


def _parse_learn_actions(response: str) -> list:
    """
    Parser robuste pour [ACTION:LEARN:category|rule] et
    [ACTION:LEARN:category|rule|tenant_target] (5D-2d).
    Retourne une liste de tuples (category, rule, target_tenant).
    """
    results = []
    TAG = '[ACTION:LEARN:'
    pos = 0
    while True:
        start = response.find(TAG, pos)
        if start == -1:
            break
        after_tag = start + len(TAG)
        pipe = response.find('|', after_tag)
        if pipe == -1:
            pos = start + 1
            continue
        category = response[after_tag:pipe].strip()
        if not category or ']' in category or '\n' in category or '|' in category:
            pos = start + 1
            continue
        rule_start = pipe + 1
        search = rule_start
        rule_end = -1
        while search < len(response):
            bracket = response.find(']', search)
            if bracket == -1:
                break
            next_pos = bracket + 1
            if next_pos >= len(response):
                rule_end = bracket
                break
            next_char = response[next_pos]
            if next_char in '\n\r[':
                rule_end = bracket
                break
            if next_char == ' ' and next_pos + 1 < len(response) and response[next_pos + 1] == '[':
                rule_end = bracket
                break
            search = bracket + 1
        if rule_end == -1:
            fallback = response.find(']', rule_start)
            if fallback != -1:
                rule_end = fallback
            else:
                pos = start + 1
                continue
        rule = response[rule_start:rule_end].strip()
        if rule:
            clean_rule, target_tenant = _extract_tenant_target(rule)
            results.append((category, clean_rule, target_tenant))
        pos = rule_end + 1
    return results


def _handle_ask_choice(response: str) -> list:
    """Parse [ACTION:ASK_CHOICE:question|option1|option2|option3]."""
    confirmed = []
    TAG = '[ACTION:ASK_CHOICE:'
    start = response.find(TAG)
    if start == -1:
        return confirmed
    content_start = start + len(TAG)
    close = response.find(']', content_start)
    if close == -1:
        return confirmed
    content = response[content_start:close]
    parts = [p.strip() for p in content.split('|') if p.strip()]
    if len(parts) < 2:
        return confirmed
    question = parts[0]
    options = parts[1:][:4]
    confirmed.append(
        _ASK_CHOICE_PREFIX + json.dumps({"question": question, "options": options}, ensure_ascii=False)
    )
    return confirmed


def _handle_memory_actions(response: str, username: str, synth_threshold: int,
                           tenant_id: str = 'couffrant_solar') -> list:
    confirmed = []

    for category, rule, target_tenant in _parse_learn_actions(response):
        if target_tenant == "_user":
            effective_tenant = None
            is_personal = True
        elif target_tenant:
            effective_tenant = target_tenant
            is_personal = False
        else:
            effective_tenant = tenant_id
            is_personal = False

        try:
            try:
                from app.rule_validator import validate_rule_before_save, apply_validation_result
                result = validate_rule_before_save(
                    username, effective_tenant or tenant_id, category, rule
                )
                decision = result.get("decision", "NEW")
                if decision == "CONFLICT":
                    conflict_msg = result.get("conflict_message", "Conflit detecte avec une regle existante.")
                    confirmed.append(f"\u26a0\ufe0f Conflit de regle : {conflict_msg}")
                    continue
                if decision == "DUPLICATE":
                    confirmed.append(f"\U0001f9e0 Deja en memoire [{category}] (doublon ignore)")
                    continue
                messages = apply_validation_result(result, username, effective_tenant or tenant_id)
                label = " | ".join(messages) if messages else f"[{category}]"
                tenant_tag = f" @{target_tenant}" if target_tenant else ""
                confirmed.append(
                    f"\U0001f9e0 Memorise {label}{tenant_tag} : "
                    f"{rule[:120]}{'...' if len(rule) > 120 else ''}"
                )
                log_activity(username, "learn", category, rule[:100], tenant_id=effective_tenant or tenant_id)
            except ImportError:
                save_rule(category, rule, "auto", 0.7, username,
                          tenant_id=effective_tenant, personal=is_personal)
                tenant_tag = f" @{target_tenant}" if target_tenant else ""
                confirmed.append(
                    f"\U0001f9e0 Memorise [{category}]{tenant_tag} : "
                    f"{rule[:120]}{'...' if len(rule) > 120 else ''}"
                )
                log_activity(username, "learn", category, rule[:100], tenant_id=effective_tenant or tenant_id)
        except Exception as e:
            print(f"[LEARN] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', response):
        topic = match.group(1).strip()
        insight = match.group(2).strip()
        try:
            save_insight(topic, insight, "auto", username)
            confirmed.append(f"\U0001f4a1 Observe [{topic}] : {insight[:120]}{'...' if len(insight) > 120 else ''}")
            log_activity(username, "insight", topic, insight[:100], tenant_id=tenant_id)
        except Exception as e:
            print(f"[INSIGHT] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', response):
        rule_id = int(match.group(1))
        try:
            deleted = delete_rule(rule_id, username)
            confirmed.append(
                f"\U0001f5d1\ufe0f Regle {rule_id} desactivee." if deleted
                else f"\u274c Regle {rule_id} introuvable."
            )
        except Exception as e:
            print(f"[FORGET] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:SYNTH:\]', response):
        try:
            threading.Thread(
                target=lambda u=username, t=synth_threshold: synthesize_session(t, u),
                daemon=True
            ).start()
            confirmed.append("\U0001f504 Synthese lancee en arriere-plan.")
        except Exception as e:
            print(f"[SYNTH] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:RESTART_ONBOARDING:\]', response):
        try:
            from app.onboarding import restart_onboarding
            ok = restart_onboarding(username, tenant_id)
            confirmed.append(
                "\U0001f504 Questionnaire relance ! Recharge la page (F5)." if ok
                else "\u274c Impossible de relancer le questionnaire."
            )
        except Exception as e:
            print(f"[RESTART_ONBOARDING] Erreur: {e}")
            confirmed.append("\u274c Erreur lors du redemarrage du questionnaire.")

    return confirmed
