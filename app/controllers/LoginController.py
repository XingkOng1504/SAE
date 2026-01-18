from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from app.services.UserService import UserService
# On importe le décorateur depuis notre nouveau fichier tools
from app.tools import reqlogged

login_bp = Blueprint('login', __name__)

us = UserService()

@login_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    msg_error = None
    if request.method == 'POST':
        # On récupère le mot de passe
        pwd = request.form.get("password")
        user = us.login(pwd)
        
        if user:
            session["logged"] = True
            # Si l'utilisateur doit changer son mot de passe
            if us.getSwitchMDP() == 1:
                return redirect(url_for("login.switchmdp"))
            # Sinon direction le dashboard admin
            return redirect(url_for("admin.admin_dashboard"))
        else:
            msg_error = 'Identifiants invalides'
            
    return render_template('login.html', msg_error=msg_error)

@login_bp.route('/switchmdp', methods=['POST', 'GET'])
@reqlogged
def switchmdp():
    if request.method == 'POST':
        new_mdp = request.form.get("new_password")
        if new_mdp:
            us.changepwd(new_mdp)
            flash("Mot de passe modifié avec succès.", "success")
            return redirect(url_for('admin.admin_dashboard'))
        else:
            return "Aucun mot de passe reçu !", 400

    # Note: Idéalement, mettez ce HTML dans switchmdp.html
    return render_template('switchmdp.html') 

@login_bp.route('/logout')
@reqlogged
def logout():
    session.clear()
    flash('Déconnexion réussie.', 'info')
    return redirect(url_for('login.login_page'))