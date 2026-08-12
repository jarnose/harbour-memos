import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0 // UUSI: Kuvanvalitsin

Dialog {
    id: dialog

    // Estetään tallentaminen, jos teksti on tyhjä TAI kuvan lataus on kesken
    canAccept: memoTextArea.text.length > 0 && !isUploading

    property string initialText: ""
    property alias memoContent: memoTextArea.text

    // The memo's server id ("memos/123"). Passed in when editing an
    // existing memo. When composing a brand new memo, this starts empty
    // and gets filled in the moment the first attachment is added (see
    // below) - because attachments can only be reliably linked to a memo
    // that already exists, we create the memo early instead of waiting
    // for Save.
    property string memoId: ""

    // True if we silently created the memo mid-composition (because an
    // attachment was added) rather than it already existing before this
    // dialog opened. Save then needs to *edit* that memo instead of
    // creating a new one, and Cancel needs to clean it up.
    property bool memoWasCreatedDuringComposition: false

    // Names of every attachment successfully uploaded during this dialog
    // session (whether composing a new memo or editing an existing one).
    // If the dialog is cancelled, these get deleted again - otherwise they
    // stay uploaded and linked to the memo (or, for a cancelled new memo,
    // become an orphaned "unused" attachment) despite never actually being
    // saved into any visible memo content.
    property var uploadedAttachments: []

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
                        if (!filePath) {
                            return
                        }

                        dialog.isUploading = true

                        function doUpload() {
                            // memoId is now known either way (existing memo,
                            // or the one we just silently created below), so
                            // the attachment links to it immediately.
                            appWindow.py.call('memos.api.upload_resource', [filePath, dialog.memoId], function(result) {
                                dialog.isUploading = false

                                if (result && result.ok && result.markdown) {
                                    if (memoTextArea.text.length > 0 && !memoTextArea.text.endsWith("\n")) {
                                        memoTextArea.text += "\n\n"
                                    }
                                    memoTextArea.text += result.markdown + "\n"

                                    if (result.name) {
                                        var updated = dialog.uploadedAttachments.slice()
                                        updated.push(result.name)
                                        dialog.uploadedAttachments = updated
                                    }
                                } else {
                                    var errMsg = (result && result.error) ? result.error : qsTr("Upload failed")
                                    console.log("Upload failed: " + errMsg)
                                    memoTextArea.placeholderText = errMsg
                                }
                            })
                        }

                        if (dialog.memoId === "") {
                            // Brand new memo and this is the first attachment:
                            // create the memo now (with whatever's been typed
                            // so far, or a placeholder space if nothing yet)
                            // so the upload has a real memo to link to.
                            //
                            // allow_queue=false: if this fails (e.g. offline),
                            // it must NOT get silently queued for later like
                            // a normal create would - otherwise Save would go
                            // on to create a second, separate memo from the
                            // final text, leaving this placeholder one behind
                            // as a stray near-empty duplicate once both sync.
                            // Attaching a photo just isn't possible offline.
                            var placeholder = memoTextArea.text.length > 0 ? memoTextArea.text : " "
                            appWindow.py.call('memos.api.create_memo', [placeholder, false], function(createResult) {
                                if (createResult && createResult.ok && createResult.name) {
                                    dialog.memoId = createResult.name
                                    dialog.memoWasCreatedDuringComposition = true
                                    doUpload()
                                } else {
                                    dialog.isUploading = false
                                    var err = (createResult && createResult.error) ? createResult.error : qsTr("Couldn't prepare memo for attachment")
                                    console.log("Provisional memo creation failed: " + err)
                                    memoTextArea.placeholderText = err
                                }
                            })
                        } else {
                            doUpload()
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
