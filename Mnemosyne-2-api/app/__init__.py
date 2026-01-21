import os
from flask import Flask, g

def create_app():
    # Configuration des chemins
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
    DB_PATH = os.path.join(INSTANCE_DIR, 'scolarite.db')
    
    app = Flask(__name__, instance_path=INSTANCE_DIR)
    app.config['DATABASE'] = DB_PATH

    # Config Auth
    app.config["SESSION_COOKIE_SECURE"] = False 
    app.secret_key = 'votre_cle_secrete_ici' # Changez ceci en prod

    try:
        os.makedirs(INSTANCE_DIR)
    except OSError:
        pass

    # --- Enregistrement des Blueprints ---
    from app.controllers.IndexController import index_bp
    # On retire SynchroController car il est fusionné dans Admin
    from app.controllers.LoginController import login_bp
    from app.controllers.AdminController import admin_bp
    
    app.register_blueprint(index_bp)
    app.register_blueprint(login_bp)
    app.register_blueprint(admin_bp)

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    return app