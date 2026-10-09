# Changelog

## v1.0.0 — Première version publique

- Interface PySide6 sombre/claire : Accueil, Téléchargements, Projets, Bibliothèque, Paramètres
- Analyse des liens : miniature, titre, durée, qualités réellement disponibles, taille estimée, images/s, codec
- Formats : MP4 H.264 (compatible montage), Original (VP9/AV1), MP3 320 kbps, WAV
- File d'attente : téléchargements simultanés, lots de liens, doublons évités, annuler / réessayer
- Vitesse réelle en Mo/s, temps restant, graphique en direct, connexions parallèles adaptatives
- Reprise des téléchargements interrompus, nouvelles tentatives automatiques
- Vérification d'intégrité (FFmpeg) et empreinte SHA-256 de chaque fichier
- Mode Monteur : un dossier par projet, classement par projet ou par source, modèles de nommage
- Bibliothèque consultable par recherche, avec les informations techniques de chaque fichier
- Français / anglais, notifications, vérification des mises à jour (Releases GitHub)
- Installateur Windows (raccourci bureau en option), version portable, SHA256SUMS
- Script de benchmark reproductible
