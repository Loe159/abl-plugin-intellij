import org.jetbrains.intellij.platform.gradle.extensions.intellijPlatform

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

plugins {
    id("org.jetbrains.intellij.platform.settings") version "2.3.0"
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
        maven {
            name = "riverside-software"
            url  = uri("https://dl.cloudsmith.io/public/riverside-software/openedge-dev/maven/")
        }
        intellijPlatform {
            defaultRepositories()
        }
    }
}

rootProject.name = "abl-intellij-plugin"
