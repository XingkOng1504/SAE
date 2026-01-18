import sqlite3
import os
import bcrypt
from app.models.User import User
from app.models.UserDAOInterface import UserDAOInterface
from flask import current_app

class UserSqliteDAO(UserDAOInterface):
    """
    User data access object dédié à SQLite
    """

    def __init__(self):
        # On pointe vers le dossier instance/database.db
        # Si on est dans le contexte flask, on utilise current_app, sinon un chemin relatif par défaut
        if current_app:
             self.databasename = os.path.join(current_app.instance_path, 'database.db')
        else:
             # Fallback si appelé hors contexte (rare avec le factory pattern)
             self.databasename = os.path.join('instance', 'database.db')
        
        self._initTable()

    def _getDbConnection(self):
        conn = sqlite3.connect(self.databasename)
        conn.row_factory = sqlite3.Row
        return conn

    def _initTable(self):
        conn = self._getDbConnection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY,
                password TEXT NOT NULL,
                switchmdp INTEGER NOT NULL DEFAULT 1
            );
        ''')
        conn.commit()
        conn.close()
    
    def _generatePwdHash(self, password):
        password_bytes = password.encode('utf-8')
        hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        password_hash = hashed_bytes.decode('utf-8')
        return password_hash

    def verifyMDP(self, password):
        conn = self._getDbConnection()
        try:
            user = conn.execute("SELECT * FROM admin WHERE id = ?;",(1,)).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
        
        if user:
            password_bytes = password.encode('utf-8')
            stored_hash_bytes = user["password"].encode('utf-8')
            
            if bcrypt.checkpw(password_bytes, stored_hash_bytes):
                return User(user)
                
        return None 
    
    def change_mdp(self, mdp):
        mdphashed = self._generatePwdHash(mdp)
        conn = self._getDbConnection()
        conn.execute("update admin set password = ?, switchmdp = ? where id = 1;",(mdphashed,0,))
        conn.commit()
        conn.close()
        user = self.verifyMDP(mdp)
        if user :
            return True 
        return False 
        
    def getSwitch_mdp(self):
        conn = self._getDbConnection()
        var = conn.execute("select switchmdp from admin where id = 1;").fetchone()
        conn.close()
        return var[0]