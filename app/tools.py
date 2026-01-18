from functools import wraps
from flask import session, flash, redirect, url_for

# Décorateur pour vérifier la connexion
def reqlogged(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged' in session:
            return f(*args, **kwargs)
        else:
            flash('Accès refusé. Veuillez vous connecter.', 'error')
            # Redirection vers la page de login
            return redirect(url_for('login.login_page')) 
    return wrap