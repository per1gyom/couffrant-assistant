"""
Endpoints webhooks Raya.

Pipeline Microsoft Graph (5 niveaux) :
  1a. Whitelist Raya (mail_filter autoriser:) → court-circuite le filtre statique
  1b. Filtre heuristique statique (noreply / newsletters / bulk domains)
  1c. Blacklist Raya (mail_filter bloquer:) → bloc supplémentaire
  2.  Règles anti_spam personnalisées
  3.  Triage Haiku : IGNORER / STOCKER_SIMPLE / ANALYSER
  4.  Analyse complète ou stockage simple + stockage
  5.  Scoring d'urgence + alerte shadow ou réelle (Phase 7)

process_incoming_mail() est source-agnostic (7-1b) :
consommé par le webhook Microsoft ET le polling Gmail.
Definition dans app/routes/webhook_ms_handlers.py.

Patterns statiques (_NOREPLY_PREFIXES, _BULK_DOMAINS, _BULK_SUBJECT_KEYWORDS)
sont definis dans webhook_microsoft.py, ou ils sont reellement utilises par
_is_bulk_heuristic(). Ils etaient ici (resilience SPLIT-R3) mais morts.
Deplaces le 01/05/2026 dans le cadre du fix import circulaire.

7-7 : heartbeat webhook_microsoft après traitement réussi.
7-8 : endpoint POST /webhook/twilio (WhatsApp entrant).
USER-PHONE : _resolve_user_by_phone cherche d'abord en base (colonne phone),
             puis tombe sur les variables d'env pour la compatibilité.
WHATSAPP-RAYA : texte libre WhatsApp → vraie réponse LLM de Raya (Sonnet,
                max 512 tokens), sauvegardée dans aria_memory.
"""
import re
import threading
from fastapi import APIRouter, Request, Response

# NOTE 01/05/2026 : l import circulaire entre webhook_ms_handlers et
# webhook_microsoft a ete corrige (suppression de la ligne morte
# "from app.routes.webhook_ms_handlers import process_incoming_mail,
# _process_mail" dans webhook_microsoft.py). L import lazy ci-dessous
# n est donc plus une protection contre un cycle, juste un import
# tardif normal.

router = APIRouter(tags=["webhook"])


# ─── RÈGLES RAYA (mail_filter) ───
# ─── PIPELINE COMMUN (source-agnostic) ───
@router.get("/webhook/microsoft")
async def webhook_validation_get(validationToken: str = ""):
    if validationToken:
        return Response(content=validationToken, media_type="text/plain", status_code=200)
    return Response(status_code=200)


