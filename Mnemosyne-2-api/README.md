## VFINALE du projet
### Récupérer le projet
dans le terminal 
```
git clone https://github.com/Solene0971/Mnemosyne.git
```

### Ajouter les identifiants ScoDoc

Aller dans le fichier app/models/ScoDocAPI.py
Lignes 21,21 -> mettre les identifiants et mot de passe vers ScoDoc

### Lancer le projet

```
cd Mnemosyne/
python3 main.py
```

Ouvir http://localhost:8000 sur firefox

cliquer sur le bouton 'SUPPRIMER LA MÉMOIRE' pour réinitialiser la bd.
Puis,
cliquer sur le bouton 'Import des données' pour insérer les données à partir de ScoDoc.

Les messages de fonctionnement ou d'erreurs spécifiques sont visibles dans le terminal depuis lequel vous avez lancer `python3 main.py`

Le site peut afficher l'erreur qui a bloqué l'insertion des données. Si aucune connection à l'API est possible, la liste des données insérés sera à 0, ce qui ait parti du fonctionnement normal.
