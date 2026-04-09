import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm")               version "2.0.0"
    id("org.jetbrains.intellij.platform")
    id("org.jetbrains.kotlin.plugin.serialization") version "2.0.0"
}

group  = providers.gradleProperty("pluginGroup").orElse("com.ablls").get()
version = providers.gradleProperty("pluginVersion").orElse("1.0.0").get()

kotlin {
    jvmToolchain(17)
}


// ─── Dépendances ─────────────────────────────────────────────────────────────
dependencies {

    // ── IntelliJ Platform ────────────────────────────────────────────────────
    intellijPlatform {
        // IDE cible
        intellijIdeaCommunity(
            providers.gradleProperty("platformVersion")
        )

        // Framework de tests pour les plugins IntelliJ
        testFramework(TestFrameworkType.Platform)

        // Vérificateur de compatibilité
        pluginVerifier()
    }

    // ── CABL / Riverside Software : parser ABL officiel ──────────────────────
    //
    // Ce package contient :
    //   - ABLLexer (ANTLR4, ~900 tokens ABL complets)
    //   - ABLParser / ProParser (ANTLR4, grammaire complète et maintenue)
    //   - ABLNodeType (enum de tous les types de nœuds AST)
    //   - ProparserTokenTypes (constantes numériques des tokens)
    //
    // Version : vérifier https://github.com/Riverside-Software/sonar-openedge/releases
    implementation("eu.rssw.openedge.parsers:proparse:3.7.2") {
        // Exclure les dépendances Sonar inutiles dans le contexte plugin
        exclude(group = "org.sonarsource.sonarqube")
        exclude(group = "org.sonarsource.analyzer-commons")
    }

    // ── Profiler parser RSSW (couverture de code via .prof) ──────────────────
    implementation("eu.rssw.openedge.parsers:profiler-parser:3.7.2") {
        exclude(group = "org.sonarsource.sonarqube")
        exclude(group = "org.sonarsource.analyzer-commons")
    }

    // ── ANTLR4 runtime (requis par proparse) ─────────────────────────────────
    implementation("org.antlr:antlr4-runtime:4.13.1")

    // ── ANTLR4 IntelliJ Adaptor ───────────────────────────────────────────────
    implementation("org.antlr:antlr4-intellij-adaptor:0.1")

    // ── Kotlin stdlib ─────────────────────────────────────────────────────────
    implementation(kotlin("stdlib"))

    // ── Sérialisation JSON (lecture openedge-project.json) ───────────────────
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    // ── Tests ─────────────────────────────────────────────────────────────────
    testImplementation(kotlin("test"))
    testImplementation("junit:junit:4.13.2")
}

// ─── Configuration IntelliJ Platform ─────────────────────────────────────────
intellijPlatform {
    pluginConfiguration {
        id.set(providers.gradleProperty("pluginGroup"))
        name.set(providers.gradleProperty("pluginName"))
        version.set(providers.gradleProperty("pluginVersion"))

        ideaVersion {
            sinceBuild = "232"   // 2023.2
            untilBuild = provider { null }  // pas de borne supérieure
        }
    }

    signing {
        // Configurer certificat pour publier sur JetBrains Marketplace
        // certificateChain.set(...)
        // privateKey.set(...)
        // password.set(...)
    }

    publishing {
        // token.set(providers.environmentVariable("PUBLISH_TOKEN"))
    }

    pluginVerification {
        ides {
            recommended()
        }
    }
}

// ─── Kotlin compile options ──────────────────────────────────────────────────
tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
    kotlinOptions {
        jvmTarget       = "17"
        freeCompilerArgs = listOf("-Xjvm-default=all", "-opt-in=kotlin.RequiresOptIn")
    }
}
