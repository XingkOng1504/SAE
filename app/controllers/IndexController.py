from flask import Blueprint, render_template, request, url_for
from app.services.DonneeService import DonneeService
import sqlite3

index_bp = Blueprint('index', __name__)

@index_bp.route('/', methods=['GET'])
def index():
    """Affiche uniquement le formulaire de recherche"""
    service = DonneeService()
    departements = []
    annees = []
    db_error = False

    try:
        if not service.is_database_ready():
            db_error = True
        else:
            departements = service.get_form_dept()
            annees = service.get_form_annees()

    except Exception as e:
        db_error = True
        print(f"Erreur BDD : {e}")

    return render_template('index.html', 
                           depts=departements,
                           annees=annees, 
                           db_error=db_error)

@index_bp.route('/cohorte', methods=['POST', 'GET'])
def cohorte():
    """Traite le formulaire et affiche le tableau de résultats"""
    service = DonneeService()
    results = []
    sankey_stats = None
    
    # Récupération des données du formulaire (POST) ou URL (GET)
    if request.method == 'POST':
        selected_dept = request.form.get('departement') 
        selected_year = request.form.get('annee')
        selected_rythme = request.form.get('rythme')
    else:
        selected_dept = request.args.get('dept') 
        selected_year = request.args.get('year')
        selected_rythme = request.args.get('rythme', 'TOUS')

    try:
        results = service.get_search_results(selected_year, selected_dept, selected_rythme)
        sankey_stats = service.get_sankey_stats(selected_year, selected_dept, selected_rythme)
    except Exception as e:
        print(f"Erreur recherche : {e}")
        results = []
        sankey_stats = None

    return render_template('cohorte.html', 
                           results=results, 
                           sel_dept=selected_dept, 
                           sel_year=selected_year,
                           sel_rythme=selected_rythme,
                           selected_year=int(selected_year) if selected_year else 2021,
                           selected_dept=selected_dept or '',
                           selected_rythme=selected_rythme or 'TOUS',
                           sankey_stats=sankey_stats)