import QtQuick 2.0
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All

    property string currentUrl: ""
    property string currentToken: ""
    property bool currentAutoUpload: false
    property int currentLineCount: 2
    property int currentCoverMode: 0

    property string savedUrl: urlField.text
    property string savedToken: tokenField.text
    property bool savedAutoUpload: autoUploadSwitch.checked

    property int savedLineCount: {
        if (lineCountCombo.currentIndex === 0) return 1;
        if (lineCountCombo.currentIndex === 1) return 2;
        if (lineCountCombo.currentIndex === 2) return 3;
        return 0;
    }

    property int savedCoverMode: coverModeCombo.currentIndex

    Component.onCompleted: {
        urlField.text = currentUrl
        tokenField.text = currentToken
        autoUploadSwitch.checked = currentAutoUpload

        if (currentLineCount === 1) lineCountCombo.currentIndex = 0;
        else if (currentLineCount === 3) lineCountCombo.currentIndex = 2;
        else if (currentLineCount === 0) lineCountCombo.currentIndex = 3;
        else lineCountCombo.currentIndex = 1;

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
                acceptText: qsTr("Save")
            }

            TextField {
                id: urlField
                width: parent.width
                label: qsTr("Server URL")
                placeholderText: "https://memos.domain.fi"
                inputMethodHints: Qt.ImhUrlCharactersOnly
            }

            TextField {
                id: tokenField
                width: parent.width
                label: qsTr("API Access Token")
                placeholderText: qsTr("Enter token")
                echoMode: TextInput.Password
            }

            TextSwitch {
                id: autoUploadSwitch
                text: qsTr("Auto-upload")
                description: qsTr("Sync memos in background")
            }

            ComboBox {
                id: lineCountCombo
                width: parent.width
                label: qsTr("Lines to show in list")
                menu: ContextMenu {
                    MenuItem { text: qsTr("1 line") }
                    MenuItem { text: qsTr("2 lines") }
                    MenuItem { text: qsTr("3 lines") }
                    MenuItem { text: qsTr("All lines") }
                }
            }

            ComboBox {
                id: coverModeCombo
                width: parent.width
                label: qsTr("Show on cover")
                menu: ContextMenu {
                    MenuItem { text: qsTr("Latest created") }
                    MenuItem { text: qsTr("Recently edited") }
                }
            }
        }
    }
}