@router.post("/webhook/microsoft")
async def webhook_notification(request: Request):
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    try:
        body = await request.json()
    except Exception:
        return Response(status_code=202)

    from app.connectors.microsoft_webhook import get_subscription_info
    from app.mail_memory_store import mail_exists
    import os

    # Etape 3.6 (01/05/2026) : mode TRIGGER vs FETCH (legacy)
    # 
    # MODE LEGACY (defaut) : pour chaque notif, fetch direct du mail via
    #   Graph API et ingestion immediate via process_incoming_mail.
    #
    # MODE TRIGGER : pour chaque notif, le webhook ne fait QUE declencher
    #   un poll delta sur la connexion concernee. Le polling delta voit
    #   le nouveau mail et l ingere (en mode WRITE).
    #   Avantage : un seul code path d ingestion. Si le webhook plante,
    #   le poll automatique toutes les 5 min rattrape.
    #
    # Activable via Railway : OUTLOOK_WEBHOOK_TRIGGER_MODE=true
    trigger_mode = os.getenv("OUTLOOK_WEBHOOK_TRIGGER_MODE", "").strip().lower() in ("1", "true", "yes", "on")

    # Dedup : on ne declenche qu un seul poll par connexion meme si Microsoft
    # envoie plusieurs notifs en meme temps (evite N polls inutiles).
    triggered_connections = set()

    for notification in body.get("value", []):
        subscription_id = notification.get("subscriptionId", "")
        sub_info = get_subscription_info(subscription_id)
        if not sub_info:
            continue
        if notification.get("clientState") != sub_info["client_state"]:
            continue

        username = sub_info["username"]
        connection_id = sub_info.get("connection_id")

        if trigger_mode:
            # MODE TRIGGER (Etape 3.6) : declenchement d un poll delta
            # sur la connexion. Le poll delta s occupe de tout le pipeline
            # d ingestion (mail_exists, filtrage, analyse, stockage).
            if connection_id and connection_id not in triggered_connections:
                triggered_connections.add(connection_id)
                threading.Thread(
                    target=_trigger_outlook_delta_poll,
                    args=(connection_id, username),
                    daemon=True,
                ).start()
            continue

        # MODE LEGACY : fetch direct + ingest
        resource = notification.get("resource", "")
        resource_data = notification.get("resourceData") or {}
        message_id = resource_data.get("id") or ""
        if not message_id and "Messages/" in resource:
            message_id = resource.split("Messages/")[-1]

        if not message_id or mail_exists(message_id, username):
            continue

        # Import lazy : tardif mais plus pour eviter un cycle (le cycle a
        # ete corrige le 01/05/2026 dans webhook_microsoft.py). Maintenu
        # car ce module charge de nombreuses dependances IA / DB / etc,
        # pas la peine de le charger au demarrage.
        from app.routes.webhook_ms_handlers import _process_mail

        threading.Thread(
            target=_process_mail,
            args=(username, message_id),
            daemon=True
        ).start()

    return Response(status_code=202)


def _trigger_outlook_delta_poll(connection_id: int, username: str):
    """Mode TRIGGER (Etape 3.6) : declenche un poll delta immediat sur une
    connexion specifique apres reception d une notification Microsoft.

    Reutilise _poll_user_outlook du module mail_outlook_delta_sync (Etape 3.3)
    qui fait deja tout le boulot : delta query Microsoft, traitement via
    process_incoming_mail (mode WRITE), stockage delta_link, log dans
    connection_health_events.

    Beneficie automatiquement de :
      - Anti-doublon (mail_exists)
      - Resilience (retries, gestion erreurs)
      - Multi-folder (Inbox + SentItems + JunkEmail)
      - Inscription dans connection_health
      - Fix tenant_id (insert_mail corrige)

    Run en thread daemon depuis webhook_notification.
    """
    from app.app_security import get_tenant_id
    from app.jobs.mail_outlook_delta_sync import _poll_user_outlook

    try:
        tenant_id = get_tenant_id(username)
        if not tenant_id:
            print(f"[Webhook][Trigger] tenant_id introuvable pour {username}")
            return

        result = _poll_user_outlook(
            connection_id=connection_id,
            tenant_id=tenant_id,
            username=username,
        )
        print(f"[Webhook][Trigger] Poll delta conn#{connection_id} ({username}) : "
              f"status={result.get('status')}, "
              f"items_new={result.get('total_items_new', 0)}, "
              f"processed={result.get('total_processed', 0)}")
    except Exception as e:
        print(f"[Webhook][Trigger] Echec poll delta conn#{connection_id} : {e}")


# ─── LIFECYCLE NOTIFICATIONS (Phase Connexions Universelles - Etape 3.5) ───

@router.get("/webhook/microsoft/lifecycle")
async def webhook_lifecycle_validation_get(validationToken: str = ""):
    """Validation initiale de l URL lifecycle (Microsoft Graph).
    Microsoft envoie un GET avec validationToken au moment de la creation
    de la subscription pour verifier que l URL existe et fonctionne.
    """
    if validationToken:
        return Response(content=validationToken, media_type="text/plain",
                        status_code=200)
    return Response(status_code=200)


