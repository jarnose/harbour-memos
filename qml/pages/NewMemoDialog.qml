import QtQuick 2.0
import Sailfish.Silica 1.0

Dialog {
    id: dialog
    allowedOrientations: Orientation.All

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
            acceptText: qsTr("Save")
        }

        TextArea {
            id: textArea
            width: parent.width
            placeholderText: qsTr("Write a memo...")
            label: qsTr("Memo")
            focus: true
        }
    }
}
