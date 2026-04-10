    # 8. Réponse propre — retire les balises [ACTION:...] du texte affiché
    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', raya_response).strip()
    if actions_confirmed:
        # \n\n entre chaque confirmation pour séparation correcte en Markdown
        clean_response += "\n\n" + "\n\n".join(actions_confirmed)
