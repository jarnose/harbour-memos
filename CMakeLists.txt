cmake_minimum_required(VERSION 3.19)
project(harbour-memos CXX)

# LISÄTTY: LinguistTools, jotta käännöstyökalut löytyvät
find_package(Qt5 COMPONENTS Core Network Qml Gui Quick LinguistTools REQUIRED)

include(FindPkgConfig)
pkg_search_module(SAILFISH sailfishapp REQUIRED)

set(CMAKE_AUTOMOC ON)
set(CMAKE_INCLUDE_CURRENT_DIR ON)

add_executable(harbour-memos src/harbour-memos.cpp)
target_compile_definitions(harbour-memos PRIVATE
    $<$<OR:$<CONFIG:Debug>,$<CONFIG:RelWithDebInfo>>:QT_QML_DEBUG>
)
target_include_directories(harbour-memos PRIVATE
    $<BUILD_INTERFACE:
    ${SAILFISH_INCLUDE_DIRS}
>)
target_link_libraries(harbour-memos
    Qt5::Quick
    ${SAILFISH_LDFLAGS}
)

# --- UUSI KÄÄNNÖSLOGIIKKA ---
# Etsitään kaikki .ts -tiedostot
file(GLOB TS_FILES "translations/*.ts")
# Muutetaan .ts -> .qm (rakennuskansioon)
qt5_add_translation(QM_FILES ${TS_FILES})
# Varmistetaan, että ne käännetään aina kun projektia rakennetaan
add_custom_target(translations_target ALL DEPENDS ${QM_FILES})
# ----------------------------

install(TARGETS harbour-memos
    RUNTIME DESTINATION bin
)
install(DIRECTORY qml
    DESTINATION share/harbour-memos
)
install(DIRECTORY python
    DESTINATION share/harbour-memos
)

# LISÄTTY: Asennetaan käännetyt .qm -tiedostot puhelimeen
install(FILES ${QM_FILES}
    DESTINATION share/harbour-memos/translations
)

install(FILES harbour-memos.desktop
    DESTINATION share/applications
)
install(FILES icons/86x86/harbour-memos.png
    DESTINATION share/icons/hicolor/86x86/apps
)
install(FILES icons/108x108/harbour-memos.png
    DESTINATION share/icons/hicolor/108x108/apps
)
install(FILES icons/128x128/harbour-memos.png
    DESTINATION share/icons/hicolor/128x128/apps
)
install(FILES icons/172x172/harbour-memos.png
    DESTINATION share/icons/hicolor/172x172/apps
)

# Get the other files reachable from the project tree in Qt Creator
add_custom_target(distfiles
    SOURCES
        harbour-memos.desktop
        python/memos.py
        qml/harbour-memos.qml
        qml/cover/CoverPage.qml
        qml/pages/FirstPage.qml
        qml/pages/NewMemoDialog.qml
        qml/pages/SettingsDialog.qml
        qml/pages/MemoPage.qml
        qml/pages/SecondPage.qml
        rpm/harbour-memos.changes.in
        rpm/harbour-memos.changes.run.in
        rpm/harbour-memos.spec
        rpm/harbour-memos.yaml
        ${TS_FILES})

# Tell Qt Creator where the application executable(s) would be located on the device.
file(WRITE "${CMAKE_BINARY_DIR}/QtCreatorDeployment.txt"
    "${CMAKE_INSTALL_PREFIX}
${CMAKE_BINARY_DIR}/harbour-memos:bin
")
