from app.models.ScoDocAPI import ScoDocAPI
from app.models.DonneeDAO import DonneeDAO
from flask import current_app
import os
import math
from datetime import datetime

class ScoDocService:
    def __init__(self):
        self.dao = DonneeDAO()
        # Configuration
        url = os.environ.get('SCODOC_URL', 'https://scodoc.univ-paris13.fr/ScoDoc/api')
        # À REMPLACER PAR VOTRE TOKEN
        token = os.environ.get('SCODOC_API_TOKEN', '') 
        
        self.api = ScoDocAPI(url)

    def is_database_ready(self):
        return self.dao.check_data_integrity()
    
    def get_form_dept(self): return self.dao.get_all_departements()
    def get_form_annees(self): return self.dao.get_all_annees()
    def get_search_results(self, y, d, r): return self.dao.search_etudiants(y, d, r)

    def run_synchronisation(self):
        """Orchestre la synchronisation complète"""
        stats = { 'departements': 0, 'formations': 0, 'etudiants': 0, 
                  'inscriptions': 0, 'competences': 0, 'evaluations': 0 }
        
        db = self.dao.get_db()
        cursor = db.cursor()

        try:
            # 1. Données statiques
            self._init_referentiels_statiques(cursor)

            # 2. Départements
            depts = self.api.get_departements()
            self._import_departements(cursor, depts, stats)

            # 3. Formations BUT & Parcours
            all_formations = self.api.get_formations()
            
            # Map : ID ScoDoc (305) -> ID Dept BDD
            scodoc_formation_ids = {} 

            for fmt in all_formations:
                # Filtre : On ne traite que les BUT
                titre = (fmt.get('titre') or fmt.get('titre_officiel') or '').upper()
                acronyme = (fmt.get('acronym') or '')

                # Condition plus large grâce à vos fichiers
                if 'BUT' in titre or 'BACH' in acronyme:
                    
                    # A. Création des 6 formations théoriques (BUT1/2/3 x FI/FA) pour ce département
                    dept_id_bdd = self._import_structure_formation(cursor, fmt, stats)
                    
                    if dept_id_bdd:
                        scodoc_id = fmt.get('id')
                        scodoc_formation_ids[scodoc_id] = dept_id_bdd

            # 4. Import des Référentiels (Parcours / Compétences)
            # Map : (ID Dept BDD, Numéro UE) -> ID Competence BDD
            map_competence_ids = {} 

            # On ne le fait qu'une fois par département pour éviter les requêtes inutiles
            depts_traites = set()

            for scodoc_id, dept_id_bdd in scodoc_formation_ids.items():
                if dept_id_bdd not in depts_traites:
                    self._import_referentiel_competence(cursor, scodoc_id, dept_id_bdd, map_competence_ids, stats)
                    depts_traites.add(dept_id_bdd)

            # 5. Inscriptions & Evaluations
            annee_actuelle = datetime.now().year
            annees_a_traiter = range(2021, annee_actuelle + 2) 

            # Caches
            cursor.execute("SELECT ine, id_etudiant FROM etudiant") #????
            cache_etus = {row['ine']: row['id_etudiant'] for row in cursor.fetchall()}
            
            cursor.execute("SELECT acronyme, id_decision FROM decision")
            cache_dec = {row['acronyme']: row['id_decision'] for row in cursor.fetchall()}

            for annee in annees_a_traiter:
                print(f"--- Synchronisation année {annee} ---")
                formsemestres = self.api.get_formsemestres_query(annee)
                
                if not formsemestres: continue

                for fs in formsemestres:
                    formation_id_scodoc = fs.get('formation_id')
                    # On ne traite que les formations BUT identifiées
                    if formation_id_scodoc in scodoc_formation_ids:
                        
                        # Récupération des notes
                        decisions_jury = self.api.get_decisions_jury(fs.get('id'))
                        
                        self._import_resultats_semestre(
                            cursor, fs, decisions_jury, 
                            annee, cache_etus, cache_dec, 
                            map_competence_ids, scodoc_formation_ids, stats
                        )

            db.commit()
            print(f"Synchro terminée: {stats}")
            return stats

        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Erreur fatale synchro: {e}")
            raise e


    # -------------------------------------------------------------------------
    # MÉTHODES D'IMPORT AMÉLIORÉES GRÂCE AUX JSON
    # -------------------------------------------------------------------------

    def _import_structure_formation(self, cursor, fmt, stats):
        """Génère les 6 formations (BUT1-3, FI/FA) pour le département de cette formation"""
        dept_id_scodoc = fmt.get('dept_id') or fmt.get('departement', {}).get('id')
        if not dept_id_scodoc: return None
        
        # On crée les combinaisons possibles.
        # Grâce à UNIQUE(annee, dept, rythme), on n'aura pas de doublons.
        nb_creations = 0
        for annee in [1, 2, 3]:
            for rythme in [1, 2]: # 1=FI, 2=FA
                cursor.execute("""
                    INSERT OR IGNORE INTO formation (annee_but, id_departement, id_rythme)
                    VALUES (?, ?, ?)
                """, (annee, dept_id_scodoc, rythme))
                if cursor.rowcount > 0: nb_creations += 1
        
        stats['formations'] += nb_creations
        return dept_id_scodoc

    def _import_resultats_semestre(self, cursor, fs_info, decisions_json, annee, cache_etus, cache_dec, map_competence_ids, scodoc_formation_ids, stats):
        """
        Importe les résultats en utilisant les champs précis 'modalite' et 'semestre_id'
        """
        
        # 1. Déterminer l'Année BUT (1, 2, 3)
        semestre_idx = fs_info.get('semestre_id')
        if not semestre_idx: return 
        
        annee_but = math.ceil(semestre_idx / 2) # S1/S2->1, S3/S4->2, S5/S6->3

        # 2. Déterminer le Rythme (FI ou FA)
        # "FI" -> Formation Initiale
        # "FAP" -> Apprentissage
        modalite = fs_info.get('modalite', '').upper()
        
        # Si modalite contient 'FAP' ou 'APP', c'est de l'alternance (ID 2)
        id_rythme = 1 if 'FI' in modalite else 2

        # 3. Retrouver l'ID Formation BDD associé au formsemester
        formation_id_scodoc = fs_info.get('formation_id')
        dept_id_bdd = scodoc_formation_ids.get(formation_id_scodoc)
        if not dept_id_bdd: return

        # On sélectionne la formation locale associée pour insérer les inscriptions
        cursor.execute("SELECT id_formation FROM formation WHERE annee_but=? AND id_departement=? AND id_rythme=?", 
                       (annee_but, dept_id_bdd, id_rythme))
        row_fmt = cursor.fetchone()
         
        id_formation_bdd = row_fmt[0]

        # 4. Traitement des étudiants et notes
        for etu in decisions_json:
            ine = etu.get('code_ine')
            if not ine: continue

            # A. Etudiant
            if ine not in cache_etus:
                cursor.execute("INSERT OR IGNORE INTO etudiant (ine) VALUES (?)", (ine,))
                cursor.execute("SELECT id_etudiant FROM etudiant WHERE ine=?", (ine,))
                rid = cursor.fetchone()
                if rid: 
                    cache_etus[ine] = rid[0]
                    stats['etudiants'] += 1
            
            id_etudiant = cache_etus.get(ine)

            # --- B. Inscription & Décision ---
            
            # récupération de la décision
            code_dec = etu.get('annee').get('code')
            
            # On récupère l'ID de la décision dans notre cache
            id_decision = cache_dec.get(code_dec)
            
            # Détermination de l'état (Inscrit ou Démissionnaire)
            etat_txt = etu.get('etat', '')
            if etat_txt == 'D' or code_dec in ['DEM', 'DEF']: 
                id_etat = 2 # Démission / Défaillant
            else: 
                id_etat = 1 # Inscrit

            # Insertion dans la base
            cursor.execute("""
                INSERT OR IGNORE INTO inscription 
                (annee_universitaire, id_etudiant, id_etat, id_formation, id_decision)
                VALUES (?, ?, ?, ?, ?) 
            """, (annee, id_etudiant, id_etat, id_formation_bdd, id_decision))
            
            # Récup ID Inscription pour les notes
            cursor.execute("SELECT id_inscription FROM inscription WHERE id_etudiant=? AND annee_universitaire=?",
                           (id_etudiant, annee))
            row_ins = cursor.fetchone()

            id_inscription = row_ins[0]
            stats['inscriptions'] += 1

            # --- C. Notes (Moyennes Annuelles des Compétences) ---
            rcues = etu.get('rcues', [])
            
            # On parcourt simplement la liste. 
            # Index 0 = Compétence 1, Index 1 = Compétence 2...
            for index, comp_data in enumerate(rcues):
                numero_competence = index + 1
                
                # On récupère l'ID BDD de la compétence (ex: la compétence 1 du département GEA est l'id 34)
                id_comp_bdd = map_competence_ids.get((dept_id_bdd, numero_competence))
                
                # moyenne consolidée (annuelle)
                moyenne = comp_data.get('moy')
                code_str = comp_data.get('code')
                
                # On récupère l'ID du code décision (ADM, ADJ...)
                id_d_comp = cache_dec.get(code_str)

                # Si on a une moyenne, on insère.
                if moyenne is not None:
                    cursor.execute("""
                        INSERT OR REPLACE INTO evaluer (id_inscription, id_competence, id_decision, moyenne)
                        VALUES (?, ?, ?, ?)
                    """, (id_inscription, id_comp_bdd, id_d_comp, moyenne))
                    
                    stats['evaluations'] += 1
    
    def _import_departements(self, cursor, depts_api, stats):
        donnees = []
        for d in depts_api:
            # Sécurisation avec .get et check 'visible'
            if d.get('visible') is True:
                d_id = d.get('id')
                nom = d.get('dept_name') or d.get('nom') or 'Inconnu'
                acro = d.get('acronym') or d.get('acronyme')
                if d_id and nom and acro:
                    donnees.append((d_id, nom, acro))
        if donnees:
            cursor.executemany("INSERT OR REPLACE INTO departement (id_departement, nom, acronyme) VALUES (?, ?, ?)", donnees)
            stats['departements'] += cursor.rowcount

    def _import_referentiel_competence(self, cursor, scodoc_id, dept_id_bdd, map_competence_ids, stats):
        """
        Importe les Parcours et Compétences depuis le référentiel ScoDoc 9.
        Format attendu : Dictionnaires uniquement.
        """
        ref = self.api.get_referentiel_competences(scodoc_id)
        if not ref or not isinstance(ref, dict): 
            return

        # ---------------------------------------------------------
        # ÉTAPE 1 : IMPORT DES PARCOURS (Format Dictionnaire)
        # ---------------------------------------------------------
        # Structure attendue : { "DevCloud": { "libelle": "..." }, "B": { ... } }
        dict_parcours = ref.get('parcours')
        
        # Si pas de parcours ou format incorrect, on arrête tout (consigne stricte)
        if not dict_parcours or not isinstance(dict_parcours, dict):
            return

        map_parcours_bdd = {} # Clé: Code Parcours (ex: 'DevCloud') -> Valeur: ID BDD

        for p_code, p_data in dict_parcours.items():
            # Dans un dictionnaire, la clé est souvent le code (A, B, C...)
            # p_data contient les détails (libelle, etc.)
            
            nom_parcours = p_data.get('libelle')
            
            # 1. On vérifie si ce parcours existe déjà pour ce département
            cursor.execute("SELECT id_parcours FROM parcours WHERE code=? AND id_departement=?", 
                           (p_code, dept_id_bdd))
            row_p = cursor.fetchone()
            
            if row_p:
                map_parcours_bdd[p_code] = row_p[0]
            else:
                # 2. Sinon on le crée
                cursor.execute("""
                    INSERT INTO parcours (code, nom, id_departement) 
                    VALUES (?, ?, ?)
                """, (p_code, nom_parcours, dept_id_bdd))
                
                map_parcours_bdd[p_code] = cursor.lastrowid #récupère l'id insérér end ernier

        # Sécurité supplémentaire : Si l'insertion a échoué et map vide, on sort.
        if not map_parcours_bdd:
            return

        # ---------------------------------------------------------
        # ÉTAPE 2 : IMPORT DES COMPÉTENCES (Format Dictionnaire)
        # ---------------------------------------------------------
        # Structure attendue : { "Piloter": { "numero": 1, ... }, ... }
        dict_competences = ref.get('competences')
        
        if not dict_competences or not isinstance(dict_competences, dict):
            return

        for key_comp, data_comp in dict_competences.items():
            # Extraction propre des données
            titre_comp = data_comp.get('titre') or key_comp
            numero = data_comp.get('numero')

            acronyme_comp = acronyme = f"C{numero}" # Ex: UE1 représente la compétence 1 et pas UE12 qui est une evaluation

            # BOUCLE CRUCIALE :
            # On associe cette compétence à TOUS les parcours récupérés au-dessus.
            # C'est ce qui permet d'avoir l'UE1 dans le Parcours A, mais aussi dans le B si présent.
            
            for code_p, id_parcours_bdd in map_parcours_bdd.items():
                
                # Vérification anti-doublon (couple acronyme + parcours unique)
                cursor.execute("""
                    SELECT id_competence FROM competence 
                    WHERE acronyme=? AND id_parcours=?
                """, (acronyme_comp, id_parcours_bdd))
                
                existing = cursor.fetchone()
                
                if existing:
                    final_id_comp = existing[0]
                else:
                    cursor.execute("""
                        INSERT INTO competence (nom, acronyme, id_parcours) 
                        VALUES (?, ?, ?)
                    """, (titre_comp, acronyme_comp, id_parcours_bdd))
                    
                    final_id_comp = cursor.lastrowid
                    stats['competences'] += 1

                # On stocke l'ID pour pouvoir insérer les notes plus tard.
                # Clé : (ID_Dept_BDD, Numero_UE) -> ID_Competence_BDD
                # Note : Si plusieurs parcours, cela écrasera la valeur avec le dernier parcours traité.
                map_competence_ids[(dept_id_bdd, numero)] = final_id_comp

    def _init_referentiels_statiques(self, cursor):
        codes = [
            ("Admis", "ADM"), ("Ajourné", "AJ"), ("Admis par Compensation", "CMP"),
            ("Admis Supérieur", "ADSUP"), ("Ajourné (Rattrapage)", "ADJR"),
            ("Ajourné (Jury)", "ADJ"), ("Défaillant", "DEF"), ("Non Admis Redouble", "NAR"),
            ("Redoublement", "RED"), ("Passage de Droit", "PASD"), 
            ("Passage Conditionnel", "PAS1NCI"), ("En attente", "ATT"),
            ("En attente (Bloqué)", "ATB"), ("Validé", "V"), ("Validé (Variante)", "VAL"),
            ("Non Validé", "NV"), ("Validé par Compensation Annuelle", "VCA"),
            ("Validé par Commission", "VCC"), ("Admis Sous Réserve", "ADM-INC"),
            ("Démissionnaire", "DEM"), ("Absence Injustifiée", "ABI"),
            ("Absence Justifiée", "ABJ"), ("Excusé", "EXC"), ("Non Inscrit", "NI"),
            ("Année Blanche", "ABL"), ("Inscrit (En cours)", "INS"), 
            ("Abdandon", "ABAN"), ("Attente Jury", "ATJ")
            ]
        cursor.executemany("INSERT OR IGNORE INTO decision (nom, acronyme) VALUES (?, ?)", codes)
        cursor.execute("INSERT OR IGNORE INTO rythme (id_rythme, nom, acronyme) VALUES (1, 'Formation Initiale', 'FI')")
        cursor.execute("INSERT OR IGNORE INTO rythme (id_rythme, nom, acronyme) VALUES (2, 'Alternance', 'FA')")
        cursor.execute("INSERT OR IGNORE INTO etat (id_etat, nom, acronyme) VALUES (1, 'Inscrit', 'I')")
        cursor.execute("INSERT OR IGNORE INTO etat (id_etat, nom, acronyme) VALUES (2, 'Démission', 'D')")