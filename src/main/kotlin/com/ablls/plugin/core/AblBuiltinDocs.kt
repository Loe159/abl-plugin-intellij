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
    }

    fun get(name: String): Optional<String> =
        Optional.ofNullable(DOCS[name.uppercase().trim()])

    fun has(name: String): Boolean =
        DOCS.containsKey(name.uppercase().trim())
}
