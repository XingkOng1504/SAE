PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS evaluer;
DROP TABLE IF EXISTS inscription;
DROP TABLE IF EXISTS competence;
DROP TABLE IF EXISTS parcours;
DROP TABLE IF EXISTS formation;
DROP TABLE IF EXISTS etudiant;
DROP TABLE IF EXISTS departement;
DROP TABLE IF EXISTS rythme;
DROP TABLE IF EXISTS etat;
DROP TABLE IF EXISTS decision;

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS decision(
    id_decision INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    acronyme TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS etat(
    id_etat INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    acronyme TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS rythme(
    id_rythme INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    acronyme TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS departement(
    id_departement INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    acronyme TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS etudiant(
    id_etudiant INTEGER PRIMARY KEY AUTOINCREMENT,
    ine TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS formation(
    id_formation INTEGER PRIMARY KEY AUTOINCREMENT,
    annee_but INTEGER NOT NULL,
    id_departement INTEGER NOT NULL,
    id_rythme INTEGER NOT NULL,
    FOREIGN KEY(id_departement) REFERENCES departement(id_departement),
    FOREIGN KEY(id_rythme) REFERENCES rythme(id_rythme),
    UNIQUE(annee_but, id_departement, id_rythme)
);

CREATE TABLE IF NOT EXISTS parcours(
    id_parcours INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(10) NOT NULL,
    nom VARCHAR(255) NOT NULL,
    id_departement INT NOT NULL,
    FOREIGN KEY(id_departement ) REFERENCES departement(id_departement )
);

CREATE TABLE IF NOT EXISTS competence(
    id_competence INTEGER PRIMARY KEY AUTOINCREMENT,
    nom VARCHAR(255) NOT NULL,
    acronyme VARCHAR(10) NOT NULL,
    id_parcours  INT NOT NULL,
    FOREIGN KEY(id_parcours) REFERENCES parcours(id_parcours)
);

CREATE TABLE IF NOT EXISTS inscription(
    id_inscription INTEGER PRIMARY KEY AUTOINCREMENT,
    annee_universitaire INTEGER NOT NULL,
    id_etudiant INTEGER NOT NULL,
    id_etat INTEGER NOT NULL,
    id_formation INTEGER NOT NULL,
    id_decision INTEGER,
    FOREIGN KEY(id_decision) REFERENCES decision(id_decision),
    FOREIGN KEY(id_etudiant) REFERENCES etudiant(id_etudiant),
    FOREIGN KEY(id_etat) REFERENCES etat(id_etat),
    FOREIGN KEY(id_formation) REFERENCES formation(id_formation),
    UNIQUE(id_etudiant, annee_universitaire)
);

CREATE TABLE IF NOT EXISTS evaluer(
    id_inscription INTEGER,
    id_competence INTEGER,
    id_decision INTEGER,
    moyenne DECIMAL(4,2), 
    PRIMARY KEY(id_inscription, id_competence),
    FOREIGN KEY(id_inscription) REFERENCES inscription(id_inscription),
    FOREIGN KEY(id_competence) REFERENCES competence(id_competence),
    FOREIGN KEY(id_decision) REFERENCES decision(id_decision)
);