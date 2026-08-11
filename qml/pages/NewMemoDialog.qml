import QtQuick 2.0
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All

    // Lisätään mahdollisuus ottaa tekstiä sisään (muokkausta varten)
    property string initialText: ""
    property string memoContent: textArea.text

    Component.onCompleted: {
        if (initialText !== "") {
            textArea.text = initialText
        }
    }

    Column {
        width: parent.width
        spacing: Theme.paddingLarge

        DialogHeader {
            acceptText: "Tallenna"
        }

        TextArea {
            id: textArea
            width: parent.width
            placeholderText: "Kirjoita muistiinpano..."
            label: "Memo"
            focus: true
        }
    }
}
