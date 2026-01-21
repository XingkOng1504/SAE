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

            # 2. Départements (Avec ajout manuel des Passerelles)
            depts = self.api.get_departements()
            self._import_departements(cursor, depts, stats)

            # 3. Formations BUT & Parcours
            all_formations = self.api.get_formations()
            
            # Map : ID ScoDoc (ex: 305) -> ID Dept BDD (ex: 1)
            scodoc_formation_ids = {} 

            for fmt in all_formations:
                # Filtre : On ne traite que les BUT
                titre = (fmt.get('titre') or fmt.get('titre_officiel') or '').upper()
                acronyme = (fmt.get('acronym') or '')

                if 'BUT' in titre or 'BACH' in acronyme:
                    # A. Création des 6 formations théoriques (BUT1/2/3 x FI/FA)
                    dept_id_bdd = self._import_structure_formation(cursor, fmt, stats)
                    
                    if dept_id_bdd:
                        scodoc_id = fmt.get('id')
                        scodoc_formation_ids[scodoc_id] = dept_id_bdd

            # --- AJOUT MANUEL DES FORMATIONS PASSERELLES ---
            # ID 9 = Passerelle SD INFO / ID 10 = Passerelle CJ GEA
            self._create_passerelle_formation(cursor, 9, stats)
            self._create_passerelle_formation(cursor, 10, stats)


            # 4. Import des Référentiels (Parcours / Compétences)
            # Map : (ID Dept BDD, Numéro UE) -> ID Competence BDD
            map_competence_ids = {} 
            depts_traites = set()

            for scodoc_id, dept_id_bdd in scodoc_formation_ids.items():
                if dept_id_bdd not in depts_traites:
                    self._import_referentiel_competence(cursor, scodoc_id, dept_id_bdd, map_competence_ids, stats)
                    depts_traites.add(dept_id_bdd)

            # 5. Inscriptions & Evaluations
            annee_actuelle = datetime.now().year
            annees_a_traiter = range(2021, annee_actuelle + 2) 

            # Caches pour optimisation (éviter de requêter la BDD en boucle)
            cursor.execute("SELECT ine, id_etudiant FROM etudiant")
            cache_etus = {row['ine']: row['id_etudiant'] for row in cursor.fetchall()}
            
            cursor.execute("SELECT acronyme, id_decision FROM decision")
            cache_dec = {row['acronyme']: row['id_decision'] for row in cursor.fetchall()}

            for annee in annees_a_traiter:
                print(f"--- Synchronisation année {annee} ---")
                formsemestres = self.api.get_formsemestres_query(annee)
                
                if not formsemestres: continue

                for fs in formsemestres:
                    formation_id_scodoc = fs.get('formation_id')
                    titre_semestre = fs.get('titre', '').upper()
                    
                    # On traite si c'est une formation connue OU si c'est une Passerelle
                    is_known = formation_id_scodoc in scodoc_formation_ids
                    is_passerelle = 'PASSERELLE' in titre_semestre

                    if is_known or is_passerelle:
                        
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
    # MÉTHODES D'IMPORT
    # -------------------------------------------------------------------------

    def _import_structure_formation(self, cursor, fmt, stats):
        """Génère les 6 formations (BUT1-3, FI/FA) pour le département"""
        dept_id_scodoc = fmt.get('dept_id') or fmt.get('departement', {}).get('id')
        if not dept_id_scodoc: return None
        
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

    def _create_passerelle_formation(self, cursor, dept_id, stats):
        """Crée la formation unique BUT2 FI pour une passerelle"""
        cursor.execute("""
            INSERT OR IGNORE INTO formation (annee_but, id_departement, id_rythme)
            VALUES (?, ?, ?)
        """, (2, dept_id, 1)) # Toujours BUT 2, Toujours FI (1)
        
        if cursor.rowcount > 0:
            stats['formations'] += 1

    def _import_resultats_semestre(self, cursor, fs_info, decisions_json, annee, cache_etus, cache_dec, map_competence_ids, scodoc_formation_ids, stats):
        """Importe les résultats, gère le mapping Passerelle et les notes RCUES"""
        
        # 1. Infos Semestre de base
        semestre_idx = fs_info.get('semestre_id')
        if not semestre_idx: return 
        annee_but = math.ceil(semestre_idx / 2) # S1/S2->1...

        modalite = fs_info.get('modalite', '').upper()
        id_rythme = 2 if ('FAP' in modalite or 'APP' in modalite or 'ALT' in modalite) else 1

        # 2. Identification du Département (Standard ou Passerelle)
        formation_id_scodoc = fs_info.get('formation_id')
        dept_id_bdd = scodoc_formation_ids.get(formation_id_scodoc)

        # --- LOGIQUE DE DÉTECTION PASSERELLE ---
        titre_semestre = fs_info.get('titre', '').upper()
        
        if "PASSERELLE" in titre_semestre:
            # On force les IDs que nous avons créés manuellement
            if "SD" in titre_semestre or "INFO" in titre_semestre:
                dept_id_bdd = 9 # P_SD_INFO
            elif "CJ" in titre_semestre or "GEA" in titre_semestre:
                dept_id_bdd = 10 # P_CJ_GEA
            
            # Les passerelles sont toujours considérées comme BUT 2 en FI
            annee_but = 2
            id_rythme = 1

        if not dept_id_bdd: return

        # 3. Récupération ID Formation BDD
        cursor.execute("SELECT id_formation FROM formation WHERE annee_but=? AND id_departement=? AND id_rythme=?", 
                       (annee_but, dept_id_bdd, id_rythme))
        row_fmt = cursor.fetchone()
        
        # Si on ne trouve pas la formation (ex: Passerelle mal configurée), on skip
        if not row_fmt: return 
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

            # B. Inscription & Décision
            # Recherche de la décision dans l'ordre de priorité
            decision_info = {}
            if etu.get('annee') and isinstance(etu.get('annee'), dict):
                decision_info = etu['annee']
            elif etu.get('semestre') and isinstance(etu['semestre'], list) and etu['semestre']:
                decision_info = etu['semestre'][0]
            elif etu.get('decision'): # Fallback ancienne API
                 d = etu.get('decision')
                 decision_info = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else {})

            code_dec = decision_info.get('code')
            id_decision = cache_dec.get(code_dec)

            # Etat
            etat_txt = etu.get('etat', '')
            if etat_txt == 'D' or code_dec in ['DEM', 'DEF', 'ABAN']: 
                id_etat = 2 # Démission
            else: 
                id_etat = 1 # Inscrit

            # Insertion Inscription
            cursor.execute("""
                INSERT OR IGNORE INTO inscription 
                (annee_universitaire, id_etudiant, id_etat, id_formation, id_decision)
                VALUES (?, ?, ?, ?, ?) 
            """, (annee, id_etudiant, id_etat, id_formation_bdd, id_decision))
            
            cursor.execute("SELECT id_inscription FROM inscription WHERE id_etudiant=? AND annee_universitaire=?",
                           (id_etudiant, annee))
            row_ins = cursor.fetchone()
            if not row_ins: continue
            id_inscription = row_ins[0]
            stats['inscriptions'] += 1

            # C. Notes (Evaluations via rcues)
            rcues = etu.get('rcues', [])
            
            for index, comp_data in enumerate(rcues):
                # Mapping : Index 0 -> Compétence 1
                numero_competence = index + 1
                
                # On retrouve l'ID BDD de la compétence
                id_comp_bdd = map_competence_ids.get((dept_id_bdd, numero_competence))
                
                # Note: Si c'est une passerelle, il n'y a peut-être pas de compétence importée automatiquement.
                # Dans ce cas, id_comp_bdd sera None et on ne stocke pas de note (logique, car pas de ref).
                if not id_comp_bdd: continue

                moyenne = comp_data.get('moy')
                code_str = comp_data.get('code')
                id_d_comp = cache_dec.get(code_str)

                if moyenne is not None:
                    cursor.execute("""
                        INSERT OR REPLACE INTO evaluer (id_inscription, id_competence, id_decision, moyenne)
                        VALUES (?, ?, ?, ?)
                    """, (id_inscription, id_comp_bdd, id_d_comp, moyenne))
                    stats['evaluations'] += 1

    def _import_departements(self, cursor, depts_api, stats):
        donnees = []
        for d in depts_api:
            if d.get('visible') is True:
                d_id = d.get('id')
                nom = d.get('dept_name') or d.get('nom') or 'Inconnu'
                acro = d.get('acronym') or d.get('acronyme')
                if d_id and nom and acro:
                    donnees.append((d_id, nom, acro))
        
        # --- AJOUT MANUEL DES PASSERELLES ---
        donnees.append((9, "Passerelle SD INFO", "P_SD_INFO"))
        donnees.append((10, "Passerelle CJ GEA", "P_CJ_GEA"))

        if donnees:
            cursor.executemany("INSERT OR REPLACE INTO departement (id_departement, nom, acronyme) VALUES (?, ?, ?)", donnees)
            stats['departements'] += cursor.rowcount

    def _import_referentiel_competence(self, cursor, scodoc_id, dept_id_bdd, map_competence_ids, stats):
        """Importe Parcours et Compétences"""
        ref = self.api.get_referentiel_competences(scodoc_id)
        if not ref or not isinstance(ref, dict): return

        # 1. Parcours
        dict_parcours = ref.get('parcours')
        if not dict_parcours or not isinstance(dict_parcours, dict): return

        map_parcours_bdd = {} 

        for p_code, p_data in dict_parcours.items():
            nom_parcours = p_data.get('libelle') or p_data.get('nom')
            
            cursor.execute("SELECT id_parcours FROM parcours WHERE code=? AND id_departement=?", 
                           (p_code, dept_id_bdd))
            row_p = cursor.fetchone()
            
            if row_p:
                map_parcours_bdd[p_code] = row_p[0]
            else:
                cursor.execute("INSERT INTO parcours (code, nom, id_departement) VALUES (?, ?, ?)", 
                               (p_code, nom_parcours, dept_id_bdd))
                map_parcours_bdd[p_code] = cursor.lastrowid

        if not map_parcours_bdd: return

        # 2. Compétences
        dict_competences = ref.get('competences')
        if not dict_competences or not isinstance(dict_competences, dict): return

        for key_comp, data_comp in dict_competences.items():
            titre_comp = data_comp.get('titre') or key_comp
            numero = data_comp.get('numero')
            if not numero: continue

            # Acronyme stable : C1, C2...
            acronyme_comp = f"C{numero}" 

            for code_p, id_parcours_bdd in map_parcours_bdd.items():
                cursor.execute("SELECT id_competence FROM competence WHERE acronyme=? AND id_parcours=?", 
                               (acronyme_comp, id_parcours_bdd))
                existing = cursor.fetchone()
                
                if existing:
                    final_id_comp = existing[0]
                else:
                    cursor.execute("INSERT INTO competence (nom, acronyme, id_parcours) VALUES (?, ?, ?)", 
                                   (titre_comp, acronyme_comp, id_parcours_bdd))
                    final_id_comp = cursor.lastrowid
                    stats['competences'] += 1

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