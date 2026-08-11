import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page
    allowedOrientations: Orientation.All

    property string memoId
    property string memoContent
    property string memoTimestamp

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        PullDownMenu {
            visible: memoId !== "queued"

            MenuItem {
                text: qsTr("Edit")
                onClicked: {
                    var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"), {initialText: memoContent})
                    dialog.accepted.connect(function() {
                        appWindow.py.call('memos.api.edit_memo', [memoId, dialog.memoContent], function() {
                            memoContent = dialog.memoContent
                        })
                    })
                }
            }
            MenuItem {
                text: qsTr("Delete")
                onClicked: {
                    appWindow.py.call('memos.api.delete_memo', [memoId], function() {
                        pageStack.pop()
                    })
                }
            }
        }

        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingLarge

            PageHeader {
                title: qsTr("Memo")
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin
                text: memoTimestamp
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                visible: memoTimestamp !== ""
                wrapMode: Text.WordWrap
            }

            Label {
                id: memoLabel
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin

                textFormat: Text.StyledText
                linkColor: Theme.highlightColor
                onLinkActivated: Qt.openUrlExternally(link)

                color: Theme.primaryColor
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeMedium

                // Python Markdown -päivitys
                property string rawContent: memoContent
                onRawContentChanged: fetchHtml()
                Component.onCompleted: fetchHtml()

                function fetchHtml() {
                    if (py) {
                        // Lasketaan tarkka leveys puhelimen ruudun koosta
                        // miinus Sailfishin vakiomarginaalit molemmista reunoista
                        var w = Screen.width - (Theme.horizontalPageMargin * 2)

                        // Jos FirstPage.qml, py.call vaatii tietysti sen "&& isMatch" tuohon if-lauseeseen,
                        // mutta MemoPage.qml:ssä mennään tällä:
                        py.call('memos.api.render_markdown', [rawContent, w], function(html) {
                            text = html
                        })
                    }
                }
            }
        }
    }
}
