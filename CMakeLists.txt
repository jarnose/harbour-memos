cmake_minimum_required(VERSION 3.19)
project(harbour-memos CXX)

find_package (Qt5 COMPONENTS Core Network Qml Gui Quick REQUIRED)

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

install(TARGETS harbour-memos
    RUNTIME DESTINATION bin
)
install(DIRECTORY qml
    DESTINATION share/harbour-memos
)
install(DIRECTORY python
    DESTINATION share/harbour-memos
)
install(DIRECTORY translations
    DESTINATION share/harbour-memos
    FILES_MATCHING PATTERN "*.qm"
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
FILE(GLOB TsFiles "translations/*.ts")
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
        ${TsFiles})

# Tell Qt Creator where the application executable(s) would be located on the
# device.
#
# It is not necessary to list other deployables than executables (runtime
# targets) here. The deployment process of Sailfish OS projects is opaque to
# Qt Creator and the information contained in QtCreatorDeployment.txt is only
# used to locate the executable associated with the active run configuration
# on the device in order to run it.
#
# Search the Qt Creator Manual to learn about the QtCreatorDeployment.txt file
# format.
file(WRITE "${CMAKE_BINARY_DIR}/QtCreatorDeployment.txt"
    "${CMAKE_INSTALL_PREFIX}
${CMAKE_BINARY_DIR}/harbour-memos:bin
")

