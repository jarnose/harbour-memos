import QtQuick 2.0
import Sailfish.Silica 1.0

CoverBackground {

    Label {
        id: headerLabel
        anchors {
            top: parent.top
            topMargin: Theme.paddingLarge
            horizontalCenter: parent.horizontalCenter
        }
        text: "Memos"
        color: Theme.secondaryColor
        font.pixelSize: Theme.fontSizeSmall
    }

    Label {
        id: memoText
        anchors {
            top: headerLabel.bottom
            topMargin: Theme.paddingMedium
            left: parent.left
            right: parent.right
            leftMargin: Theme.paddingMedium
            rightMargin: Theme.paddingMedium
        }

        textFormat: Text.StyledText
        color: Theme.primaryColor
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeMedium

        maximumLineCount: 7
        truncationMode: TruncationMode.Fade

        // Python Markdown -päivitys
        property string rawContent: appWindow.latestMemoText
        onRawContentChanged: fetchHtml()
        Component.onCompleted: fetchHtml()

        function fetchHtml() {
            if (appWindow.py) {
                appWindow.py.call('memos.api.render_markdown', [rawContent], function(html) {
                    memoText.text = html
                })
            }
        }
    }

    CoverActionList {
        id: coverAction

        CoverAction {
            iconSource: "image://theme/icon-cover-new"
            onTriggered: {
                appWindow.activate()
                appWindow.requestNewMemo()
            }
        }
    }
}
