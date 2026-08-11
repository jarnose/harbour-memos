import QtQuick 2.0
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All

    property string currentUrl: ""
    property string currentToken: ""
    property bool currentAutoUpload: false
    property int currentLineCount: 2
    property int currentCoverMode: 0 // UUSI ASETUS

    property string savedUrl: urlField.text
    property string savedToken: tokenField.text
    property bool savedAutoUpload: autoUploadSwitch.checked

    property int savedLineCount: {
        if (lineCountCombo.currentIndex === 0) return 1;
        if (lineCountCombo.currentIndex === 1) return 2;
        if (lineCountCombo.currentIndex === 2) return 3;
        return 0;
    }

    // Luetaan kansilehden valinta suoraan
    property int savedCoverMode: coverModeCombo.currentIndex

    Component.onCompleted: {
        urlField.text = currentUrl
        tokenField.text = currentToken
        autoUploadSwitch.checked = currentAutoUpload

        if (currentLineCount === 1) lineCountCombo.currentIndex = 0;
        else if (currentLineCount === 3) lineCountCombo.currentIndex = 2;
        else if (currentLineCount === 0) lineCountCombo.currentIndex = 3;
        else lineCountCombo.currentIndex = 1;

        // Asetetaan kansilehden valikko aiemmin tallennetun mukaiseksi
        coverModeCombo.currentIndex = currentCoverMode;
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingLarge

            DialogHeader {
                acceptText: "Tallenna"
            }

            TextField {
                id: urlField
                width: parent.width
                label: "Palvelimen osoite"
                placeholderText: "https://memos.domain.fi"
                inputMethodHints: Qt.ImhUrlCharactersOnly
            }

            TextField {
                id: tokenField
                width: parent.width
                label: "API Access Token"
                placeholderText: "Syötä token"
                echoMode: TextInput.Password
            }

            TextSwitch {
                id: autoUploadSwitch
                text: "Automaattinen lähetys"
                description: "Synkronoi merkinnät taustalla"
            }

            ComboBox {
                id: lineCountCombo
                width: parent.width
                label: "Listassa näytettävät rivit"
                menu: ContextMenu {
                    MenuItem { text: "1 rivi" }
                    MenuItem { text: "2 riviä" }
                    MenuItem { text: "3 riviä" }
                    MenuItem { text: "Kaikki rivit" }
                }
            }

            // UUSI VALIKKO KANSILEHDELLE
            ComboBox {
                id: coverModeCombo
                width: parent.width
                label: "Kansilehdellä näytetään"
                menu: ContextMenu {
                    MenuItem { text: "Uusin luotu" }
                    MenuItem { text: "Viimeksi muokattu" }
                }
            }
        }
    }
}
