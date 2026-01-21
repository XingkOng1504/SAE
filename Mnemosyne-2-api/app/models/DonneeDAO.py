import sqlite3
from flask import g, current_app, session

class DonneeDAO:
    def __init__(self):
        pass

    def get_db(self):
        """Récupère la connexion à la base stockée dans g"""
        db = getattr(g, '_database', None)
        if db is None:
            # On utilise le chemin défini dans la config de l'app
            db = g._database = sqlite3.connect(current_app.config['DATABASE'])
            db.row_factory = sqlite3.Row
        return db

    #verification simple du peuplement de la base de données
    def check_data_integrity(self):
        """Vérifie si la BDD est peuplée"""
        db = self.get_db()
        cursor = db.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM departement")
            d = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM inscription")
            i = cursor.fetchone()[0]
            return d > 0 and i > 0
        except: return False

    def _init_db(self):
        """Crée les tables via schema.sql"""
        db = self.get_db()
        with current_app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

    # --- MÉTHODES DE LECTURE (POUR LE FRONT) ---

    def get_all_departements(self):
        cursor = self.get_db().cursor()
        cursor.execute("SELECT acronyme FROM departement WHERE acronyme NOT IN ('FC', 'P_CJ_GEA') ORDER BY acronyme")
        return [row['acronyme'] for row in cursor.fetchall()]

    def get_all_annees(self):
        cursor = self.get_db().cursor()
        cursor.execute("SELECT DISTINCT annee_universitaire FROM inscription ORDER BY annee_universitaire")
        return [str(row['annee_universitaire']) for row in cursor.fetchall()]

    def search_etudiants(self, annee_debut, dept, rythme, regles):
        """Recherche dynamique pour le tableau de bord"""
        db = self.get_db()
        cursor = db.cursor()

        params = [annee_debut]
        sql_conditions = "WHERE i.annee_universitaire = ? + (f.annee_but - 1)"

        if dept != "TOUS":
            sql_conditions += " AND d.acronyme = ?"
            params.append(dept)
        
        if rythme != "TOUS":
            if rythme == "FI":
                sql_conditions += " AND f.id_rythme = 1"
            elif rythme == "FA":
                sql_conditions += " AND f.id_rythme = 2"
        
        if regles!="":
            query = f"""
            SELECT DISTINCT
                e.id_etudiant,
                e.ine,
                i.annee_universitaire,
                f.annee_but,
                dec.acronyme as resultat,
                d.acronyme as dept,
                r.acronyme as rythme,
                et.acronyme as etat
            FROM etudiant e
            JOIN inscription i ON e.id_etudiant = i.id_etudiant
            JOIN formation f ON i.id_formation = f.id_formation
            JOIN departement d ON f.id_departement = d.id_departement
            LEFT JOIN decision dec ON i.id_decision = dec.id_decision
            
            -- Jointures de structure (Rythme / Etat)
            JOIN rythme r ON f.id_rythme = r.id_rythme
            JOIN etat et ON i.id_etat = et.id_etat

            -- Jointures pour les règles (Notes / Compétences / Parcours)
            -- J'utilise LEFT JOIN pour ne pas perdre un étudiant s'il n'a pas encore de note
            LEFT JOIN evaluer ev ON i.id_inscription = ev.id_inscription
            LEFT JOIN competence c ON ev.id_competence = c.id_competence
            LEFT JOIN parcours p ON c.id_parcours = p.id_parcours

            {sql_conditions} AND {regles}
            ORDER BY e.ine;
            """

        else:
            query = f"""
            SELECT 
                e.ine,
                i.annee_universitaire,
                f.annee_but,
                dec.acronyme as resultat,
                d.acronyme as dept,
                r.acronyme as rythme
            FROM inscription i
            JOIN formation f ON i.id_formation = f.id_formation
            JOIN departement d ON f.id_departement = d.id_departement
            JOIN etudiant e ON i.id_etudiant = e.id_etudiant
            JOIN rythme r ON f.id_rythme = r.id_rythme
            LEFT JOIN decision dec ON i.id_decision = dec.id_decision
            {sql_conditions}
            ORDER BY e.ine;
            """
        
        cursor.execute(query, params)
        return cursor.fetchall()


    def get_sankey_data(self, annee_debut, dept, rythme, regles):
        """
        Calcule les flux étudiants pour le diagramme de Sankey
        Retourne les comptages par niveau et les transitions entre niveaux
        """
        db = self.get_db()
        cursor = db.cursor()

        # Construire les conditions de filtrage
        params = []
        sql_dept = ""
        sql_rythme = ""
        
        if dept != "TOUS":
            sql_dept = " AND d.acronyme = ?"
            params.append(dept)
        
        if rythme != "TOUS":
            if rythme == "FI":
                sql_rythme = " AND f.id_rythme = 1"
            elif rythme == "FA":
                sql_rythme = " AND f.id_rythme = 2"

        if regles != "":
            # Récupérer toutes les inscriptions de la cohorte sur 3 ans + année précédente pour les redoublants entrants
            query = f"""
            SELECT DISTINCT
                e.id_etudiant,
                e.ine,
                i.annee_universitaire,
                f.annee_but,
                dec.acronyme as resultat,
                d.acronyme as dept,
                r.acronyme as rythme,
                et.acronyme as etat
            FROM etudiant e
            JOIN inscription i ON e.id_etudiant = i.id_etudiant
            JOIN formation f ON i.id_formation = f.id_formation
            JOIN departement d ON f.id_departement = d.id_departement
            LEFT JOIN decision dec ON i.id_decision = dec.id_decision
            
            -- Jointures de structure (Rythme / Etat)
            JOIN rythme r ON f.id_rythme = r.id_rythme
            JOIN etat et ON i.id_etat = et.id_etat

            -- Jointures pour les règles (Notes / Compétences / Parcours)
            -- J'utilise LEFT JOIN pour ne pas perdre un étudiant s'il n'a pas encore de note
            LEFT JOIN evaluer ev ON i.id_inscription = ev.id_inscription
            LEFT JOIN competence c ON ev.id_competence = c.id_competence
            LEFT JOIN parcours p ON c.id_parcours = p.id_parcours

            WHERE {regles} AND i.annee_universitaire BETWEEN ? AND ?
            {sql_dept}
            {sql_rythme}
            ORDER BY e.id_etudiant, i.annee_universitaire
            """
        else :
            # Récupérer toutes les inscriptions de la cohorte sur 3 ans + année précédente pour les redoublants entrants
            query = f"""
            SELECT 
                e.id_etudiant,
                e.ine,
                i.annee_universitaire,
                f.annee_but,
                dec.acronyme as resultat,
                d.acronyme as dept
            FROM etudiant e
            JOIN inscription i ON e.id_etudiant = i.id_etudiant
            JOIN formation f ON i.id_formation = f.id_formation
            JOIN departement d ON f.id_departement = d.id_departement
            LEFT JOIN decision dec ON i.id_decision = dec.id_decision
            WHERE i.annee_universitaire BETWEEN ? AND ?
            {sql_dept}
            {sql_rythme}
            ORDER BY e.id_etudiant, i.annee_universitaire
            """
        
        annee_int = int(annee_debut)
        all_params = [annee_int - 1, annee_int + 2] + params  # Inclure l'année précédente
        cursor.execute(query, all_params)
        rows = cursor.fetchall()

        # Organiser les données par étudiant
        etudiants = {}
        for row in rows:
            etu_id = row['id_etudiant']
            if etu_id not in etudiants:
                etudiants[etu_id] = {}
            etudiants[etu_id][row['annee_universitaire']] = {
                'annee_but': row['annee_but'],
                'resultat': row['resultat']
            }

        # Calculer les statistiques
        stats = {
            'but1_total': 0,
            'but1_admis': 0,
            'but1_redouble': 0,
            'but1_abandon': 0,
            'but2_total': 0,
            'but2_admis': 0,
            'but2_redouble': 0,
            'but2_abandon': 0,
            'but2_reorientation': 0,
            'but3_total': 0,
            'but3_diplome': 0,
            'but3_redouble': 0,
            'but3_abandon': 0,
            'nouveaux_but2': 0,  # Entrées directes en BUT2 (passerelle/ecandidat)
            'nouveaux_but3': 0,  # Entrées directes en BUT3
            'redoublants_entrant_but1': 0,  # Redoublants qui arrivent en BUT1 (de l'année précédente)
            'redoublants_entrant_but2': 0,  # Redoublants qui arrivent en BUT2 (de l'année précédente)
            'redoublants_entrant_but3': 0   # Redoublants qui arrivent en BUT3 (de l'année précédente)
        }

        annee0, annee1, annee2, annee3 = annee_int - 1, annee_int, annee_int + 1, annee_int + 2

        for etu_id, parcours in etudiants.items():
            # Analyser le parcours de chaque étudiant
            
            # Redoublants entrants: étudiants qui étaient en BUT X l'année précédente et reviennent en BUT X cette année
            if annee0 in parcours and annee1 in parcours:
                if parcours[annee0]['annee_but'] == 1 and parcours[annee1]['annee_but'] == 1:
                    stats['redoublants_entrant_but1'] += 1
                if parcours[annee0]['annee_but'] == 2 and parcours[annee1]['annee_but'] == 2:
                    stats['redoublants_entrant_but2'] += 1
                if parcours[annee0]['annee_but'] == 3 and parcours[annee1]['annee_but'] == 3:
                    stats['redoublants_entrant_but3'] += 1
            
            # Année 1 (BUT1)
            if annee1 in parcours and parcours[annee1]['annee_but'] == 1:
                stats['but1_total'] += 1
                res = parcours[annee1]['resultat']
                
                # Vérifier passage en BUT2
                if annee2 in parcours and parcours[annee2]['annee_but'] == 2:
                    stats['but1_admis'] += 1
                elif annee2 in parcours and parcours[annee2]['annee_but'] == 1:
                    stats['but1_redouble'] += 1
                elif res and ('ADM' in res):
                    stats['but1_admis'] += 1  # Admis mais pas réinscrit
                else:
                    stats['but1_abandon'] += 1
            
            # Entrées directes en BUT2 (nouveaux étudiants)
            if annee1 in parcours and parcours[annee1]['annee_but'] == 2:
                stats['nouveaux_but2'] += 1
            
            # Année 2 (BUT2)
            if annee2 in parcours and parcours[annee2]['annee_but'] == 2:
                stats['but2_total'] += 1
                res = parcours[annee2]['resultat']
                
                # Vérifier passage en BUT3
                if annee3 in parcours and parcours[annee3]['annee_but'] == 3:
                    stats['but2_admis'] += 1
                elif annee3 in parcours and parcours[annee3]['annee_but'] == 2:
                    stats['but2_redouble'] += 1
                elif res and ('ADM' in res):
                    stats['but2_admis'] += 1
                elif res and ('AJ' in res or 'ABAN' in res):
                    stats['but2_abandon'] += 1
                else:
                    stats['but2_reorientation'] += 1
            
            # Année 3 (BUT3)
            if annee3 in parcours and parcours[annee3]['annee_but'] == 3:
                stats['but3_total'] += 1
                res = parcours[annee3]['resultat']
                
                if res and ('ADM' in res or 'DIP' in res):
                    stats['but3_diplome'] += 1
                elif res and 'AJ' in res:
                    stats['but3_redouble'] += 1
                else:
                    stats['but3_abandon'] += 1

        return stats