from flask import Blueprint, render_template, request, redirect, url_for
from app.services.ScoDocService import ScoDocService
from app.services.DonneeService import DonneeService
from app.tools import reqlogged
from app.services.RegleService import RegleService

# Création du Blueprint
admin_bp = Blueprint('admin', __name__)
#Création de l'objet AdminController
rs = RegleService()

@admin_bp.route('/admin', methods=['GET'])
@reqlogged
def admin_dashboard():
    """Affiche la page d'administration"""
    r = rs.get_regles()
    return render_template('admin.html', rules = r)

@admin_bp.route('/admin/init', methods=['POST'])
@reqlogged
def initialisation():
    """Lance l'initialisation de la BDD (Action du formulaire 1)"""
    dao = DonneeService()
    msg_db = None

    try:
        dao.creation_db()
        msg_db = "Base de données initialisée avec succès."
        print("lancement")
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
    
    r = rs.get_regles()
    return render_template('admin.html', msg_import=msg_import, stats=stats, rules=r)

@admin_bp.route('/admin/addregle', methods=['POST'])
@reqlogged
def ajouteRegle():
    nom = request.form.get('nom')
    description = request.form.get('description')
    condition = request.form.get("condition")

    if nom and description and condition:
        rs.ajouter_regle(
            nom,
            description,
            condition
        )

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/delregle', methods=['POST'])
@reqlogged
def suppRegle():
    index = int(request.form.get('index'))
    rs.supprimer_regle(index)
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/update_statut', methods=['POST'])
@reqlogged
def update_statut():

    index = int(request.form.get("index"))

    # Si la checkbox existe dans le form → True, sinon False
    statut = "statut" in request.form

    rs.modifier_statut(index, statut)

    return redirect(url_for('admin.admin_dashboard'))