@router.post("/webhook/microsoft/lifecycle")
async def webhook_lifecycle_notification(request: Request):
    """Endpoint des Lifecycle Notifications Microsoft Graph.

    Phase Connexions Universelles - Etape 3.5 (1er mai 2026).
    AURAIT EVITE LE BUG 17 JOURS du 14/04 au 01/05.

    Events recus :
      - subscriptionRemoved : Microsoft a supprime la sub silencieusement
        -> recreation automatique
      - missed : une notif a ete loupee (timing serveur, redemarrage Raya)
        -> declenchement d un poll delta force pour rattraper
      - reauthorizationRequired : token va expirer dans peu de temps
        -> tentative refresh + renouvellement de la sub
    """
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain",
                        status_code=200)

    try:
        body = await request.json()
    except Exception:
        return Response(status_code=202)

    from app.connectors.microsoft_webhook import get_subscription_info

    for notification in body.get("value", []):
        try:
            subscription_id = notification.get("subscriptionId", "")
            lifecycle_event = notification.get("lifecycleEvent", "")
            sub_info = get_subscription_info(subscription_id)

            if not sub_info:
                # Sub inconnue (peut etre orpheline / supprimee de notre cote)
                continue
            if notification.get("clientState") != sub_info["client_state"]:
                # Securite : on rejette si le clientState ne match pas
                continue

            username = sub_info["username"]

            # Lance le traitement en thread (ne pas bloquer Microsoft Graph)
            threading.Thread(
                target=_handle_lifecycle_event,
                args=(lifecycle_event, subscription_id, username),
                daemon=True,
            ).start()

        except Exception as e:
            # Best effort : on log mais on retourne 202 pour eviter que
            # Microsoft considere notre endpoint defaillant
            print(f"[Lifecycle] Erreur traitement notification : {e}")

    return Response(status_code=202)


def _handle_lifecycle_event(lifecycle_event: str, subscription_id: str,
                              username: str):
    """Traitement d un evenement lifecycle Microsoft Graph en background.

    Run en thread daemon depuis webhook_lifecycle_notification.
    """
    print(f"[Lifecycle] Event recu : {lifecycle_event} pour sub={subscription_id} user={username}")

    try:
        if lifecycle_event == "subscriptionRemoved":
            _handle_subscription_removed(subscription_id, username)
        elif lifecycle_event == "missed":
            _handle_missed_notification(subscription_id, username)
        elif lifecycle_event == "reauthorizationRequired":
            _handle_reauthorization_required(subscription_id, username)
        else:
            print(f"[Lifecycle] Event non gere : {lifecycle_event}")
    except Exception as e:
        print(f"[Lifecycle] Crash _handle_lifecycle_event : {e}")


def _handle_subscription_removed(subscription_id: str, username: str):
    """Subscription supprimee par Microsoft. On recree.

    C est EXACTEMENT le scenario du bug 17 jours : Microsoft a desactive la
    sub silencieusement apres 4 erreurs 500 en cascade. Avec lifecycle,
    on est prevenu et on recree automatiquement.

    Apres recreation, on declenche aussi un poll delta force pour rattraper
    les mails qui auraient pu arriver pendant le creneau ou la sub etait
    morte.
    """
    from app.connectors.microsoft_webhook import (
        _delete_subscription_from_db, create_subscription,
    )
    from app.token_manager import get_valid_microsoft_token

    print(f"[Lifecycle][CRITICAL] subscriptionRemoved pour {username} - recreation auto")

    # 1. Supprimer la sub morte de notre DB
    _delete_subscription_from_db(subscription_id)

    # 2. Recreer la subscription
    try:
        token = get_valid_microsoft_token(username)
        if token:
            new_sub = create_subscription(token, username)
            if new_sub:
                print(f"[Lifecycle] Sub recreee pour {username} : {new_sub.get('id')}")
            else:
                print(f"[Lifecycle] ECHEC recreation sub pour {username}")
        else:
            print(f"[Lifecycle] Pas de token pour {username} - alerte")
    except Exception as e:
        print(f"[Lifecycle] Erreur recreation sub {username} : {e}")

    # 3. Alerte via dispatcher pour informer l user (l incident a ete auto-resolu)
    try:
        from app.alert_dispatcher import send
        from app.app_security import get_tenant_id
        tenant_id = get_tenant_id(username)
        send(
            severity="warning",
            title="Subscription Microsoft auto-recreee",
            message=(
                f"Microsoft a supprime la subscription mail Outlook pour {username}. "
                f"Raya l a auto-recreee. Aucun mail manque (le polling delta tourne "
                f"en parallele) mais l incident est trace pour investigation."
            ),
            tenant_id=tenant_id,
            username=username,
            source_type="microsoft_lifecycle",
            source_id=subscription_id,
            component=f"lifecycle_{username}",
            alert_type="subscription_recreated",
        )
    except Exception as e:
        print(f"[Lifecycle] Alerte echec : {e}")


