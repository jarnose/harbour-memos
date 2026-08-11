import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page
    allowedOrientations: Orientation.All

    property string memoId
    property string memoContent
    property string memoTimestamp

    function formatText(rawText) {
        if (!rawText) return "";
        var html = rawText;

        html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<a href="$2">[Kuva: $1]</a>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

        html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>');
        html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>');
        html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>');

        html = html.replace(/\*\*([^\*]+)\*\*/g, '<b>$1</b>');
        html = html.replace(/(^|[^\w\*])\*([^\*]+)\*(?=[^\w\*]|$)/g, '$1<i>$2</i>');
        html = html.replace(/(^|\s)(#[^\s]+)/g, '$1<font color="' + Theme.highlightColor + '">$2</font>');

        html = html.replace(/\n/g, '<br>');
        html = html.replace(/<\/h([1-3])><br>/g, '</h$1>');

        html = html.replace(/(^|<br>)([-*]\s+)?\[ \]\s/g, '$1<font color="#888888">☐</font> ');
        html = html.replace(/(^|<br>)([-*]\s+)?\[x\]\s/gi, '$1<font color="' + Theme.highlightColor + '">☑</font> ');

        return html;
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        PullDownMenu {
            visible: memoId !== "queued"

            MenuItem {
                text: "Muokkaa"
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
                text: "Poista"
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
                title: "Muistiinpano"
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin
                text: memoTimestamp
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                visible: memoTimestamp !== ""
                wrapMode: Text.WordWrap // Varmistaa ettei katkea rumasti!
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin

                textFormat: Text.StyledText
                text: formatText(memoContent)

                linkColor: Theme.highlightColor
                onLinkActivated: Qt.openUrlExternally(link)

                color: Theme.primaryColor
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeMedium
            }
        }
    }
}
