from flask import Blueprint, render_template
from app.services.ScoDocService import ScoDocService
from app.DonneeDAO import DonneeDAO
# On importe le décorateur de sécurité
from app.tools import reqlogged

# Création du Blueprint
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin', methods=['GET'])
@reqlogged
def admin_dashboard():
    """Affiche la page d'administration"""
    return render_template('admin.html')

@admin_bp.route('/admin/init', methods=['POST'])
@reqlogged
def initialisation():
    """Lance l'initialisation de la BDD (Action du formulaire 1)"""
    dao = DonneeDAO()
    msg_db = None

    try:
        dao.init_db()
        msg_db = "Base de données initialisée avec succès."
    except Exception as e:
        msg_db = f"Erreur lors de l'initialisation : {e}"

    return render_template("admin.html", msg_db=msg_db)

@admin_bp.route('/admin/sync', methods=['POST'])
@reqlogged
def synchronisation():
    """Lance la synchronisation JSON (Action du formulaire 2)"""
    service = ScoDocService()
    stats = None
    msg_import = None

    try:
        stats = service.run_synchronisation()
        msg_import = "Données importées avec succès."
    except Exception as e:
        msg_import = f"Erreur Import : {e}"
    
    return render_template('admin.html', msg_import=msg_import, stats=stats)