def _handle_missed_notification(subscription_id: str, username: str):
    """Une notification a ete loupee (timing serveur Microsoft, redemarrage
    Raya, surcharge). On rattrape via le polling delta.
    """
    print(f"[Lifecycle] missed pour {username} - pas d action urgente")
    print(f"[Lifecycle] Le polling delta toutes les 5 min va rattraper")
    # Pas besoin de declencher un poll force : le polling tourne deja toutes
    # les 5 min via le scheduler. Les mails missed seront recuperes au
    # prochain cycle.


def _handle_reauthorization_required(subscription_id: str, username: str):
    """Le token va expirer dans peu de temps. On le refresh et on renouvelle
    la sub pour eviter qu elle expire.
    """
    from app.connectors.microsoft_webhook import renew_subscription
    from app.token_manager import get_valid_microsoft_token

    print(f"[Lifecycle] reauthorizationRequired pour {username} - refresh + renew")

    try:
        # get_valid_microsoft_token fait deja le refresh si necessaire
        token = get_valid_microsoft_token(username)
        if token:
            ok = renew_subscription(token, subscription_id, username)
            if ok:
                print(f"[Lifecycle] Sub {subscription_id} renouvelee apres refresh token")
            else:
                print(f"[Lifecycle] Renew sub echec pour {username}")
        else:
            print(f"[Lifecycle] Token refresh echec pour {username} - alerte user")
            # Le token est mort, alerte
            try:
                from app.alert_dispatcher import send
                from app.app_security import get_tenant_id
                tenant_id = get_tenant_id(username)
                send(
                    severity="attention",
                    title="Token Microsoft expire bientot",
                    message=(
                        f"Microsoft demande la reauthorisation du compte {username}. "
                        f"Reconnecte via /login pour eviter une coupure."
                    ),
                    tenant_id=tenant_id,
                    username=username,
                    actions=[
                        {"label": "Reconnecter Outlook",
                         "url": "/login?provider=microsoft"},
                    ],
                    source_type="microsoft_lifecycle",
                    source_id=subscription_id,
                    component=f"lifecycle_{username}_reauth",
                    alert_type="reauthorization_required",
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[Lifecycle] Erreur reauth {username} : {e}")


@router.post("/webhook/twilio")
async def webhook_twilio(request: Request):
    """
    Webhook Twilio pour les messages WhatsApp entrants. (7-8)
    L'utilisateur répond à un message Raya depuis WhatsApp.
    """
    try:
        form = await request.form()
        from_number = form.get("From", "").replace("whatsapp:", "").strip()
        body = form.get("Body", "").strip()

        if not from_number or not body:
            return Response(status_code=200)

        username = _resolve_user_by_phone(from_number)
        if not username:
            print(f"[Twilio] Numéro inconnu : {from_number}")
            return Response(status_code=200)

        threading.Thread(
            target=_handle_whatsapp_command,
            args=(username, body, from_number),
            daemon=True,
        ).start()

    except Exception as e:
        print(f"[Twilio] Erreur webhook: {e}")

    return Response(status_code=200)

