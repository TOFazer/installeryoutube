# Plan d'amélioration OverLoad

## État de l'implémentation de départ

Cette base ne contenait ni application, ni téléchargeur, ni intégration vidéo. Le socle livré met en place le post-téléchargement et les flux de préparation ci-dessous. Le téléchargement de sources en ligne et l'insertion automatique dans une timeline restent à connecter au code du téléchargeur / aux API officielles des logiciels.

| Priorité | Fonction | État dans ce socle |
|---|---|---|
| 1 | Détection du conteneur et des codecs | FFprobe, pistes, durée, dimensions, cadence et profils de compatibilité conservateurs. |
| 2 | Intégrité et erreurs compréhensibles | Taille reçue, détection des flux, décodage intégral avec FFmpeg si installé ; conservation en `Needs review` en cas de doute. |
| 3 | Conversion facultative | Profil MP4 H.264/AAC, copie/remultiplexage si possible, progression et annulation, original préservé. |
| 4 | Mode « Prêt pour le montage » | Projets avec sous-dossiers Vidéo/Audio/Images/Converted/Exports/Needs review, bibliothèque et diagnostics. |
| 5 | Logiciels de montage | Ouverture best-effort du média dans l'application installée et accès au dossier commun. Import/timeline et détection de version restent spécifiques aux logiciels. |
| 6 | Tests de non-régression | Tests unitaires simulés ajoutés ; matrice réelle à automatiser sur chaque OS et versions de logiciels. |

## Contrats de diagnostic

- **Intégrité** : `verified` (FFprobe puis décodage intégral FFmpeg réussi), `readable` (métadonnées lisibles, décodage intégral non effectué), `incomplete`, `size_mismatch`, `corrupt`, `not_media` ou `unverified`.
- **Compatibilité** : profil distinct par Premiere Pro, DaVinci Resolve et CapCut. Une mise en garde codec n'est pas une corruption.
- Un média sans piste audio est valide. Plusieurs pistes audio sont signalées ; elles sont conservées/copiées ou normalisées en AAC par le profil de conversion.
- En cas de taille reçue différente de la taille attendue, le fichier n'est jamais déclaré prêt, même si FFprobe peut encore lire son en-tête.
- L'analyse complète se fait après le transfert local. Un délai de décodage dépassé laisse le média à vérifier, sans le qualifier à tort de corrompu.

## Étapes suivantes

1. Connecter le bouton **Télécharger et importer** au téléchargeur réel et transmettre sa taille attendue / son état de fin au service de vérification.
2. Ajouter des essais de fixtures réelles (MP4 H.264/H.265/AV1, WebM VP9/AV1, MOV, MKV, fichier tronqué, pistes audio absentes/multiples) sur des versions FFmpeg supportées.
3. Tester les conversions sur divers débits, résolutions, fréquences d'images, HDR et fréquences d'images variables ; mesurer durée, taille et qualité avant/après.
4. Tester l'ouverture et l'importation avec les versions installées de Premiere Pro, Resolve et CapCut sous Windows/macOS ; implémenter des adaptateurs par version si leurs interfaces le permettent.
5. Exécuter cette matrice sur CI avec des médias de test redistribuables et documenter les versions des outils, sans ajouter de gros médias ni de fichiers sous licence au dépôt.
