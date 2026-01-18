## Pour lancer le code avec linux pour la prmeière fois

```
git clone https://github.com/Solene0971/Mnemosyne.git
cd Mnemosyne/
python3 main.py
```
aller dans la page setup pour initialiser et synchroniser la base de données 

### Si vous avez dejà récupéré le projet avant
Dans le dossier du projet, lancer :

```
git pull
```

pour voir la version 1.0 du code avec API :

```
git checkout v1-api
```

pour voir la version 2.0 du code avec API :

```
git checkout v2-api
```

pour voir la version de base sans API :

```
git checkout main
```

Pour voir dans quelle branche du projet vous êtes acuellement :
```
git status
```


les fichiers ScoDocAPI.py et services/ScoDocService.py permettent la synchronisation des données provenant de ScoDoc.

l'initialisation de la base de données se fait avec avec le services/DonneeService.py et DonneeDao.py
