import sqlite3
import bcrypt
import os

# Configuration des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'database.db') # La base pour l'admin
SCHEMA_PATH = os.path.join(BASE_DIR, 'app', 'schema_admin.sql')

# Création du dossier instance s'il n'existe pas
if not os.path.exists(INSTANCE_DIR):
    os.makedirs(INSTANCE_DIR)

def _generatePwdHash(password):
    password_bytes = password.encode('utf-8')
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    password_hash = hashed_bytes.decode('utf-8')
    return password_hash

# Mot de passe par défaut
mdp = _generatePwdHash("mnemosyne")

print(f"Connexion à la base de données : {DB_PATH}")
connection = sqlite3.connect(DB_PATH)

print(f"Exécution du script SQL : {SCHEMA_PATH}")
with open(SCHEMA_PATH, 'r') as f:
    connection.executescript(f.read())

cur = connection.cursor()

# Insertion de l'admin
try:
    cur.execute("insert into admin (password) values (?)", (mdp,))
    print("Utilisateur admin créé avec succès.")
except sqlite3.Error as e:
    print(f"Erreur lors de l'insertion : {e}")

connection.commit()
connection.close()