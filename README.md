# OverLoad — atelier média local

OverLoad prépare les médias téléchargés avant le montage : organisation par projet, détection des conteneurs et codecs, contrôle de lisibilité, diagnostic de compatibilité prudent et conversion facultative vers MP4 H.264/AAC.

> **État de cette base :** le dépôt ne contenait que son README initial — aucun téléchargeur ni intégration existante. Le bouton **Télécharger et importer** ouvre donc le sélecteur de fichiers et importe une copie locale déjà téléchargée. Il ne récupère pas encore de média depuis une URL ou un service. Le raccordement au moteur de téléchargement devra se faire lorsque son code et ses sources seront disponibles.

## Démarrage

Prérequis : Python 3.10 ou supérieur. L'interface et l'API n'utilisent que la bibliothèque standard Python.

```bash
python -m overload
```

OverLoad ouvre son interface dans le navigateur, sur `http://127.0.0.1:8765`. Pour choisir un port ou un dossier de données :

```bash
python -m overload serve --port 9000 --data-dir ~/Videos/OverLoad
```

Pour un lancement sans navigateur :

```bash
python -m overload serve --no-browser
```

Les projets sont enregistrés dans `~/.overload/projects` par défaut. `OVERLOAD_HOME` permet de remplacer cet emplacement. Les fichiers choisis dans le navigateur sont **copiés** dans le projet OverLoad ; le fichier source de l'utilisateur n'est ni déplacé ni supprimé.

## FFmpeg et FFprobe

Installe une distribution FFmpeg contenant **ffmpeg** et **ffprobe** et rends les deux exécutables accessibles dans le `PATH`. Sans FFprobe, OverLoad conserve les fichiers mais les marque **non vérifiés** ; il ne prétend pas connaître leurs codecs. Sans FFmpeg, l'analyse des métadonnées peut fonctionner avec FFprobe, mais le décodage intégral et la conversion ne sont pas disponibles.

Les chemins peuvent être définis explicitement avec `OVERLOAD_FFMPEG` et `OVERLOAD_FFPROBE`. La page d'accueil affiche l'état de ces outils.

Un import vérifie d'abord la taille reçue lorsque celle du fichier source est connue et lit les métadonnées avec FFprobe. Si FFmpeg est disponible, OverLoad tente aussi de décoder les flux audio et vidéo jusqu'au bout. Une vérification complète peut donc prendre du temps ; l'interface n'affiche pas le média comme intégralement vérifié avant sa fin. Les avertissements de compatibilité codec ne sont pas confondus avec les erreurs d'intégrité.

## Fonctions incluses

- Conteneurs et flux vidéo/audio : MP4, WebM, MKV, MOV et autres formats reconnus par FFprobe ; codec, durée, dimensions, cadence, nombre de pistes audio.
- Diagnostic séparé pour média lisible, codec à risque, taille incomplète, flux indécodables et absence d'outils.
- Classement automatique dans `Media/Video`, `Media/Audio`, `Media/Images` ou `Needs review`.
- Profil facultatif **MP4 H.264/AAC** dans `Converted`. Les médias déjà compatibles peuvent être remultiplexés/copier les flux ; sinon FFmpeg réencode. L'original reste intact, la résolution n'est pas réduite et la cadence n'est pas forcée par une option de sortie.
- Progression, estimation du temps restant lorsque FFmpeg la fournit et annulation des tâches de conversion.
- Ouverture du fichier par l'application système, ouverture du dossier de projet et lancement best-effort dans Premiere Pro, DaVinci Resolve ou CapCut lorsque l'application est détectée.
- Une structure de projet commune, indépendante du logiciel de montage, et un manifeste JSON local.

## Limites importantes

- Le diagnostic de compatibilité est volontairement conservateur : la prise en charge exacte dépend de la version, du système d'exploitation et des extensions installées. OverLoad n'interroge pas encore la version précise de Premiere Pro/Resolve/CapCut.
- « Ouvrir dans un logiciel » lance l'application avec le fichier en argument lorsque possible. L'import dans un projet ou une timeline n'est pas garanti par une interface de ligne de commande commune ; l'utilisateur peut devoir confirmer l'import dans l'application.
- Cette version importe des fichiers locaux déjà téléchargés ; elle ne surveille pas un dossier de téléchargement et ne contient pas de fournisseur/téléchargeur média.
- Les médias sont copiés dans le dossier de données OverLoad ; prévois l'espace disque nécessaire aux originaux et aux versions converties.
- Le serveur écoute sur `127.0.0.1` par défaut et vérifie l'en-tête `Host` pour limiter les requêtes par rebinding DNS. Les hôtes locaux et le domaine de prévisualisation Arena (`*.e2b.app`) sont autorisés ; pour un proxy inverse de confiance, configure `OVERLOAD_ALLOWED_HOSTS`. Ne l'expose pas sur un réseau public sans ajouter une authentification et une politique d'accès adaptées.

## CLI

Inspecter un média et imprimer le rapport JSON :

```bash
python -m overload inspect "clip.mp4" --editor premiere
python -m overload inspect "clip.webm" --editor resolve --expected-size 28400123
python -m overload inspect "clip.mov" --metadata-only
```

Les codes de sortie de `inspect` sont `0` pour un fichier vérifié/lisible et `1` lorsqu'il est incomplet, corrompu ou non vérifié. `--metadata-only` évite le décodage intégral.

## Développement et tests

```bash
python -m unittest discover -s tests -v
```

Les tests unitaires simulent FFprobe/FFmpeg et n'exigent pas leur installation. Un test d'intégration réel (dimensions, cadence, taille et SSIM) s'exécute si FFmpeg dispose de `libx264` et du filtre `ssim`, sinon il est ignoré. Les essais avec plusieurs versions de logiciels de montage restent à effectuer sur les systèmes cibles.

Voir [`docs/ROADMAP.md`](docs/ROADMAP.md) pour le découpage d'implémentation et les validations prévues.
