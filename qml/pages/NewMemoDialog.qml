import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0 // UUSI: Kuvanvalitsin

Dialog {
    id: dialog

    // Estetään tallentaminen, jos teksti on tyhjä TAI kuvan lataus on kesken
    canAccept: memoTextArea.text.length > 0 && !isUploading

    property string initialText: ""
    property alias memoContent: memoTextArea.text

    // Tieto siitä, ladataanko kuvaa parhaillaan
    property bool isUploading: false

    Component.onCompleted: {
        if (initialText !== "") {
            memoTextArea.text = initialText
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        PullDownMenu {
            // Poistetaan valikko käytöstä latauksen ajaksi
            busy: dialog.isUploading

            MenuItem {
                text: qsTr("Add image")
                enabled: !dialog.isUploading
                onClicked: {
                    // Avataan Sailfishin natiivi kuvagalleria/kamera
                    var picker = pageStack.push("Sailfish.Pickers.ImagePickerPage")

                    picker.selectedContentPropertiesChanged.connect(function() {
                        var filePath = picker.selectedContentProperties.filePath
                        if (filePath) {
                            dialog.isUploading = true

                            // Kutsutaan Pythonia lataamaan kuva
                            appWindow.py.call('memos.api.upload_resource', [filePath], function(result) {
                                dialog.isUploading = false

                                // Jos tulos alkaa '!' tai '[', se on onnistunut markdown-linkki
                                if (result.indexOf("![") === 0 || result.indexOf("[") === 0) {
                                    // Lisätään rivinvaihdot, jos tekstiä on jo
                                    if (memoTextArea.text.length > 0 && !memoTextArea.text.endsWith("\n")) {
                                        memoTextArea.text += "\n\n"
                                    }
                                    memoTextArea.text += result + "\n"
                                } else {
                                    // Näytetään virheteksti hetken aikaa placeholderissa (tai logissa)
                                    console.log("Upload failed: " + result)
                                    memoTextArea.placeholderText = result
                                }
                            })
                        }
                    })
                }
            }
        }

        Column {
            id: column
            width: parent.width

            DialogHeader {
                // Muutetaan tallennusnapin tekstiä latauksen ajaksi
                acceptText: dialog.isUploading ? qsTr("Uploading...") : qsTr("Save")
            }

            TextArea {
                id: memoTextArea
                width: parent.width
                height: Math.max(dialog.height - y - Theme.paddingLarge, implicitHeight)

                placeholderText: dialog.isUploading ? qsTr("Uploading image, please wait...") : qsTr("Write your memo here...")
                label: qsTr("Memo content")
                focus: true
                background: null
            }
        }
    }
}
