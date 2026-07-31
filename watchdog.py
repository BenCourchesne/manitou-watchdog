#!/usr/bin/env python3
"""Watchdog Firebase Lac Manitou -> Pushover.

Vérifie que la base RTDB continue de recevoir des données :
  1. /readings  — écriture Home Assistant toutes les 5 min (santé du Pi/HA + écriture Firebase)
  2. /daily     — agrégation horaire des jours complétés (Option A)

Lecture publique (.read = true) : aucun secret Firebase requis.
Seuls PUSHOVER_TOKEN / PUSHOVER_USER doivent être fournis en variables d'env.
"""
import os
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DB = "https://lac-manitou-temperatures-d284a-default-rtdb.firebaseio.com"

# Seuils (surchargeable via variables d'env)
MAX_READINGS_AGE_MIN = int(os.environ.get("MAX_READINGS_AGE_MIN", "30"))  # writes 5 min -> 30 min = 6 cycles ratés
MAX_DAILY_AGE_H = int(os.environ.get("MAX_DAILY_AGE_H", "60"))            # sain: 24-50 h ; alerte au-dela

PO_TOKEN = os.environ["PUSHOVER_TOKEN"]
PO_USER = os.environ["PUSHOVER_USER"]


def latest_key_ms(node):
    """Plus grande clé (timestamp ms) du noeud, filtrée cote serveur (1 seul enregistrement)."""
    q = urllib.parse.urlencode({"orderBy": '"$key"', "limitToLast": 1})
    url = f"{DB}/{node}.json?{q}"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    if not data:
        return None
    return int(next(iter(data)))  # les clés ms font 13 chiffres -> ordre lexical == numerique


def push(title, msg, priority=0):
    body = urllib.parse.urlencode({
        "token": PO_TOKEN,
        "user": PO_USER,
        "title": title,
        "message": msg,
        "priority": priority,
    }).encode()
    with urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=body, timeout=20) as r:
        r.read()


def main():
    now = time.time()
    alerts = []

    # 1) /readings — santé live
    try:
        r_ms = latest_key_ms("readings")
        if r_ms is None:
            alerts.append("- /readings est VIDE (aucune donnee lisible).")
        else:
            age_min = (now - r_ms / 1000) / 60
            print(f"readings: derniere donnee il y a {age_min:.1f} min")
            if age_min > MAX_READINGS_AGE_MIN:
                alerts.append(
                    f"- Aucune donnee live depuis {age_min:.0f} min (seuil {MAX_READINGS_AGE_MIN} min). "
                    f"Pi/HA hors ligne ou ecriture Firebase en echec."
                )
    except Exception as e:
        alerts.append(f"- Lecture /readings impossible: {e}")

    # 2) /daily — agregation horaire
    try:
        d_ms = latest_key_ms("daily")
        if d_ms is None:
            alerts.append("- /daily est VIDE (agregation jamais executee ?).")
        else:
            age_h = (now - d_ms / 1000) / 3600
            day = datetime.fromtimestamp(d_ms / 1000, timezone.utc).date()
            print(f"daily: dernier jour agrege {day} (il y a {age_h:.1f} h)")
            if age_h > MAX_DAILY_AGE_H:
                alerts.append(
                    f"- Agregation /daily figee: dernier jour {day} (il y a {age_h:.0f} h, seuil {MAX_DAILY_AGE_H} h). "
                    f"Script horaire manitou_aggregate_daily en panne ?"
                )
    except Exception as e:
        alerts.append(f"- Lecture /daily impossible: {e}")

    if alerts:
        push("Watchdog Lac Manitou", "\n".join(alerts), priority=1)
        print("ALERTE ENVOYEE")
    else:
        print("OK - tout est frais.")


if __name__ == "__main__":
    main()
