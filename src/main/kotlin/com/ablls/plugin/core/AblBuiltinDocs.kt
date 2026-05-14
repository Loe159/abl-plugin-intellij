package com.ablls.plugin.core

import java.util.Optional

/**
 * Documentation des built-ins ABL pour le hover (Ctrl+Q) et la complétion.
 *
 * Chaque valeur est du Markdown converti en HTML par [AblDocumentationProvider].
 * Clés en MAJUSCULES — lookup case-insensitive.
 */
object AblBuiltinDocs {

    private val DOCS: Map<String, String> = buildMap {

        // ── Fonctions de chaînes ──────────────────────────────────────────────

        put("LENGTH", """
            **LENGTH** `(string [, type])` → `INTEGER`

            Retourne le nombre de caractères dans une chaîne.

            ```abl
            LENGTH("Hello").       /* 5 */
            LENGTH("café").        /* 4 */
            LENGTH(cVar, "RAW").   /* en octets */
            ```
            """.trimIndent())

        put("SUBSTRING", """
            **SUBSTRING** `(string, start [, length])` → `CHARACTER`

            Extrait une sous-chaîne à partir d'une position (1-based).

            ```abl
            SUBSTRING("Hello World", 7).     /* "World" */
            SUBSTRING("Hello World", 1, 5).  /* "Hello" */
            ```
            """.trimIndent())

        put("SUBSTR", "**Alias** de `SUBSTRING`.")
        put("ENTRY", """
            **ENTRY** `(position, list [, delimiter])` → `CHARACTER`

            Retourne l'élément à la position donnée dans une liste délimitée.

            ```abl
            ENTRY(2, "A,B,C").       /* "B" */
            ENTRY(1, "A:B", ":").    /* "A" */
            ```
            """.trimIndent())

        put("NUM-ENTRIES", """
            **NUM-ENTRIES** `(list [, delimiter])` → `INTEGER`

            Nombre d'éléments dans une liste délimitée.

            ```abl
            NUM-ENTRIES("A,B,C").    /* 3 */
            ```
            """.trimIndent())

        put("REPLACE", """
            **REPLACE** `(source, from, to)` → `CHARACTER`

            Remplace toutes les occurrences de `from` par `to`.

            ```abl
            REPLACE("Hello World", "World", "ABL").  /* "Hello ABL" */
            ```
            """.trimIndent())

        put("TRIM", """
            **TRIM** `(string [, chars])` → `CHARACTER`

            Supprime les espaces (ou caractères spécifiés) en début et fin.

            ```abl
            TRIM("  Hello  ").      /* "Hello" */
            TRIM("..Hello..", "."). /* "Hello" */
            ```
            Voir aussi : `LEFT-TRIM`, `RIGHT-TRIM`
            """.trimIndent())

        put("LEFT-TRIM",  "**LEFT-TRIM** `(string [, chars])` → `CHARACTER`\n\nSupprime les espaces en **début** de chaîne.")
        put("RIGHT-TRIM", "**RIGHT-TRIM** `(string [, chars])` → `CHARACTER`\n\nSupprime les espaces en **fin** de chaîne.")

        put("STRING", """
            **STRING** `(value [, format])` → `CHARACTER`

            Convertit une valeur en chaîne de caractères.

            ```abl
            STRING(42).                    /* "42"         */
            STRING(TODAY, "99/99/9999").   /* "30/03/2026" */
            STRING(TRUE).                  /* "yes"        */
            ```
            """.trimIndent())

        put("INTEGER", """
            **INTEGER** `(value)` → `INTEGER`

            Convertit une valeur en entier (tronque les décimales).

            ```abl
            INTEGER("42").   /* 42 */
            INTEGER(3.99).   /* 3  */
            ```
            """.trimIndent())

        put("INT",     "**Alias** de `INTEGER`. Ex: `INT(\"42\")` → `42`")
        put("INT64",   "**INT64** `(value)` → `INT64`\n\nConvertit en entier 64 bits.")
        put("DECIMAL", "**DECIMAL** `(value)` → `DECIMAL`\n\nConvertit en décimal. Ex: `DECIMAL(\"3.14\")` → `3.14`")
        put("DEC",     "**Alias** de `DECIMAL`.")

        put("CAPS",  "**CAPS** / **UPPER** `(string)` → `CHARACTER`\n\nConvertit en MAJUSCULES.")
        put("UPPER", get("CAPS")!!)
        put("LC",    "**LC** / **LOWER** `(string)` → `CHARACTER`\n\nConvertit en minuscules.")
        put("LOWER", get("LC")!!)

        put("FILL", """
            **FILL** `(string, count)` → `CHARACTER`

            Répète une chaîne `count` fois.

            ```abl
            FILL("*", 5).    /* "*****"  */
            FILL("AB", 3).   /* "ABABAB" */
            ```
            """.trimIndent())

        put("CHR",   "**CHR** `(code)` → `CHARACTER`\n\nRetourne le caractère ASCII/Unicode. Ex: `CHR(65)` → `\"A\"`")
        put("ASC",   "**ASC** `(char)` → `INTEGER`\n\nRetourne le code du caractère. Ex: `ASC(\"A\")` → `65`")
        put("INDEX", """
            **INDEX** `(source, target [, start])` → `INTEGER`

            Position de la première occurrence de `target` dans `source`. `0` si non trouvé.

            ```abl
            INDEX("Hello World", "World").   /* 7 */
            INDEX("ABCABC", "BC", 3).       /* 5 */
            ```
            """.trimIndent())

        put("LOOKUP", """
            **LOOKUP** `(entry, list [, delimiter])` → `INTEGER`

            Position d'un élément dans une liste délimitée. `0` si non trouvé.

            ```abl
            LOOKUP("B", "A,B,C").   /* 2 */
            ```
            """.trimIndent())

        // ── Fonctions numériques ──────────────────────────────────────────────

        put("ABS",       "**ABS** / **ABSOLUTE** `(n)` → même type\n\nValeur absolue. Ex: `ABS(-42)` → `42`")
        put("ABSOLUTE",  get("ABS")!!)
        put("MAX",       "**MAX** `(v1, v2, ...)` → même type\n\nValeur maximale. Ex: `MAX(1,5,3)` → `5`")
        put("MIN",       "**MIN** `(v1, v2, ...)` → même type\n\nValeur minimale. Ex: `MIN(1,5,3)` → `1`")
        put("ROUND",     "**ROUND** `(number, decimals)` → `DECIMAL`\n\nArrondit. Ex: `ROUND(3.456, 2)` → `3.46`")
        put("TRUNCATE",  "**TRUNCATE** `(number, decimals)` → `DECIMAL`\n\nTronque sans arrondi.")
        put("SQRT",      "**SQRT** `(number)` → `DECIMAL`\n\nRacine carrée.")
        put("EXP",       "**EXP** `(base, exponent)` → `DECIMAL`\n\nPuissance.")
        put("LOG",       "**LOG** `(number [, base])` → `DECIMAL`\n\nLogarithme.")
        put("MODULO",    "**MODULO** `(n, m)` → `INTEGER`\n\nReste de la division entière.")

        // ── Fonctions date / heure ────────────────────────────────────────────

        put("TODAY",    "**TODAY** → `DATE`\n\nDate du jour courant.")
        put("NOW",      "**NOW** → `DATETIME-TZ`\n\nDate et heure courantes avec fuseau horaire.")
        put("TIME",     "**TIME** → `INTEGER`\n\nHeure courante en secondes depuis minuit.")
        put("YEAR",     "**YEAR** `(date)` → `INTEGER`\n\nAnnée. Ex: `YEAR(TODAY)` → `2026`")
        put("MONTH",    "**MONTH** `(date)` → `INTEGER`\n\nMois (1-12).")
        put("DAY",      "**DAY** `(date)` → `INTEGER`\n\nJour du mois (1-31).")
        put("WEEKDAY",  "**WEEKDAY** `(date)` → `INTEGER`\n\nJour de la semaine (1=Dim…7=Sam).")
        put("DATE",     "**DATE** `(month, day, year)` → `DATE`\n\nConstruit une date. Ex: `DATE(3, 31, 2026)`")
        put("DATETIME", "**DATETIME** `(date [, ms])` → `DATETIME`\n\nConstruit une datetime.")
        put("ADD-INTERVAL", """
            **ADD-INTERVAL** `(datetime, value, unit)` → `DATETIME` / `DATETIME-TZ`

            Ajoute un intervalle. Unités : `"years"`, `"months"`, `"days"`, `"hours"`, `"minutes"`, `"seconds"`.

            ```abl
            ADD-INTERVAL(TODAY, 7, "days").    /* Dans 7 jours */
            ```
            """.trimIndent())
        put("INTERVAL", "**INTERVAL** `(dt1, dt2, unit)` → `INT64`\n\nDifférence entre deux dates/heures.")

        // ── Fonctions base de données ─────────────────────────────────────────

        put("CAN-FIND", """
            **CAN-FIND** `([FIRST|LAST] record [WHERE] [lock])` → `LOGICAL`

            Teste l'existence d'un enregistrement **sans** le rendre disponible.

            ```abl
            IF CAN-FIND(Customer WHERE Customer.CustNum = iId) THEN
                MESSAGE "Trouvé" VIEW-AS ALERT-BOX.
            ```
            """.trimIndent())

        put("CAN-DO", """
            **CAN-DO** `(list, value)` → `LOGICAL`

            Teste si `value` appartient à `list`. Supporte `*`, `?`, `!`.

            ```abl
            CAN-DO("ADMIN,MANAGER", cRole).
            CAN-DO("*,!GUEST", cRole).
            ```
            """.trimIndent())

        put("AVAILABLE", """
            **AVAILABLE** `[(record)]` → `LOGICAL`

            `TRUE` si l'enregistrement a été trouvé (après FIND ou FOR EACH).

            ```abl
            FIND Customer WHERE Customer.CustNum = 1 NO-LOCK NO-ERROR.
            IF AVAILABLE Customer THEN MESSAGE Customer.Name VIEW-AS ALERT-BOX.
            ```
            """.trimIndent())

        put("AVAIL",          "**Alias** de `AVAILABLE`.")
        put("AMBIGUOUS",      "**AMBIGUOUS** `(record)` → `LOGICAL`\n\n`TRUE` si plusieurs enregistrements correspondent.")
        put("ROWID",          "**ROWID** `(record)` → `ROWID`\n\nIdentifiant de ligne unique d'un enregistrement.")
        put("RECID",          "**RECID** `(record)` → `RECID`\n\nIdentifiant interne. Préférer `ROWID`.")
        put("CURRENT-VALUE",  "**CURRENT-VALUE** `(sequence)` → `INT64`\n\nValeur courante d'une séquence.")
        put("NEXT-VALUE",     "**NEXT-VALUE** `(sequence)` → `INT64`\n\nProchaine valeur d'une séquence.")
        put("FIRST-OF",       "**FIRST-OF** `(field)` → `LOGICAL`\n\n`TRUE` pour le premier enregistrement d'un groupe (`BREAK BY`).")
        put("LAST-OF",        "**LAST-OF** `(field)` → `LOGICAL`\n\n`TRUE` pour le dernier enregistrement d'un groupe.")
        put("COUNT-OF",       "**COUNT-OF** `(record [WHERE])` → `INTEGER`\n\nNombre d'enregistrements correspondants.")
        put("LOCKED",         "**LOCKED** `(record)` → `LOGICAL`\n\n`TRUE` si l'enregistrement est verrouillé par un autre utilisateur.")

        // ── OO / handles ──────────────────────────────────────────────────────

        put("VALID-OBJECT", """
            **VALID-OBJECT** `(object)` → `LOGICAL`

            `TRUE` si la référence objet est valide (non `?` et non détruite).

            ```abl
            IF VALID-OBJECT(oService) THEN oService:DoSomething().
            ```
            """.trimIndent())

        put("VALID-HANDLE", """
            **VALID-HANDLE** `(handle)` → `LOGICAL`

            `TRUE` si le handle est valide.

            ```abl
            IF VALID-HANDLE(hQuery) THEN DELETE OBJECT hQuery.
            ```
            """.trimIndent())

        put("TYPE-OF", """
            **TYPE-OF** `(object, ClassName)` → `LOGICAL`

            `TRUE` si l'objet est une instance de la classe spécifiée.

            ```abl
            IF TYPE-OF(oErr, Progress.Lang.AppError) THEN ...
            ```
            """.trimIndent())

        put("CAST", """
            **CAST** `(object, ClassName)` → référence du type cible

            Caste une référence objet. Lève `SysError` si invalide.

            ```abl
            oApp = CAST(oError, Progress.Lang.AppError).
            ```
            """.trimIndent())

        put("DYNAMIC-FUNCTION", "**DYNAMIC-FUNCTION** `(name [, args])` → `CHARACTER`\n\nAppelle une fonction ABL dynamiquement.")
        put("DYNAMIC-INVOKE",   "**DYNAMIC-INVOKE** `(object, method [, args])`\n\nAppelle une méthode dynamiquement.")
        put("DYNAMIC-NEW",      "**DYNAMIC-NEW** `(ClassName [, args])`\n\nInstancie une classe dynamiquement.")
        put("GET-CLASS",        "**GET-CLASS** `(ClassName)` → `Progress.Lang.Class`\n\nObtient le méta-objet d'une classe.")

        // ── Système / handles système ─────────────────────────────────────────

        put("PROGRAM-NAME",  "**PROGRAM-NAME** `(level)` → `CHARACTER`\n\nNom du programme à un niveau de pile.")
        put("USERID",        "**USERID** `[(db)]` → `CHARACTER`\n\nNom d'utilisateur connecté.")
        put("OPSYS",         "**OPSYS** → `CHARACTER`\n\nNom du système d'exploitation.")
        put("PROVERSION",    "**PROVERSION** → `CHARACTER`\n\nVersion d'OpenEdge. Ex: `\"12.7\"`")
        put("PROPATH",       "**PROPATH** → `CHARACTER`\n\nChemin de recherche des programmes ABL.")
        put("SEARCH",        "**SEARCH** `(filename)` → `CHARACTER`\n\nRecherche un fichier dans le PROPATH. Retourne `?` si non trouvé.")
        put("OS-GETENV",     "**OS-GETENV** `(varname)` → `CHARACTER`\n\nValeur d'une variable d'environnement.")
        put("GENERATE-UUID", "**GENERATE-UUID** → `RAW`\n\nGénère un UUID unique.")
        put("MD5-DIGEST",    "**MD5-DIGEST** `(value)` → `RAW`\n\nCondensé MD5.")
        put("SHA1-DIGEST",   "**SHA1-DIGEST** `(value)` → `RAW`\n\nCondensé SHA-1.")

        put("SESSION", """
            **SESSION** — Handle vers la session courante

            | Attribut | Description |
            |----------|-------------|
            | `SESSION:BATCH-MODE` | `TRUE` en mode batch |
            | `SESSION:PARAMETER` | Valeur du paramètre `-param` |
            | `SESSION:CHARSET` | Jeu de caractères |

            ```abl
            IF SESSION:BATCH-MODE THEN QUIT.
            ```
            """.trimIndent())

        put("THIS-PROCEDURE", """
            **THIS-PROCEDURE** — Handle vers la procédure courante

            ```abl
            MESSAGE THIS-PROCEDURE:FILE-NAME VIEW-AS ALERT-BOX.
            ```
            """.trimIndent())

        put("THIS-OBJECT",   "**THIS-OBJECT** — Référence à l'instance courante (équivalent de `this`).")
        put("SUPER",         "**SUPER** — Référence à la classe parente.")
        put("ERROR-STATUS",  "**ERROR-STATUS** — État d'erreur après `NO-ERROR`.\n\nEx: `ERROR-STATUS:ERROR`, `ERROR-STATUS:GET-MESSAGE(1)`")
        put("RETURN-VALUE",  "**RETURN-VALUE** → `CHARACTER`\n\nValeur retournée par le dernier `RUN` ou `RETURN \"valeur\"`.")

        // ── Instructions ──────────────────────────────────────────────────────

        put("DEFINE", """
            **DEFINE** — Déclaration d'une variable, paramètre, table temporaire, etc.

            ```abl
            DEFINE VARIABLE   cName  AS CHARACTER NO-UNDO.
            DEFINE PARAMETER  iId    AS INTEGER.
            DEFINE TEMP-TABLE ttData NO-UNDO FIELD Id AS INTEGER FIELD Name AS CHARACTER.
            ```
            """.trimIndent())

        put("ASSIGN", """
            **ASSIGN** `field = value [field = value ...]`

            Affecte des valeurs en une seule transaction atomique.

            ```abl
            ASSIGN
                Customer.Name    = "Smith"
                Customer.Balance = Customer.Balance + 100.
            ```
            """.trimIndent())

        put("FOR", """
            **FOR** `[EACH|FIRST|LAST] record [WHERE] [BY] [NO-LOCK]:`

            Itère sur des enregistrements.

            ```abl
            FOR EACH Customer WHERE Customer.Balance > 0 NO-LOCK BY Customer.Name:
                DISPLAY Customer.Name Customer.Balance.
            END.
            ```
            """.trimIndent())

        put("FIND", """
            **FIND** `[FIRST|LAST|NEXT|PREV] record [WHERE] [NO-LOCK] [NO-ERROR]`

            Recherche un seul enregistrement.

            ```abl
            FIND Customer WHERE Customer.CustNum = iId NO-LOCK NO-ERROR.
            IF NOT AVAILABLE Customer THEN MESSAGE "Introuvable" VIEW-AS ALERT-BOX.
            ```
            """.trimIndent())

        put("MESSAGE", """
            **MESSAGE** `items [...] [VIEW-AS ALERT-BOX]`

            Affiche un message à l'utilisateur.

            ```abl
            MESSAGE "Valeur:" dAmount VIEW-AS ALERT-BOX TITLE "Résultat".
            ```
            """.trimIndent())

        put("RUN", """
            **RUN** `program [IN handle] [PERSISTENT SET handle] [(params)]`

            Exécute un programme ou une procédure ABL.

            ```abl
            RUN myproc.p (INPUT iId, OUTPUT cResult).
            ```
            """.trimIndent())

        put("CREATE", """
            **CREATE** `record`

            Crée un nouvel enregistrement (dans une transaction).

            ```abl
            CREATE Customer.
            ASSIGN Customer.CustNum = NEXT-VALUE(CustSeq)
                   Customer.Name    = "New Customer".
            ```
            """.trimIndent())

        put("DELETE",  "**DELETE** `record [NO-ERROR]`\n\nSupprime un enregistrement.")
        put("RELEASE", "**RELEASE** `record`\n\nLibère le verrou sur un enregistrement.")

        put("NEW", """
            **NEW** `ClassName([args])`

            Instancie une classe ABL OO.

            ```abl
            oSvc = NEW com.myapp.CustomerService("localhost").
            ```
            """.trimIndent())

        put("USING",      "**USING** `package[.*]`\n\nImporte un package pour éviter les noms qualifiés complets.")
        put("INHERITS",   "**INHERITS** `ClassName`\n\nDéclare l'héritage dans une définition de classe.")
        put("IMPLEMENTS", "**IMPLEMENTS** `Interface [, Interface2]`\n\nDéclare les interfaces implémentées.")

        put("CATCH", """
            **CATCH** `var AS [CLASS] ExceptionType:`

            Capture une exception ABL.

            ```abl
            CATCH e AS Progress.Lang.AppError:
                MESSAGE e:ReturnValue VIEW-AS ALERT-BOX.
            END CATCH.
            ```
            """.trimIndent())

        put("THROW", """
            **THROW** `error-object`

            Lève une exception ABL.

            ```abl
            THROW NEW Progress.Lang.AppError("Erreur métier", 1).
            ```
            """.trimIndent())

        put("FINALLY", "**FINALLY** — Bloc exécuté quoi qu'il arrive (après CATCH).")
        put("UNDO",     "**UNDO** `[label] [LEAVE|NEXT|RETURN|RETRY|THROW]`\n\nAnnule les modifications et transfère le contrôle.")
        put("QUIT",     "**QUIT** — Quitte le programme ABL.")
        put("RETURN",   "**RETURN** `[value]`\n\nRetourne depuis une procédure/fonction.")
        put("LEAVE",    "**LEAVE** `[label]`\n\nSort d'une boucle.")
        put("NEXT",     "**NEXT** `[label]`\n\nPasse à l'itération suivante.")

        // ── Fonctions de chaînes (suite) ──────────────────────────────────────

        put("SUBSTITUTE", """
            **SUBSTITUTE** `(string, v1 [, v2 ...])` → `CHARACTER`

            Remplace les marqueurs `&1`, `&2`… par les valeurs correspondantes.

            ```abl
            SUBSTITUTE("Bonjour &1, vous avez &2 messages.", cName, iCount).
            /* "Bonjour Alice, vous avez 3 messages." */
            ```
            """.trimIndent())

        put("COMPARE", """
            **COMPARE** `(s1, operator, s2 [, type])` → `LOGICAL`

            Compare deux chaînes en tenant compte du type (CASE-SENSITIVE, RAW…).

            ```abl
            COMPARE("abc", "EQ", "ABC", "CASE-SENSITIVE").  /* FALSE */
            COMPARE("abc", "EQ", "ABC", "CASE-INSENSITIVE"). /* TRUE  */
            ```
            """.trimIndent())

        put("MATCHES", """
            **MATCHES** `(string, pattern)` → `LOGICAL`

            Teste une correspondance de motif (wildcards `*` et `?`).

            ```abl
            IF cName MATCHES "*Smith*" THEN ...
            ```
            Opérateur équivalent : `string MATCHES pattern`
            """.trimIndent())

        put("BEGINS", """
            **BEGINS** — opérateur de comparaison de préfixe

            `s1 BEGINS s2` → `TRUE` si `s1` commence par `s2` (insensible à la casse).

            ```abl
            IF cName BEGINS "Sm" THEN ...
            ```
            """.trimIndent())

        put("ENCODE", """
            **ENCODE** `(string)` → `CHARACTER`

            Encode un mot de passe (sens unique, non réversible).

            ```abl
            cHash = ENCODE(cPassword).
            ```
            """.trimIndent())

        put("BASE64-ENCODE", """
            **BASE64-ENCODE** `(data)` → `CHARACTER`

            Encode en Base64. Accepte `CHARACTER` ou `RAW`.

            ```abl
            cEncoded = BASE64-ENCODE(CAST(mLob, RAW)).
            ```
            """.trimIndent())

        put("BASE64-DECODE", """
            **BASE64-DECODE** `(string)` → `RAW`

            Décode une chaîne Base64 en `RAW`.

            ```abl
            rData = BASE64-DECODE(cEncoded).
            ```
            """.trimIndent())

        put("HEX-ENCODE", "**HEX-ENCODE** `(data)` → `CHARACTER`\n\nEncode en hexadécimal.")
        put("HEX-DECODE", "**HEX-DECODE** `(string)` → `RAW`\n\nDécode une chaîne hexadécimale.")

        put("OVERLAY", """
            **OVERLAY** `(target, position, length)` = `source`

            Remplace une portion d'une chaîne à une position donnée.

            ```abl
            DEFINE VARIABLE cStr AS CHARACTER NO-UNDO INITIAL "Hello World".
            OVERLAY(cStr, 7, 5) = "ABL  ".   /* "Hello ABL  " */
            ```
            """.trimIndent())

        put("GETBYTE",  "**GETBYTE** `(string, position)` → `INTEGER`\n\nRetourne la valeur d'octet à la position donnée.")
        put("PUTBYTE",  "**PUTBYTE** `(target, position)` = `integer`\n\nEcrit un octet à la position.")
        put("GET-BYTE", "**Alias** de `GETBYTE`.")
        put("PUT-BYTE", "**Alias** de `PUTBYTE`.")

        // ── Fonctions numériques (suite) ──────────────────────────────────────

        put("MAXIMUM", "**MAXIMUM** `(v1, v2, ...)` → même type\n\nAlias de `MAX`.")
        put("MINIMUM", "**MINIMUM** `(v1, v2, ...)` → même type\n\nAlias de `MIN`.")
        put("RANDOM",  "**RANDOM** `(low, high)` → `INTEGER`\n\nNombre entier aléatoire entre `low` et `high` (inclus).")
        put("SIGN",    "**SIGN** `(n)` → `INTEGER`\n\n`1` si positif, `0` si zéro, `-1` si négatif.")

        // ── Fonctions date / heure (suite) ────────────────────────────────────

        put("MTIME",           "**MTIME** `[(date)]` → `INTEGER`\n\nHeure en millisecondes depuis minuit. Sans argument : heure courante.")
        put("DATETIME-TZ",     "**DATETIME-TZ** `(date, ms, tz)` → `DATETIME-TZ`\n\nConstruit une datetime avec fuseau horaire.")
        put("TIMEZONE",        "**TIMEZONE** `[(datetime-tz)]` → `INTEGER`\n\nDécalage UTC en minutes.")
        put("ISO-DATE",        "**ISO-DATE** `(date|datetime)` → `CHARACTER`\n\nFormate en ISO 8601. Ex: `\"2026-03-31\"`")
        put("DATE-TO-INTEGER", "**DATE-TO-INTEGER** `(date)` → `INTEGER`\n\nNombre de jours depuis le 1er janvier 01.")
        put("INTEGER-TO-DATE", "**INTEGER-TO-DATE** `(integer)` → `DATE`\n\nConvertit un entier en date.")

        // ── Fonctions logiques / flux ─────────────────────────────────────────

        put("IF", """
            **IF** `condition THEN value1 ELSE value2` — expression ternaire inline

            Utilisé comme expression (pas comme instruction).

            ```abl
            cLabel = IF lActive THEN "Actif" ELSE "Inactif".
            ```
            Voir aussi l'instruction `IF ... THEN: ... ELSE: ... END.`
            """.trimIndent())

        put("CASE", """
            **CASE** `expression:`

            Branchement multi-valeurs.

            ```abl
            CASE cStatus:
                WHEN "A" THEN MESSAGE "Actif".
                WHEN "I" THEN MESSAGE "Inactif".
                OTHERWISE    MESSAGE "Inconnu".
            END CASE.
            ```
            """.trimIndent())

        put("DO", """
            **DO** `[WHILE|UNTIL cond] [ON ERROR|STOP|QUIT UNDO] :`

            Bloc délimité. Forme loop avec WHILE/UNTIL.

            ```abl
            DO WHILE iCounter < 10:
                iCounter = iCounter + 1.
            END.
            ```
            """.trimIndent())

        put("REPEAT", """
            **REPEAT** `[WHILE|UNTIL cond] :`

            Boucle infinie ou conditionnelle.

            ```abl
            REPEAT WHILE NOT lDone:
                /* traitement */
                IF cInput = "QUIT" THEN LEAVE.
            END.
            ```
            """.trimIndent())

        // ── Affichage / UI ────────────────────────────────────────────────────

        put("DISPLAY", """
            **DISPLAY** `items [...] [IN FRAME name] [WITH FRAME name]`

            Affiche des valeurs dans un frame.

            ```abl
            DISPLAY Customer.CustNum Customer.Name Customer.Balance WITH FRAME fMain.
            ```
            """.trimIndent())

        put("PROMPT-FOR", """
            **PROMPT-FOR** `fields [...] [IN FRAME name]`

            Attend la saisie de l'utilisateur sur les champs spécifiés.

            ```abl
            PROMPT-FOR Customer.Name WITH FRAME fInput.
            ```
            """.trimIndent())

        put("UPDATE", """
            **UPDATE** `fields [...] [IN FRAME name]`

            Affiche et attend la modification de champs (display + prompt-for).

            ```abl
            UPDATE Customer.Name Customer.CreditLimit WITH FRAME fEdit.
            ```
            """.trimIndent())

        put("ENABLE",  "**ENABLE** `[ALL|fields] [IN FRAME name]`\n\nActive les champs pour la saisie.")
        put("DISABLE", "**DISABLE** `[ALL|fields] [IN FRAME name]`\n\nDésactive les champs pour la saisie.")
        put("HIDE",    "**HIDE** `[FRAME name|ALL] [NO-PAUSE]`\n\nMasque un frame.")
        put("CLEAR",   "**CLEAR** `[FRAME name] [ALL] [NO-PAUSE]`\n\nEfface le contenu d'un frame.")

        put("INPUT-CLEAR", "**INPUT CLEAR**\n\nVide le buffer de saisie.")

        put("BELL", "**BELL**\n\nÉmet un signal sonore.")

        // ── E/S fichiers ──────────────────────────────────────────────────────

        put("INPUT", """
            **INPUT FROM** `{file|TERMINAL|PIPE cmd|CLIPBOARD}` `[NO-ECHO] [ECHO]`

            Redirige l'entrée standard vers un fichier ou terminal.

            ```abl
            INPUT FROM "data.txt".
            REPEAT:
                IMPORT cLine.
                IF cLine = "" THEN LEAVE.
            END.
            INPUT CLOSE.
            ```
            """.trimIndent())

        put("OUTPUT", """
            **OUTPUT TO** `{file|TERMINAL|PRINTER|CLIPBOARD}` `[APPEND]`

            Redirige la sortie vers un fichier ou imprimante.

            ```abl
            OUTPUT TO "report.txt".
            DISPLAY "Hello".
            OUTPUT CLOSE.
            ```
            """.trimIndent())

        put("IMPORT", """
            **IMPORT** `[DELIMITER char] vars [UNFORMATTED]`

            Lit une ligne depuis l'entrée courante dans des variables.

            ```abl
            IMPORT DELIMITER "," cCol1 cCol2 cCol3.
            ```
            """.trimIndent())

        put("EXPORT", """
            **EXPORT** `[DELIMITER char] values`

            Écrit des valeurs dans la sortie courante.

            ```abl
            EXPORT DELIMITER "," Customer.CustNum Customer.Name.
            ```
            """.trimIndent())

        put("PUT", """
            **PUT** `[UNFORMATTED] values`

            Écrit dans la sortie courante sans formatage.

            ```abl
            PUT UNFORMATTED "ligne de texte" SKIP.
            ```
            """.trimIndent())

        put("GET", """
            **GET** `[NEXT|PREV|FIRST|LAST|CURRENT] queryname`

            Déplace le curseur d'une requête.

            ```abl
            OPEN QUERY qCustomer FOR EACH Customer.
            GET FIRST qCustomer.
            ```
            """.trimIndent())

        put("COPY-LOB", """
            **COPY-LOB** `[FROM] source TO target [NO-CONVERT]`

            Copie un LOB (CLOB/BLOB) entre variables ou fichiers.

            ```abl
            COPY-LOB FROM FILE "image.png" TO rBlob.
            COPY-LOB FROM rBlob TO FILE "copy.png".
            ```
            """.trimIndent())

        put("READ-JSON", """
            **READ-JSON** `(schema-type, source [, read-mode])`

            Lit du JSON dans un DATASET ou TEMP-TABLE.

            ```abl
            dsOrder:READ-JSON("DATASET", "order.json", "EMPTY").
            ```
            """.trimIndent())

        put("WRITE-JSON", """
            **WRITE-JSON** `(schema-type, target [, pretty-print])`

            Sérialise un DATASET ou TEMP-TABLE en JSON.

            ```abl
            dsOrder:WRITE-JSON("DATASET", "out.json", TRUE).
            ```
            """.trimIndent())

        put("READ-XML", "**READ-XML** `(schema-type, source [, read-mode [, schema-source [, lang]]])`\n\nLit du XML dans un DATASET ou TEMP-TABLE.")
        put("WRITE-XML", "**WRITE-XML** `(schema-type, target [, pretty-print ...])`\n\nSérialise un DATASET ou TEMP-TABLE en XML.")

        // ── Buffer / requête ──────────────────────────────────────────────────

        put("BUFFER-COPY", """
            **BUFFER-COPY** `source TO target [EXCEPT fields]`

            Copie les champs d'un buffer dans un autre.

            ```abl
            BUFFER-COPY Customer TO ttCustomer EXCEPT Customer.CustNum.
            ```
            """.trimIndent())

        put("BUFFER-COMPARE", """
            **BUFFER-COMPARE** `source TO target [EXCEPT fields]` → `LOGICAL`

            Compare deux buffers champ par champ.

            ```abl
            IF BUFFER-COMPARE Customer TO ttOriginal THEN
                MESSAGE "Pas de changement" VIEW-AS ALERT-BOX.
            ```
            """.trimIndent())

        put("QUERY-OFF-END", """
            **QUERY-OFF-END** `(queryname)` → `LOGICAL`

            `TRUE` si la dernière opération GET a dépassé les bornes de la requête.

            ```abl
            GET NEXT qCustomer.
            IF QUERY-OFF-END("qCustomer") THEN LEAVE.
            ```
            """.trimIndent())

        put("NUM-RESULTS", "**NUM-RESULTS** `(queryname)` → `INTEGER`\n\nNombre d'enregistrements de la requête (si disponible).")

        put("OPEN QUERY", """
            **OPEN QUERY** `name FOR [EACH|FIRST|LAST] record [WHERE] [BY]`

            Ouvre une requête nommée.

            ```abl
            OPEN QUERY qCust FOR EACH Customer WHERE Customer.Active = TRUE NO-LOCK.
            ```
            """.trimIndent())

        put("CLOSE QUERY", "**CLOSE QUERY** `name`\n\nFerme et libère une requête nommée.")

        put("DEFINE QUERY", """
            **DEFINE QUERY** `name FOR record [, record2]`

            Déclare une requête statique.

            ```abl
            DEFINE QUERY qCust FOR Customer SCROLLING.
            ```
            """.trimIndent())

        // ── Tables temporaires / datasets ─────────────────────────────────────

        put("TEMP-TABLE", """
            **DEFINE TEMP-TABLE** `name [NO-UNDO] FIELD name AS type [...]`

            Déclare une table temporaire (en mémoire ou profilée).

            ```abl
            DEFINE TEMP-TABLE ttOrder NO-UNDO
                FIELD OrderId AS INTEGER
                FIELD Amount  AS DECIMAL
                INDEX idxOrder IS PRIMARY UNIQUE OrderId.
            ```
            """.trimIndent())

        put("DATASET", """
            **DEFINE DATASET** `name FOR table1 [, table2 ...]`

            Déclare un dataset multi-tables.

            ```abl
            DEFINE DATASET dsOrder FOR ttOrder, ttLine.
            ```
            """.trimIndent())

        put("EMPTY TEMP-TABLE", "**EMPTY TEMP-TABLE** `name`\n\nVide une table temporaire.")

        // ── Transactions / erreurs ────────────────────────────────────────────

        put("TRANSACTION", """
            **TRANSACTION** → `LOGICAL`

            `TRUE` si une transaction est en cours.

            ```abl
            IF TRANSACTION THEN UNDO, RETURN "Déjà en transaction".
            ```
            """.trimIndent())

        put("NO-ERROR", "**NO-ERROR** — Supprime l'exception sur l'instruction courante. Tester `ERROR-STATUS:ERROR` ensuite.")
        put("NO-LOCK",  "**NO-LOCK** — Accès lecture seule sans verrouillage (le plus performant pour les lectures).")
        put("SHARE-LOCK",     "**SHARE-LOCK** — Verrou partagé (plusieurs lecteurs, un seul écrivain).")
        put("EXCLUSIVE-LOCK", "**EXCLUSIVE-LOCK** — Verrou exclusif (lecture + écriture, bloque les autres).")
        put("NO-WAIT",  "**NO-WAIT** — Retourne immédiatement si l'enregistrement est verrouillé (plutôt que d'attendre).")
        put("NO-UNDO",  "**NO-UNDO** — La variable/temp-table n'est pas restaurée lors d'un UNDO (meilleure performance).")

        put("ERROR",    "**ERROR** → `LOGICAL`\n\nAttribut de `ERROR-STATUS`. `TRUE` si la dernière instruction a levé une erreur.")

        // ── Système de fichiers ───────────────────────────────────────────────

        put("OS-COPY",   "**OS-COPY** `source dest`\n\nCopie un fichier.")
        put("OS-DELETE", "**OS-DELETE** `filename`\n\nSupprime un fichier.")
        put("OS-RENAME", "**OS-RENAME** `old new`\n\nRenomme ou déplace un fichier.")
        put("OS-CREATE-DIR", "**OS-CREATE-DIR** `path`\n\nCrée un répertoire.")
        put("OS-ERROR",  "**OS-ERROR** → `INTEGER`\n\nCode d'erreur de la dernière opération OS. `0` = succès.")

        put("FILE-INFO", """
            **FILE-INFO** — Handle vers les informations du fichier courant

            | Attribut | Description |
            |----------|-------------|
            | `FILE-INFO:FILE-NAME` | Nom complet du fichier |
            | `FILE-INFO:FULL-PATHNAME` | Chemin absolu |
            | `FILE-INFO:FILE-TYPE` | `"F"`, `"D"`, `"L"` ou `?` |
            | `FILE-INFO:FILE-MOD-TIME` | Timestamp de modification |
            | `FILE-INFO:FILE-SIZE` | Taille en octets |

            ```abl
            FILE-INFO:FILE-NAME = "report.txt".
            IF FILE-INFO:FILE-TYPE = "F" THEN MESSAGE "Fichier trouvé".
            ```
            """.trimIndent())

        // ── Réseau / AppServer ────────────────────────────────────────────────

        put("CONNECT", """
            **CONNECT** `[-db dbname] [-ld logicalName] [-H host] [-S port]`

            Connecte à une base de données.

            ```abl
            CONNECT -db sports2020 -ld sports -H localhost -S 8500 -N tcp.
            ```
            """.trimIndent())

        put("DISCONNECT", "**DISCONNECT** `logicalName`\n\nDéconnecte d'une base de données.")

        put("SOAPREQUEST", "**SOAPREQUEST** — Objet pour les appels SOAP Web Services.")

        // ── Contrôle de flux avancé ───────────────────────────────────────────

        put("PROCEDURE", """
            **PROCEDURE** `name [PRIVATE|PROTECTED] :`

            Déclare une procédure interne.

            ```abl
            PROCEDURE processOrder:
                DEFINE INPUT PARAMETER iId AS INTEGER NO-UNDO.
                /* corps */
            END PROCEDURE.
            ```
            """.trimIndent())

        put("FUNCTION", """
            **FUNCTION** `name RETURNS type [PRIVATE] :`

            Déclare une fonction interne.

            ```abl
            FUNCTION calcTax RETURNS DECIMAL (INPUT dAmount AS DECIMAL):
                RETURN dAmount * 0.2.
            END FUNCTION.
            ```
            """.trimIndent())

        put("CLASS", """
            **CLASS** `ClassName [INHERITS Parent] [IMPLEMENTS Iface] :`

            Déclare une classe ABL OO.

            ```abl
            CLASS com.myapp.OrderService INHERITS BaseService:
                METHOD PUBLIC VOID processOrder(INPUT iId AS INTEGER):
                    /* corps */
                END METHOD.
            END CLASS.
            ```
            """.trimIndent())

        put("METHOD", """
            **METHOD** `[access] [scope] returnType name ([params]) :`

            Déclare une méthode dans une classe.

            ```abl
            METHOD PUBLIC DECIMAL calcTotal(INPUT iQty AS INTEGER):
                RETURN iQty * dUnitPrice.
            END METHOD.
            ```
            """.trimIndent())

        put("CONSTRUCTOR", """
            **CONSTRUCTOR** `[PUBLIC|PROTECTED|PRIVATE] ClassName ([params]) :`

            Déclare un constructeur de classe.

            ```abl
            CONSTRUCTOR PUBLIC OrderService(INPUT cConfig AS CHARACTER):
                THIS-OBJECT:Config = cConfig.
            END CONSTRUCTOR.
            ```
            """.trimIndent())

        put("DESTRUCTOR", """
            **DESTRUCTOR** `PUBLIC ClassName () :`

            Déclare un destructeur de classe (finalizer).

            ```abl
            DESTRUCTOR PUBLIC OrderService():
                IF VALID-OBJECT(oHelper) THEN DELETE OBJECT oHelper.
            END DESTRUCTOR.
            ```
            """.trimIndent())

        put("INTERFACE", """
            **INTERFACE** `InterfaceName [INHERITS Parent] :`

            Déclare une interface ABL OO.

            ```abl
            INTERFACE com.myapp.IService:
                METHOD PUBLIC VOID process(INPUT iId AS INTEGER).
            END INTERFACE.
            ```
            """.trimIndent())

        put("ABSTRACT", "**ABSTRACT** — Modificateur : la méthode/classe doit être implémentée par les sous-classes.")
        put("OVERRIDE", "**OVERRIDE** — Indique qu'une méthode redéfinit la méthode parente.")
        put("FINAL",    "**FINAL** — Modificateur : la méthode/classe ne peut pas être redéfinie.")
        put("STATIC",   "**STATIC** — Modificateur : membre de classe, pas d'instance.")

        // ── Préprocesseurs ────────────────────────────────────────────────────

        put("&IF", """
            **&IF** `DEFINED(name)` / **&IF** `expression`

            Compilation conditionnelle.

            ```abl
            &IF DEFINED(DEBUG) &THEN
                MESSAGE "Mode debug" VIEW-AS ALERT-BOX.
            &ENDIF
            ```
            """.trimIndent())

        put("&DEFINE",        "**&DEFINE** `name value`\n\nDéfinit un préprocesseur. Ex: `&DEFINE MAX-RETRY 3`")
        put("&SCOPED-DEFINE", "**&SCOPED-DEFINE** `name value`\n\nPréprocesseur limité au fichier courant.")
        put("&GLOBAL-DEFINE", "**&GLOBAL-DEFINE** `name value`\n\nPréprocesseur disponible dans tous les includes.")
        put("&UNDEFINE",      "**&UNDEFINE** `name`\n\nSupprime la définition d'un préprocesseur.")
        put("&ANALYZE-SUSPEND", "**&ANALYZE-SUSPEND** / **&ANALYZE-RESUME**\n\nSuspend l'analyse statique (zones générées par AppBuilder).")
        put("DEFINED",        "**DEFINED** `(name)` → `INTEGER`\n\n`0` si non défini, `1` si global, `2` si scoped, `3` si paramètre.")

        // ── Attributs objet courants ──────────────────────────────────────────

        put("EXTENT", """
            **EXTENT** — Déclare ou obtient la taille d'un tableau.

            ```abl
            DEFINE VARIABLE aiValues AS INTEGER EXTENT 10 NO-UNDO.
            MESSAGE EXTENT(aiValues) VIEW-AS ALERT-BOX.  /* 10 */
            ```
            """.trimIndent())

        put("INITIAL", "**INITIAL** `value` — Valeur initiale d'une variable lors de sa déclaration.")
        put("FORMAT",  "**FORMAT** `\"fmt\"` — Masque de saisie/affichage. Ex: `FORMAT \"X(30)\"`, `FORMAT \"99/99/9999\"`.")
        put("LABEL",   "**LABEL** `\"text\"` — Libellé d'un champ dans un frame.")
        put("COLUMN-LABEL", "**COLUMN-LABEL** `\"text\"`\n\nLibellé de colonne dans un DISPLAY.")

        // ── Annotations ──────────────────────────────────────────────────────

        put("@", """
            **@AnnotationName** — Annotation ABL OO

            Les annotations ABL sont utilisées par ABLUnit et certains frameworks.

            ```abl
            @Test.
            METHOD PUBLIC VOID testCalcTax():
                Assert:Equals(0.2, calcTax(1)).
            END METHOD.
            ```
            """.trimIndent())
    }

    fun get(name: String): Optional<String> =
        Optional.ofNullable(DOCS[name.uppercase().trim()])

    fun has(name: String): Boolean =
        DOCS.containsKey(name.uppercase().trim())
}
