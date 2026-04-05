from app.assistant_analyzer import analyze_single_mail

fake_message = {
    "subject": "Demande raccordement ENEDIS",
    "from": {"emailAddress": {"address": "client@test.com"}},
    "bodyPreview": "Pouvez-vous me confirmer le raccordement ? Merci."
}

result = analyze_single_mail(fake_message)

print(result)