/*
 * OE debug bootstrap — extrait à chaque session debug par AblProgramRunner.
 *
 * Rôle : pauser OE le temps qu'IntelliJ se connecte au port -debugReady et
 * enregistre les breakpoints. Sans ce sas, OE exécuterait le programme avant
 * que les breakpoints soient envoyés et ils ne seraient jamais atteints.
 *
 * Variables d'environnement :
 *   ABL_DEBUG_PROGRAM   chemin absolu du fichier utilisateur (.p / .w)
 *   ABL_DEBUG_PROPATH   PROPATH à appliquer (séparé par ',')
 *
 * Séquence :
 *   1. OE démarre, ouvre le port -debugReady.
 *   2. Ce script applique le PROPATH puis bloque sur READKEY.
 *   3. IntelliJ se connecte, envoie SETPROP IDE 1, envoie les breakpoints.
 *   4. IntelliJ écrit un caractère sur stdin → READKEY débloque.
 *   5. RUN VALUE(ABL_DEBUG_PROGRAM) → le programme utilisateur s'exécute.
 */

DEFINE VARIABLE userProgram AS CHARACTER NO-UNDO.
DEFINE VARIABLE extraPath   AS CHARACTER NO-UNDO.

ASSIGN
    userProgram = OS-GETENV("ABL_DEBUG_PROGRAM")
    extraPath   = OS-GETENV("ABL_DEBUG_PROPATH").

IF extraPath <> "" THEN
    ASSIGN PROPATH = extraPath + "," + PROPATH.

/* Sas — IntelliJ libère READKEY après le handshake */
READKEY.

IF userProgram <> "" THEN
    RUN VALUE(userProgram).
