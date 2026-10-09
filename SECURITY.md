# Sécurité

- OverLoad n'accepte que les liens `http`/`https` publics : adresses locales et privées, identifiants dans l'URL et autres schémas sont refusés.
- Les noms de fichiers sont assainis ; aucun fichier existant n'est écrasé.
- Les mises à jour sont vérifiées **uniquement** via les Releases GitHub officielles de `TOFazer/OverLoad`, chaque fichier étant accompagné d'un `SHA256SUMS.txt`.

Tu as trouvé une faille ? Ne la publie pas : signale-la en privé via l'onglet *Security* du dépôt GitHub (Report a vulnerability).
