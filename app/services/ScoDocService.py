import json
import glob
import os
import re
import sqlite3
from flask import current_app
from app.DonneeDAO import DonneeDAO

class ScoDocService:
    def __init__(self):
        self.dao = DonneeDAO()
        # On désactive l'API pour l'instant
        self.api = None 

    def is_database_ready(self):
        return self.dao.check_data_integrity()
    
    # Méthodes pour le Controller (Index)
    def get_form_dept(self): return self.dao.get_all_departements()
    def get_form_annees(self): return self.dao.get_all_annees()
    def get_search_results(self, y, d, r): return self.dao.search_etudiants(y, d, r)

    def run_synchronisation(self):
        """
        Exécute la logique de 'import_data.py' pour importer les JSON locaux.
        """
        # 1. Configuration des chemins via Flask
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # app/
        json_dir = os.path.join(base_dir, 'static', 'data', 'json')
        
        print(f"--- Démarrage Synchro Locale depuis {json_dir} ---")

        # 2. Récupération de la connexion DB via le DAO
        db = self.dao.get_db()
        cursor = db.cursor()

        try:
            # Chargement des fichiers de référence
            path_dept = os.path.join(json_dir, 'departements.json')
            path_form = os.path.join(json_dir, 'formations.json') # Pas utilisé directement dans ta logique formation(), mais bon à avoir

            if not os.path.exists(path_dept):
                print("Erreur: departements.json introuvable")
                return {"error": "Fichiers JSON introuvables"}

            with open(path_dept, 'r', encoding='utf-8') as f:
                departements_json = json.load(f)

            # --- Exécution des fonctions d'import (Logique import_data.py) ---
            
            # 1. Tables de référence
            self._import_departement(cursor, departements_json)
            self._import_decision(cursor)
            self._import_rythme(cursor)
            self._import_etat(cursor)
            
            # 2. Etudiants
            self._import_etudiants(cursor, json_dir)

            # 3. Formations (logique calculée)
            self._import_formation(cursor)

            # 4. Inscriptions (Le gros morceau)
            self._import_inscription(cursor, json_dir)

            db.commit()
            print("--- Synchro Locale Terminée (CARRÉ !) ---")
            return {"status": "success", "message": "Import local terminé"}

        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Erreur synchro locale: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    # =========================================================================
    #  MÉTHODES PRIVÉES (Copiées et adaptées de ton import_data.py)
    # =========================================================================

    def _import_decision(self, cursor):
        codes_scodoc = [
            ("Admis", "ADM"), ("Ajourné", "AJ"), ("Admis par Compensation", "CMP"),
            ("Admis Supérieur (Décision Jury)", "ADSUP"), ("Ajourné (Rattrapage)", "ADJR"),
            ("Ajourné (Jury)", "ADJ"), ("Défaillant", "DEF"),
            ("Non Admis Redouble", "NAR"), ("Redoublement", "RED"),
            ("Passage de Droit", "PASD"), ("Passage Conditionnel (AJAC)", "PAS1NCI"), 
            ("En attente", "ATT"), ("En attente (Bloqué)", "ATB"),
            ("Validé", "V"), ("Validé (Variante)", "VAL"), ("Non Validé", "NV"),
            ("Validé par Compensation Annuelle", "VCA"), ("Validé par Commission", "VCC"),
            ("Admis Sous Réserve", "ADM-INC"),
            ("Démissionnaire", "DEM"), ("Absence Injustifiée", "ABI"),
            ("Absence Justifiée", "ABJ"), ("Excusé", "EXC"), ("Non Inscrit", "NI"),
            ("Année Blanche", "ABL"), ("Inscrit (En cours)", "INS"),
            ("Abdandon", "ABAN"), ("Attente Jury", "ATJ")
        ]
        cursor.executemany("INSERT OR IGNORE INTO decision (nom, acronyme) VALUES (?, ?)", codes_scodoc)

    def _import_departement(self, cursor, data):
        donnees = [ (d['id'] , d['dept_name'], d['acronym']) for d in data ]
        # Ajout passerelles manuelles
        donnees.append((9, "Passerelle SD INFO", "P_SD_INFO"))
        donnees.append((10, "Passerelle CJ GEA", "P_CJ_GEA"))
        cursor.executemany("INSERT OR REPLACE INTO departement (id_departement, nom, acronyme) VALUES (?, ?, ?)", donnees)

    def _import_rythme(self, cursor):
        cursor.execute("INSERT OR REPLACE INTO rythme (id_rythme, nom, acronyme) VALUES (1, 'Formation Initiale', 'FI')")
        cursor.execute("INSERT OR REPLACE INTO rythme (id_rythme, nom, acronyme) VALUES (2, 'Formation Apprentissage', 'FA')")

    def _import_etat(self, cursor):
        cursor.execute("INSERT OR REPLACE INTO etat (id_etat, nom, acronyme) VALUES (1, 'Inscrit', 'I')")
        cursor.execute("INSERT OR REPLACE INTO etat (id_etat, nom, acronyme) VALUES (2, 'Démission', 'D')")

    def _import_etudiants(self, cursor, dossier_json):
        pattern = os.path.join(dossier_json, "decisions_*.json")
        liste_fichiers = glob.glob(pattern)
        ines_uniques = set()

        for fichier in liste_fichiers:
            try:
                with open(fichier, 'r', encoding='utf-8') as f:
                    contenu = json.load(f)
                    liste = contenu if isinstance(contenu, list) else contenu.get('etudiants', [])
                    for record in liste:
                        ine = record.get('etudid')
                        if ine: ines_uniques.add(str(ine))
            except Exception as e:
                print(f"Erreur lecture {os.path.basename(fichier)} : {e}")

        donnees_sql = [(ine,) for ine in ines_uniques]
        cursor.executemany("INSERT OR IGNORE INTO etudiant (ine) VALUES (?)", donnees_sql)

    def _import_formation(self, cursor):
        annee_alternance = { 2: 1, 1: 3, 3: 2, 4: 2, 5: 2, 8: 2 } # GEA, CJ, GEII, INFO, RT, SD
        ID_FI, ID_FA = 1, 2
        
        cursor.execute("SELECT id_departement FROM departement")
        tous_les_departements = [row[0] for row in cursor.fetchall()]
        donnees_a_inserer = []

        for dept_id in tous_les_departements:
            if dept_id not in [9, 10]:
                for annee in [1, 2, 3]: donnees_a_inserer.append((annee, dept_id, ID_FI))
                if dept_id in annee_alternance:
                    debut_fa = annee_alternance[dept_id]
                    for annee in [1, 2, 3]:
                        if annee >= debut_fa: donnees_a_inserer.append((annee, dept_id, ID_FA))

        if 9 in tous_les_departements: donnees_a_inserer.append((2, 9, ID_FI))
        if 10 in tous_les_departements: donnees_a_inserer.append((2, 10, ID_FI))

        cursor.executemany("INSERT OR IGNORE INTO formation (annee_but, id_departement, id_rythme) VALUES (?, ?, ?)", donnees_a_inserer)

    def _get_departement_id(self, filename, cache_depts):
        name = filename.lower()
        if "passerelle" in name:
            if any(x in name for x in ["sd", "stid", "info", "donn"]): return cache_depts.get('P_SD_INFO')
            if any(x in name for x in ["cj", "juridique", "gea"]): return cache_depts.get('P_CJ_GEA')
            return None
        if any(x in name for x in ["electrique", "geii"]): return cache_depts.get('GEII')
        if any(x in name for x in ["reseaux", "rt", "r_t"]): return cache_depts.get('RT')
        if any(x in name for x in ["stid", "donn", "_sd_", "but_sd"]): return cache_depts.get('STID')
        if any(x in name for x in ["informatique", "_info_", "but_info"]): return cache_depts.get('INFO')
        if any(x in name for x in ["juridiques", "cj"]): return cache_depts.get('CJ')
        if "gea" in name: return cache_depts.get('GEA')
        return None

    def _import_inscription(self, cursor, dossier_json):
        # Caches
        cursor.execute("SELECT acronyme, id_departement FROM departement")
        cache_depts = {row[0].upper(): row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT ine, id_etudiant FROM etudiant")
        cache_etudiants = {str(row[0]).strip().lower(): row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT acronyme, id_decision FROM decision")
        cache_decisions = {row[0].upper(): row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT id_departement, annee_but, id_rythme, id_formation FROM formation")
        cache_formations = {(row[0], row[1], row[2]): row[3] for row in cursor.fetchall()}

        ID_P_SD_INFO = cache_depts.get('P_SD_INFO')
        ID_P_CJ_GEA = cache_depts.get('P_CJ_GEA')

        pattern = os.path.join(dossier_json, "decisions_*.json")
        fichiers = glob.glob(pattern)
        donnees_a_inserer = []

        for fichier in fichiers:
            nom_fichier = os.path.basename(fichier)
            id_dept = self._get_departement_id(nom_fichier, cache_depts)
            if not id_dept: continue

            annee_match = re.search(r'(\d{4})', nom_fichier) 
            annee_fichier = int(annee_match.group(1)) if annee_match else None

            nom_lower = nom_fichier.lower()
            mots_cles_alt = ['fa', 'apprentissage', 'alternance', 'apprenti', 'alt', 'app']
            id_rythme_fichier = 2 if any(m in nom_lower for m in mots_cles_alt) else 1

            try:
                with open(fichier, 'r', encoding='utf-8') as f:
                    contenu = json.load(f)
            except: continue

            liste_etudiants = contenu if isinstance(contenu, list) else contenu.get('etudiants', [])

            for etu in liste_etudiants:
                ine = etu.get('etudid')
                if not ine: continue
                id_etudiant = cache_etudiants.get(str(ine).strip().lower())
                if not id_etudiant: continue

                data_annee = etu.get('annee', {}) if isinstance(etu.get('annee'), dict) else {}
                data_dec = etu.get('decision', {}) if isinstance(etu.get('decision'), dict) else {}
                data_sem = etu.get('semestre', {}) if isinstance(etu.get('semestre'), dict) else {}

                annee_reelle = annee_fichier
                code_decision = data_annee.get('code') or data_dec.get('code') or data_sem.get('code')
                
                # Récupération année précise si dispo
                if data_annee.get('annee_scolaire'):
                    try: annee_reelle = int(data_annee.get('annee_scolaire'))
                    except: pass

                if not code_decision:
                    etat_admin = etu.get('etat')
                    if etat_admin in ['D', 'ABAN']: code_decision = 'DEM'
                    elif etat_admin == 'DEF': code_decision = 'DEF'
                    elif etat_admin == 'I': code_decision = 'INS'

                if not code_decision or not annee_reelle: continue

                id_decision = cache_decisions.get(str(code_decision).upper())
                if not id_decision: continue

                niveau = 1
                val_ordre = str(data_annee.get('ordre', '')).upper()
                if '3' in val_ordre: niveau = 3
                elif '2' in val_ordre: niveau = 2

                id_formation = cache_formations.get((id_dept, niveau, id_rythme_fichier))

                # Logique passerelle
                if id_dept in [ID_P_SD_INFO, ID_P_CJ_GEA] and not id_formation:
                     id_formation = cache_formations.get((id_dept, 2, id_rythme_fichier))

                # Logique sauvetage alternance
                if not id_formation and id_rythme_fichier == 2:
                    id_formation = cache_formations.get((id_dept, 2, 2)) or cache_formations.get((id_dept, 3, 2))

                if not id_formation: continue

                id_etat = 2 if code_decision in ['DEM', 'DEF', 'ABAN', 'NI', 'D'] else 1
                donnees_a_inserer.append((annee_reelle, id_etudiant, id_etat, id_formation, id_decision))

        cursor.executemany("""
            INSERT OR IGNORE INTO inscription 
            (annee_universitaire, id_etudiant, id_etat, id_formation, id_decision) 
            VALUES (?, ?, ?, ?, ?)
        """, donnees_a_inserer)