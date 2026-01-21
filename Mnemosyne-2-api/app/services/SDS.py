from app.models.ScoDocAPI import ScoDocAPI
from app.models.DonneeDAO import DonneeDAO
from flask import current_app
import os
from datetime import datetime

class ScoDocService:
    def __init__(self):
        self.dao = DonneeDAO()
        # Configuration
        url = os.environ.get('SCODOC_URL', 'https://scodoc.univ-paris13.fr/ScoDoc/api')
        self.api = ScoDocAPI(url)

    def is_database_ready(self):
        return self.dao.check_data_integrity()

#synchronisation des données de l'API vers la base de données
    def run_synchronisation(self):
        """la synchronisation complète"""
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
            self._import_formation()
           
            # 4. Inscriptions & Evaluations (Années Dynamiques)
            annee_actuelle = datetime.now().year
            # De 2021 jusqu'à l'année scolaire en cours + 1
            annees_a_traiter = range(2021, annee_actuelle + 2) 

            # Caches pour optimiser les boucles
            cursor.execute("SELECT ine, id_etudiant FROM etudiant")
            cache_etus = {row['ine']: row['id_etudiant'] for row in cursor.fetchall()}
            
            cursor.execute("SELECT acronyme, id_decision FROM decision")
            cache_dec = {row['acronyme']: row['id_decision'] for row in cursor.fetchall()}

            for annee in annees_a_traiter:
                print(f"Synchronisation année scolaire {annee}...")
                formsemestres = self.api.get_formsemestres_query(annee)
                
                if not formsemestres: continue

                for fs in formsemestres:
                    # On ignore les semestres des formations non importées
                    formation_id_scodoc = fs.get('formation_id')
                    if formation_id_scodoc not in map_formation_ids:
                        continue
                    
                    id_formation_bdd = map_formation_ids[formation_id_scodoc]

                    # Récupération des bulletins (notes + décisions)
                    decisions_jury = self.api.get_decisions_jury(fs['id'])
                    
                    self._import_resultats_semestre(
                        cursor, decisions_jury, 
                        annee, id_formation_bdd, 
                        cache_etus, cache_dec, 
                        map_competence_ids, stats
                    )

            db.commit()
            print(f"Synchro terminée: {stats}")
            return stats

        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Erreur fatale synchro: {e}")
            raise e

    # -------------------------------------------------------------------------
    # LOGIQUE D'IMPORT
    # -------------------------------------------------------------------------

    def _init_referentiels_statiques(self, cursor):
        """Réinitialise les codes de base"""
        # Rythmes
        cursor.execute("INSERT OR IGNORE INTO rythme (id_rythme, nom, acronyme) VALUES (1, 'Formation Initiale', 'FI')")
        cursor.execute("INSERT OR IGNORE INTO rythme (id_rythme, nom, acronyme) VALUES (2, 'Alternance', 'FA')")
        # Etats
        cursor.execute("INSERT OR IGNORE INTO etat (id_etat, nom, acronyme) VALUES (1, 'Inscrit', 'I')")
        cursor.execute("INSERT OR IGNORE INTO etat (id_etat, nom, acronyme) VALUES (2, 'Démission', 'D')")
        # Décisions
        codes = [("Admis", "ADM"), ("Ajourné", "AJ"), ("Validé", "V"), ("Non Validé", "NV"), 
                 ("Défaillant", "DEF"), ("Démission", "DEM"), ("Inscrit", "INS"), 
                 ("Admis par Compensation", "CMP"), ("Admis Sous Réserve", "ADM-INC")]
        cursor.executemany("INSERT OR IGNORE INTO decision (nom, acronyme) VALUES (?, ?)", codes)

    #vérifier que le departement FC n'est pas ajouté
    def _import_departements(self, cursor, depts_api, stats):
        donnees = [(d['dept_name'], d['acronym']) for d in depts_api if d.get('visible')]
        donnees.append(("Passerelle SD INFO", "P_SD_INFO"))
        donnees.append(("Passerelle CJ GEA", "P_CJ_GEA"))

        cursor.executemany("INSERT OR REPLACE INTO departement (nom, acronyme) VALUES (?,?)", (donnees))
        stats['departements'] += cursor.rowcount
        
    def _import_formation(self, cursor, fmt, stats):
        """Insertion manuelle des formations"""
        annee_alternance = {2: 1, 1: 3, 3: 2, 4: 2, 5: 2, 6: 2} # GEA, CJ, GEII, INFO, RT, SD
        cursor.execute("SELECT id_departement FROM departement")
        all_depts = [r[0] for r in cursor.fetchall()]
        to_insert = []
        for d_id in all_depts:
            if d_id not in [9, 10]:
                for a in [1, 2, 3]: to_insert.append((a, d_id, 1)) # FI
                if d_id in annee_alternance:
                    debut_fa = annee_alternance[d_id]
                    for a in [1, 2, 3]:
                        if a >= debut_fa: to_insert.append((a, d_id, 2)) # FA
        if 9 in all_depts: to_insert.append((2, 9, 1))
        if 10 in all_depts: to_insert.append((2, 10, 1))
        cursor.executemany("INSERT OR IGNORE INTO formation (annee_but, id_departement, id_rythme) VALUES (?, ?, ?)", to_insert)

    def _import_referentiel_competence(self, cursor, formation_id_scodoc, stats, map_competence_ids):
        """Remplit les tables Parcours et Competence"""
        ref = self.api.get_referentiel_competences(formation_id_scodoc)
        if not ref: return

        # Récupération ID département de la formation en cours
        current_fmt_id = map_competence_ids.get('current_fmt_bdd_id')
        cursor.execute("SELECT id_departement FROM formation WHERE id_formation=?", (current_fmt_id,))
        row = cursor.fetchone()
        id_dept = row[0] if row else 1

        # 1. Parcours
        parcours_api = ref.get('parcours', [])
        map_parcours_ids = {} # ID ScoDoc -> ID BDD

        if not parcours_api:
            # Création parcours par défaut
            cursor.execute("INSERT OR IGNORE INTO parcours (code, nom, id_departement) VALUES (?, ?, ?)",
                           ('TC', 'Tronc Commun', id_dept))
            cursor.execute("SELECT id_parcours FROM parcours WHERE code='TC' AND id_departement=?", (id_dept,))
            row_p = cursor.fetchone()
            default_parcours_id = row_p[0] if row_p else 1
        else:
            default_parcours_id = 1
            for p in parcours_api:
                cursor.execute("INSERT OR IGNORE INTO parcours (code, nom, id_departement) VALUES (?, ?, ?)",
                               (str(p.get('id')), p.get('nom', 'Parcours')[:255], id_dept))
                cursor.execute("SELECT id_parcours FROM parcours WHERE code=?", (str(p.get('id')),))
                pid = cursor.fetchone()
                if pid: map_parcours_ids[p['id']] = pid[0]

        # 2. Compétences
        competences = ref.get('competences', [])
        for comp in competences:
            # Recherche du parcours associé
            scodoc_parcours_id = comp.get('parcours_id')
            id_parcours_bdd = map_parcours_ids.get(scodoc_parcours_id, default_parcours_id)
            
            acronyme_comp = f"UE{comp.get('numero')}"
            
            cursor.execute("""
                INSERT OR IGNORE INTO competence (nom, acronyme, id_parcours) 
                VALUES (?, ?, ?)
            """, (comp.get('libelle', 'Inconnu')[:255], acronyme_comp, id_parcours_bdd))
            
            stats['competences'] += 1

            # Mapping ID ScoDoc -> ID BDD pour lier les notes
            cursor.execute("SELECT id_competence FROM competence WHERE acronyme=? AND id_parcours=?", 
                           (acronyme_comp, id_parcours_bdd))
            row_comp = cursor.fetchone()
            if row_comp:
                # ScoDoc utilise l'ID comme clé dans les résultats
                map_competence_ids[comp['id']] = row_comp[0]

    def _import_resultats_semestre(self, cursor, decisions_json, annee, id_formation_bdd, cache_etus, cache_dec, map_competence_ids, stats):
        
        for etu in decisions_json:
            ine = etu.get('code_ine') or etu.get('etudid')
            if not ine: continue
            
            # A. Etudiant
            if ine not in cache_etus:
                cursor.execute("INSERT OR IGNORE INTO etudiant (ine) VALUES (?)", (ine,))
                cursor.execute("SELECT id_etudiant FROM etudiant WHERE ine=?", (ine,))
                row = cursor.fetchone()
                if row: 
                    cache_etus[ine] = row[0]
                    stats['etudiants'] += 1
            
            id_etudiant = cache_etus.get(ine)
            if not id_etudiant: continue

            # B. Inscription
            code_dec = etu.get('decision', {}).get('code')
            id_decision = cache_dec.get(code_dec, cache_dec.get('INS')) # Fallback INS
            id_etat = 2 if code_dec in ['DEM', 'DEF'] else 1

            cursor.execute("""
                INSERT OR IGNORE INTO inscription 
                (annee_universitaire, id_etudiant, id_etat, id_formation, id_decision)
                VALUES (?, ?, ?, ?, ?)
            """, (annee, id_etudiant, id_etat, id_formation_bdd, id_decision))
            
            # Récupération ID inscription
            cursor.execute("""
                SELECT id_inscription FROM inscription 
                WHERE id_etudiant=? AND annee_universitaire=?
            """, (id_etudiant, annee))
            row_ins = cursor.fetchone()
            
            if row_ins:
                id_inscription = row_ins[0]
                stats['inscriptions'] += 1

                # C. Evaluations (Notes)
                validations = etu.get('validation_competences', {})
                
                for id_comp_scodoc, val_data in validations.items():
                    try:
                        id_comp_scodoc_int = int(id_comp_scodoc)
                    except: continue

                    # On retrouve la compétence BDD grâce au mapping créé dans l'étape Ref
                    id_competence_local = map_competence_ids.get(id_comp_scodoc_int)
                    
                    if id_competence_local:
                        moyenne = val_data.get('moyenne')
                        code_dec_comp = val_data.get('code')
                        id_dec_comp = cache_dec.get(code_dec_comp)
                        
                        # Insertion/Mise à jour note
                        cursor.execute("""
                            INSERT OR REPLACE INTO evaluer (id_inscription, id_competence, id_decision, moyenne)
                            VALUES (?, ?, ?, ?)
                        """, (id_inscription, id_competence_local, id_dec_comp, moyenne))
                        
                        stats['evaluations'] += 1