        # REPLY — format [ACTION:REPLY:message_id:texte]
        # Regex robuste : message_id = tout sauf ':' (>20 chars), texte = tout jusqu'à ']'
        for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', aria_response, re.DOTALL):
            msg_id, reply_text = match.group(1).strip(), match.group(2).strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("❌ ID invalide pour réponse")
                continue
            try:
                result = perform_outlook_action("send_reply", {"message_id": msg_id, "reply_body": reply_text}, outlook_token)
                if result.get("status") == "ok":
                    try:
                        learn_from_correction(original="", corrected=reply_text, context="réponse mail")
                    except Exception:
                        pass
                actions_confirmed.append("✅ Réponse envoyée" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur envoi : {str(e)[:100]}")
